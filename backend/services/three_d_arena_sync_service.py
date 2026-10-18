"""Synchronize the living 3D Arena leaderboard into evaluation rows."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    Metric,
    Paper,
    Task,
    TaskDatasetMetric,
)
from backend.services.evaluation_service import EvaluationService
from backend.services.leaderboard_sync_ownership import managed_methodology_prefix

ARENA_ENDPOINT = "https://3d-arena-3d-arena.hf.space/api/leaderboard?vote_type=render"
ARENA_SOURCE_URL = "https://huggingface.co/spaces/3d-arena/3d-arena"
DATASET_SLUG = "3d-arena-iso3d-living"
TASK_SLUG = "3d-generation"
METRIC_NAME = "Elo (live, external)"
MANAGED_METHODOLOGY_PREFIX = managed_methodology_prefix("3D Arena")
MIN_EXPECTED_ENTRIES = 15
MAX_EXPECTED_ENTRIES = 100
RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
MAX_FETCH_ATTEMPTS = 4
RETRY_BACKOFF_SECONDS = (2.0, 4.0, 8.0)
MAX_RETRY_AFTER_SECONDS = 30.0


# This deliberately exact manifest is the trust boundary between an upstream model
# label and a PwC paper. Product names without a defensible paper are left unmatched.
MODEL_PAPER_ARXIV_IDS: dict[str, str] = {
    "TRELLIS-3DGS": "2412.01506",
    "TRELLIS": "2412.01506",
    "Hunyuan3D-2": "2501.12202",
    "Hunyuan3D-2.1": "2506.15442",
    "InstantMesh": "2404.07191",
    "Pixal3D": "2605.10922",
    "SAM-3D-Objects-3DGS": "2511.16624",
    "Unique3D": "2405.20343",
    "SF3D": "2408.00653",
    "MeshFormer": "2408.10198",
    "Real3D": "2406.08479",
    "TRELLIS.2-4B": "2512.14692",
    "SPAR3D": "2501.04689",
    "TripoSR": "2403.02151",
    "LGM": "2402.05054",
    "3DTopia-XL": "2409.12957",
}


@dataclass(frozen=True)
class ArenaEntry:
    name: str
    rank: int
    score: int
    votes: int
    open_source: bool


@dataclass
class ArenaSyncStats:
    fetched: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    unmatched_models: list[str] = field(default_factory=list)
    missing_papers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetched": self.fetched,
            "matched": self.matched,
            "created": self.created,
            "updated": self.updated,
            "deleted": self.deleted,
            "unmatched_models": self.unmatched_models,
            "missing_papers": self.missing_papers,
        }


def parse_arena_leaderboard(payload: Any) -> list[ArenaEntry]:
    """Validate the public Space response before it can affect persisted rows."""
    if not isinstance(payload, list):
        raise TypeError("3D Arena response must be a JSON list")
    if not MIN_EXPECTED_ENTRIES <= len(payload) <= MAX_EXPECTED_ENTRIES:
        raise ValueError(
            f"3D Arena returned {len(payload)} rows; expected "
            f"{MIN_EXPECTED_ENTRIES}-{MAX_EXPECTED_ENTRIES}"
        )

    entries: list[ArenaEntry] = []
    names: set[str] = set()
    ranks: set[int] = set()
    for raw in payload:
        if not isinstance(raw, dict):
            raise TypeError("3D Arena rows must be JSON objects")
        name = raw.get("name")
        rank = raw.get("rank")
        score = raw.get("score")
        votes = raw.get("votes")
        open_source = raw.get("open_source")
        if not isinstance(name, str) or not name.strip() or len(name) > 255:
            raise ValueError("3D Arena row has an invalid model name")
        try:
            parsed_rank = int(rank)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"3D Arena rank is invalid for {name}") from exc
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise TypeError(f"3D Arena score is invalid for {name}")
        if isinstance(votes, bool) or not isinstance(votes, int):
            raise TypeError(f"3D Arena vote count is invalid for {name}")
        if not isinstance(open_source, bool):
            raise TypeError(f"3D Arena open-source flag is invalid for {name}")
        if name in names or parsed_rank in ranks:
            raise ValueError("3D Arena response contains duplicate names or ranks")
        if parsed_rank < 1 or not 0 < score < 10_000 or votes < 0:
            raise ValueError(f"3D Arena row is outside accepted bounds for {name}")
        names.add(name)
        ranks.add(parsed_rank)
        entries.append(
            ArenaEntry(
                name=name,
                rank=parsed_rank,
                score=int(score),
                votes=votes,
                open_source=open_source,
            )
        )

    if ranks != set(range(1, len(entries) + 1)):
        raise ValueError("3D Arena ranks must be contiguous and start at one")
    return sorted(entries, key=lambda entry: entry.rank)


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        try:
            delay = float(retry_after)
        except ValueError:
            delay = None
        else:
            if 0 < delay <= MAX_RETRY_AFTER_SECONDS:
                return delay
    if attempt < len(RETRY_BACKOFF_SECONDS):
        return RETRY_BACKOFF_SECONDS[attempt]
    return RETRY_BACKOFF_SECONDS[-1]


def fetch_arena_leaderboard(
    client: httpx.Client | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> list[ArenaEntry]:
    """Fetch the public JSON proxy exposed by the 3D Arena Space."""
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(20, connect=5),
        follow_redirects=False,
        headers={"User-Agent": "paperswithcode-3d-arena-sync/1.0"},
    )
    try:
        response: httpx.Response | None = None
        for attempt in range(MAX_FETCH_ATTEMPTS):
            response = active_client.get(ARENA_ENDPOINT)
            if (
                response.status_code in RETRYABLE_STATUS_CODES
                and attempt + 1 < MAX_FETCH_ATTEMPTS
            ):
                sleep(_retry_delay(response, attempt))
                continue
            response.raise_for_status()
            return parse_arena_leaderboard(response.json())
        assert response is not None
        response.raise_for_status()
        raise AssertionError("unreachable")
    finally:
        if owned_client:
            active_client.close()


class ThreeDArenaSyncService:
    """Replace only the evaluation rows owned by the 3D Arena live sync."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        metric = self.db.query(Metric).filter(Metric.name == METRIC_NAME).one_or_none()
        if task is None or dataset is None or metric is None:
            raise RuntimeError("3D Arena task, benchmark, or metric is not configured")
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
            raise RuntimeError("3D Arena leaderboard metric is not linked to the task")
        return task, dataset

    def sync(
        self,
        entries: list[ArenaEntry],
        *,
        fetched_at: datetime | None = None,
        commit: bool = True,
    ) -> ArenaSyncStats:
        if not entries:
            raise ValueError("Refusing to synchronize an empty 3D Arena leaderboard")
        now = fetched_at or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        stats = ArenaSyncStats(fetched=len(entries))

        try:
            task, dataset = self._leaderboard_identity()
            paper_ids_by_arxiv = {
                paper.arxiv_id: paper.id
                for paper in self.db.query(Paper)
                .filter(
                    Paper.arxiv_id.in_(set(MODEL_PAPER_ARXIV_IDS.values())),
                    Paper.is_latest_version,
                )
                .all()
            }
            managed_rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                    Evaluation.best_metric == METRIC_NAME,
                    Evaluation.methodology.like(f"{MANAGED_METHODOLOGY_PREFIX}%"),
                )
                .all()
            )
            managed_by_name: dict[str, Evaluation] = {}
            duplicate_rows: list[Evaluation] = []
            for row in managed_rows:
                existing = managed_by_name.get(row.model_name)
                if existing is None:
                    managed_by_name[row.model_name] = row
                    continue
                keep, discard = _preferred_managed_row(existing, row)
                managed_by_name[row.model_name] = keep
                duplicate_rows.append(discard)
            upstream_names = {entry.name for entry in entries}

            for entry in entries:
                arxiv_id = MODEL_PAPER_ARXIV_IDS.get(entry.name)
                if arxiv_id is None:
                    stats.unmatched_models.append(entry.name)
                    continue
                paper_id = paper_ids_by_arxiv.get(arxiv_id)
                if paper_id is None:
                    stats.missing_papers.append(f"{entry.name}:{arxiv_id}")
                    continue

                methodology = (
                    f"{MANAGED_METHODOLOGY_PREFIX} Upstream rank {entry.rank}; "
                    f"{entry.votes} votes; fetched {now.isoformat()}."
                )
                row = managed_by_name.get(entry.name)
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
                row.paper_id = paper_id
                row.methodology = methodology
                row.metrics = {METRIC_NAME: entry.score}
                row.uses_additional_data = False
                row.is_open = entry.open_source
                row.best_metric = METRIC_NAME
                row.evaluated_on = now.date()
                row.external_source_url = ARENA_SOURCE_URL
                row.source_url = ARENA_SOURCE_URL
                row.external = True
                row.updated_at = now
                stats.matched += 1

            # A successful, validated upstream response is authoritative for model
            # presence. Rows whose model disappeared are removed, while a current
            # but temporarily unresolved model is protected from deletion.
            # Duplicate leftovers (same model, stale source URL) are removed so
            # the canonical Space URL row is the only managed copy.
            skipped_duplicates = {id(row) for row in duplicate_rows}
            for row in duplicate_rows:
                self.db.delete(row)
                stats.deleted += 1
            for row in managed_rows:
                if id(row) in skipped_duplicates:
                    continue
                if row.model_name not in upstream_names:
                    self.db.delete(row)
                    stats.deleted += 1

            self.db.flush()
            EvaluationService(self.db).recalculate_ranks(
                task.id,
                dataset.id,
                metric_name=METRIC_NAME,
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


def _preferred_managed_row(
    existing: Evaluation, candidate: Evaluation
) -> tuple[Evaluation, Evaluation]:
    """Keep the canonical Space URL row when two managed copies exist."""
    if (
        existing.external_source_url != ARENA_SOURCE_URL
        and candidate.external_source_url == ARENA_SOURCE_URL
    ):
        return candidate, existing
    return existing, candidate
