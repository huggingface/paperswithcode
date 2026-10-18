"""Synchronize arXiv-backed MMTEB v2 scores from the official MTEB API."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    HfArtifact,
    Metric,
    Paper,
    PaperHfArtifact,
    Task,
    TaskDatasetMetric,
)
from backend.services.evaluation_service import EvaluationService
from backend.services.leaderboard_sync_ownership import managed_methodology_prefix

BENCHMARK_NAME = "MTEB(Multilingual, v2)"
MMTEB_API_URL = (
    "https://mteb-leaderboard-backend.hf.space/v1/benchmarks/"
    "MTEB%28Multilingual%2C%20v2%29/scores"
)
DATASET_SLUG = "mmteb-v2"
MIN_EXPECTED_ENTRIES = 100
MAX_EXPECTED_ENTRIES = 2_000
MIN_SCORED_ENTRIES = {
    "overall": 25,
    "retrieval": 50,
    "reranking": 50,
}
MIN_RESOLVED_ENTRIES = {
    "overall": 10,
    "retrieval": 20,
    "reranking": 20,
}
MANAGED_METHODOLOGY_PREFIX = managed_methodology_prefix("MMTEB v2")
LEGACY_METHODOLOGY_PREFIX = (
    "Official MTEB leaderboard external evaluation for MTEB(Multilingual, v2):"
)

_ARXIV_PATTERNS = (
    re.compile(
        r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})(?:v[0-9]+)?", re.IGNORECASE
    ),
    re.compile(
        r"\beprint\s*=\s*[{'\"]*\s*([0-9]{4}\.[0-9]{4,5})",
        re.IGNORECASE,
    ),
    re.compile(r"\barXiv\s*:\s*([0-9]{4}\.[0-9]{4,5})", re.IGNORECASE),
)


@dataclass(frozen=True)
class MmtebLane:
    task_slug: str
    metric_name: str
    api_score_key: str | None
    api_score_label: str


LANES: dict[str, MmtebLane] = {
    "overall": MmtebLane(
        task_slug="embedding-models",
        metric_name="MMTEB Score",
        api_score_key=None,
        api_score_label="meanTask",
    ),
    "retrieval": MmtebLane(
        task_slug="retrieval",
        metric_name="Retrieval",
        api_score_key="Retrieval",
        api_score_label='scoresByTaskType["Retrieval"]',
    ),
    "reranking": MmtebLane(
        task_slug="text-reranking",
        metric_name="Rerank",
        api_score_key="Reranking",
        api_score_label='scoresByTaskType["Reranking"]',
    ),
}


@dataclass(frozen=True)
class MmtebEntry:
    model_name: str
    model_url: str
    api_rank: int
    mean_task: float | None
    scores_by_task_type: dict[str, float]
    arxiv_ids: tuple[str, ...]
    total_params: int | None
    is_open: bool
    hf_model_url: str | None

    def score_for(self, lane: MmtebLane) -> float | None:
        raw = (
            self.mean_task
            if lane.api_score_key is None
            else self.scores_by_task_type.get(lane.api_score_key)
        )
        return None if raw is None else raw * 100


@dataclass
class MmtebSyncStats:
    fetched: int = 0
    scored: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    no_arxiv_models: list[str] = field(default_factory=list)
    missing_papers: list[str] = field(default_factory=list)
    ambiguous_papers: list[str] = field(default_factory=list)
    unmanaged_conflicts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetched": self.fetched,
            "scored": self.scored,
            "matched": self.matched,
            "created": self.created,
            "updated": self.updated,
            "deleted": self.deleted,
            "no_arxiv_models": self.no_arxiv_models,
            "missing_papers": self.missing_papers,
            "ambiguous_papers": self.ambiguous_papers,
            "unmanaged_conflicts": self.unmanaged_conflicts,
        }


def _optional_score(value: Any, *, field_name: str, model_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError(f"MMTEB {field_name} is invalid for {model_name}")
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"MMTEB {field_name} is invalid for {model_name}") from exc
    if not isfinite(score) or not -1 <= score <= 1:
        raise ValueError(f"MMTEB {field_name} is out of bounds for {model_name}")
    return score


def _arxiv_ids(citation: Any) -> tuple[str, ...]:
    if not isinstance(citation, str):
        return ()
    ids: set[str] = set()
    for pattern in _ARXIV_PATTERNS:
        ids.update(pattern.findall(citation))
    return tuple(sorted(ids))


def _official_hf_model_url(model_name: str, model_url: Any) -> str | None:
    if not isinstance(model_url, str):
        return None
    parsed = urlsplit(model_url.rstrip("/"))
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower() != "huggingface.co" or len(parts) != 2:
        return None
    if "/".join(parts).lower() != model_name.lower():
        return None
    return f"https://huggingface.co/{'/'.join(parts)}"


def parse_mmteb_leaderboard(payload: Any) -> list[MmtebEntry]:
    """Strictly parse the official MTEB v2 benchmark summary response."""
    if not isinstance(payload, dict):
        raise TypeError("MMTEB API payload must be an object")
    if payload.get("benchmarkName") != BENCHMARK_NAME:
        raise ValueError(
            "MMTEB API benchmark name does not match the configured source"
        )
    task_types = payload.get("taskTypes")
    if not isinstance(task_types, list) or not {"Retrieval", "Reranking"}.issubset(
        task_types
    ):
        raise ValueError("MMTEB API task types do not include retrieval and reranking")
    aggregations = payload.get("aggregations")
    if not isinstance(aggregations, list) or not {
        "mean_task",
        "task_types",
    }.issubset(aggregations):
        raise ValueError("MMTEB API aggregations do not match the published contract")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise TypeError("MMTEB API rows must be a list")
    if not MIN_EXPECTED_ENTRIES <= len(rows) <= MAX_EXPECTED_ENTRIES:
        raise ValueError(
            f"MMTEB API returned {len(rows)} rows; expected at least "
            f"{MIN_EXPECTED_ENTRIES} and at most {MAX_EXPECTED_ENTRIES}"
        )

    entries: list[MmtebEntry] = []
    names: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("model"), dict):
            raise TypeError("MMTEB API rows must contain model objects")
        model = row["model"]
        canonical_name = model.get("name")
        if not isinstance(canonical_name, str) or not canonical_name.strip():
            raise ValueError("MMTEB API model names must be non-empty strings")
        model_name = canonical_name.rstrip("/").rsplit("/", 1)[-1]
        if len(model_name) > 255 or model_name in names:
            raise ValueError("MMTEB model names must be unique and at most 255 chars")
        names.add(model_name)

        try:
            api_rank = int(row["rank"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"MMTEB API rank is invalid for {model_name}") from exc
        if api_rank < 1:
            raise ValueError(f"MMTEB API rank is invalid for {model_name}")

        scores_raw = row.get("scoresByTaskType")
        if not isinstance(scores_raw, dict):
            raise TypeError(f"MMTEB task-type scores are invalid for {model_name}")
        scores: dict[str, float] = {}
        for key in ("Retrieval", "Reranking"):
            score = _optional_score(
                scores_raw.get(key),
                field_name=f"{key} score",
                model_name=model_name,
            )
            if score is not None:
                scores[key] = score

        total_params_b = model.get("totalParamsB")
        total_params: int | None = None
        if total_params_b is not None:
            if isinstance(total_params_b, bool):
                raise TypeError(f"MMTEB parameter count is invalid for {model_name}")
            try:
                params_b = float(total_params_b)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"MMTEB parameter count is invalid for {model_name}"
                ) from exc
            if not isfinite(params_b) or not 0 <= params_b < 9_000_000_000:
                raise ValueError(
                    f"MMTEB parameter count is out of bounds for {model_name}"
                )
            total_params = round(params_b * 1_000_000_000)

        open_weights = model.get("openWeights")
        if not isinstance(open_weights, bool):
            raise TypeError(f"MMTEB openWeights is invalid for {model_name}")
        model_url = model.get("url") if isinstance(model.get("url"), str) else ""
        entries.append(
            MmtebEntry(
                model_name=model_name,
                model_url=model_url,
                api_rank=api_rank,
                mean_task=_optional_score(
                    row.get("meanTask"),
                    field_name="meanTask",
                    model_name=model_name,
                ),
                scores_by_task_type=scores,
                arxiv_ids=_arxiv_ids(model.get("citation")),
                total_params=total_params,
                is_open=open_weights,
                hf_model_url=_official_hf_model_url(canonical_name, model_url),
            )
        )
    return entries


def fetch_mmteb_leaderboard(
    client: httpx.Client | None = None,
) -> list[MmtebEntry]:
    """Fetch the official pre-aggregated MMTEB v2 summary API."""
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(60, connect=10),
        follow_redirects=True,
        headers={"User-Agent": "paperswithcode-mmteb-sync/1.0"},
    )
    try:
        response = active_client.get(MMTEB_API_URL)
        response.raise_for_status()
        return parse_mmteb_leaderboard(response.json())
    finally:
        if owned_client:
            active_client.close()


def _hf_repo_id(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlsplit(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.lower() != "huggingface.co" or len(parts) != 2:
        return None
    return "/".join(parts)


class MmtebSyncService:
    """Replace one task-specific MMTEB lane with arXiv-backed API rows."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self, lane: MmtebLane) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == lane.task_slug).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        metric = (
            self.db.query(Metric).filter(Metric.name == lane.metric_name).one_or_none()
        )
        if task is None or dataset is None or metric is None:
            raise RuntimeError(
                f"MMTEB {lane.task_slug} task, benchmark, or metric is not configured"
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
                f"MMTEB {lane.metric_name} metric is not linked to {lane.task_slug}"
            )
        return task, dataset

    def _resolve_papers(
        self,
        entries: list[MmtebEntry],
        stats: MmtebSyncStats,
    ) -> dict[str, Paper]:
        all_ids = {arxiv_id for entry in entries for arxiv_id in entry.arxiv_ids}
        papers = (
            self.db.query(Paper)
            .filter(Paper.arxiv_id.in_(all_ids), Paper.is_latest_version)
            .all()
            if all_ids
            else []
        )
        papers_by_arxiv = {paper.arxiv_id: paper for paper in papers}
        paper_ids = {paper.id for paper in papers}
        repo_ids = {
            repo_id
            for entry in entries
            if (repo_id := _hf_repo_id(entry.hf_model_url)) is not None
        }
        artifact_links: dict[str, set[int]] = {repo_id: set() for repo_id in repo_ids}
        if repo_ids and paper_ids:
            for paper_id, repo_id in (
                self.db.query(PaperHfArtifact.paper_id, HfArtifact.repo_id)
                .join(HfArtifact, HfArtifact.id == PaperHfArtifact.hf_artifact_id)
                .filter(
                    PaperHfArtifact.paper_id.in_(paper_ids),
                    HfArtifact.repo_id.in_(repo_ids),
                )
                .all()
            ):
                artifact_links[repo_id].add(paper_id)

        resolved: dict[str, Paper] = {}
        for entry in entries:
            if not entry.arxiv_ids:
                stats.no_arxiv_models.append(entry.model_name)
                continue
            candidates = [
                papers_by_arxiv[arxiv_id]
                for arxiv_id in entry.arxiv_ids
                if arxiv_id in papers_by_arxiv
            ]
            if not candidates:
                stats.missing_papers.append(
                    f"{entry.model_name}:{','.join(entry.arxiv_ids)}"
                )
                continue
            if len(candidates) == 1:
                resolved[entry.model_name] = candidates[0]
                continue

            model_url = entry.hf_model_url
            repo_id = _hf_repo_id(model_url)
            linked_ids = artifact_links.get(repo_id or "", set())
            linked = [paper for paper in candidates if paper.id in linked_ids]
            if model_url:
                linked.extend(
                    paper
                    for paper in candidates
                    if model_url in (paper.hf_models or []) and paper not in linked
                )
            if len(linked) == 1:
                resolved[entry.model_name] = linked[0]
            else:
                stats.ambiguous_papers.append(
                    f"{entry.model_name}:{','.join(entry.arxiv_ids)}"
                )
        return resolved

    @staticmethod
    def _validate_lane_coverage(
        *,
        lane_id: str,
        fetched: int,
        scored: int,
        resolved: int,
        existing_managed: int,
    ) -> None:
        if fetched < MIN_EXPECTED_ENTRIES:
            return
        if scored < MIN_SCORED_ENTRIES[lane_id]:
            raise RuntimeError(
                f"MMTEB {lane_id} returned only {scored} scored rows; refusing "
                "to replace the managed leaderboard"
            )
        if resolved < MIN_RESOLVED_ENTRIES[lane_id]:
            raise RuntimeError(
                f"MMTEB {lane_id} resolved only {resolved} arXiv-backed rows; "
                "refusing to replace the managed leaderboard"
            )
        if existing_managed and resolved * 2 < existing_managed:
            raise RuntimeError(
                f"MMTEB {lane_id} resolved {resolved} rows versus "
                f"{existing_managed} managed rows; refusing a drop over 50%"
            )

    def sync(
        self,
        entries: list[MmtebEntry],
        *,
        lane_id: str,
        fetched_at: datetime | None = None,
        commit: bool = True,
    ) -> MmtebSyncStats:
        if not entries:
            raise ValueError("Refusing to synchronize an empty MMTEB leaderboard")
        try:
            lane = LANES[lane_id]
        except KeyError as exc:
            raise ValueError(f"Unknown MMTEB lane: {lane_id}") from exc
        now = fetched_at or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        stats = MmtebSyncStats(fetched=len(entries))

        try:
            task, dataset = self._leaderboard_identity(lane)
            scored_entries = [
                entry for entry in entries if entry.score_for(lane) is not None
            ]
            stats.scored = len(scored_entries)
            papers_by_model = self._resolve_papers(scored_entries, stats)
            managed_rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                    Evaluation.best_metric == lane.metric_name,
                    or_(
                        Evaluation.methodology.like(f"{MANAGED_METHODOLOGY_PREFIX}%"),
                        Evaluation.methodology.like(f"{LEGACY_METHODOLOGY_PREFIX}%"),
                    ),
                )
                .all()
            )
            managed_by_name = {row.model_name: row for row in managed_rows}
            self._validate_lane_coverage(
                lane_id=lane_id,
                fetched=len(entries),
                scored=len(scored_entries),
                resolved=len(papers_by_model),
                existing_managed=len(managed_rows),
            )
            managed_ids = {row.id for row in managed_rows}
            unmanaged_names = {
                model_name
                for row_id, model_name in (
                    self.db.query(Evaluation.id, Evaluation.model_name)
                    .filter(
                        Evaluation.task_id == task.id,
                        Evaluation.dataset_id == dataset.id,
                        Evaluation.best_metric == lane.metric_name,
                    )
                    .all()
                )
                if row_id not in managed_ids
            }
            current_names = set(papers_by_model)

            for entry in scored_entries:
                paper = papers_by_model.get(entry.model_name)
                if paper is None:
                    continue
                if (
                    entry.model_name in unmanaged_names
                    and entry.model_name not in managed_by_name
                ):
                    stats.unmanaged_conflicts.append(entry.model_name)
                    continue
                score = entry.score_for(lane)
                assert score is not None
                methodology = (
                    f"{MANAGED_METHODOLOGY_PREFIX} {BENCHMARK_NAME} "
                    f"{lane.api_score_label} × 100; official API Borda rank "
                    f"{entry.api_rank}; fetched {now.isoformat()}. Only models with "
                    "an unambiguous local arXiv paper are synchronized."
                )
                row = managed_by_name.get(entry.model_name)
                if row is None:
                    row = Evaluation(
                        paper_id=paper.id,
                        task_id=task.id,
                        dataset_id=dataset.id,
                        model_name=entry.model_name,
                    )
                    self.db.add(row)
                    stats.created += 1
                else:
                    stats.updated += 1
                row.paper_id = paper.id
                row.methodology = methodology
                row.metrics = {lane.metric_name: score}
                row.best_metric = lane.metric_name
                row.uses_additional_data = False
                row.is_open = entry.is_open
                row.num_parameters = entry.total_params
                row.hf_model_url = entry.hf_model_url
                row.evaluated_on = now.date()
                row.external_source_url = MMTEB_API_URL
                row.source_url = MMTEB_API_URL
                row.external = True
                row.updated_at = now
                if entry.hf_model_url:
                    hf_models = list(paper.hf_models or [])
                    if entry.hf_model_url not in hf_models:
                        hf_models.append(entry.hf_model_url)
                        paper.hf_models = hf_models
                stats.matched += 1

            for row in managed_rows:
                if row.model_name not in current_names:
                    self.db.delete(row)
                    stats.deleted += 1

            self.db.flush()
            EvaluationService(self.db).recalculate_ranks(
                task.id,
                dataset.id,
                metric_name=lane.metric_name,
                commit=False,
            )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise
