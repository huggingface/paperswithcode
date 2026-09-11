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
)
from backend.services.evaluation_service import EvaluationService

SPACE_APP_URL = "https://hf-audio-open-tts-leaderboard.hf.space"
SPACE_SOURCE_URL = "https://huggingface.co/spaces/hf-audio/open_tts_leaderboard"
DEFAULT_LANGUAGE = "🇬🇧 English"
DEFAULT_DATASETS = ["Seed-TTS", "CV3-Eval"]
EXPECTED_LANGUAGES = (
    "🇬🇧 English",
    "🇨🇳 Chinese",
    "🇫🇷 French",
    "🇪🇸 Spanish",
    "🇩🇪 German",
    "🇮🇹 Italian",
    "🇯🇵 Japanese",
    "🇰🇷 Korean",
    "🇷🇺 Russian",
)
MIN_EXPECTED_ENTRIES = 15
MIN_EXPECTED_ALL_LANGUAGE_ENTRIES = 5
MAX_EXPECTED_ENTRIES = 100
DATASET_SLUG = "open-tts-leaderboard"
ALL_LANGUAGE_DATASET_SLUG = "open-tts-leaderboard-all-languages"
TASK_SLUG = "text-to-speech"
WER_METRIC = "WER"
RTFX_METRIC = "RTFx"
MANAGED_METHODOLOGY_PREFIX = "Managed by the Papers with Code Open TTS live sync."
METHODOLOGY_BY_DATASET = {
    DATASET_SLUG: "English macro-average across Seed-TTS and CV3-Eval",
    ALL_LANGUAGE_DATASET_SLUG: (
        "Macro-average across all available languages on Seed-TTS and CV3-Eval"
    ),
}

_MODEL_LINK_RE = re.compile(
    r'<a\b[^>]*\bhref=["\']https://huggingface\.co/([^"\'?#]+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class ReviewedModel:
    paper: PaperIdentity
    display_name: str


# Reviewed against the model cards linked by the default leaderboard on
# 2026-09-11. Only models with a dedicated arXiv paper are published.
MODEL_CATALOG = {
    "microsoft/VibeVoice-Realtime-0.5B": ReviewedModel(
        PaperIdentity(arxiv_id="2508.19205", is_open=True),
        "VibeVoice Realtime 0.5B",
    ),
    "fishaudio/s2-pro": ReviewedModel(
        PaperIdentity(arxiv_id="2603.08823", is_open=True), "Fish Audio S2 Pro"
    ),
    "k2-fsa/OmniVoice": ReviewedModel(
        PaperIdentity(arxiv_id="2604.00688", is_open=True), "OmniVoice"
    ),
    "kyutai/pocket-tts": ReviewedModel(
        PaperIdentity(arxiv_id="2509.06926", is_open=True), "Pocket TTS"
    ),
    "FunAudioLLM/Fun-CosyVoice3-0.5B-2512": ReviewedModel(
        PaperIdentity(arxiv_id="2505.17589", is_open=True),
        "CosyVoice 3 0.5B (RL)",
    ),
    "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice": ReviewedModel(
        PaperIdentity(arxiv_id="2601.15621", is_open=True),
        "Qwen3-TTS 1.7B (CustomVoice)",
    ),
    "facebook/seamless-m4t-v2-large": ReviewedModel(
        PaperIdentity(arxiv_id="2312.05187", is_open=True),
        "SeamlessM4T v2 Large",
    ),
    "microsoft/speecht5_tts": ReviewedModel(
        PaperIdentity(arxiv_id="2110.07205", is_open=True), "SpeechT5"
    ),
    "OpenMOSS-Team/MOSS-TTS": ReviewedModel(
        PaperIdentity(arxiv_id="2603.18090", is_open=True), "MOSS-TTS"
    ),
    "Qwen/Qwen3-Omni-30B-A3B-Instruct": ReviewedModel(
        PaperIdentity(arxiv_id="2509.17765", is_open=True), "Qwen3-Omni 30B-A3B"
    ),
    "mistralai/Voxtral-4B-TTS-2603": ReviewedModel(
        PaperIdentity(arxiv_id="2603.25551", is_open=True), "Voxtral 4B TTS"
    ),
}
MODEL_PAPER_IDENTITIES = {
    model_id: model.paper for model_id, model in MODEL_CATALOG.items()
}
MODEL_DISPLAY_NAMES = {
    model_id: model.display_name for model_id, model in MODEL_CATALOG.items()
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
    excluded_models: list[str] = field(default_factory=list)
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


def _table_value(payload: Any, *, languages: list[str]) -> Any:
    if not isinstance(payload, (list, tuple)) or len(payload) < 10:
        raise TypeError("Open TTS response is missing default filter echoes")
    echoed = []
    for index in (3, 4, 5, 6, 7, 8):
        update = payload[index]
        if not isinstance(update, dict) or "value" not in update:
            raise TypeError("Open TTS response is missing default filter echoes")
        echoed.append(update["value"])
    expected = [
        languages,
        DEFAULT_DATASETS,
        False,
        languages,
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


def _default_table_value(payload: Any) -> Any:
    return _table_value(payload, languages=[DEFAULT_LANGUAGE])


def _available_languages(payload: Any) -> list[str]:
    if not isinstance(payload, (list, tuple)) or len(payload) < 4:
        raise TypeError("Open TTS response is missing language choices")
    update = payload[3]
    choices = update.get("choices") if isinstance(update, dict) else None
    if not isinstance(choices, list):
        raise TypeError("Open TTS response is missing language choices")
    languages: list[str] = []
    for choice in choices:
        if (
            not isinstance(choice, (list, tuple))
            or len(choice) != 2
            or not isinstance(choice[1], str)
            or not choice[1]
        ):
            raise TypeError("Open TTS response contains invalid language choices")
        languages.append(choice[1])
    if len(languages) != len(set(languages)) or not set(EXPECTED_LANGUAGES).issubset(
        languages
    ):
        raise ValueError("Open TTS response is missing expected language choices")
    return languages


def parse_open_tts_leaderboard(
    payload: Any, *, min_ranked_entries: int = MIN_EXPECTED_ENTRIES
) -> list[OpenTtsEntry]:
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
        aggregate_values = (
            row[indexes["Rank"]],
            row[indexes["Average WER ⬇️"]],
            row[indexes["Average RTFx ⬆️"]],
        )
        if aggregate_values == (None, None, None):
            continue
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
    if len(entries) < min_ranked_entries:
        raise ValueError(
            f"Open TTS returned {len(entries)} ranked rows; expected at least "
            f"{min_ranked_entries}"
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


def fetch_open_tts_leaderboards(
    client_factory: Callable[..., Any] = Client,
) -> dict[str, list[OpenTtsEntry]]:
    """Fetch the English and all-available-language comparable views."""
    client = client_factory(SPACE_APP_URL, verbose=False)
    english_payload = client.predict(
        "latest",
        "",
        [DEFAULT_LANGUAGE],
        DEFAULT_DATASETS,
        False,
        api_name="/partial",
    )
    languages = _available_languages(english_payload)
    english = parse_open_tts_leaderboard(_default_table_value(english_payload))
    all_language_payload = client.predict(
        "latest",
        "",
        languages,
        DEFAULT_DATASETS,
        False,
        api_name="/partial",
    )
    all_languages = parse_open_tts_leaderboard(
        _table_value(all_language_payload, languages=languages),
        min_ranked_entries=MIN_EXPECTED_ALL_LANGUAGE_ENTRIES,
    )
    return {
        DATASET_SLUG: english,
        ALL_LANGUAGE_DATASET_SLUG: all_languages,
    }


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

    def _leaderboard_identity(self, dataset_slug: str) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == dataset_slug).one_or_none()
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

    def _sync_dataset(
        self,
        entries: list[OpenTtsEntry],
        *,
        dataset_slug: str,
        discovery: ArtificialAnalysisDiscovery,
        now: datetime,
    ) -> OpenTtsSyncStats:
        stats = OpenTtsSyncStats(fetched=len(entries))
        task, dataset = self._leaderboard_identity(dataset_slug)
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
        selected_ids: set[str] = set()
        reviewed_ids = {model_id.casefold() for model_id in MODEL_PAPER_IDENTITIES}
        tagged_paper_ids = {
            paper_id
            for (paper_id,) in self.db.query(PaperTask.paper_id)
            .filter(PaperTask.task_id == task.id)
            .all()
        }
        for entry in entries:
            key = entry.model_id.casefold()
            if key not in reviewed_ids:
                stats.excluded_models.append(entry.model_id)
                continue
            paper_id = discovery.papers.get(entry.model_id)
            if paper_id is None:
                stats.missing_papers.append(entry.model_id)
                continue
            selected_ids.add(key)
            row = managed_by_id.get(key)
            if row is None:
                row = Evaluation(
                    paper_id=paper_id,
                    task_id=task.id,
                    dataset_id=dataset.id,
                )
                self.db.add(row)
                stats.created += 1
            else:
                stats.updated += 1
            row.paper_id = paper_id
            row.model_name = MODEL_DISPLAY_NAMES.get(entry.model_id, entry.model_name)
            row.methodology = (
                f"{MANAGED_METHODOLOGY_PREFIX} Upstream rank {entry.rank}; "
                f"{METHODOLOGY_BY_DATASET[dataset_slug]} without voice cloning; "
                f"fetched {now.isoformat()}."
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
            if not model_id or model_id.casefold() not in selected_ids:
                self.db.delete(row)
                stats.deleted += 1

        self.db.flush()
        EvaluationService(self.db).recalculate_ranks(
            task.id, dataset.id, metric_name=WER_METRIC, commit=False
        )
        return stats

    def _sync_benchmarks(
        self,
        leaderboards: dict[str, list[OpenTtsEntry]],
        *,
        discovery: ArtificialAnalysisDiscovery,
        fetched_at: datetime | None,
        commit: bool,
    ) -> dict[str, OpenTtsSyncStats]:
        if not leaderboards or any(not entries for entries in leaderboards.values()):
            raise ValueError("Refusing to synchronize an empty Open TTS leaderboard")
        if not set(leaderboards).issubset(METHODOLOGY_BY_DATASET):
            raise ValueError("Open TTS leaderboard dataset is not supported")
        now = fetched_at or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        try:
            stats = {
                dataset_slug: self._sync_dataset(
                    entries,
                    dataset_slug=dataset_slug,
                    discovery=discovery,
                    now=now,
                )
                for dataset_slug, entries in leaderboards.items()
            }
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise

    def sync(
        self,
        entries: list[OpenTtsEntry],
        *,
        discovery: ArtificialAnalysisDiscovery,
        fetched_at: datetime | None = None,
        commit: bool = True,
    ) -> OpenTtsSyncStats:
        return self._sync_benchmarks(
            {DATASET_SLUG: entries},
            discovery=discovery,
            fetched_at=fetched_at,
            commit=commit,
        )[DATASET_SLUG]

    def sync_benchmarks(
        self,
        leaderboards: dict[str, list[OpenTtsEntry]],
        *,
        discovery: ArtificialAnalysisDiscovery,
        fetched_at: datetime | None = None,
        commit: bool = True,
    ) -> dict[str, OpenTtsSyncStats]:
        expected = {DATASET_SLUG, ALL_LANGUAGE_DATASET_SLUG}
        if set(leaderboards) != expected:
            raise ValueError("Both Open TTS leaderboard views are required")
        return self._sync_benchmarks(
            leaderboards,
            discovery=discovery,
            fetched_at=fetched_at,
            commit=commit,
        )
