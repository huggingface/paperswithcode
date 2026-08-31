"""Synchronize paper-linked Artificial Analysis text-to-speech quality scores."""

from __future__ import annotations

import asyncio
import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    Metric,
    PaperTask,
    Task,
    TaskDatasetMetric,
)
from backend.services.artificial_analysis_sync_service import (
    ArtificialAnalysisDiscovery,
    ArtificialAnalysisPaperDiscoveryService,
    PaperIdentity,
)
from backend.services.evaluation_service import EvaluationService

TTS_MODELS_URL = "https://artificialanalysis.ai/text-to-speech/models"
SOURCE_URL_PREFIX = f"{TTS_MODELS_URL}/"
TASK_SLUG = "text-to-speech"
DATASET_SLUG = "artificial-analysis-provider-voice-tts-arena"
METRIC_NAME = "Quality Elo"
MANAGED_METHODOLOGY_PREFIX = (
    "Managed by the Papers with Code Artificial Analysis TTS live sync."
)
MIN_EXPECTED_MODELS = 80
MAX_EXPECTED_MODELS = 200


# Only model-to-paper links reviewed against the Artificial Analysis catalog are
# published. Newly listed models remain absent until their canonical paper has
# been identified and added here.
MODEL_PAPER_IDENTITIES: dict[str, PaperIdentity] = {
    "fish-audio-s2-pro": PaperIdentity(arxiv_id="2603.08823", is_open=True),
    "luna-tts": PaperIdentity(arxiv_id="2608.11593"),
    "openvoice-v2": PaperIdentity(arxiv_id="2312.01479", is_open=True),
    "qwen3-tts-vc-realtime": PaperIdentity(arxiv_id="2601.15621"),
    "qwen3-tts-flash": PaperIdentity(arxiv_id="2601.15621"),
    "raon-speechlm": PaperIdentity(arxiv_id="2605.23912"),
    "st260629": PaperIdentity(arxiv_id="2605.23463"),
    "step-audio-editx-mar-2026": PaperIdentity(arxiv_id="2511.03601", is_open=True),
    "styletts-2": PaperIdentity(arxiv_id="2306.07691", is_open=True),
    "vibe-voice-1-5b": PaperIdentity(arxiv_id="2508.19205"),
    "vibe-voice-7b": PaperIdentity(arxiv_id="2508.19205", is_open=True),
    "voxtral-tts": PaperIdentity(arxiv_id="2603.25551", is_open=True),
    "wavenet": PaperIdentity(arxiv_id="1609.03499"),
    "xtts-v2": PaperIdentity(arxiv_id="2406.04904", is_open=True),
}


@dataclass(frozen=True)
class ArtificialAnalysisTtsEntry:
    slug: str
    name: str
    quality_elo: float
    is_open: bool


@dataclass
class ArtificialAnalysisTtsSyncStats:
    fetched: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    missing_papers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _next_payloads(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    chunks: list[str] = []
    prefix = "self.__next_f.push("
    for script in soup.find_all("script"):
        text = script.string or ""
        if not text.startswith(prefix) or not text.endswith(")"):
            continue
        try:
            payload = json.loads(text[len(prefix) : -1])
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Artificial Analysis TTS page has invalid Next data"
            ) from exc
        if (
            not isinstance(payload, list)
            or len(payload) < 2
            or not isinstance(payload[1], str)
        ):
            raise TypeError("Artificial Analysis TTS Next payload is malformed")
        chunks.append(payload[1])
    if not chunks:
        raise ValueError("Artificial Analysis TTS page has no Next data")
    return "".join(chunks)


def _model_objects(payload: str) -> dict[str, dict[str, Any]]:
    decoder = json.JSONDecoder()
    models: dict[str, dict[str, Any]] = {}
    position = 0
    marker = re.compile(r'"model"\s*:\s*(?=\{)')
    while True:
        match = marker.search(payload, position)
        if match is None:
            break
        try:
            model, end = decoder.raw_decode(payload, match.end())
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Artificial Analysis TTS page has an invalid model payload"
            ) from exc
        position = end
        if not isinstance(model, dict):
            raise TypeError("Artificial Analysis TTS model payload must be an object")
        slug = model.get("slug")
        url = model.get("url")
        if not isinstance(url, str) or not url.startswith("/text-to-speech/models/"):
            continue
        if not isinstance(slug, str) or not slug or len(slug) > 255:
            raise ValueError("Artificial Analysis TTS model has an invalid slug")
        if url != f"/text-to-speech/models/{slug}":
            raise ValueError(f"Artificial Analysis TTS URL is invalid for {slug}")
        previous = models.get(slug)
        if previous is not None and previous != model:
            raise ValueError(
                f"Artificial Analysis TTS has conflicting payloads for {slug}"
            )
        models[slug] = model
    return models


def parse_artificial_analysis_tts_leaderboard(
    html: str,
) -> list[ArtificialAnalysisTtsEntry]:
    if not isinstance(html, str) or not html.strip():
        raise TypeError("Artificial Analysis TTS response must be non-empty HTML")
    models = _model_objects(_next_payloads(html))
    if not MIN_EXPECTED_MODELS <= len(models) <= MAX_EXPECTED_MODELS:
        raise ValueError(
            f"Artificial Analysis TTS returned {len(models)} models; expected "
            f"{MIN_EXPECTED_MODELS}-{MAX_EXPECTED_MODELS}"
        )
    missing = sorted(set(MODEL_PAPER_IDENTITIES) - set(models))
    if missing:
        raise ValueError(
            f"Artificial Analysis TTS is missing reviewed models: {','.join(missing)}"
        )

    entries: list[ArtificialAnalysisTtsEntry] = []
    for slug, identity in MODEL_PAPER_IDENTITIES.items():
        model = models[slug]
        name = model.get("name")
        raw_score = model.get("qualityElo")
        is_open = model.get("isOpenWeights")
        if not isinstance(name, str) or not name or len(name) > 255:
            raise ValueError(f"Artificial Analysis TTS name is invalid for {slug}")
        if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
            raise TypeError(
                f"Artificial Analysis TTS Quality Elo is invalid for {slug}"
            )
        score = float(raw_score)
        if not math.isfinite(score) or not 0 <= score <= 3_000:
            raise ValueError(
                f"Artificial Analysis TTS Quality Elo is out of bounds for {slug}"
            )
        if is_open is not None and not isinstance(is_open, bool):
            raise TypeError(
                f"Artificial Analysis TTS open-weights flag is invalid for {slug}"
            )
        entries.append(ArtificialAnalysisTtsEntry(slug, name, score, identity.is_open))
    return entries


def fetch_artificial_analysis_tts_leaderboard(
    client: httpx.Client | None = None,
) -> list[ArtificialAnalysisTtsEntry]:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(30, connect=5),
        follow_redirects=True,
        headers={"User-Agent": "paperswithcode-artificial-analysis-tts-sync/1.0"},
    )
    try:
        response = active_client.get(TTS_MODELS_URL)
        response.raise_for_status()
        return parse_artificial_analysis_tts_leaderboard(response.text)
    finally:
        if owned_client:
            active_client.close()


class ArtificialAnalysisTtsSyncService:
    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        metric = self.db.query(Metric).filter(Metric.name == METRIC_NAME).one_or_none()
        if task is None or dataset is None or metric is None:
            raise RuntimeError(
                "Artificial Analysis TTS task, benchmark, or metric is not configured"
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
                "Artificial Analysis TTS metric is not linked to the task"
            )
        return task, dataset

    def sync(
        self,
        entries: list[ArtificialAnalysisTtsEntry],
        *,
        discovery: ArtificialAnalysisDiscovery,
        fetched_at: datetime | None = None,
        commit: bool = True,
    ) -> ArtificialAnalysisTtsSyncStats:
        if {entry.slug for entry in entries} != set(MODEL_PAPER_IDENTITIES):
            raise ValueError(
                "Refusing to synchronize an incomplete reviewed TTS model set"
            )
        now = fetched_at or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        stats = ArtificialAnalysisTtsSyncStats(fetched=len(entries))
        try:
            task, dataset = self._leaderboard_identity()
            rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                )
                .all()
            )
            rows_by_slug = {
                row.external_source_url.removeprefix(SOURCE_URL_PREFIX): row
                for row in rows
                if (row.external_source_url or "").startswith(SOURCE_URL_PREFIX)
                and (row.methodology or "").startswith(MANAGED_METHODOLOGY_PREFIX)
            }
            tagged_paper_ids = {
                paper_id
                for (paper_id,) in self.db.query(PaperTask.paper_id)
                .filter(PaperTask.task_id == task.id)
                .all()
            }
            for entry in entries:
                paper_id = discovery.papers.get(entry.slug)
                if paper_id is None:
                    if commit:
                        raise RuntimeError(
                            f"No reviewed paper resolved for {entry.slug}"
                        )
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
                source_url = f"{SOURCE_URL_PREFIX}{entry.slug}"
                row.paper_id = paper_id
                row.model_name = entry.name
                row.methodology = (
                    f"{MANAGED_METHODOLOGY_PREFIX} Provider Voice Arena Quality "
                    f"Elo; fetched {now.isoformat()}. Score is stored exactly as "
                    "published by Artificial Analysis."
                )
                row.metrics = {METRIC_NAME: entry.quality_elo}
                row.uses_additional_data = False
                row.is_open = entry.is_open
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


async def discover_artificial_analysis_tts_papers(
    db: Session, *, persist: bool = True
) -> ArtificialAnalysisDiscovery:
    return await ArtificialAnalysisPaperDiscoveryService(db).discover(
        persist=persist, identities=MODEL_PAPER_IDENTITIES
    )


def run_tts_discovery(db: Session, *, persist: bool = True):
    return asyncio.run(discover_artificial_analysis_tts_papers(db, persist=persist))
