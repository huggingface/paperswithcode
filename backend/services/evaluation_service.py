"""
Evaluation service for handling evaluation-related business logic.

This service provides methods for retrieving and managing benchmark evaluation data,
including pagination, filtering by paper, task, and dataset.
"""

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse, urlunparse
from sqlalchemy.orm import Session, load_only
from sqlalchemy import desc, asc, or_, func

from backend.models.database import (
    Evaluation as DBEvaluation,
    Paper as DBPaper,
    Task as DBTask,
    Dataset as DBDataset,
    HfArtifact as DBHfArtifact,
    PaperHfArtifact as DBPaperHfArtifact,
    ProjectPage as DBProjectPage,
    PaperProjectPage as DBPaperProjectPage,
    Repository as DBRepository,
    PaperRepository as DBPaperRepository,
    TaskDataset,
    TaskDatasetMetric,
    Metric as DBMetric,
)
from backend.models.evaluations import (
    Evaluation,
    Evaluations,
)
from backend.utils.exceptions import DatabaseError
from backend.utils.task_hierarchy import collect_descendant_task_ids
from backend.utils.urls import external_source_url_to_paper_url, parse_arxiv_url
from backend.services.evaluation_entry_identity import (
    evaluation_display_entry_key,
    leaderboard_model_key,
)
from backend.services.leaderboard_metric_service import LeaderboardMetricService
from backend.services.metric_value_service import parse_metric_value
from backend.services.catalog_errors import (
    CatalogConflictError,
    CatalogNotFoundError,
    CatalogPersistenceError,
    CatalogValidationError,
)

RankScopes = set[tuple[int, int, str]]

_PAPER_REF = re.compile(r"^paper:(\d+)$", re.IGNORECASE)
# Hugging Face paper pages and their markdown mirrors are surfaces of the arXiv
# paper, e.g. https://huggingface.co/papers/2111.12993.md.
_HF_PAPER_URL = re.compile(
    r"^https?://(?:www\.)?huggingface\.co/papers/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.md)?/?(?:[?#].*)?$",
    re.IGNORECASE,
)
_CVF_OPENACCESS_PATH = re.compile(
    r"^/content/([^/]+)/(?:html|papers)/([^/]+?)(?:\.(?:html|pdf))?$",
    re.IGNORECASE,
)

# First path segments on huggingface.co that are site sections, not model owners.
_HUGGINGFACE_NON_REPO_ROOTS = frozenset(
    {
        "api",
        "blog",
        "buckets",
        "changelog",
        "chat",
        "collections",
        "docs",
        "enterprise",
        "join",
        "learn",
        "login",
        "models",
        "new",
        "organizations",
        "papers",
        "posts",
        "pricing",
        "settings",
        "tasks",
    }
)
# Path segments after `{owner}/{repo}` that address files in the repository.
_HUGGINGFACE_REPO_SUBPATHS = frozenset({"blob", "raw", "resolve", "tree"})


def _looks_like_paper_slug(segment: str) -> bool:
    base = segment.rsplit(".", 1)[0] if "." in segment else segment
    return "_" in base or len(base) >= 20


def _normalize_url_for_match(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    raw = url.strip()
    if not raw:
        return None

    paper_ref = _PAPER_REF.match(raw)
    if paper_ref:
        return f"paper:{paper_ref.group(1)}"

    parsed_arxiv = parse_arxiv_url(raw)
    if parsed_arxiv:
        return f"arxiv:{parsed_arxiv[0].lower()}"

    hf_paper = _HF_PAPER_URL.match(raw)
    if hf_paper:
        return f"arxiv:{hf_paper.group(1)}"

    parsed = urlparse(raw)
    if not parsed.scheme and raw.startswith("/paper/"):
        return raw.rstrip("/").lower()
    if not parsed.scheme or not parsed.netloc:
        return raw.rstrip("/").lower()

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/")

    # OpenReview exposes the same submission through /forum?id=... and
    # /pdf?id=.... Preserve the submission id while treating those surfaces as
    # equivalent; dropping the query would collapse every OpenReview paper to
    # the same host/path key.
    if netloc == "openreview.net" and path.lower() in {"/forum", "/pdf"}:
        submission_id = parse_qs(parsed.query).get("id", [None])[0]
        if submission_id:
            return f"openreview:{submission_id.lower()}"

    return urlunparse((scheme, netloc, path, "", "", "")).lower()


def _paper_pdf_url(paper_arxiv_id: Optional[str]) -> Optional[str]:
    if not paper_arxiv_id:
        return None
    return f"https://arxiv.org/pdf/{paper_arxiv_id}.pdf"


def _paper_route_keys(paper_id: int, paper_arxiv_id: Optional[str]) -> set[str]:
    keys = {
        f"paper:{paper_id}",
        f"/paper/{paper_id}",
        _normalize_url_for_match(f"https://paperswithcode.co/paper/{paper_id}"),
    }
    if paper_arxiv_id:
        base = paper_arxiv_id.lower().split("v")[0]
        keys.update(
            {
                f"arxiv:{base}",
                f"/paper/{base}",
                _normalize_url_for_match(f"https://paperswithcode.co/paper/{base}"),
                _normalize_url_for_match(f"https://arxiv.org/abs/{base}"),
                _normalize_url_for_match(f"https://arxiv.org/pdf/{base}.pdf"),
            }
        )
    return {key for key in keys if key}


def _huggingface_repo_key(path_parts: list[str]) -> Optional[str]:
    """`hfrepo:{kind}/{repo id}` for a Hugging Face repository URL path.

    Handles `{owner}/{repo}` ids and legacy namespace-less ids such as `gpt2`.
    """
    parts = [part.lower() for part in path_parts]
    kind = "model"
    if parts and parts[0] in {"datasets", "spaces"}:
        kind = parts[0].removesuffix("s")
        parts = parts[1:]
    elif parts and parts[0] in _HUGGINGFACE_NON_REPO_ROOTS:
        return None
    if not parts:
        return None
    # The repo id ends where a file action (blob/resolve/raw/tree) starts.
    id_length = 1 if len(parts) > 1 and parts[1] in _HUGGINGFACE_REPO_SUBPATHS else 2
    if len(parts) > id_length and parts[id_length] not in _HUGGINGFACE_REPO_SUBPATHS:
        return None
    return f"hfrepo:{kind}/{'/'.join(parts[:id_length])}"


def _source_match_keys(url: Optional[str]) -> set[str]:
    """Normalized URL keys plus equivalence keys for alternate paper surfaces."""
    keys: set[str] = set()
    normalized = _normalize_url_for_match(url)
    if normalized:
        keys.add(normalized)

    if not url:
        return keys

    raw = url.strip()
    if not raw or _PAPER_REF.match(raw) or parse_arxiv_url(raw):
        return keys

    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return keys

    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/")
    path_parts = [part for part in path.split("/") if part]

    # A report, result file, or README inside a linked GitHub repository is
    # first-party evidence for that paper. Give both repository roots and files
    # below them the same key while keeping different repositories distinct.
    if netloc in {"github.com", "raw.githubusercontent.com"} and len(path_parts) >= 2:
        owner = path_parts[0].lower()
        repository = path_parts[1].removesuffix(".git").lower()
        keys.add(f"githubrepo:{owner}/{repository}")

    # Files inside a linked Hugging Face model, dataset, or Space repository
    # (README, tech report under /resolve/, results under /blob/) are likewise
    # first-party evidence. Repository kinds stay distinct.
    if netloc in {"huggingface.co", "hf.co"}:
        hf_repo_key = _huggingface_repo_key(path_parts)
        if hf_repo_key:
            keys.add(hf_repo_key)

    cvf_match = _CVF_OPENACCESS_PATH.match(path)
    if cvf_match and netloc == "openaccess.thecvf.com":
        conf, slug = cvf_match.group(1).lower(), cvf_match.group(2).lower()
        keys.add(f"cvf:{conf}:{slug}")

    segment = path.rsplit("/", 1)[-1]
    if segment and _looks_like_paper_slug(segment):
        slug_base = segment.rsplit(".", 1)[0].lower()
        keys.add(f"hostslug:{netloc}:{slug_base}")

    return {key for key in keys if key}


def _extend_keys_from_url(keys: set[str], url: Optional[str]) -> None:
    keys.update(_source_match_keys(url))


def _paper_related_keys(
    paper_id: int,
    paper_arxiv_id: Optional[str],
    db: Optional[Session],
    related_keys: Optional[set[str]],
) -> set[str]:
    """Source keys tied to a paper, preferring a batch-prefetched key set."""
    if related_keys is not None:
        return related_keys
    if db is not None:
        return _related_source_keys(db, paper_id, paper_arxiv_id)
    return _paper_route_keys(paper_id, paper_arxiv_id)


def evaluation_is_external(
    source_url: Optional[str],
    paper_arxiv_id: Optional[str],
    paper_id: int,
    db: Optional[Session] = None,
    related_keys: Optional[set[str]] = None,
) -> bool:
    """True when a score source is independent of the evaluated paper/model."""
    if not source_url:
        return False

    source_keys = _source_match_keys(source_url)
    if not source_keys:
        return False

    related = _paper_related_keys(paper_id, paper_arxiv_id, db, related_keys)
    return not source_keys.intersection(related)


def evaluation_external_flag(
    stored_external: bool,
    source_url: Optional[str],
    paper_arxiv_id: Optional[str],
    paper_id: int,
    db: Optional[Session] = None,
    related_keys: Optional[set[str]] = None,
) -> bool:
    """Resolve whether an evaluation is externally sourced for API display."""
    if source_url:
        return evaluation_is_external(
            source_url, paper_arxiv_id, paper_id, db, related_keys
        )
    return bool(stored_external)


def evaluation_public_source_url(
    source_url: Optional[str],
    db: Optional[Session] = None,
) -> Optional[str]:
    """Public link for an evaluation source."""
    if not source_url:
        return None
    paper_ref = _PAPER_REF.match(source_url.strip())
    if paper_ref:
        paper_id = int(paper_ref.group(1))
        if db is not None:
            # `get` reuses papers already loaded by batch serialization.
            paper = db.get(DBPaper, paper_id)
            if paper and paper.arxiv_id:
                return f"/paper/{paper.arxiv_id}"
        return f"/paper/{paper_id}"
    return external_source_url_to_paper_url(source_url)


def evaluation_result_url(
    source_url: Optional[str],
    paper_id: int,
    paper_arxiv_id: Optional[str],
    paper_source_url: Optional[str],
    db: Optional[Session] = None,
    related_keys: Optional[set[str]] = None,
) -> Optional[str]:
    """Resolve the result/source link shown on evaluation rows."""
    if source_url:
        source_keys = _source_match_keys(source_url)
        related = _paper_related_keys(paper_id, paper_arxiv_id, db, related_keys)
        if source_keys.intersection(related):
            if paper_arxiv_id:
                return _paper_pdf_url(paper_arxiv_id) or evaluation_public_source_url(
                    source_url, db
                )
            return paper_source_url or f"/paper/{paper_id}"
        return evaluation_public_source_url(source_url, db)
    if paper_arxiv_id:
        return f"https://arxiv.org/abs/{paper_arxiv_id}"
    return paper_source_url


def _related_source_keys(
    db: Session,
    paper_id: int,
    paper_arxiv_id: Optional[str],
) -> set[str]:
    """Known official/linked source keys for a paper/model."""
    keys = _paper_route_keys(paper_id, paper_arxiv_id)
    paper = db.get(DBPaper, paper_id)
    keys.update(_related_source_keys_by_paper(db, {paper_id: paper})[paper_id])
    return keys


def _related_source_keys_by_paper(
    db: Session,
    papers: dict[int, Optional[DBPaper]],
) -> dict[int, set[str]]:
    """Known official/linked source keys for many papers in bounded queries."""
    keys = {
        paper_id: _paper_route_keys(paper_id, paper.arxiv_id if paper else None)
        for paper_id, paper in papers.items()
    }
    for paper_id, paper in papers.items():
        if not paper:
            continue
        for url in [
            paper.source_url,
            paper.conference_url_abs,
            paper.conference_url_pdf,
            *(paper.hf_models or []),
            *(paper.hf_datasets or []),
            *(paper.hf_spaces or []),
        ]:
            _extend_keys_from_url(keys[paper_id], url)

    if not keys:
        return keys
    paper_ids = list(keys)
    linked_urls = [
        db.query(DBPaperRepository.paper_id, DBRepository.url)
        .join(DBRepository, DBRepository.id == DBPaperRepository.repository_id)
        .filter(DBPaperRepository.paper_id.in_(paper_ids)),
        db.query(DBPaperProjectPage.paper_id, DBProjectPage.url)
        .join(
            DBProjectPage,
            DBProjectPage.id == DBPaperProjectPage.project_page_id,
        )
        .filter(DBPaperProjectPage.paper_id.in_(paper_ids)),
        db.query(DBPaperHfArtifact.paper_id, DBHfArtifact.url)
        .join(DBHfArtifact, DBHfArtifact.id == DBPaperHfArtifact.hf_artifact_id)
        .filter(DBPaperHfArtifact.paper_id.in_(paper_ids)),
    ]
    for query in linked_urls:
        for paper_id, url in query:
            _extend_keys_from_url(keys[paper_id], url)

    return keys


class EvaluationService:
    """Service class for evaluation-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def _serialize_evaluation(self, db_evaluation: DBEvaluation) -> Evaluation:
        return self._serialize_evaluations([db_evaluation])[0]

    def _serialize_evaluations(
        self, db_evaluations: list[DBEvaluation]
    ) -> list[Evaluation]:
        """Serialize rows with a fixed number of queries, not several per row."""
        if not db_evaluations:
            return []

        paper_ids = {row.paper_id for row in db_evaluations}
        source_paper_ids = set()
        for row in db_evaluations:
            paper_ref = _PAPER_REF.match(
                (row.source_url or row.external_source_url or "").strip()
            )
            if paper_ref:
                source_paper_ids.add(int(paper_ref.group(1)))

        # Holding these objects keeps them in the session identity map, so
        # `db.get` lookups in the URL helpers do not query again.
        papers = {
            paper.id: paper
            for paper in self.db.query(DBPaper)
            .options(
                load_only(
                    DBPaper.title,
                    DBPaper.arxiv_id,
                    DBPaper.date_published,
                    DBPaper.source_url,
                    DBPaper.conference_url_abs,
                    DBPaper.conference_url_pdf,
                    DBPaper.hf_models,
                    DBPaper.hf_datasets,
                    DBPaper.hf_spaces,
                )
            )
            .filter(DBPaper.id.in_(paper_ids | source_paper_ids))
        }
        tasks = {
            task.id: task
            for task in self.db.query(DBTask)
            .options(load_only(DBTask.name, DBTask.slug))
            .filter(DBTask.id.in_({row.task_id for row in db_evaluations}))
        }
        datasets = {
            dataset.id: dataset
            for dataset in self.db.query(DBDataset)
            .options(load_only(DBDataset.name, DBDataset.slug))
            .filter(DBDataset.id.in_({row.dataset_id for row in db_evaluations}))
        }
        code_urls: dict[int, str] = {}
        for paper_id, url in (
            self.db.query(DBPaperRepository.paper_id, DBRepository.url)
            .join(DBRepository, DBRepository.id == DBPaperRepository.repository_id)
            .filter(DBPaperRepository.paper_id.in_(paper_ids))
            # Same choice as dataset leaderboards: official, then most starred.
            .order_by(
                desc(DBPaperRepository.is_official),
                desc(DBRepository.num_stars),
                asc(DBRepository.url),
            )
        ):
            code_urls.setdefault(paper_id, url)
        related_keys = _related_source_keys_by_paper(
            self.db, {paper_id: papers.get(paper_id) for paper_id in paper_ids}
        )

        return [
            self._evaluation_model(
                row,
                papers.get(row.paper_id),
                tasks.get(row.task_id),
                datasets.get(row.dataset_id),
                code_urls.get(row.paper_id),
                related_keys[row.paper_id],
            )
            for row in db_evaluations
        ]

    def _evaluation_model(
        self,
        db_evaluation: DBEvaluation,
        paper: Optional[DBPaper],
        task: Optional[DBTask],
        dataset: Optional[DBDataset],
        code_url: Optional[str],
        related_keys: set[str],
    ) -> Evaluation:
        paper_arxiv_id = paper.arxiv_id if paper else None
        stored_source_url = (
            db_evaluation.source_url or db_evaluation.external_source_url
        )
        public_source_url = evaluation_public_source_url(stored_source_url, self.db)
        result_url = evaluation_result_url(
            stored_source_url,
            db_evaluation.paper_id,
            paper_arxiv_id,
            paper.source_url if paper else None,
            self.db,
            related_keys,
        )
        external = evaluation_external_flag(
            db_evaluation.external,
            stored_source_url,
            paper_arxiv_id,
            db_evaluation.paper_id,
            self.db,
            related_keys,
        )

        return Evaluation(
            id=str(db_evaluation.id),
            paper_id=str(db_evaluation.paper_id),
            task_id=str(db_evaluation.task_id),
            dataset_id=str(db_evaluation.dataset_id),
            model_name=db_evaluation.model_name,
            harness=db_evaluation.harness,
            methodology=db_evaluation.methodology,
            metrics=db_evaluation.metrics,
            uses_additional_data=db_evaluation.uses_additional_data,
            is_open=db_evaluation.is_open,
            best_rank=db_evaluation.best_rank,
            best_metric=db_evaluation.best_metric,
            evaluated_on=db_evaluation.evaluated_on,
            external_source_url=public_source_url,
            source_url=public_source_url,
            external=external,
            is_external=external,
            num_parameters=db_evaluation.num_parameters,
            hf_model_url=db_evaluation.hf_model_url,
            created_at=db_evaluation.created_at,
            updated_at=db_evaluation.updated_at,
            paper_title=paper.title if paper else None,
            paper_arxiv_id=paper_arxiv_id,
            code_url=code_url,
            paper_published_date=(
                str(paper.date_published) if paper and paper.date_published else None
            ),
            result_url=result_url,
            task_name=task.name if task else None,
            task_slug=task.slug if task else None,
            dataset_name=dataset.name if dataset else None,
            dataset_slug=dataset.slug if dataset else None,
        )

    def _derive_external(self, paper_id: int, source_url: Optional[str]) -> bool:
        paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
        return evaluation_is_external(
            source_url,
            paper.arxiv_id if paper else None,
            paper_id,
            self.db,
        )

    def _validate_dataset_task_consistency(
        self, task_id: int, dataset_id: int
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that the task-dataset pair has metrics defined (i.e., is a valid leaderboard).

        A (task, dataset) pair is valid if it has at least one metric defined in
        TASK_DATASET_METRICS. This ensures evaluations are only added to defined leaderboards.

        Args:
            task_id: Task ID to validate
            dataset_id: Dataset ID

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check if this task-dataset pair has any metrics defined
        has_metrics = (
            self.db.query(TaskDatasetMetric)
            .filter(
                TaskDatasetMetric.task_id == task_id,
                TaskDatasetMetric.dataset_id == dataset_id,
            )
            .first()
        )

        if not has_metrics:
            # Get task and dataset names for error message
            task = self.db.query(DBTask).filter(DBTask.id == task_id).first()
            dataset = (
                self.db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
            )

            return False, (
                f"No leaderboard defined for task '{task.name if task else task_id}' "
                f"and dataset '{dataset.name if dataset else dataset_id}'. "
                f"Please define metrics for this task-dataset pair before adding evaluations."
            )

        return True, None

    def find_leaderboard_duplicate(
        self,
        task_id: int,
        dataset_id: int,
        best_metric: Optional[str],
        model_name: Optional[str],
        harness: Optional[str],
        exclude_id: Optional[int] = None,
    ) -> Optional[DBEvaluation]:
        """Return the row already showing this model on the leaderboard, on any paper."""
        key = leaderboard_model_key(model_name, harness)
        if not key[0] or best_metric is None:
            return None
        rows = (
            self.db.query(DBEvaluation)
            .options(
                load_only(
                    DBEvaluation.id,
                    DBEvaluation.paper_id,
                    DBEvaluation.model_name,
                    DBEvaluation.harness,
                )
            )
            .filter(
                DBEvaluation.task_id == task_id,
                DBEvaluation.dataset_id == dataset_id,
                DBEvaluation.best_metric == best_metric,
            )
        )
        if exclude_id is not None:
            rows = rows.filter(DBEvaluation.id != exclude_id)
        for row in rows.order_by(DBEvaluation.id):
            if leaderboard_model_key(row.model_name, row.harness) == key:
                return row
        return None

    def move_paper_evaluations(
        self, source_paper_id: int, target_paper_id: int
    ) -> None:
        """Hand a paper's evaluations to the paper that supersedes it.

        Leaderboards list rows from every paper, so an entry the target already
        shows is dropped rather than moved, and those boards are re-ranked.
        """

        def entry(row: DBEvaluation) -> tuple:
            return (
                row.task_id,
                row.dataset_id,
                row.best_metric,
            ) + leaderboard_model_key(row.model_name, row.harness)

        target_entries = {
            entry(row)
            for row in self.db.query(DBEvaluation).filter(
                DBEvaluation.paper_id == target_paper_id
            )
        }
        dropped_scopes: RankScopes = set()
        for row in (
            self.db.query(DBEvaluation)
            .filter(DBEvaluation.paper_id == source_paper_id)
            .order_by(DBEvaluation.id)
            .all()
        ):
            if entry(row) in target_entries:
                dropped_scopes |= self._rank_scopes(row)
                self.db.delete(row)
            else:
                row.paper_id = target_paper_id
                target_entries.add(entry(row))
        if dropped_scopes:
            self.refresh_rank_scopes(dropped_scopes)

    def _reject_leaderboard_duplicate(self, **identity) -> None:
        duplicate = self.find_leaderboard_duplicate(**identity)
        if duplicate is not None:
            raise CatalogConflictError(
                f"'{identity['model_name']}' is already on this leaderboard as "
                f"evaluation {duplicate.id} (paper {duplicate.paper_id}). Update or "
                "move that row instead, or set a distinct harness."
            )

    def _validate_harness_support(
        self, task_id: int, dataset_id: int, harness: Optional[str]
    ) -> tuple[bool, Optional[str]]:
        if not harness:
            return True, None

        task_dataset = (
            self.db.query(TaskDataset)
            .filter(
                TaskDataset.task_id == task_id,
                TaskDataset.dataset_id == dataset_id,
            )
            .first()
        )
        if task_dataset and task_dataset.supports_harness:
            return True, None

        task = self.db.query(DBTask).filter(DBTask.id == task_id).first()
        dataset = self.db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
        return False, (
            f"Leaderboard for task '{task.name if task else task_id}' and dataset "
            f"'{dataset.name if dataset else dataset_id}' does not support harness values. "
            "Put runtime/framework details in methodology instead, or enable "
            "supports_harness for this leaderboard."
        )

    def get_evaluations(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        paper_id: Optional[int] = None,
        task_id: Optional[int] = None,
        include_descendants: bool = False,
        dataset_id: Optional[int] = None,
        best_metric: Optional[str] = None,
        is_open: Optional[bool] = None,
        external: Optional[bool] = None,
        max_parameters_exclusive: Optional[int] = None,
        order_by: str = "created_at",
        order_dir: str = "desc",
    ) -> Evaluations:
        """
        Get a paginated list of benchmark evaluations with optional filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of evaluations per page
            search: Search term for model name or methodology
            paper_id: Filter by paper ID
            task_id: Filter by task ID
            dataset_id: Filter by dataset ID
            best_metric: Filter by best metric name (e.g., 'AbsRel', 'delta1')
            max_parameters_exclusive: Strict upper bound for a displayed
                leaderboard entry's consistent parameter count.
            order_by: Field to order by (created_at, best_rank, evaluated_on,
                benchmark_popularity). benchmark_popularity sorts rows by the
                total number of evaluations on each row's dataset across the
                whole database, so the most popular benchmarks surface first.
            order_dir: Order direction (asc, desc)

        Returns:
            Evaluations object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Base query
            query = self.db.query(DBEvaluation)

            # Apply filters
            if search:
                # Use ilike for case-insensitive search in model name, harness and methodology
                query = query.filter(
                    or_(
                        DBEvaluation.model_name.ilike(f"%{search}%")
                        if DBEvaluation.model_name
                        else False,
                        DBEvaluation.harness.ilike(f"%{search}%")
                        if DBEvaluation.harness
                        else False,
                        DBEvaluation.methodology.ilike(f"%{search}%")
                        if DBEvaluation.methodology
                        else False,
                    )
                )

            if paper_id is not None:
                query = query.filter(DBEvaluation.paper_id == paper_id)

            if task_id is not None:
                if include_descendants:
                    descendant_ids = collect_descendant_task_ids(self.db, task_id)
                    query = query.filter(DBEvaluation.task_id.in_(descendant_ids))
                else:
                    query = query.filter(DBEvaluation.task_id == task_id)

            if dataset_id is not None:
                query = query.filter(DBEvaluation.dataset_id == dataset_id)

            if best_metric is not None:
                query = query.filter(DBEvaluation.best_metric == best_metric)

            if is_open is not None:
                query = query.filter(DBEvaluation.is_open == is_open)

            if external is not None:
                query = query.filter(DBEvaluation.external == external)

            # Apply ordering
            if order_by == "benchmark_popularity":
                # Popularity = total number of evaluation rows on each row's
                # dataset across the whole table. We aggregate in a subquery
                # so the per-evaluation result set is preserved (no GROUP BY
                # on the outer query) and so the count reflects the full
                # database, not just the filtered slice for this caller.
                popularity_sq = (
                    self.db.query(
                        DBEvaluation.dataset_id.label("dataset_id"),
                        func.count(DBEvaluation.id).label("popularity"),
                    )
                    .group_by(DBEvaluation.dataset_id)
                    .subquery()
                )
                query = query.outerjoin(
                    popularity_sq,
                    DBEvaluation.dataset_id == popularity_sq.c.dataset_id,
                )
                popularity_field = func.coalesce(popularity_sq.c.popularity, 0)
                primary = (
                    desc(popularity_field)
                    if order_dir == "desc"
                    else asc(popularity_field)
                )
                # Tie-breakers: keep all rows for the same benchmark together,
                # then sort by best_rank (ascending, nulls last) so the strongest
                # entries on each benchmark surface first — mirroring the
                # benchmark leaderboard view. Fall back to evaluation id for a
                # fully stable order when ranks tie or are absent.
                query = query.order_by(
                    primary,
                    asc(DBEvaluation.dataset_id),
                    asc(DBEvaluation.best_rank).nulls_last(),
                    asc(DBEvaluation.id),
                )
            else:
                if order_by == "created_at":
                    order_field = DBEvaluation.created_at
                elif order_by == "best_rank":
                    order_field = DBEvaluation.best_rank
                elif order_by == "evaluated_on":
                    order_field = DBEvaluation.evaluated_on
                else:
                    order_field = DBEvaluation.created_at

                if order_by == "best_rank":
                    primary = (
                        desc(order_field).nulls_last()
                        if order_dir == "desc"
                        else asc(order_field).nulls_last()
                    )
                    query = query.order_by(
                        primary,
                        asc(DBEvaluation.best_metric).nulls_last(),
                        asc(DBEvaluation.id),
                    )
                elif order_dir == "desc":
                    query = query.order_by(desc(order_field))
                else:
                    query = query.order_by(asc(order_field))

            # Parameter metadata belongs to a displayed leaderboard entry, not
            # to an individual metric row. Calculate coverage in SQL so the
            # ordinary, paginated leaderboard endpoint remains bounded.
            parameter_coverage_total = 0
            parameter_coverage_known = 0
            parameter_counts = func.count(func.distinct(DBEvaluation.num_parameters))
            parameter_groups = (
                query.order_by(None)
                .with_entities(
                    DBEvaluation.paper_id,
                    DBEvaluation.task_id,
                    DBEvaluation.dataset_id,
                    func.coalesce(DBEvaluation.model_name, ""),
                    func.coalesce(DBEvaluation.harness, ""),
                )
                .group_by(
                    DBEvaluation.paper_id,
                    DBEvaluation.task_id,
                    DBEvaluation.dataset_id,
                    func.coalesce(DBEvaluation.model_name, ""),
                    func.coalesce(DBEvaluation.harness, ""),
                )
            )
            parameter_coverage_total = parameter_groups.count()
            parameter_coverage_known = parameter_groups.having(
                parameter_counts == 1
            ).count()

            if max_parameters_exclusive is not None:
                # Keep sibling metric rows together by the same identity used
                # by the frontend table. A bound is an explicit leaderboard
                # request, so it is the only path that materializes entries.
                parameter_entries = self._parameter_entries(query.all())
                filtered_entries = [
                    rows
                    for rows, parameter_count in parameter_entries
                    if parameter_count is not None
                    and parameter_count < max_parameters_exclusive
                ]
                total_count = len(filtered_entries)
                offset = (page - 1) * page_size
                results = [
                    row
                    for rows in filtered_entries[offset : offset + page_size]
                    for row in rows
                ]
            else:
                # Preserve the established row-level pagination contract for
                # ordinary evaluation queries.
                total_count = query.count()
                offset = (page - 1) * page_size
                results = query.offset(offset).limit(page_size).all()

            evaluation_list = self._serialize_evaluations(results)

            # Calculate pagination
            total_pages = (total_count + page_size - 1) // page_size
            next_page = page + 1 if page < total_pages else None
            previous_page = page - 1 if page > 1 else None

            return Evaluations(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=evaluation_list,
                parameter_coverage_known=parameter_coverage_known,
                parameter_coverage_total=parameter_coverage_total,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve evaluations: {str(e)}")

    @staticmethod
    def _parameter_entries(
        evaluations: list[DBEvaluation],
    ) -> list[tuple[list[DBEvaluation], Optional[int]]]:
        """Group metric siblings and return their unambiguous parameter count.

        A missing sibling value does not make an otherwise-known entry
        ambiguous. Multiple distinct non-null values do, and are deliberately
        excluded from parameter-constrained results.
        """
        entries: dict[tuple[int, int, int, str, str], list[DBEvaluation]] = {}
        for evaluation in evaluations:
            key = evaluation_display_entry_key(
                evaluation.paper_id,
                evaluation.task_id,
                evaluation.dataset_id,
                evaluation.model_name,
                evaluation.harness,
            )
            entries.setdefault(key, []).append(evaluation)

        grouped: list[tuple[list[DBEvaluation], Optional[int]]] = []
        for rows in entries.values():
            counts = {
                row.num_parameters for row in rows if row.num_parameters is not None
            }
            parameter_count = counts.pop() if len(counts) == 1 else None
            grouped.append((rows, parameter_count))
        return grouped

    def get_evaluation(self, evaluation_id: int) -> Optional[Evaluation]:
        """
        Get a specific evaluation by ID.

        Args:
            evaluation_id: Evaluation ID

        Returns:
            Evaluation object or None if not found

        Raises:
            DatabaseError: If database query fails
        """
        try:
            db_evaluation = (
                self.db.query(DBEvaluation)
                .filter(DBEvaluation.id == evaluation_id)
                .first()
            )

            if not db_evaluation:
                return None

            return self._serialize_evaluation(db_evaluation)

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve evaluation: {str(e)}")

    def list_catalog_evaluations(
        self, *, ordering: Optional[str], **filters
    ) -> Evaluations:
        """Return evaluations using the typed HTTP read contract."""
        ordering_value = ordering or (
            "best_rank" if filters.get("dataset_id") is not None else "-created_at"
        )
        order_dir = "desc" if ordering_value.startswith("-") else "asc"
        order_by = ordering_value.removeprefix("-")
        if order_by not in {
            "created_at",
            "best_rank",
            "evaluated_on",
            "benchmark_popularity",
        }:
            order_by = "created_at"
        try:
            return self.get_evaluations(
                order_by=order_by, order_dir=order_dir, **filters
            )
        except DatabaseError as error:
            raise CatalogPersistenceError(str(error)) from error

    def get_catalog_evaluation(self, evaluation_id: int) -> Evaluation:
        """Return one evaluation or a typed not-found/persistence failure."""
        try:
            evaluation = self.get_evaluation(evaluation_id)
        except DatabaseError as error:
            raise CatalogPersistenceError(str(error)) from error
        if evaluation is None:
            raise CatalogNotFoundError(f"Evaluation {evaluation_id} not found")
        return evaluation

    def search_evaluations(
        self, query: str, page: int = 1, page_size: int = 50
    ) -> Evaluations:
        """
        Search evaluations by model name or methodology.

        Args:
            query: Search query string
            page: Page number (1-based)
            page_size: Number of evaluations per page

        Returns:
            Evaluations object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        return self.get_evaluations(
            page=page,
            page_size=page_size,
            search=query,
            order_by="created_at",
            order_dir="desc",
        )

    def create_evaluation(
        self,
        paper_id: int,
        task_id: int,
        dataset_id: int,
        metrics: dict,
        model_name: Optional[str] = None,
        harness: Optional[str] = None,
        methodology: Optional[str] = None,
        uses_additional_data: bool = False,
        is_open: bool = True,
        best_rank: Optional[int] = None,
        best_metric: Optional[str] = None,
        evaluated_on: Optional[str] = None,
        external_source_url: Optional[str] = None,
        source_url: Optional[str] = None,
        num_parameters: Optional[int] = None,
        hf_model_url: Optional[str] = None,
        commit: bool = True,
        rank_scopes: RankScopes | None = None,
    ) -> Evaluation:
        """
        Create a new evaluation.

        Args:
            paper_id: Paper ID
            task_id: Task ID
            dataset_id: Dataset ID
            metrics: Dictionary of metric names and values
            model_name: Model name
            methodology: Methodology description
            uses_additional_data: Whether additional data was used
            best_rank: Best rank achieved
            best_metric: Name of best metric
            evaluated_on: Evaluation date
            external_source_url: External source URL

        Returns:
            Created Evaluation object

        Raises:
            ValueError: If metrics are not valid for this dataset
            DatabaseError: If database operation fails
        """
        try:
            # Validate that the task is consistent with the dataset's officially linked tasks
            is_valid, error_message = self._validate_dataset_task_consistency(
                task_id, dataset_id
            )
            if not is_valid:
                raise CatalogValidationError(error_message)

            # Validate metrics against leaderboard's allowed metrics
            metric_service = LeaderboardMetricService(self.db)
            metric_keys = list(metrics.keys())
            is_valid, error_message = metric_service.validate_metrics_for_leaderboard(
                task_id, dataset_id, metric_keys, best_metric
            )

            if not is_valid:
                raise CatalogValidationError(error_message)

            is_valid, error_message = self._validate_harness_support(
                task_id, dataset_id, harness
            )
            if not is_valid:
                raise CatalogValidationError(error_message)

            self._reject_leaderboard_duplicate(
                task_id=task_id,
                dataset_id=dataset_id,
                best_metric=best_metric,
                model_name=model_name,
                harness=harness,
            )

            canonical_source_url = source_url or external_source_url
            derived_external = self._derive_external(paper_id, canonical_source_url)

            db_evaluation = DBEvaluation(
                paper_id=paper_id,
                task_id=task_id,
                dataset_id=dataset_id,
                model_name=model_name,
                harness=harness,
                methodology=methodology,
                metrics=metrics,
                uses_additional_data=uses_additional_data,
                is_open=is_open,
                best_rank=best_rank,
                best_metric=best_metric,
                evaluated_on=evaluated_on,
                external_source_url=canonical_source_url,
                source_url=canonical_source_url,
                external=derived_external,
                num_parameters=num_parameters,
                hf_model_url=hf_model_url,
            )

            self.db.add(db_evaluation)
            self.db.flush()
            self.db.refresh(db_evaluation)

            self._refresh_or_collect_ranks(
                self._rank_scopes(db_evaluation), rank_scopes
            )
            if commit:
                self.db.commit()

            return self._serialize_evaluation(db_evaluation)

        except ValueError:
            if commit:
                self.db.rollback()
            raise
        except CatalogNotFoundError:
            if commit:
                self.db.rollback()
            raise
        except DatabaseError:
            if commit:
                self.db.rollback()
            raise
        except Exception as e:
            if commit:
                self.db.rollback()
            raise DatabaseError(f"Failed to create evaluation: {str(e)}")

    def update_evaluation(
        self,
        evaluation_id: int,
        task_id: Optional[int] = None,
        dataset_id: Optional[int] = None,
        model_name: Optional[str] = None,
        harness: Optional[str] = None,
        methodology: Optional[str] = None,
        metrics: Optional[dict] = None,
        uses_additional_data: Optional[bool] = None,
        is_open: Optional[bool] = None,
        best_rank: Optional[int] = None,
        best_metric: Optional[str] = None,
        evaluated_on: Optional[str] = None,
        external_source_url: Optional[str] = None,
        source_url: Optional[str] = None,
        num_parameters: Optional[int] = None,
        hf_model_url: Optional[str] = None,
        harness_set: bool = False,
        source_url_set: bool = False,
        num_parameters_set: bool = False,
        hf_model_url_set: bool = False,
        commit: bool = True,
        rank_scopes: RankScopes | None = None,
    ) -> Evaluation:
        """
        Update an existing evaluation.

        Args:
            evaluation_id: Evaluation ID to update
            task_id: Task ID (changing this moves evaluation to different leaderboard)
            dataset_id: Dataset ID (changing this moves evaluation to different leaderboard)
            model_name: Model name
            methodology: Methodology description
            metrics: Dictionary of metric names and values
            uses_additional_data: Whether additional data was used
            best_rank: Best rank achieved
            best_metric: Name of best metric
            evaluated_on: Evaluation date
            external_source_url: External source URL

        Returns:
            Updated Evaluation object

        Raises:
            ValueError: If metrics are not valid for this dataset
            CatalogNotFoundError: If the evaluation does not exist
            DatabaseError: If database operation fails
        """
        try:
            db_evaluation = (
                self.db.query(DBEvaluation)
                .filter(DBEvaluation.id == evaluation_id)
                .first()
            )

            if not db_evaluation:
                raise CatalogNotFoundError(f"Evaluation {evaluation_id} not found")

            # Capture the original leaderboard before changing its keys or metrics.
            old_task_id = db_evaluation.task_id
            old_dataset_id = db_evaluation.dataset_id
            affected_scopes = self._rank_scopes(db_evaluation)

            # Determine which dataset to validate against
            target_dataset_id = dataset_id if dataset_id is not None else old_dataset_id

            # Determine which metrics and best_metric to validate
            target_metrics = metrics if metrics is not None else db_evaluation.metrics
            target_best_metric = (
                best_metric if best_metric is not None else db_evaluation.best_metric
            )

            # Determine which task to validate against
            target_task_id = task_id if task_id is not None else old_task_id

            target_harness = harness if harness_set else db_evaluation.harness

            # Validate dataset-task consistency if task or dataset is changing
            if task_id is not None or dataset_id is not None:
                is_valid, error_message = self._validate_dataset_task_consistency(
                    target_task_id, target_dataset_id
                )
                if not is_valid:
                    raise CatalogValidationError(error_message)

            is_valid, error_message = self._validate_harness_support(
                target_task_id, target_dataset_id, target_harness
            )
            if not is_valid:
                raise CatalogValidationError(error_message)

            # Existing rows keep editing freely; only a change of leaderboard or
            # model identity must not land on another row's entry.
            target_model_name = (
                model_name if model_name is not None else db_evaluation.model_name
            )
            if (
                target_task_id,
                target_dataset_id,
                target_best_metric,
                leaderboard_model_key(target_model_name, target_harness),
            ) != (
                old_task_id,
                old_dataset_id,
                db_evaluation.best_metric,
                leaderboard_model_key(db_evaluation.model_name, db_evaluation.harness),
            ):
                self._reject_leaderboard_duplicate(
                    task_id=target_task_id,
                    dataset_id=target_dataset_id,
                    best_metric=target_best_metric,
                    model_name=target_model_name,
                    harness=target_harness,
                    exclude_id=evaluation_id,
                )

            # Validate metrics if they are being changed or task/dataset is changing
            if (
                metrics is not None
                or dataset_id is not None
                or task_id is not None
                or best_metric is not None
            ):
                metric_service = LeaderboardMetricService(self.db)
                metric_keys = list(target_metrics.keys())
                is_valid, error_message = (
                    metric_service.validate_metrics_for_leaderboard(
                        target_task_id,
                        target_dataset_id,
                        metric_keys,
                        target_best_metric,
                    )
                )

                if not is_valid:
                    raise CatalogValidationError(error_message)

            # Update only provided fields
            if task_id is not None:
                db_evaluation.task_id = task_id
            if dataset_id is not None:
                db_evaluation.dataset_id = dataset_id
            if model_name is not None:
                db_evaluation.model_name = model_name
            if harness_set:
                db_evaluation.harness = harness
            if methodology is not None:
                db_evaluation.methodology = methodology
            if metrics is not None:
                db_evaluation.metrics = metrics
            if uses_additional_data is not None:
                db_evaluation.uses_additional_data = uses_additional_data
            if is_open is not None:
                db_evaluation.is_open = is_open
            if best_rank is not None:
                db_evaluation.best_rank = best_rank
            if best_metric is not None:
                db_evaluation.best_metric = best_metric
            if evaluated_on is not None:
                db_evaluation.evaluated_on = evaluated_on
            if source_url_set or external_source_url is not None:
                canonical_source_url = (
                    source_url if source_url_set else external_source_url
                )
                db_evaluation.source_url = canonical_source_url
                db_evaluation.external_source_url = canonical_source_url
                db_evaluation.external = self._derive_external(
                    db_evaluation.paper_id, canonical_source_url
                )
            if num_parameters_set:
                db_evaluation.num_parameters = num_parameters
            if hf_model_url_set:
                db_evaluation.hf_model_url = hf_model_url

            self.db.flush()
            self.db.refresh(db_evaluation)

            affected_scopes.update(self._rank_scopes(db_evaluation))
            self._refresh_or_collect_ranks(affected_scopes, rank_scopes)
            if commit:
                self.db.commit()

            return self._serialize_evaluation(db_evaluation)

        except ValueError:
            if commit:
                self.db.rollback()
            raise
        except CatalogNotFoundError:
            if commit:
                self.db.rollback()
            raise
        except DatabaseError:
            if commit:
                self.db.rollback()
            raise
        except Exception as e:
            if commit:
                self.db.rollback()
            raise DatabaseError(f"Failed to update evaluation: {str(e)}")

    def delete_evaluation(
        self,
        evaluation_id: int,
        *,
        commit: bool = True,
        rank_scopes: RankScopes | None = None,
    ) -> bool:
        """
        Delete an evaluation.

        Args:
            evaluation_id: Evaluation ID to delete

        Returns:
            True if deletion was successful

        Raises:
            CatalogNotFoundError: If the evaluation does not exist
            DatabaseError: If database operation fails
        """
        try:
            db_evaluation = (
                self.db.query(DBEvaluation)
                .filter(DBEvaluation.id == evaluation_id)
                .first()
            )

            if not db_evaluation:
                raise CatalogNotFoundError(f"Evaluation {evaluation_id} not found")

            affected_scopes = self._rank_scopes(db_evaluation)
            self.db.delete(db_evaluation)
            self.db.flush()
            self._refresh_or_collect_ranks(affected_scopes, rank_scopes)
            if commit:
                self.db.commit()

            return True

        except CatalogNotFoundError:
            if commit:
                self.db.rollback()
            raise
        except Exception as e:
            if commit:
                self.db.rollback()
            raise DatabaseError(f"Failed to delete evaluation: {str(e)}")

    def restore_evaluation_snapshot(
        self, snapshot: Optional[dict], *, commit: bool = False
    ) -> Optional[DBEvaluation]:
        """Restore one exact audited row, or its audited absence."""

        evaluation_id = int(snapshot["id"]) if snapshot else None
        current = self.db.get(DBEvaluation, evaluation_id) if evaluation_id else None
        if snapshot is None:
            if current is not None:
                self.db.delete(current)
            self.db.flush()
            if commit:
                self.db.commit()
            return None

        is_valid, error = self._validate_dataset_task_consistency(
            int(snapshot["task_id"]), int(snapshot["dataset_id"])
        )
        if not is_valid:
            raise ValueError(error)
        metric_service = LeaderboardMetricService(self.db)
        is_valid, error = metric_service.validate_metrics_for_leaderboard(
            int(snapshot["task_id"]),
            int(snapshot["dataset_id"]),
            list((snapshot.get("metrics") or {}).keys()),
            snapshot.get("best_metric"),
        )
        if not is_valid:
            raise ValueError(error)
        values = {
            key: snapshot.get(key)
            for key in (
                "paper_id",
                "task_id",
                "dataset_id",
                "model_name",
                "harness",
                "methodology",
                "metrics",
                "uses_additional_data",
                "is_open",
                "best_rank",
                "best_metric",
                "evaluated_on",
                "external_source_url",
                "source_url",
                "external",
                "num_parameters",
                "hf_model_url",
                "created_at",
                "updated_at",
            )
        }
        if isinstance(values["evaluated_on"], str):
            from datetime import date

            values["evaluated_on"] = date.fromisoformat(values["evaluated_on"])
        for key in ("created_at", "updated_at"):
            if isinstance(values[key], str):
                from datetime import datetime

                values[key] = datetime.fromisoformat(values[key])
        if current is None:
            current = DBEvaluation(id=evaluation_id, **values)
            self.db.add(current)
        else:
            for key, value in values.items():
                setattr(current, key, value)
        self.db.flush()
        if commit:
            self.db.commit()
        return current

    @staticmethod
    def _metric_names_for_rank_refresh(
        metrics: Optional[dict], best_metric: Optional[str]
    ) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for name in [best_metric, *(metrics or {}).keys()]:
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return names

    def _rank_scopes(self, row: DBEvaluation) -> RankScopes:
        return {
            (row.task_id, row.dataset_id, metric)
            for metric in self._metric_names_for_rank_refresh(
                row.metrics, row.best_metric
            )
        }

    def _refresh_or_collect_ranks(
        self, affected: RankScopes, batch: RankScopes | None
    ) -> None:
        if batch is None:
            self.refresh_rank_scopes(affected)
        else:
            batch.update(affected)

    def refresh_rank_scopes(self, scopes: RankScopes) -> None:
        """Refresh each affected leaderboard after all writes, without committing."""
        self.db.flush()
        for task_id, dataset_id, metric in sorted(scopes):
            self.recalculate_ranks(
                task_id, dataset_id, metric_name=metric, commit=False
            )
        # Required with autoflush=False, including before audit snapshots/reloads.
        self.db.flush()

    def recalculate_ranks(
        self,
        task_id: int,
        dataset_id: int,
        metric_name: Optional[str] = None,
        uses_additional_data: Optional[bool] = None,
        commit: bool = True,
    ) -> int:
        """
        Recalculate ranks for evaluations in a specific leaderboard.

        For each metric, every evaluation on the (task, dataset) pair that carries a
        parseable value for that metric in `metrics` participates in ranking — including
        rows whose primary metric is different (e.g. mAP-primary rows that also report FPS).
        `best_rank` is written only on rows where `best_metric` matches the metric being
        ranked.

        The ranking direction (higher is better vs lower is better) is determined by the
        metrics table. Evaluations with the same metric value get the same rank.

        Leaderboards are defined by (task, dataset, metric) triples. If metric_name is
        provided, only recalculates ranks for that specific metric. If None, recalculates
        for all metrics present as `best_metric` on evaluations for this task-dataset pair.

        Args:
            task_id: Task ID to recalculate ranks for
            dataset_id: Dataset ID to recalculate ranks for
            metric_name: Optional metric name to recalculate ranks for. If None, recalculates all.
            uses_additional_data: If specified, only recalculate for evaluations with this value

        Returns:
            Number of evaluations updated

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            # If metric_name is provided, recalculate only for that metric
            # Otherwise, recalculate for all unique metrics in this task-dataset pair
            if metric_name:
                metrics_to_process = [metric_name]
            else:
                unique_metrics = (
                    self.db.query(DBEvaluation.best_metric)
                    .filter(
                        DBEvaluation.task_id == task_id,
                        DBEvaluation.dataset_id == dataset_id,
                        DBEvaluation.best_metric.isnot(None),
                    )
                    .distinct()
                    .all()
                )
                metrics_to_process = [m[0] for m in unique_metrics]

                all_evals = self.db.query(DBEvaluation).filter(
                    DBEvaluation.task_id == task_id,
                    DBEvaluation.dataset_id == dataset_id,
                )
                if uses_additional_data is not None:
                    all_evals = all_evals.filter(
                        DBEvaluation.uses_additional_data == uses_additional_data
                    )
                for eval_obj in all_evals.all():
                    if eval_obj.metrics:
                        for key in eval_obj.metrics:
                            if key not in metrics_to_process:
                                metrics_to_process.append(key)

            if not metrics_to_process:
                return 0

            total_updated = 0

            # Process each metric separately
            for current_metric in metrics_to_process:
                query = self.db.query(DBEvaluation).filter(
                    DBEvaluation.task_id == task_id,
                    DBEvaluation.dataset_id == dataset_id,
                )

                if uses_additional_data is not None:
                    query = query.filter(
                        DBEvaluation.uses_additional_data == uses_additional_data
                    )

                evaluations = query.all()

                if not evaluations:
                    continue

                # Determine the ranking direction from the metrics table
                metric_direction = "higher_is_better"  # Default

                # Query metrics table for ranking direction
                metric_def = (
                    self.db.query(DBMetric)
                    .filter(DBMetric.name == current_metric)
                    .first()
                )

                if metric_def:
                    metric_direction = metric_def.direction
                else:
                    # Log warning if metric not found in database
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"Metric '{current_metric}' not found in metrics table. "
                        f"Defaulting to 'higher_is_better' for ranking."
                    )

                eval_scores = []
                for eval_obj in evaluations:
                    metric_value = parse_metric_value(
                        (eval_obj.metrics or {}).get(current_metric)
                    )
                    eval_scores.append((eval_obj, metric_value))

                # Sort by metric value based on direction
                # Place evaluations without valid metric values at the end
                if metric_direction == "lower_is_better":
                    # For "lower is better" metrics (WER, error rates, perplexity)
                    # Lower values should get rank 1
                    eval_scores.sort(
                        key=lambda x: (
                            x[1] is None,
                            x[1] if x[1] is not None else float("inf"),
                        )
                    )
                else:
                    # For "higher is better" metrics (AP, accuracy, F1)
                    # Higher values should get rank 1 (default behavior)
                    eval_scores.sort(
                        key=lambda x: (x[1] is None, -x[1] if x[1] is not None else 0)
                    )

                # Assign ranks (same value = same rank)
                current_rank = 1
                previous_score = None

                for idx, (eval_obj, score) in enumerate(eval_scores):
                    if score is None:
                        if eval_obj.best_metric == current_metric:
                            eval_obj.best_rank = None
                            total_updated += 1
                        continue

                    if previous_score is not None and score != previous_score:
                        current_rank = idx + 1
                    elif previous_score is None:
                        current_rank = idx + 1

                    if eval_obj.best_metric == current_metric:
                        eval_obj.best_rank = current_rank
                        total_updated += 1

                    previous_score = score

            # Commit all rank updates
            if commit:
                self.db.commit()

            return total_updated

        except Exception as e:
            if commit:
                self.db.rollback()
            raise DatabaseError(f"Failed to recalculate ranks: {str(e)}")
