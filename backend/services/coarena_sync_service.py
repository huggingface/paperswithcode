"""Synchronize CoArena's living computer-use agent leaderboard."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
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

COARENA_ENDPOINT = "https://coarena.ai/api/leaderboard"
COARENA_SOURCE_URL = "https://coarena.ai/leaderboard"
DATASET_SLUG = "coarena"
TASK_SLUG = "computer-use-agents"
METRIC_NAME = "Elo (live, external)"
MANAGED_METHODOLOGY_PREFIX = "Managed by the Papers with Code CoArena live sync."
MIN_EXPECTED_ENTRIES = 5
MAX_EXPECTED_ENTRIES = 100
# Published CoArena statuses. `stable` is used for long-standing top models
# such as Fable 5; treating it as invalid aborted the hourly sync.
VALID_RATING_STATUSES = {"ranked", "provisional", "stable"}


@dataclass(frozen=True)
class PaperIdentity:
    arxiv_id: str | None = None
    source_url: str | None = None
    is_open: bool = False

    def __post_init__(self) -> None:
        if (self.arxiv_id is None) == (self.source_url is None):
            raise ValueError("PaperIdentity requires exactly one stable identity")


# Exact upstream IDs are the trust boundary between a product label and a paper.
# New models remain unmatched until their release identity has been reviewed.
MODEL_PAPER_IDENTITIES: dict[str, PaperIdentity] = {
    "fable-5": PaperIdentity(
        source_url="https://www.anthropic.com/news/claude-fable-5-mythos-5"
    ),
    "gemini-3-flash": PaperIdentity(
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/"
        )
    ),
    "opus-5": PaperIdentity(source_url="https://www.anthropic.com/news/claude-opus-5"),
    "gpt-5-6-sol": PaperIdentity(source_url="https://openai.com/index/gpt-5-6/"),
    "grok-4-6": PaperIdentity(source_url="https://x.ai/news/grok-4-6"),
    "qwen3p8-max": PaperIdentity(source_url="https://qwen.ai/blog?id=qwen3.8"),
    "gpt-5-6-terra": PaperIdentity(source_url="https://openai.com/index/gpt-5-6/"),
    "gemini-3-7-flash": PaperIdentity(
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/introducing-gemini-3-7-flash/"
        )
    ),
    "sonnet-5": PaperIdentity(
        source_url="https://www.anthropic.com/news/claude-sonnet-5"
    ),
    "gpt-5-6-luna": PaperIdentity(source_url="https://openai.com/index/gpt-5-6/"),
    "inkling": PaperIdentity(
        source_url="https://thinkingmachines.ai/news/introducing-inkling/",
        is_open=True,
    ),
    "haiku-4-5": PaperIdentity(source_url="https://www.anthropic.com/claude/haiku"),
    "kimi-k3": PaperIdentity(arxiv_id="2607.24653", is_open=True),
    "muse-spark-1-2-contributor": PaperIdentity(
        source_url="https://developer.meta.com/ai/resources/blog/build-with-muse-code/"
    ),
    "gemini-3-5-flash": PaperIdentity(
        source_url=(
            "https://blog.google/innovation-and-ai/models-and-research/"
            "gemini-models/gemini-3-5/"
        )
    ),
}


@dataclass(frozen=True)
class CoArenaEntry:
    id: str
    name: str
    model: str
    effort: str | None
    elo: float
    online_elo: float
    rating_basis: str
    rating_status: str
    win_rate: float
    ci: float
    company: str | None


@dataclass
class CoArenaSyncStats:
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


def _finite_number(value: Any, *, field_name: str, model_id: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"CoArena {field_name} is invalid for {model_id}")
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError(f"CoArena {field_name} is not finite for {model_id}")
    return parsed


def parse_coarena_leaderboard(payload: Any) -> list[CoArenaEntry]:
    """Validate the public response before it can affect persisted rows."""
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise TypeError("CoArena response must contain an entries list")
    rows = payload["entries"]
    if not MIN_EXPECTED_ENTRIES <= len(rows) <= MAX_EXPECTED_ENTRIES:
        raise ValueError(
            f"CoArena returned {len(rows)} rows; expected "
            f"{MIN_EXPECTED_ENTRIES}-{MAX_EXPECTED_ENTRIES}"
        )

    entries: list[CoArenaEntry] = []
    ids: set[str] = set()
    names: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise TypeError("CoArena entries must be JSON objects")
        model_id = raw.get("id")
        name = raw.get("name")
        model = raw.get("model")
        effort = raw.get("effort")
        company = raw.get("company")
        for field_name, value in (
            ("id", model_id),
            ("name", name),
            ("model", model),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > 255:
                raise ValueError(f"CoArena row has an invalid {field_name}")
        # Company is display metadata, and upstream may omit it for a rated
        # model. Stable IDs, ratings and paper mappings remain mandatory.
        if company is not None and (
            not isinstance(company, str) or not company.strip() or len(company) > 255
        ):
            raise ValueError("CoArena row has an invalid company")
        if model_id in ids or name in names:
            raise ValueError("CoArena response contains duplicate IDs or names")
        if effort is not None and (
            not isinstance(effort, str) or not effort.strip() or len(effort) > 32
        ):
            raise ValueError(f"CoArena effort is invalid for {model_id}")
        if raw.get("rated") is not True or raw.get("hasRuns") is not True:
            raise ValueError(f"CoArena published an unrated entry for {model_id}")
        rating_basis = raw.get("ratingBasis")
        rating_status = raw.get("ratingStatus")
        if rating_basis not in {"bradley_terry", "online_elo"}:
            raise ValueError(f"CoArena rating basis is invalid for {model_id}")
        if rating_status not in VALID_RATING_STATUSES:
            raise ValueError(f"CoArena rating status is invalid for {model_id}")

        elo = _finite_number(raw.get("elo"), field_name="elo", model_id=model_id)
        online_elo = _finite_number(
            raw.get("onlineElo"), field_name="onlineElo", model_id=model_id
        )
        win_rate = _finite_number(
            raw.get("winRate"), field_name="winRate", model_id=model_id
        )
        ci = _finite_number(raw.get("ci"), field_name="ci", model_id=model_id)
        if not 100 <= elo <= 3000 or not 100 <= online_elo <= 3000:
            raise ValueError(f"CoArena Elo is outside accepted bounds for {model_id}")
        if not 0 <= win_rate <= 1 or not 0 <= ci <= 1000:
            raise ValueError(f"CoArena statistics are invalid for {model_id}")

        ids.add(model_id)
        names.add(name)
        entries.append(
            CoArenaEntry(
                id=model_id,
                name=name,
                model=model,
                effort=effort,
                elo=elo,
                online_elo=online_elo,
                rating_basis=rating_basis,
                rating_status=rating_status,
                win_rate=win_rate,
                ci=ci,
                company=company,
            )
        )
    return entries


def fetch_coarena_leaderboard(
    client: httpx.Client | None = None,
) -> list[CoArenaEntry]:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(20, connect=5),
        follow_redirects=False,
        headers={"User-Agent": "paperswithcode-coarena-sync/1.0"},
    )
    try:
        response = active_client.get(COARENA_ENDPOINT)
        response.raise_for_status()
        return parse_coarena_leaderboard(response.json())
    finally:
        if owned_client:
            active_client.close()


class CoArenaSyncService:
    """Replace only evaluation rows owned by the CoArena live sync."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        metric = self.db.query(Metric).filter(Metric.name == METRIC_NAME).one_or_none()
        if task is None or dataset is None or metric is None:
            raise RuntimeError("CoArena task, benchmark, or metric is not configured")
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
            raise RuntimeError("CoArena leaderboard metric is not linked to the task")
        return task, dataset

    def sync(
        self,
        entries: list[CoArenaEntry],
        *,
        fetched_at: datetime | None = None,
        commit: bool = True,
    ) -> CoArenaSyncStats:
        if not entries:
            raise ValueError("Refusing to synchronize an empty CoArena leaderboard")
        now = fetched_at or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        stats = CoArenaSyncStats(fetched=len(entries))

        try:
            task, dataset = self._leaderboard_identity()
            arxiv_ids = {
                identity.arxiv_id
                for identity in MODEL_PAPER_IDENTITIES.values()
                if identity.arxiv_id
            }
            source_urls = {
                identity.source_url
                for identity in MODEL_PAPER_IDENTITIES.values()
                if identity.source_url
            }
            papers_by_arxiv = {
                paper.arxiv_id: paper.id
                for paper in self.db.query(Paper)
                .filter(Paper.arxiv_id.in_(arxiv_ids), Paper.is_latest_version)
                .all()
            }
            papers_by_source = {
                paper.source_url: paper.id
                for paper in self.db.query(Paper)
                .filter(
                    Paper.source == "external",
                    Paper.source_url.in_(source_urls),
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
                    Evaluation.external_source_url == COARENA_SOURCE_URL,
                    Evaluation.methodology.like(f"{MANAGED_METHODOLOGY_PREFIX}%"),
                )
                .all()
            )
            managed_by_key = {
                self._managed_model_id(row.methodology): row for row in managed_rows
            }
            upstream_ids = {entry.id for entry in entries}

            for entry in entries:
                identity = MODEL_PAPER_IDENTITIES.get(entry.id)
                if identity is None:
                    stats.unmatched_models.append(entry.id)
                    continue
                paper_id = (
                    papers_by_arxiv.get(identity.arxiv_id)
                    if identity.arxiv_id
                    else papers_by_source.get(identity.source_url)
                )
                if paper_id is None:
                    stats.missing_papers.append(
                        f"{entry.id}:{identity.arxiv_id or identity.source_url}"
                    )
                    continue

                methodology = (
                    f"{MANAGED_METHODOLOGY_PREFIX} upstream_id={entry.id}; "
                    f"basis={entry.rating_basis}; status={entry.rating_status}; "
                    f"95% CI ±{entry.ci:g}; win rate {entry.win_rate:.3f}; "
                    f"online Elo {entry.online_elo:.3f}; fetched {now.isoformat()}."
                )
                row = managed_by_key.get(entry.id)
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
                row.model_name = entry.name
                row.methodology = methodology
                row.metrics = {METRIC_NAME: entry.elo}
                row.uses_additional_data = False
                row.is_open = identity.is_open
                row.best_metric = METRIC_NAME
                row.evaluated_on = now.date()
                row.external_source_url = COARENA_SOURCE_URL
                row.source_url = COARENA_SOURCE_URL
                row.external = True
                row.updated_at = now
                stats.matched += 1

            for row in managed_rows:
                model_id = self._managed_model_id(row.methodology)
                if model_id and model_id not in upstream_ids:
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

    @staticmethod
    def _managed_model_id(methodology: str | None) -> str | None:
        if not methodology or not methodology.startswith(MANAGED_METHODOLOGY_PREFIX):
            return None
        marker = " upstream_id="
        start = methodology.find(marker)
        if start == -1:
            return None
        start += len(marker)
        end = methodology.find(";", start)
        return methodology[start:] if end == -1 else methodology[start:end]
