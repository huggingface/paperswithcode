"""Synchronize the Artificial Analysis Decision Index board.

The Data API has no Decision Index field, so the scores come from the
server-rendered evaluation page. Fetching it costs no API quota.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.models.database import Evaluation, PaperTask
from backend.services.artificial_analysis_sync_service import (
    ArtificialAnalysisDiscovery,
    ArtificialAnalysisPaperDiscoveryService,
    PaperIdentity,
    external,
)
from backend.services.artificial_analysis_tts_sync_service import next_payloads
from backend.services.evaluation_service import EvaluationService
from backend.services.leaderboard_model_matching_service import (
    LeaderboardModel,
    LeaderboardModelMatcher,
)
from backend.services.leaderboard_sync_catalog import resolve_leaderboard
from backend.services.leaderboard_sync_ownership import managed_methodology_prefix

DECISION_INDEX_URL = (
    "https://artificialanalysis.ai/evaluations/artificial-analysis-decision-index"
)
TASK_SLUG = "decision-making"
DATASET_SLUG = "artificial-analysis-decision-index"
METRIC_NAME = "Score"
# The board publishes the v2.1 headline index. Another version reweights the
# components, so it needs a review before its scores replace these.
INDEX_VERSION = "v2.1"
MANAGED_METHODOLOGY_PREFIX = managed_methodology_prefix(
    "Artificial Analysis Decision Index"
)
KIND_SOURCE_PREFIXES = {
    "decisionModel": "https://artificialanalysis.ai/decision-models/",
    "llm": "https://artificialanalysis.ai/models/",
}
MIN_EXPECTED_DECISION_MODELS = 10
MAX_EXPECTED_CONTESTANTS = 200
# Reasoning-effort settings of one language model; the board keeps the best.
_EFFORT_SUFFIX = re.compile(
    r"\s*\((?:max|xhigh|high|medium|low|minimal)\)\s*$", re.IGNORECASE
)

# Contestant slugs ("<host>_<model>") reviewed against their canonical paper.
# Other contestants bind through the model-release catalog or become radar
# signals until a paper exists.
DREX_REPORT = PaperIdentity(arxiv_id="2611.07854", is_open=True)
CLAUDE_HAIKU_5_5 = external(
    "https://www.anthropic.com/claude-haiku-5-5",
    "Introducing Claude Haiku 5.5",
    "2026-10-07",
)
GPT_6_LUNA = external(
    "https://openai.com/index/introducing-gpt-6-sol-and-luna/",
    "Introducing GPT-6 Sol and Luna",
    "2026-09-22",
)
MODEL_PAPER_IDENTITIES: dict[str, PaperIdentity] = {
    "anthropic_claude-haiku-5-5": CLAUDE_HAIKU_5_5,
    "anthropic_claude-haiku-5-5-low": CLAUDE_HAIKU_5_5,
    "google-ai-studio_gemini-decision-1": external(
        "https://blog.google/innovation-and-ai/technology/developers-tools/"
        "gemini-decisions-api/",
        "Gemini Decisions API: Fast, calibrated multimodal decisions",
        "2026-11-11",
    ),
    # Drex Max v1.1 is served by API only; v2.0 has public weights.
    "nace_drex-max-v1-1": PaperIdentity(arxiv_id="2611.07854"),
    "nace_drex-v2-0": DREX_REPORT,
    "openai_gpt-6-luna": GPT_6_LUNA,
    "openai_gpt-6-luna-low": GPT_6_LUNA,
}


@dataclass(frozen=True)
class DecisionIndexEntry:
    slug: str
    name: str
    kind: str
    lab: str
    score: float

    @property
    def source_url(self) -> str:
        # "nace_drex-max-v1-1" -> /decision-models/drex-max-v1-1
        return KIND_SOURCE_PREFIXES[self.kind] + self.slug.split("_", 1)[1]


@dataclass(frozen=True)
class DecisionIndexLeaderboard:
    version: str
    entries: list[DecisionIndexEntry]


@dataclass
class DecisionIndexSyncStats:
    fetched: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    retired: int = 0
    # Lower effort settings of a model already on the board.
    collapsed: list[str] = field(default_factory=list)
    # Names outside MODEL_PAPER_IDENTITIES that the catalog matched.
    auto_matched: list[str] = field(default_factory=list)
    # Names with no paper yet; each is a release signal for the radar.
    unreviewed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _index_version(payload: str) -> str:
    match = re.search(
        r'"slug":"artificial-analysis-decision-index","name":'
        r'"Artificial Analysis Decision Index (v[\w.]+)"',
        payload,
    )
    if match is None:
        raise ValueError("Artificial Analysis Decision Index version is missing")
    return match.group(1)


def _contestants(payload: str) -> list[Any]:
    starts = [m.end() for m in re.finditer(r'"contestants"\s*:\s*(?=\[)', payload)]
    if len(starts) != 1:
        raise ValueError(
            f"Artificial Analysis Decision Index has {len(starts)} contestant lists"
        )
    contestants, _ = json.JSONDecoder().raw_decode(payload, starts[0])
    return contestants


def _entry(raw: Any) -> DecisionIndexEntry:
    if not isinstance(raw, dict):
        raise TypeError("Artificial Analysis Decision Index contestant is malformed")
    slug, name, kind, lab = (
        raw.get(k) for k in ("slug", "name", "kind", "creatorName")
    )
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9-]+_[a-z0-9.-]+", slug):
        raise ValueError(f"Artificial Analysis Decision Index slug is invalid: {slug}")
    if kind not in KIND_SOURCE_PREFIXES:
        raise ValueError(f"Artificial Analysis Decision Index kind is invalid: {kind}")
    for value in (name, lab):
        if not isinstance(value, str) or not value.strip() or len(value) > 255:
            raise ValueError(f"Artificial Analysis Decision Index {slug} is unnamed")
    score = raw.get("indexScore")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise TypeError(f"Artificial Analysis Decision Index score is invalid: {slug}")
    if not math.isfinite(score) or not 0 <= score <= 100:
        raise ValueError(
            f"Artificial Analysis Decision Index score is out of bounds: {slug}"
        )
    return DecisionIndexEntry(slug, name.strip(), kind, lab.strip(), float(score))


def parse_decision_index_leaderboard(html: str) -> DecisionIndexLeaderboard:
    payload = next_payloads(html, "Artificial Analysis Decision Index")
    version = _index_version(payload)
    if version != INDEX_VERSION:
        raise ValueError(
            f"Artificial Analysis Decision Index is {version}, not {INDEX_VERSION}; "
            "review the new methodology before syncing"
        )
    entries = [_entry(raw) for raw in _contestants(payload)]
    if len({entry.slug for entry in entries}) != len(entries):
        raise ValueError("Artificial Analysis Decision Index repeats a contestant")
    decision_models = sum(1 for entry in entries if entry.kind == "decisionModel")
    if (
        decision_models < MIN_EXPECTED_DECISION_MODELS
        or len(entries) > MAX_EXPECTED_CONTESTANTS
    ):
        raise ValueError(
            f"Artificial Analysis Decision Index returned {decision_models} decision "
            f"models of {len(entries)} contestants"
        )
    missing = sorted(set(MODEL_PAPER_IDENTITIES) - {entry.slug for entry in entries})
    if missing:
        raise ValueError(
            "Artificial Analysis Decision Index is missing reviewed models: "
            + ",".join(missing)
        )
    return DecisionIndexLeaderboard(version, entries)


def fetch_decision_index_leaderboard(
    client: httpx.Client | None = None,
) -> DecisionIndexLeaderboard:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(30, connect=5),
        follow_redirects=True,
        headers={"User-Agent": "paperswithcode-artificial-analysis-sync/1.0"},
    )
    try:
        response = active_client.get(DECISION_INDEX_URL)
        response.raise_for_status()
        return parse_decision_index_leaderboard(response.text)
    finally:
        if owned_client:
            active_client.close()


class DecisionIndexSyncService:
    def __init__(self, db: Session):
        self.db = db

    def sync(
        self,
        leaderboard: DecisionIndexLeaderboard,
        *,
        discovery: ArtificialAnalysisDiscovery,
        fetched_at: datetime | None = None,
        commit: bool = True,
    ) -> DecisionIndexSyncStats:
        now = fetched_at or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        stats = DecisionIndexSyncStats(fetched=len(leaderboard.entries))
        try:
            task, dataset = resolve_leaderboard(
                self.db,
                "Artificial Analysis Decision Index",
                TASK_SLUG,
                DATASET_SLUG,
                (METRIC_NAME,),
            )
            rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                )
                .all()
            )
            managed = {
                row.external_source_url: row
                for row in rows
                if (row.methodology or "").startswith(MANAGED_METHODOLOGY_PREFIX)
            }
            # (paper id, is_open) per contestant slug
            bound: dict[str, tuple[int, bool]] = {}
            for entry in leaderboard.entries:
                if (identity := MODEL_PAPER_IDENTITIES.get(entry.slug)) is not None:
                    paper_id = discovery.papers.get(entry.slug)
                    if paper_id is None:
                        # A dry run does not index the reviewed paper.
                        if commit:
                            raise RuntimeError(
                                f"No reviewed paper resolved for {entry.slug}"
                            )
                        continue
                    bound[entry.slug] = (paper_id, identity.is_open)
            new_entries = [
                e for e in leaderboard.entries if e.slug not in MODEL_PAPER_IDENTITIES
            ]
            matcher = LeaderboardModelMatcher(
                self.db,
                provider="artificial-analysis-decision",
                leaderboard_name="Artificial Analysis Decision Index",
                leaderboard_url=DECISION_INDEX_URL,
            )
            matched = matcher.match(
                [LeaderboardModel(e.name, e.lab) for e in new_entries]
            )
            unmatched: list[LeaderboardModel] = []
            for entry in new_entries:
                if (match := matched.get(entry.name)) is not None:
                    bound[entry.slug] = (match.paper_id, match.is_open)
                    stats.auto_matched.append(entry.name)
                elif (row := managed.get(entry.source_url)) is not None:
                    # Keep the binding an earlier run matched.
                    bound[entry.slug] = (row.paper_id, bool(row.is_open))
                else:
                    stats.unreviewed.append(entry.name)
                    unmatched.append(LeaderboardModel(entry.name, entry.lab))
            matcher.report_unmatched(unmatched, now=now)

            # One row per model and paper: effort settings keep their best.
            best: dict[tuple[int, str], DecisionIndexEntry] = {}
            for entry in leaderboard.entries:
                if entry.slug not in bound:
                    continue
                key = (bound[entry.slug][0], _EFFORT_SUFFIX.sub("", entry.name))
                previous = best.get(key)
                if previous is None or entry.score > previous.score:
                    if previous is not None:
                        stats.collapsed.append(previous.name)
                    best[key] = entry
                else:
                    stats.collapsed.append(entry.name)
            selected = {entry.source_url: entry for entry in best.values()}

            # The page lists every scored contestant; owned rows it no longer
            # selects were withdrawn upstream or collapsed into a better setting.
            for source_url, row in managed.items():
                if source_url not in selected:
                    self.db.delete(row)
                    stats.retired += 1
            tagged_paper_ids = {
                paper_id
                for (paper_id,) in self.db.query(PaperTask.paper_id)
                .filter(PaperTask.task_id == task.id)
                .all()
            }
            for source_url, entry in selected.items():
                paper_id, is_open = bound[entry.slug]
                row = managed.get(source_url)
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
                row.methodology = (
                    f"{MANAGED_METHODOLOGY_PREFIX} Artificial Analysis Decision "
                    f"Index {leaderboard.version} headline score; fetched "
                    f"{now.isoformat()}. Score is stored exactly as published."
                )
                row.metrics = {METRIC_NAME: entry.score}
                row.uses_additional_data = False
                row.is_open = is_open
                row.best_metric = METRIC_NAME
                row.evaluated_on = now.date()
                row.external_source_url = source_url
                row.source_url = source_url
                row.external = True
                row.updated_at = now
                if paper_id not in tagged_paper_ids:
                    self.db.add(
                        PaperTask(paper_id=paper_id, task_id=task.id, source="auto")
                    )
                    tagged_paper_ids.add(paper_id)
                stats.matched += 1
            self.db.flush()
            EvaluationService(self.db).recalculate_ranks(
                task.id, dataset.id, metric_name=METRIC_NAME, commit=False
            )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise


def run_decision_discovery(
    db: Session, *, persist: bool = True
) -> ArtificialAnalysisDiscovery:
    return asyncio.run(
        ArtificialAnalysisPaperDiscoveryService(db).discover(
            persist=persist, identities=MODEL_PAPER_IDENTITIES
        )
    )
