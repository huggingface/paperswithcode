"""Synchronize the living Open TTS Leaderboard into evaluation rows."""

from __future__ import annotations

import asyncio
import html
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from gradio_client import Client
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
    external,
)
from backend.services.evaluation_service import EvaluationService

SPACE_APP_URL = "https://hf-audio-open-tts-leaderboard.hf.space"
SPACE_SOURCE_URL = "https://huggingface.co/spaces/hf-audio/open_tts_leaderboard"
DEFAULT_LANGUAGE = "🇬🇧 English"
DEFAULT_DATASETS = ["Seed-TTS", "CV3-Eval"]
MIN_EXPECTED_ENTRIES = 15
MAX_EXPECTED_ENTRIES = 100
DATASET_SLUG = "open-tts-leaderboard"
TASK_SLUG = "text-to-speech"
WER_METRIC = "WER"
RTFX_METRIC = "RTFx"
MANAGED_METHODOLOGY_PREFIX = "Managed by the Papers with Code Open TTS live sync."

_MODEL_LINK_RE = re.compile(
    r'<a\b[^>]*\bhref=["\']https://huggingface\.co/([^"\'?#]+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


# Reviewed against the model cards linked by the default leaderboard on
# 2026-09-11. A release page is used when a model has no dedicated paper;
# architecture or evaluation papers are not substituted for model provenance.
MODEL_PAPER_IDENTITIES: dict[str, PaperIdentity] = {
    "microsoft/VibeVoice-Realtime-0.5B": PaperIdentity(
        arxiv_id="2508.19205", is_open=True
    ),
    "hexgrad/Kokoro-82M": external(
        "https://huggingface.co/hexgrad/Kokoro-82M",
        "Kokoro-82M",
        "2025-01-27",
        is_open=True,
    ),
    "Supertone/supertonic-3": external(
        "https://huggingface.co/Supertone/supertonic-3",
        "Supertonic 3",
        "2026-05-06",
        is_open=True,
    ),
    "fishaudio/s2-pro": PaperIdentity(arxiv_id="2603.08823", is_open=True),
    "k2-fsa/OmniVoice": PaperIdentity(arxiv_id="2604.00688", is_open=True),
    "kyutai/pocket-tts": PaperIdentity(arxiv_id="2509.06926", is_open=True),
    "FunAudioLLM/Fun-CosyVoice3-0.5B-2512": PaperIdentity(
        arxiv_id="2505.17589", is_open=True
    ),
    "ResembleAI/chatterbox": external(
        "https://huggingface.co/ResembleAI/chatterbox",
        "Chatterbox",
        "2025-04-24",
        is_open=True,
    ),
    "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice": PaperIdentity(
        arxiv_id="2601.15621", is_open=True
    ),
    "BreezeBlue/Breeze-TTS-2": external(
        "https://huggingface.co/BreezeBlue/Breeze-TTS-2",
        "Breeze TTS 2",
        "2026-08-25",
        is_open=True,
    ),
    "nvidia/magpie_tts_multilingual_357m": external(
        "https://huggingface.co/nvidia/magpie_tts_multilingual_357m",
        "MagpieTTS Multilingual 357M",
        "2025-12-11",
        is_open=True,
    ),
    "facebook/seamless-m4t-v2-large": PaperIdentity(
        arxiv_id="2312.05187", is_open=True
    ),
    "owensong/Inflect-Micro-v2": external(
        "https://huggingface.co/owensong/Inflect-Micro-v2",
        "Inflect-Micro-v2: Complete Local Text-to-Waveform TTS Under 10M Parameters",
        "2026-06-25",
        is_open=True,
    ),
    "bosonai/higgs-tts-2-3b-base": external(
        "https://huggingface.co/bosonai/higgs-tts-2-3b-base",
        "Higgs TTS 2: Redefining Expressiveness in Audio Generation",
        "2025-07-01",
        is_open=True,
    ),
    "microsoft/speecht5_tts": PaperIdentity(arxiv_id="2110.07205", is_open=True),
    "OpenMOSS-Team/MOSS-TTS": PaperIdentity(arxiv_id="2603.18090", is_open=True),
    "Qwen/Qwen3-Omni-30B-A3B-Instruct": PaperIdentity(
        arxiv_id="2509.17765", is_open=True
    ),
    "mistralai/Voxtral-4B-TTS-2603": PaperIdentity(arxiv_id="2603.25551", is_open=True),
    "bosonai/higgs-tts-3-4b": external(
        "https://huggingface.co/bosonai/higgs-tts-3-4b",
        "Higgs TTS 3: Conversational Speech for Voice AI from Boson AI",
        "2026-06-04",
        is_open=True,
    ),
    "openbmb/VoxCPM2": external(
        "https://huggingface.co/openbmb/VoxCPM2",
        "VoxCPM2: Tokenizer-Free TTS for Multilingual Speech Generation, Creative Voice Design, and True-to-Life Cloning",
        "2026-04-03",
        is_open=True,
    ),
    "neuphonic/neutts-nano": external(
        "https://huggingface.co/neuphonic/neutts-nano",
        "NeuTTS Nano",
        "2025-11-18",
        is_open=True,
    ),
    "neuphonic/neutts-nano-q8-gguf": external(
        "https://huggingface.co/neuphonic/neutts-nano",
        "NeuTTS Nano",
        "2025-11-18",
        is_open=True,
    ),
    "sesame/csm-1b": external(
        "https://huggingface.co/sesame/csm-1b",
        "CSM-1B",
        "2025-03-06",
        is_open=True,
    ),
    "owensong/Inflect-Nano-v1": external(
        "https://huggingface.co/owensong/Inflect-Nano-v1",
        "Inflect-Nano-v1",
        "2026-06-16",
        is_open=True,
    ),
}


@dataclass(frozen=True)
class OpenTtsEntry:
    model_id: str
    model_name: str
    rank: int
    wer: float
    rtfx: float
    is_open: bool


@dataclass
class OpenTtsSyncStats:
    fetched: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    missing_papers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _number(value: Any, *, field: str, model_id: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"Open TTS {field} is invalid for {model_id}")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Open TTS {field} is invalid for {model_id}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"Open TTS {field} is invalid for {model_id}")
    return parsed


def _default_table_value(payload: Any) -> Any:
    if not isinstance(payload, (list, tuple)) or len(payload) < 10:
        raise TypeError("Open TTS response is missing default filter echoes")
    echoed = []
    for index in (3, 4, 5, 6, 7, 8):
        update = payload[index]
        if not isinstance(update, dict) or "value" not in update:
            raise TypeError("Open TTS response is missing default filter echoes")
        echoed.append(update["value"])
    expected = [
        [DEFAULT_LANGUAGE],
        DEFAULT_DATASETS,
        False,
        [DEFAULT_LANGUAGE],
        DEFAULT_DATASETS,
        False,
    ]
    if echoed != expected:
        raise ValueError("Open TTS did not echo the requested default filters")
    table_update = payload[9]
    table = table_update.get("value") if isinstance(table_update, dict) else None
    if not isinstance(table, dict) or "headers" not in table or "data" not in table:
        raise TypeError("Open TTS response does not contain the default dataframe")
    return table


def parse_open_tts_leaderboard(payload: Any) -> list[OpenTtsEntry]:
    """Validate the public default table before it can affect persisted rows."""
    if not isinstance(payload, dict):
        raise TypeError("Open TTS response must be a dataframe object")
    headers = payload.get("headers")
    rows = payload.get("data")
    if not isinstance(headers, list) or not isinstance(rows, list):
        raise TypeError("Open TTS response must contain headers and data lists")
    required = {
        "Rank",
        "Model",
        "Average WER ⬇️",
        "Average RTFx ⬆️",
        "License",
    }
    if not required.issubset(headers):
        raise ValueError("Open TTS response is missing required columns")
    if not MIN_EXPECTED_ENTRIES <= len(rows) <= MAX_EXPECTED_ENTRIES:
        raise ValueError(
            f"Open TTS returned {len(rows)} rows; expected "
            f"{MIN_EXPECTED_ENTRIES}-{MAX_EXPECTED_ENTRIES}"
        )

    indexes = {name: headers.index(name) for name in required}
    entries: list[OpenTtsEntry] = []
    model_ids: set[str] = set()
    ranks: set[int] = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != len(headers):
            raise ValueError("Open TTS response contains a malformed row")
        model_cell = str(row[indexes["Model"]])
        link = _MODEL_LINK_RE.fullmatch(model_cell.strip())
        if link is None:
            raise ValueError("Open TTS row has an invalid model link")
        model_id = html.unescape(link.group(1)).strip("/")
        model_name = html.unescape(_TAG_RE.sub("", link.group(2))).strip()
        if model_id.count("/") != 1 or not model_name or len(model_name) > 255:
            raise ValueError("Open TTS row has an invalid model identity")
        rank_value = _number(row[indexes["Rank"]], field="rank", model_id=model_id)
        rank = int(rank_value)
        wer = _number(row[indexes["Average WER ⬇️"]], field="WER", model_id=model_id)
        rtfx = _number(row[indexes["Average RTFx ⬆️"]], field="RTFx", model_id=model_id)
        if (
            rank_value != rank
            or rank < 1
            or not 0 <= wer < 100
            or not 0 < rtfx < 1_000_000
        ):
            raise ValueError(f"Open TTS row is outside accepted bounds for {model_id}")
        key = model_id.casefold()
        if key in model_ids or rank in ranks:
            raise ValueError("Open TTS response contains duplicate models or ranks")
        model_ids.add(key)
        ranks.add(rank)
        license_name = html.unescape(
            _TAG_RE.sub("", str(row[indexes["License"]]))
        ).strip()
        entries.append(
            OpenTtsEntry(
                model_id=model_id,
                model_name=model_name,
                rank=rank,
                wer=wer,
                rtfx=rtfx,
                is_open=license_name.casefold() not in {"proprietary", "closed"},
            )
        )
    if ranks != set(range(1, len(entries) + 1)):
        raise ValueError("Open TTS ranks must be contiguous and start at one")
    return sorted(entries, key=lambda entry: entry.rank)


def fetch_open_tts_leaderboard(
    client_factory: Callable[..., Any] = Client,
) -> list[OpenTtsEntry]:
    """Fetch English scores across Seed-TTS and CV3-Eval without cloning."""
    client = client_factory(SPACE_APP_URL, verbose=False)
    payload = client.predict(
        "latest",
        "",
        [DEFAULT_LANGUAGE],
        DEFAULT_DATASETS,
        False,
        api_name="/partial",
    )
    return parse_open_tts_leaderboard(_default_table_value(payload))


async def discover_open_tts_papers(
    db: Session, *, persist: bool = True
) -> ArtificialAnalysisDiscovery:
    return await ArtificialAnalysisPaperDiscoveryService(db).discover(
        persist=persist,
        identities=MODEL_PAPER_IDENTITIES,
    )


def run_open_tts_discovery(
    db: Session, *, persist: bool = True
) -> ArtificialAnalysisDiscovery:
    return asyncio.run(discover_open_tts_papers(db, persist=persist))


class OpenTtsSyncService:
    """Replace only evaluation rows owned by the Open TTS live sync."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        metrics = {
            metric.name: metric
            for metric in self.db.query(Metric)
            .filter(Metric.name.in_((WER_METRIC, RTFX_METRIC)))
            .all()
        }
        if (
            task is None
            or dataset is None
            or set(metrics)
            != {
                WER_METRIC,
                RTFX_METRIC,
            }
        ):
            raise RuntimeError(
                "Open TTS task, benchmark, or metrics are not configured"
            )
        configured = {
            row.metric_id
            for row in self.db.query(TaskDatasetMetric)
            .filter(
                TaskDatasetMetric.task_id == task.id,
                TaskDatasetMetric.dataset_id == dataset.id,
            )
            .all()
        }
        if {metric.id for metric in metrics.values()} - configured:
            raise RuntimeError(
                "Open TTS leaderboard metrics are not linked to the task"
            )
        return task, dataset

    def sync(
        self,
        entries: list[OpenTtsEntry],
        *,
        discovery: ArtificialAnalysisDiscovery,
        fetched_at: datetime | None = None,
        commit: bool = True,
    ) -> OpenTtsSyncStats:
        if not entries:
            raise ValueError("Refusing to synchronize an empty Open TTS leaderboard")
        now = fetched_at or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        stats = OpenTtsSyncStats(fetched=len(entries))
        try:
            task, dataset = self._leaderboard_identity()
            candidate_rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                )
                .all()
            )
            managed_rows = [
                row
                for row in candidate_rows
                if row.external_source_url == SPACE_SOURCE_URL
                and (row.methodology or "").startswith(MANAGED_METHODOLOGY_PREFIX)
            ]
            model_url_prefix = "https://huggingface.co/"
            managed_by_id = {
                row.hf_model_url.removeprefix(model_url_prefix).casefold(): row
                for row in managed_rows
                if (row.hf_model_url or "").startswith(model_url_prefix)
            }
            upstream_ids = {entry.model_id.casefold() for entry in entries}
            tagged_paper_ids = {
                paper_id
                for (paper_id,) in self.db.query(PaperTask.paper_id)
                .filter(PaperTask.task_id == task.id)
                .all()
            }
            for entry in entries:
                key = entry.model_id.casefold()
                paper_id = discovery.papers.get(entry.model_id)
                if paper_id is None:
                    stats.missing_papers.append(entry.model_id)
                    continue
                row = managed_by_id.get(key)
                if row is None:
                    row = Evaluation(
                        paper_id=paper_id,
                        task_id=task.id,
                        dataset_id=dataset.id,
                        model_name=entry.model_name,
                    )
                    self.db.add(row)
                    stats.created += 1
                else:
                    stats.updated += 1
                row.paper_id = paper_id
                row.model_name = entry.model_name
                row.methodology = (
                    f"{MANAGED_METHODOLOGY_PREFIX} Upstream rank {entry.rank}; "
                    "English macro-average across Seed-TTS and CV3-Eval without "
                    f"voice cloning; fetched {now.isoformat()}."
                )
                row.metrics = {WER_METRIC: entry.wer, RTFX_METRIC: entry.rtfx}
                row.uses_additional_data = False
                row.is_open = entry.is_open
                row.best_metric = WER_METRIC
                row.evaluated_on = now.date()
                row.external_source_url = SPACE_SOURCE_URL
                row.source_url = SPACE_SOURCE_URL
                row.external = True
                row.updated_at = now
                row.hf_model_url = f"{model_url_prefix}{entry.model_id}"
                if paper_id not in tagged_paper_ids:
                    self.db.add(
                        PaperTask(paper_id=paper_id, task_id=task.id, source="auto")
                    )
                    tagged_paper_ids.add(paper_id)
                stats.matched += 1

            for row in managed_rows:
                model_id = (row.hf_model_url or "").removeprefix(model_url_prefix)
                if not model_id or model_id.casefold() not in upstream_ids:
                    self.db.delete(row)
                    stats.deleted += 1

            self.db.flush()
            EvaluationService(self.db).recalculate_ranks(
                task.id, dataset.id, metric_name=WER_METRIC, commit=False
            )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise
