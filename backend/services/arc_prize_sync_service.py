"""Synchronize paper-linked results from the three ARC Prize leaderboards."""

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

ARC_PRIZE_SOURCE_URL = "https://arcprize.org/leaderboard"
TASK_SLUG = "reasoning"
MANAGED_METHODOLOGY_PREFIX = "Managed by the Papers with Code ARC Prize live sync."
LEGACY_METHODOLOGY_PREFIX = "Strongest verified configuration for this paper/release"


@dataclass(frozen=True)
class VersionConfig:
    version: str
    endpoint: str
    upstream_dataset_id: str
    dataset_name: str
    dataset_slug: str
    metric_name: str
    min_entries: int
    max_entries: int


VERSION_CONFIGS: dict[str, VersionConfig] = {
    "v1": VersionConfig(
        version="v1",
        endpoint="https://arcprize.org/media/data/leaderboard/v1.json",
        upstream_dataset_id="v1_Semi_Private",
        dataset_name="ARC-AGI-1",
        dataset_slug="arc-agi",
        metric_name="Accuracy",
        min_entries=100,
        max_entries=400,
    ),
    "v2": VersionConfig(
        version="v2",
        endpoint="https://arcprize.org/media/data/leaderboard/v2.json",
        upstream_dataset_id="v2_Semi_Private",
        dataset_name="ARC-AGI-2",
        dataset_slug="arc-agi-2",
        metric_name="Accuracy",
        min_entries=100,
        max_entries=400,
    ),
    "v3": VersionConfig(
        version="v3",
        endpoint="https://arcprize.org/media/data/leaderboard/v3.json",
        upstream_dataset_id="v3_Semi_Private",
        dataset_name="ARC-AGI-3",
        dataset_slug="arc-agi-3",
        metric_name="RHAE",
        min_entries=5,
        max_entries=400,
    ),
}


@dataclass(frozen=True)
class PaperIdentity:
    arxiv_id: str | None = None
    source_url: str | None = None
    is_open: bool = False
    hf_model_url: str | None = None

    def __post_init__(self) -> None:
        if (self.arxiv_id is None) == (self.source_url is None):
            raise ValueError("PaperIdentity requires exactly one stable identity")

    @property
    def key(self) -> str:
        return (
            f"arxiv:{self.arxiv_id}" if self.arxiv_id else f"source:{self.source_url}"
        )


def _source(url: str, *, is_open: bool = False, hf: str | None = None) -> PaperIdentity:
    return PaperIdentity(source_url=url, is_open=is_open, hf_model_url=hf)


def _arxiv(
    arxiv_id: str, *, is_open: bool = True, hf: str | None = None
) -> PaperIdentity:
    return PaperIdentity(arxiv_id=arxiv_id, is_open=is_open, hf_model_url=hf)


# Exact upstream group/model IDs are the trust boundary between a display label
# and a canonical release paper. Unknown families remain visible in job warnings.
SELECTOR_PAPER_IDENTITIES: dict[str, PaperIdentity] = {
    "group:anthropic-claude-fable-5": _source(
        "https://www.anthropic.com/news/claude-fable-5-mythos-5"
    ),
    "group:google-gemini-3-1-pro-preview": _source(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-pro/"
    ),
    "model:gemini-3-1-pro-preview": _source(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-1-pro/"
    ),
    "group:openai-gpt-5-6-sol": _source("https://openai.com/index/gpt-5-6/"),
    "group:openai-gpt-5-6-terra": _source("https://openai.com/index/gpt-5-6/"),
    "group:openai-gpt-5-6-luna": _source("https://openai.com/index/gpt-5-6/"),
    "group:openai-gpt-5-6-luna-2026-07-30": _source(
        "https://openai.com/index/gpt-5-6/"
    ),
    "group:gpt-5-5-2026-04-22-thinking": _source(
        "https://openai.com/index/introducing-gpt-5-5/"
    ),
    "group:gpt-5-5-pro-2026-04-23-thinking": _source(
        "https://openai.com/index/introducing-gpt-5-5/"
    ),
    "group:openai-gpt-5-5-2026-04-23-thinking": _source(
        "https://openai.com/index/introducing-gpt-5-5/"
    ),
    "model:gemini_3_deep_think_022026": _source(
        "https://blog.google/products-and-platforms/products/gemini/gemini-3"
    ),
    "group:gemini-3-deep-think-preview": _source(
        "https://blog.google/products-and-platforms/products/gemini/gemini-3"
    ),
    "group:moonshot-kimi-k3": _arxiv(
        "2607.24653", hf="https://huggingface.co/moonshotai/Kimi-K3"
    ),
    "group:claude-opus-4-6-thinking": _source(
        "https://www.anthropic.com/news/claude-opus-4-6"
    ),
    "group:anthropic-opus-4-6-max-effort": _source(
        "https://www.anthropic.com/news/claude-opus-4-6"
    ),
    "group:claude-4-7": _source("https://www.anthropic.com/news/claude-opus-4-7"),
    "group:anthropic-opus-4-7": _source(
        "https://www.anthropic.com/news/claude-opus-4-7"
    ),
    "group:anthropic-opus-4-8": _source(
        "https://www.anthropic.com/news/claude-opus-4-8"
    ),
    "group:anthropic-claude-opus-5": _source(
        "https://www.anthropic.com/news/claude-opus-5"
    ),
    "group:gemini-3-5-flash": _source(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-5/"
    ),
    "group:gemini-3-5-flash-lite": _source(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/"
    ),
    "group:gemini-3-6-flash": _source(
        "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/"
    ),
    "group:deepseek-v4-flash-0731": _arxiv(
        "2606.19348", hf="https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731"
    ),
    "group:xai-grok-4-6": _source("https://x.ai/news/grok-4-6"),
    "group:xai-grok-4-5": _source("https://x.ai/news/grok-4-5"),
    "group:claude-sonnet-4-6": _source(
        "https://www.anthropic.com/news/claude-sonnet-4-6"
    ),
    "group:opus-4-5-thinking": _source(
        "https://www.anthropic.com/news/claude-opus-4-5"
    ),
    "model:thinky-inkling": _source(
        "https://thinkingmachines.ai/news/introducing-inkling/",
        is_open=True,
        hf="https://huggingface.co/thinkingmachines/inkling",
    ),
    "model:glm-5.2": _source(
        "https://z.ai/blog/glm-5.2",
        is_open=True,
        hf="https://huggingface.co/zai-org/GLM-5.2",
    ),
    "model:gpt-5-pro-2025-10-06": _arxiv("2601.03267", is_open=False),
    "model:kimi-k2.5": _arxiv(
        "2602.02276", hf="https://huggingface.co/moonshotai/Kimi-K2.5"
    ),
    "group:gpt-5-4-mini-reasoning": _source(
        "https://openai.com/index/introducing-gpt-5-4-mini-and-nano/"
    ),
    "group:gpt-5-4-nano-reasoning": _source(
        "https://openai.com/index/introducing-gpt-5-4-mini-and-nano/"
    ),
    "group:claude-sonnet-4-5-20250929": _source(
        "https://www.anthropic.com/news/claude-sonnet-4-5"
    ),
    "model:minimax-m2.5": _source(
        "https://huggingface.co/MiniMaxAI/MiniMax-M2.5",
        is_open=True,
        hf="https://huggingface.co/MiniMaxAI/MiniMax-M2.5",
    ),
    "group:o3": _source("https://openai.com/index/introducing-o3-and-o4-mini/"),
    "group:o3-pro": _source("https://openai.com/index/introducing-o3-and-o4-mini/"),
    "group:o4-mini": _source("https://openai.com/index/introducing-o3-and-o4-mini/"),
    "model:deepseek-v3.2": _arxiv("2512.02556"),
    "model:ARChitects": _arxiv("2412.04604"),
    "group:gemini-2-5-pro-2025-06-17-thinking": _arxiv("2507.06261", is_open=False),
    "group:claude-sonnet-4-20250514-thinking": _source(
        "https://www.anthropic.com/news/claude-4"
    ),
    "group:claude-opus-4-20250514-thinking": _source(
        "https://www.anthropic.com/news/claude-4"
    ),
    "model:trm-2025-10-07": _arxiv("2510.04871"),
    "group:Claude_3_7_thinking": _source(
        "https://www.anthropic.com/news/claude-3-7-sonnet"
    ),
    "model:NVARC_2025": _arxiv("2601.10904"),
    "model:R1": _arxiv(
        "2501.12948", hf="https://huggingface.co/deepseek-ai/DeepSeek-R1"
    ),
    "model:deepseek_r1_0528-openrouter": _arxiv(
        "2501.12948", hf="https://huggingface.co/deepseek-ai/DeepSeek-R1"
    ),
    "model:qwen3-235b-a22b-instruct-2507": _arxiv("2505.09388"),
    "model:magistral-medium-2506-thinking": _arxiv("2506.10910", is_open=False),
    "model:magistral-medium-2506-nonthinking": _arxiv("2506.10910", is_open=False),
    "group:Llama 4": _source(
        "https://ai.meta.com/blog/llama-4-multimodal-intelligence/", is_open=True
    ),
    "group:gpt-5-4": _source("https://openai.com/index/introducing-gpt-5-4/"),
    "group:gpt-5-4-pro": _source("https://openai.com/index/introducing-gpt-5-4/"),
    "group:openai-gpt-5-4-2026-03-05-thinking": _source(
        "https://openai.com/index/introducing-gpt-5-4/"
    ),
    "group:gpt-5-2-2025-12-11-thinking": _source(
        "https://openai.com/index/introducing-gpt-5-2/"
    ),
    "group:gpt-5-2-pro-2025-12-11-thinking": _source(
        "https://openai.com/index/introducing-gpt-5-2/"
    ),
    "group:thinky-inkling-small": _source(
        "https://huggingface.co/thinkingmachines/Inkling-Small",
        is_open=True,
        hf="https://huggingface.co/thinkingmachines/Inkling-Small",
    ),
}


@dataclass(frozen=True)
class ArcPrizeEntry:
    version: str
    model_id: str
    model_group: str | None
    model_name: str
    score: float
    results_url: str | None


@dataclass(frozen=True)
class ArcPrizeSnapshot:
    version: str
    generated_at: datetime
    entries: tuple[ArcPrizeEntry, ...]


@dataclass
class ArcPrizeSyncStats:
    fetched: int = 0
    selected: int = 0
    matched: int = 0
    created: int = 0
    adopted: int = 0
    updated: int = 0
    deleted: int = 0
    suppressed: int = 0
    unmatched_model_families: list[str] = field(default_factory=list)
    missing_papers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _required_text(raw: dict[str, Any], field_name: str) -> str:
    value = raw.get(field_name)
    if not isinstance(value, str) or not value.strip() or len(value) > 255:
        raise ValueError(f"ARC Prize row has an invalid {field_name}")
    return value


def parse_arc_prize_leaderboard(
    payload: Any, config: VersionConfig
) -> ArcPrizeSnapshot:
    """Strictly validate one public ARC Prize leaderboard response."""
    if not isinstance(payload, dict) or payload.get("version") != config.version:
        raise ValueError(f"ARC Prize response is not {config.version}")
    generated_raw = payload.get("generatedAt")
    if not isinstance(generated_raw, str):
        raise TypeError("ARC Prize response has no generatedAt timestamp")
    try:
        generated_at = datetime.fromisoformat(generated_raw)
    except ValueError as exc:
        raise ValueError("ARC Prize generatedAt timestamp is invalid") from exc
    if generated_at.tzinfo is None:
        raise ValueError("ARC Prize generatedAt timestamp must include a timezone")

    rows = payload.get("evaluations")
    if not isinstance(rows, list):
        raise TypeError("ARC Prize response must contain an evaluations list")
    if not config.min_entries <= len(rows) <= config.max_entries:
        raise ValueError(
            f"ARC Prize {config.version} returned {len(rows)} rows; expected "
            f"{config.min_entries}-{config.max_entries}"
        )

    entries: list[ArcPrizeEntry] = []
    model_ids: dict[str, tuple[Any, ...]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            raise TypeError("ARC Prize evaluations must be JSON objects")
        model_id = _required_text(raw, "modelId")
        model_name = _required_text(raw, "modelDisplayName")
        if raw.get("datasetId") != config.upstream_dataset_id:
            raise ValueError(f"ARC Prize datasetId is invalid for {model_id}")
        if raw.get("datasetDisplayName") != config.dataset_name:
            raise ValueError(f"ARC Prize datasetDisplayName is invalid for {model_id}")
        group = raw.get("modelGroup") or None
        if group is not None and (
            not isinstance(group, str) or not group.strip() or len(group) > 255
        ):
            raise ValueError(f"ARC Prize modelGroup is invalid for {model_id}")
        score_raw = raw.get("score")
        if isinstance(score_raw, bool) or not isinstance(score_raw, (int, float)):
            raise TypeError(f"ARC Prize score is invalid for {model_id}")
        score = float(score_raw)
        if not isfinite(score) or not 0 <= score <= 1:
            raise ValueError(f"ARC Prize score is outside 0-1 for {model_id}")
        if not isinstance(raw.get("display"), bool):
            raise TypeError(f"ARC Prize display flag is invalid for {model_id}")
        results_url = raw.get("resultsUrl") or None
        if results_url is not None and (
            not isinstance(results_url, str) or not results_url.startswith("/results/")
        ):
            raise ValueError(f"ARC Prize resultsUrl is invalid for {model_id}")
        signature = (group, model_name, score, results_url, raw["display"])
        previous = model_ids.get(model_id)
        if previous is not None:
            if previous == signature:
                continue
            raise ValueError(
                f"ARC Prize response contains conflicting duplicate modelId {model_id}"
            )
        model_ids[model_id] = signature
        if not raw["display"]:
            continue
        entries.append(
            ArcPrizeEntry(
                version=config.version,
                model_id=model_id,
                model_group=group,
                model_name=model_name,
                score=score * 100,
                results_url=results_url,
            )
        )
    return ArcPrizeSnapshot(
        config.version, generated_at.astimezone(UTC), tuple(entries)
    )


def fetch_arc_prize_leaderboards(
    client: httpx.Client | None = None,
) -> list[ArcPrizeSnapshot]:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(20, connect=5),
        follow_redirects=False,
        headers={"User-Agent": "paperswithcode-arc-prize-sync/1.0"},
    )
    try:
        snapshots = []
        for config in VERSION_CONFIGS.values():
            response = active_client.get(config.endpoint)
            response.raise_for_status()
            snapshots.append(parse_arc_prize_leaderboard(response.json(), config))
        return snapshots
    finally:
        if owned_client:
            active_client.close()


def _entry_identity(entry: ArcPrizeEntry) -> PaperIdentity | None:
    if entry.model_group:
        identity = SELECTOR_PAPER_IDENTITIES.get(f"group:{entry.model_group}")
        if identity:
            return identity
    return SELECTOR_PAPER_IDENTITIES.get(f"model:{entry.model_id}")


def _metric_value(row: Evaluation, metric_name: str) -> float | None:
    value = (row.metrics or {}).get(metric_name)
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


class ArcPrizeSyncService:
    """Upsert one strongest row per paper/release and ARC benchmark."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboards(self) -> tuple[Task, dict[str, tuple[Dataset, Metric]]]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        if task is None:
            raise RuntimeError("ARC Prize task is not configured")
        configured: dict[str, tuple[Dataset, Metric]] = {}
        for version, config in VERSION_CONFIGS.items():
            dataset = (
                self.db.query(Dataset)
                .filter(Dataset.slug == config.dataset_slug)
                .one_or_none()
            )
            metric = (
                self.db.query(Metric)
                .filter(Metric.name == config.metric_name)
                .one_or_none()
            )
            if dataset is None or metric is None:
                raise RuntimeError(
                    f"ARC Prize {version} benchmark or metric is not configured"
                )
            linked = (
                self.db.query(TaskDatasetMetric)
                .filter(
                    TaskDatasetMetric.task_id == task.id,
                    TaskDatasetMetric.dataset_id == dataset.id,
                    TaskDatasetMetric.metric_id == metric.id,
                )
                .one_or_none()
            )
            if linked is None:
                raise RuntimeError(
                    f"ARC Prize {version} metric is not linked to the task"
                )
            configured[version] = (dataset, metric)
        return task, configured

    def sync(
        self,
        snapshots: list[ArcPrizeSnapshot],
        *,
        fetched_at: datetime | None = None,
        commit: bool = True,
    ) -> ArcPrizeSyncStats:
        versions = {snapshot.version for snapshot in snapshots}
        if len(snapshots) != len(VERSION_CONFIGS) or versions != set(VERSION_CONFIGS):
            raise ValueError(
                "ARC Prize sync requires exactly one snapshot for v1, v2, and v3"
            )
        now = fetched_at or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        stats = ArcPrizeSyncStats(
            fetched=sum(len(snapshot.entries) for snapshot in snapshots)
        )

        try:
            task, leaderboards = self._leaderboards()
            selected: dict[
                tuple[str, str], tuple[ArcPrizeEntry, PaperIdentity, datetime]
            ] = {}
            unmatched: set[str] = set()
            for snapshot in snapshots:
                for entry in snapshot.entries:
                    identity = _entry_identity(entry)
                    if identity is None:
                        unmatched.add(entry.model_group or entry.model_id)
                        continue
                    key = (snapshot.version, identity.key)
                    current = selected.get(key)
                    if current is None or entry.score > current[0].score:
                        selected[key] = (entry, identity, snapshot.generated_at)
            stats.selected = len(selected)
            stats.unmatched_model_families = sorted(unmatched)

            identities = {identity for _, identity, _ in selected.values()}
            arxiv_ids = {
                identity.arxiv_id for identity in identities if identity.arxiv_id
            }
            source_urls = {
                identity.source_url for identity in identities if identity.source_url
            }
            papers_by_arxiv = {
                paper.arxiv_id: paper
                for paper in self.db.query(Paper)
                .filter(Paper.arxiv_id.in_(arxiv_ids), Paper.is_latest_version)
                .all()
            }
            papers_by_source = {
                paper.source_url: paper
                for paper in self.db.query(Paper)
                .filter(
                    Paper.source == "external",
                    Paper.source_url.in_(source_urls),
                    Paper.is_latest_version,
                )
                .all()
            }
            dataset_ids = [dataset.id for dataset, _ in leaderboards.values()]
            existing_rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id.in_(dataset_ids),
                )
                .all()
            )
            rows_by_paper_dataset: dict[tuple[int, int], list[Evaluation]] = {}
            managed_by_key: dict[tuple[int, str], Evaluation] = {}
            for row in existing_rows:
                rows_by_paper_dataset.setdefault(
                    (row.paper_id, row.dataset_id), []
                ).append(row)
                managed_identity = self._managed_identity(row.methodology)
                if managed_identity:
                    managed_by_key[(row.dataset_id, managed_identity)] = row

            active_keys: set[tuple[int, str]] = set()
            for (version, identity_key), (
                entry,
                identity,
                generated_at,
            ) in selected.items():
                dataset, metric = leaderboards[version]
                active_keys.add((dataset.id, identity_key))
                paper = (
                    papers_by_arxiv.get(identity.arxiv_id)
                    if identity.arxiv_id
                    else papers_by_source.get(identity.source_url)
                )
                managed = managed_by_key.get((dataset.id, identity_key))
                if paper is None:
                    stats.missing_papers.append(identity_key)
                    continue
                peers = rows_by_paper_dataset.get((paper.id, dataset.id), [])
                unmanaged = [
                    row
                    for row in peers
                    if row is not managed
                    and not (row.methodology or "").startswith(
                        MANAGED_METHODOLOGY_PREFIX
                    )
                    and row.best_metric == metric.name
                ]
                legacy_rows = [
                    row
                    for row in unmanaged
                    if (row.methodology or "").startswith(LEGACY_METHODOLOGY_PREFIX)
                ]
                independent_rows = [row for row in unmanaged if row not in legacy_rows]
                strongest_unmanaged = max(
                    (
                        (_metric_value(row, metric.name), row)
                        for row in independent_rows
                    ),
                    key=lambda pair: float("-inf") if pair[0] is None else pair[0],
                    default=(None, None),
                )
                if (
                    strongest_unmanaged[0] is not None
                    and strongest_unmanaged[0] >= entry.score
                ):
                    if managed is not None:
                        self.db.delete(managed)
                        stats.deleted += 1
                    stats.suppressed += 1
                    continue
                if managed is None:
                    legacy_value, legacy = max(
                        ((_metric_value(row, metric.name), row) for row in legacy_rows),
                        key=lambda pair: float("-inf") if pair[0] is None else pair[0],
                        default=(None, None),
                    )
                    if legacy_value is not None and legacy_value > entry.score:
                        stats.suppressed += 1
                        continue
                    if legacy is not None:
                        managed = legacy
                        stats.adopted += 1
                    else:
                        managed = Evaluation(
                            paper_id=paper.id,
                            task_id=task.id,
                            dataset_id=dataset.id,
                        )
                        self.db.add(managed)
                        rows_by_paper_dataset.setdefault(
                            (paper.id, dataset.id), []
                        ).append(managed)
                        stats.created += 1
                else:
                    stats.updated += 1

                result_url = (
                    f"https://arcprize.org{entry.results_url}"
                    if entry.results_url
                    else ARC_PRIZE_SOURCE_URL
                )
                managed.paper_id = paper.id
                managed.task_id = task.id
                managed.dataset_id = dataset.id
                managed.model_name = entry.model_name
                managed.harness = None
                managed.methodology = (
                    f"{MANAGED_METHODOLOGY_PREFIX} identity={identity_key}; version={version}; "
                    f"upstream_model_id={entry.model_id}; generated={generated_at.isoformat()}; "
                    f"fetched={now.isoformat()}. Strongest mapped configuration for this release."
                )
                managed.metrics = {metric.name: entry.score}
                managed.uses_additional_data = False
                managed.is_open = identity.is_open
                managed.best_metric = metric.name
                managed.evaluated_on = generated_at.date()
                managed.external_source_url = ARC_PRIZE_SOURCE_URL
                managed.source_url = result_url
                managed.external = True
                managed.hf_model_url = identity.hf_model_url
                managed.updated_at = now
                stats.matched += 1

            for (dataset_id, identity_key), row in managed_by_key.items():
                if (dataset_id, identity_key) not in active_keys:
                    self.db.delete(row)
                    stats.deleted += 1

            self.db.flush()
            for dataset, metric in leaderboards.values():
                EvaluationService(self.db).recalculate_ranks(
                    task.id, dataset.id, metric_name=metric.name, commit=False
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
    def _managed_identity(methodology: str | None) -> str | None:
        if not methodology or not methodology.startswith(MANAGED_METHODOLOGY_PREFIX):
            return None
        marker = " identity="
        start = methodology.find(marker)
        if start == -1:
            return None
        start += len(marker)
        end = methodology.find(";", start)
        return methodology[start:] if end == -1 else methodology[start:end]
