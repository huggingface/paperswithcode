"""Synchronize Artificial Analysis Intelligence and Agentic Index results."""

from __future__ import annotations

import asyncio
import math
import re
import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    Metric,
    ModelProviderAlias,
    ModelRelease,
    Paper,
    PaperTask,
    Task,
    TaskDatasetMetric,
)
from backend.services.evaluation_service import EvaluationService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.leaderboard_sync_ownership import managed_methodology_prefix
from backend.services.model_release_identity_service import ModelReleaseIdentityService
from backend.services.paper_ingestion_service import PaperIngestionService

API_ENDPOINT = "https://artificialanalysis.ai/api/v2/language/models/free"
# The free Data API key allows 100 requests per day and a full fetch costs one
# request per 200-model page. The every-two-hours sync and the three-hourly
# release radar share that budget.
SOURCE_URL_PREFIX = "https://artificialanalysis.ai/models/"
METRIC_NAME = "Score"
MANAGED_METHODOLOGY_PREFIX = managed_methodology_prefix("Artificial Analysis")


# Reviewed upstream renames. Only previously managed rows may carry their
# existing paper binding across these exact slug changes.
MODEL_SLUG_RENAMES = {
    "k2-4b-ph1": "k2-horizon-3-7b",
    "k2-7b-ph2": "k2-horizon-7b",
    "k2-mova-36b-mid5": "k2-horizon-mova-36b-a4b",
}


@dataclass(frozen=True)
class ArtificialAnalysisIndex:
    key: str
    evaluation_key: str
    dataset_slug: str
    task_slug: str
    label: str
    min_expected_models: int
    max_expected_models: int


INDEXES: tuple[ArtificialAnalysisIndex, ...] = (
    ArtificialAnalysisIndex(
        key="intelligence",
        evaluation_key="artificial_analysis_intelligence_index",
        dataset_slug="artificial-analysis-intelligence-index",
        task_slug="language-modeling",
        label="Intelligence Index",
        # Index v5 (2026-10-27) re-scored only 77 models.
        min_expected_models=50,
        max_expected_models=1_000,
    ),
    ArtificialAnalysisIndex(
        key="agentic",
        evaluation_key="artificial_analysis_agentic_index",
        dataset_slug="artificial-analysis-agentic-index",
        task_slug="agents",
        label="Agentic Index",
        min_expected_models=20,
        max_expected_models=1_000,
    ),
)
INDEXES_BY_KEY = {index.key: index for index in INDEXES}
INTELLIGENCE_INDEX = INDEXES_BY_KEY["intelligence"]
AGENTIC_INDEX = INDEXES_BY_KEY["agentic"]
DATASET_SLUG = INTELLIGENCE_INDEX.dataset_slug
TASK_SLUG = INTELLIGENCE_INDEX.task_slug
MIN_EXPECTED_MODELS = INTELLIGENCE_INDEX.min_expected_models
MAX_EXPECTED_MODELS = INTELLIGENCE_INDEX.max_expected_models
# Refuse a response that drops more than a quarter of the reviewed models.
MAX_MISSING_REVIEWED_DIVISOR = 4


@dataclass(frozen=True)
class PaperIdentity:
    arxiv_id: str | None = None
    source_url: str | None = None
    title: str | None = None
    date_published: date | None = None
    is_open: bool = False

    def __post_init__(self) -> None:
        if (self.arxiv_id is None) == (self.source_url is None):
            raise ValueError("PaperIdentity requires exactly one stable identity")
        if self.source_url and (not self.title or not self.date_published):
            raise ValueError(
                "External paper identities require title and publication date"
            )


def external(source_url: str, title: str, published: str, *, is_open: bool = False):
    return PaperIdentity(
        source_url=source_url,
        title=title,
        date_published=date.fromisoformat(published),
        is_open=is_open,
    )


# Exact, reviewed links for the model variants plotted on the Artificial
# Analysis homepage chart. Upstream additions remain unmatched until their
# canonical technical report or official release page has been reviewed.
MODEL_PAPER_IDENTITIES: dict[str, PaperIdentity] = {
    "a-x-k2": external(
        "https://github.com/SKT-AI/A.X-K2/blob/main/A_X_K2_Tech_Report.pdf",
        "A.X K2 Technical Report",
        "2026-07-29",
        is_open=True,
    ),
    "claude-4-5-haiku-reasoning": external(
        "https://www.anthropic.com/claude/haiku",
        "Claude Haiku 4.5",
        "2025-10-15",
    ),
    "claude-fable-5": external(
        "https://www.anthropic.com/news/claude-fable-5-mythos-5",
        "Claude Fable 5 and Claude Mythos 5",
        "2026-06-09",
    ),
    "claude-opus-5": external(
        "https://www.anthropic.com/news/claude-opus-5",
        "Introducing Claude Opus 5",
        "2026-07-24",
    ),
    "command-a-plus": external(
        "https://cohere.com/blog/command-a-plus",
        "Command A+",
        "2026-05-20",
        is_open=True,
    ),
    "deepseek-v4-pro": PaperIdentity(arxiv_id="2606.19348", is_open=True),
    "gemini-3-5-flash-lite": external(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/",
        "Introducing Gemini 3.6 Flash, 3.5 Flash-Lite, and 3.5 Flash Cyber",
        "2026-07-21",
    ),
    "gemini-3-7-flash": external(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-3-7-flash/",
        "Introducing Gemini 3.7 Flash",
        "2026-08-13",
    ),
    "glm-5-2": external(
        "https://z.ai/blog/glm-5.2",
        "GLM-5.2: Built for Long-Horizon Tasks",
        "2026-06-16",
        is_open=True,
    ),
    "gpt-5-6-luna": external(
        "https://openai.com/index/gpt-5-6/",
        "GPT-5.6: Frontier intelligence that scales with your ambition",
        "2026-07-09",
    ),
    "gpt-5-6-sol": external(
        "https://openai.com/index/gpt-5-6/",
        "GPT-5.6: Frontier intelligence that scales with your ambition",
        "2026-07-09",
    ),
    "gpt-5-6-terra": external(
        "https://openai.com/index/gpt-5-6/",
        "GPT-5.6: Frontier intelligence that scales with your ambition",
        "2026-07-09",
    ),
    "gpt-oss-120b": PaperIdentity(arxiv_id="2508.10925", is_open=True),
    "grok-4-6": external(
        "https://x.ai/news/grok-4-6", "Introducing Grok 4.6", "2026-08-12"
    ),
    "inkling": external(
        "https://thinkingmachines.ai/news/introducing-inkling/",
        "Inkling: Our open-weights model",
        "2026-07-15",
        is_open=True,
    ),
    "k-exaone-2-0-0803": PaperIdentity(arxiv_id="2608.04505", is_open=True),
    "kimi-k3": PaperIdentity(arxiv_id="2607.24653", is_open=True),
    "ling-3-1-flash": external(
        "https://developer.ant-ling.com/en/docs/models/ling#ling-31-flash",
        "Ling-3.1-flash",
        "2026-09-30",
    ),
    "minimax-m3": external(
        "https://www.minimax.io/blog/minimax-m3",
        "MiniMax M3: Frontier Coding, 1M Context, Native Multimodality — All in One Model",
        "2026-06-01",
        is_open=True,
    ),
    "mistral-medium-3-5": external(
        "https://docs.mistral.ai/models/mistral-medium-3-5-26-04",
        "Mistral Medium 3.5",
        "2026-04-28",
        is_open=True,
    ),
    "motif-3": PaperIdentity(arxiv_id="2608.09119", is_open=True),
    "muse-glimmer": external(
        "https://huggingface.co/meta-models/Muse-Glimmer-30B",
        "Muse Glimmer-30B",
        "2026-08-09",
        is_open=True,
    ),
    "muse-spark-1-2": external(
        "https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/",
        "Introducing Muse Spark 1.1",
        "2026-07-09",
    ),
    "muse-wonder": external(
        "https://research.meta.ai/blog/muse-wonder",
        "Muse Wonder: A Frontier Model For Personal & Professional AI Agents",
        "2026-10-12",
    ),
    "muse-wonder-full": external(
        "https://research.meta.ai/blog/muse-wonder",
        "Muse Wonder: A Frontier Model For Personal & Professional AI Agents",
        "2026-10-12",
    ),
    "nemotron-3-5-lightning": external(
        "https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-Base-BF16",
        "NVIDIA Nemotron 3.5 Lightning",
        "2026-08-11",
        is_open=True,
    ),
    "nvidia-nemotron-3-super-120b-a12b": PaperIdentity(
        arxiv_id="2512.20856", is_open=True
    ),
    "nvidia-nemotron-3-ultra-550b-a55b": PaperIdentity(
        arxiv_id="2606.15007", is_open=True
    ),
    "qwen3-8-max": external(
        "https://qwen.ai/blog?id=qwen3.8",
        "Qwen3.8-Max: A New Bar for Coding and Cowork",
        "2026-08-03",
    ),
    "solar-open2-250b": PaperIdentity(arxiv_id="2607.20062", is_open=True),
}


@dataclass(frozen=True)
class ArtificialAnalysisEntry:
    slug: str
    name: str
    scores: dict[str, float]
    release_date: date


@dataclass(frozen=True)
class ArtificialAnalysisLeaderboard:
    index_version: str
    entries: list[ArtificialAnalysisEntry]
    # Daily API budget left after this fetch, from the last page's headers.
    quota_remaining: str | None = None
    quota_limit: str | None = None
    # Reviewed slugs Artificial Analysis no longer lists.
    missing_reviewed: list[str] = field(default_factory=list)
    # Indexes with no scores at all; their rows are kept until scores return.
    withdrawn_indexes: list[str] = field(default_factory=list)


@dataclass
class ArtificialAnalysisDiscovery:
    papers: dict[str, int] = field(default_factory=dict)
    indexed_papers: list[str] = field(default_factory=list)
    would_index: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolved": len(self.papers),
            "indexed_papers": self.indexed_papers,
            "would_index": self.would_index,
        }


@dataclass
class ArtificialAnalysisIndexStats:
    fetched: int = 0
    selected: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    retired: int = 0
    missing_papers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ArtificialAnalysisSyncStats:
    fetched: int = 0
    selected: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    retired: int = 0
    indexed_papers: int = 0
    missing_papers: list[str] = field(default_factory=list)
    missing_upstream: list[str] = field(default_factory=list)
    indexes: dict[str, ArtificialAnalysisIndexStats] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "fetched": self.fetched,
            "selected": self.selected,
            "matched": self.matched,
            "created": self.created,
            "updated": self.updated,
            "retired": self.retired,
            "indexed_papers": self.indexed_papers,
            "missing_papers": self.missing_papers,
            "missing_upstream": self.missing_upstream,
        }
        payload.update({key: stats.to_dict() for key, stats in self.indexes.items()})
        return payload


def _parse_score(raw_score: Any, *, slug: str, index: ArtificialAnalysisIndex) -> float:
    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        raise TypeError(
            f"Artificial Analysis {index.label} score is invalid for {slug}"
        )
    score = float(raw_score)
    if not math.isfinite(score) or not -100 <= score <= 100:
        raise ValueError(
            f"Artificial Analysis {index.label} score is out of bounds for {slug}"
        )
    return score


def _parse_page(
    payload: Any,
) -> tuple[str, list[ArtificialAnalysisEntry], dict, set[str]]:
    if not isinstance(payload, dict):
        raise TypeError("Artificial Analysis response must be a JSON object")
    version = payload.get("intelligence_index_version")
    pagination = payload.get("pagination")
    rows = payload.get("data")
    if isinstance(version, bool) or not isinstance(version, (str, int, float)):
        raise TypeError("Artificial Analysis response has invalid index version")
    version = str(version).strip()
    if not version:
        raise ValueError("Artificial Analysis response has no index version")
    if not isinstance(pagination, dict) or not isinstance(rows, list):
        raise TypeError("Artificial Analysis response has invalid pagination or data")

    entries: list[ArtificialAnalysisEntry] = []
    listed: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise TypeError("Artificial Analysis model rows must be objects")
        slug = row.get("slug")
        if isinstance(slug, str):
            listed.add(slug)
        name = row.get("name")
        evaluations = row.get("evaluations")
        scores: dict[str, float] = {}
        for index in INDEXES:
            raw_score = (
                evaluations.get(index.evaluation_key)
                if isinstance(evaluations, dict)
                else None
            )
            if raw_score is None:
                continue
            if not isinstance(slug, str) or not slug or len(slug) > 255:
                raise ValueError("Artificial Analysis row has an invalid slug")
            if not isinstance(name, str) or not name or len(name) > 255:
                raise ValueError(f"Artificial Analysis row {slug} has an invalid name")
            scores[index.key] = _parse_score(raw_score, slug=slug, index=index)
        if not scores:
            continue
        if not isinstance(slug, str) or not slug or len(slug) > 255:
            raise ValueError("Artificial Analysis row has an invalid slug")
        if not isinstance(name, str) or not name or len(name) > 255:
            raise ValueError(f"Artificial Analysis row {slug} has an invalid name")
        try:
            released = date.fromisoformat(row["release_date"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Artificial Analysis release date is invalid for {slug}"
            ) from exc
        entries.append(ArtificialAnalysisEntry(slug, name, scores, released))
    return version, entries, pagination, listed


def fetch_artificial_analysis_leaderboard(
    *, api_key: str | None = None, client: httpx.Client | None = None
) -> ArtificialAnalysisLeaderboard:
    key = api_key or os.environ.get("ARTIFICIAL_ANALYSIS_API_KEY")
    if not key:
        raise RuntimeError("ARTIFICIAL_ANALYSIS_API_KEY is required")
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(30, connect=5),
        follow_redirects=False,
        headers={"User-Agent": "paperswithcode-artificial-analysis-sync/1.0"},
    )
    try:
        all_entries: list[ArtificialAnalysisEntry] = []
        listed_slugs: set[str] = set()
        version: str | None = None
        page = 1
        while True:
            response = active_client.get(
                API_ENDPOINT,
                headers={"x-api-key": key},
                params={"page": page, "page_size": 200},
            )
            response.raise_for_status()
            quota_remaining = response.headers.get("x-ratelimit-remaining")
            quota_limit = response.headers.get("x-ratelimit-limit")
            page_version, entries, pagination, listed = _parse_page(response.json())
            if version is not None and page_version != version:
                raise ValueError(
                    "Artificial Analysis index version changed during fetch"
                )
            version = page_version
            all_entries.extend(entries)
            listed_slugs |= listed
            has_more = pagination.get("has_more")
            total_pages = pagination.get("total_pages")
            if not isinstance(has_more, bool) or not isinstance(total_pages, int):
                raise TypeError("Artificial Analysis pagination fields are invalid")
            if not has_more:
                if page != total_pages:
                    raise ValueError(
                        "Artificial Analysis pagination ended unexpectedly"
                    )
                break
            if page >= total_pages or total_pages > 20:
                raise ValueError("Artificial Analysis pagination is inconsistent")
            page += 1
    finally:
        if owned_client:
            active_client.close()

    unique_entries: dict[str, ArtificialAnalysisEntry] = {}
    for entry in all_entries:
        previous = unique_entries.get(entry.slug)
        if previous is not None and previous != entry:
            raise ValueError(
                f"Artificial Analysis response contains conflicting model slug: {entry.slug}"
            )
        unique_entries[entry.slug] = entry
    all_entries = list(unique_entries.values())
    # Listed-but-unscored models (deprecated or awaiting re-scoring) are present.
    missing = sorted(set(MODEL_PAPER_IDENTITIES) - listed_slugs)
    # A few withdrawn models are normal; a large gap means a broken response.
    if len(missing) > len(MODEL_PAPER_IDENTITIES) // MAX_MISSING_REVIEWED_DIVISOR:
        raise ValueError(
            "Artificial Analysis is missing reviewed models: " + ",".join(missing)
        )
    withdrawn: list[str] = []
    for index in INDEXES:
        scored = [entry.slug for entry in all_entries if index.key in entry.scores]
        if not scored:
            # Artificial Analysis cleared the whole index (Agentic, 2026-10-29).
            withdrawn.append(index.key)
            continue
        if not index.min_expected_models <= len(scored) <= index.max_expected_models:
            raise ValueError(
                f"Artificial Analysis {index.label} returned {len(scored)} scored "
                f"models; expected {index.min_expected_models}-{index.max_expected_models}"
            )
    return ArtificialAnalysisLeaderboard(
        version or "unknown",
        all_entries,
        quota_remaining=quota_remaining,
        quota_limit=quota_limit,
        missing_reviewed=missing,
        withdrawn_indexes=withdrawn,
    )


class ArtificialAnalysisPaperDiscoveryService:
    def __init__(
        self,
        db: Session,
        *,
        ingestion_service: PaperIngestionService | None = None,
        external_service: ExternalResourceService | None = None,
    ):
        self.db = db
        self.ingestion_service = ingestion_service or PaperIngestionService(db)
        self.external_service = external_service or ExternalResourceService(db)

    async def discover(
        self,
        *,
        persist: bool = True,
        leaderboard: ArtificialAnalysisLeaderboard | None = None,
        identities: dict[str, PaperIdentity] | None = None,
    ) -> ArtificialAnalysisDiscovery:
        result = ArtificialAnalysisDiscovery()
        active_identities = MODEL_PAPER_IDENTITIES if identities is None else identities
        for slug, identity in active_identities.items():
            query = self.db.query(Paper).filter(Paper.is_latest_version)
            paper = (
                (
                    query.filter(Paper.arxiv_id == identity.arxiv_id)
                    if identity.arxiv_id
                    else query.filter(
                        Paper.source == "external",
                        Paper.source_url == identity.source_url,
                    )
                )
                .order_by(Paper.id.desc())
                .first()
            )
            if paper is None and not persist:
                result.would_index.append(
                    identity.arxiv_id or identity.source_url or slug
                )
                continue
            if paper is None and identity.arxiv_id:
                paper, created = await self.ingestion_service.get_or_import_arxiv_paper(
                    identity.arxiv_id
                )
                if created:
                    result.indexed_papers.append(identity.arxiv_id)
            elif paper is None:
                ingestion = self.external_service.add_external_resource(
                    ExternalResourceInput(
                        source_url=identity.source_url or "",
                        title=identity.title or slug,
                        date_published=identity.date_published,
                    )
                )
                paper = (
                    self.db.query(Paper)
                    .filter(Paper.id == int(ingestion.paper.id))
                    .one()
                )
                result.indexed_papers.append(identity.source_url or slug)
            result.papers[slug] = paper.id
        if leaderboard is not None:
            identity_service = ModelReleaseIdentityService(self.db)
            resolved_releases = identity_service.resolve_many(
                "artificial-analysis",
                [
                    (entry.slug, entry.name)
                    for entry in leaderboard.entries
                    if entry.slug not in result.papers
                ],
            )
            for entry in leaderboard.entries:
                if entry.slug in result.papers:
                    continue
                release = resolved_releases.get(entry.slug)
                if release is not None and release.paper_id is not None:
                    result.papers[entry.slug] = release.paper_id
        return result


def _stale_index_version(
    methodology: str | None, index: ArtificialAnalysisIndex, version: str
) -> bool:
    """Whether a managed row names an index version other than ``version``."""
    match = re.search(rf"{re.escape(index.label)} (\S+); fetched", methodology or "")
    return match is not None and match.group(1) != version


class ArtificialAnalysisSyncService:
    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(
        self, index: ArtificialAnalysisIndex
    ) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == index.task_slug).one_or_none()
        dataset = (
            self.db.query(Dataset)
            .filter(Dataset.slug == index.dataset_slug)
            .one_or_none()
        )
        metric = self.db.query(Metric).filter(Metric.name == METRIC_NAME).one_or_none()
        if task is None or dataset is None or metric is None:
            raise RuntimeError(
                f"Artificial Analysis {index.label} leaderboard is not configured"
            )
        configured = (
            self.db.query(TaskDatasetMetric)
            .filter(
                TaskDatasetMetric.task_id == task.id,
                TaskDatasetMetric.dataset_id == dataset.id,
                TaskDatasetMetric.metric_id == metric.id,
            )
            .one_or_none()
        )
        if configured is None:
            raise RuntimeError(
                f"Artificial Analysis {index.label} metric is not linked to the task"
            )
        return task, dataset

    def _sync_index(
        self,
        index: ArtificialAnalysisIndex,
        leaderboard: ArtificialAnalysisLeaderboard,
        *,
        discovery: ArtificialAnalysisDiscovery,
        now: datetime,
        commit: bool,
    ) -> ArtificialAnalysisIndexStats:
        selected = [
            entry
            for entry in leaderboard.entries
            if entry.slug in discovery.papers and index.key in entry.scores
        ]
        listed = {entry.slug for entry in leaderboard.entries}
        reviewed = set(MODEL_PAPER_IDENTITIES) & listed
        scored_reviewed = {
            entry.slug
            for entry in leaderboard.entries
            if entry.slug in reviewed and index.key in entry.scores
        }
        if not scored_reviewed.issubset({entry.slug for entry in selected}):
            raise ValueError(
                f"Refusing to synchronize an incomplete reviewed model set for "
                f"{index.label}"
            )
        stats = ArtificialAnalysisIndexStats(
            fetched=sum(
                1 for entry in leaderboard.entries if index.key in entry.scores
            ),
            selected=len(selected),
        )
        task, dataset = self._leaderboard_identity(index)
        candidate_rows = (
            self.db.query(Evaluation)
            .filter(
                Evaluation.task_id == task.id,
                Evaluation.dataset_id == dataset.id,
            )
            .all()
        )
        rows_by_slug = {
            row.external_source_url.removeprefix(SOURCE_URL_PREFIX): row
            for row in candidate_rows
            if (row.external_source_url or "").startswith(SOURCE_URL_PREFIX)
        }
        entries_by_slug = {entry.slug: entry for entry in leaderboard.entries}
        papers = dict(discovery.papers)
        for row in candidate_rows:
            if not (row.methodology or "").startswith(MANAGED_METHODOLOGY_PREFIX):
                continue
            slug = (row.external_source_url or "").removeprefix(SOURCE_URL_PREFIX)
            entry = entries_by_slug.get(slug)
            if entry is None and slug in MODEL_SLUG_RENAMES:
                renamed_slug = MODEL_SLUG_RENAMES[slug]
                entry = entries_by_slug.get(renamed_slug)
                if entry is not None:
                    replacement = rows_by_slug.get(renamed_slug)
                    if replacement is not None:
                        # Retire only an owned duplicate of the same paper and
                        # metric. Manual rows and conflicting bindings need review.
                        if (
                            (replacement.methodology or "").startswith(
                                MANAGED_METHODOLOGY_PREFIX
                            )
                            and replacement.paper_id == row.paper_id
                            and replacement.best_metric == row.best_metric
                        ):
                            self.db.delete(row)
                            stats.retired += 1
                        continue
                    rows_by_slug[renamed_slug] = row
                    slug = renamed_slug
            if entry is None:
                # The index version is the Intelligence Index's; a new version
                # rescales every score, so unlisted older rows stop comparing.
                if index is INTELLIGENCE_INDEX and _stale_index_version(
                    row.methodology, index, leaderboard.index_version
                ):
                    self.db.delete(row)
                    stats.retired += 1
                continue
            if index.key not in entry.scores:
                self.db.delete(row)
                stats.retired += 1
            elif slug not in papers:
                # Preserve the already curated paper binding for managed rows.
                papers[slug] = row.paper_id
                selected.append(entry)
        stats.selected = len(selected)
        tagged_paper_ids: set[int] = set()
        for entry in selected:
            paper_id = papers.get(entry.slug)
            if paper_id is None:
                if commit:
                    raise RuntimeError(f"No reviewed paper resolved for {entry.slug}")
                stats.missing_papers.append(entry.slug)
                continue
            row = rows_by_slug.get(entry.slug)
            if row is None:
                row = Evaluation(
                    paper_id=paper_id,
                    task_id=task.id,
                    dataset_id=dataset.id,
                    model_name=entry.name,
                )
                self.db.add(row)
                stats.created += 1
            else:
                stats.updated += 1
            identity = MODEL_PAPER_IDENTITIES.get(entry.slug)
            release_alias = None
            if identity is None:
                release_alias = (
                    self.db.query(ModelProviderAlias)
                    .filter(
                        ModelProviderAlias.provider == "artificial-analysis",
                        ModelProviderAlias.alias == entry.slug,
                    )
                    .one_or_none()
                )
            release = (
                self.db.get(ModelRelease, release_alias.model_release_id)
                if release_alias is not None
                else None
            )
            source_url = f"{SOURCE_URL_PREFIX}{entry.slug}"
            row.paper_id = paper_id
            row.model_name = entry.name
            row.methodology = (
                f"{MANAGED_METHODOLOGY_PREFIX} Artificial Analysis Data API v2 "
                f"{index.label} {leaderboard.index_version}; fetched "
                f"{now.isoformat()}. Score is stored exactly as returned by the API."
            )
            row.metrics = {METRIC_NAME: entry.scores[index.key]}
            row.uses_additional_data = False
            row.is_open = (
                identity.is_open
                if identity is not None
                else release.is_open
                if release is not None
                else bool(row.is_open)
            )
            row.best_metric = METRIC_NAME
            row.evaluated_on = now.date()
            row.external_source_url = source_url
            row.source_url = source_url
            row.external = True
            row.updated_at = now
            # Several AA slugs can share a paper; the session does not autoflush.
            if (
                paper_id not in tagged_paper_ids
                and self.db.query(PaperTask)
                .filter(PaperTask.paper_id == paper_id, PaperTask.task_id == task.id)
                .first()
                is None
            ):
                self.db.add(
                    PaperTask(paper_id=paper_id, task_id=task.id, source="auto")
                )
            tagged_paper_ids.add(paper_id)
            stats.matched += 1
        self.db.flush()
        EvaluationService(self.db).recalculate_ranks(
            task.id, dataset.id, metric_name=METRIC_NAME, commit=False
        )
        return stats

    def sync(
        self,
        leaderboard: ArtificialAnalysisLeaderboard,
        *,
        discovery: ArtificialAnalysisDiscovery,
        fetched_at: datetime | None = None,
        commit: bool = True,
    ) -> ArtificialAnalysisSyncStats:
        now = fetched_at or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        stats = ArtificialAnalysisSyncStats(
            fetched=len(leaderboard.entries),
            indexed_papers=len(discovery.indexed_papers),
            missing_upstream=list(leaderboard.missing_reviewed),
        )
        try:
            for index in INDEXES:
                if index.key in leaderboard.withdrawn_indexes:
                    continue
                index_stats = self._sync_index(
                    index,
                    leaderboard,
                    discovery=discovery,
                    now=now,
                    commit=commit,
                )
                stats.indexes[index.key] = index_stats
                stats.selected += index_stats.selected
                stats.matched += index_stats.matched
                stats.created += index_stats.created
                stats.updated += index_stats.updated
                stats.retired += index_stats.retired
                stats.missing_papers.extend(index_stats.missing_papers)
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise


async def discover_artificial_analysis_papers(
    db: Session,
    *,
    persist: bool = True,
    leaderboard: ArtificialAnalysisLeaderboard | None = None,
) -> ArtificialAnalysisDiscovery:
    return await ArtificialAnalysisPaperDiscoveryService(db).discover(
        persist=persist, leaderboard=leaderboard
    )


def run_discovery(
    db: Session,
    *,
    persist: bool = True,
    leaderboard: ArtificialAnalysisLeaderboard | None = None,
):
    return asyncio.run(
        discover_artificial_analysis_papers(
            db, persist=persist, leaderboard=leaderboard
        )
    )
