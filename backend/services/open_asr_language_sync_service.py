"""Synchronize the Open ASR Leaderboard's per-language views into boards.

The Space's multilingual tab (deeplinked as `?languages=<code>`) ranks models
by one language's average WER across that language's datasets. Each language
gets its own benchmark next to the English `open-asr-leaderboard` board.

A model is published only when it has a paper on arXiv or a technical report.
Its paper comes from the English board's live row, the reviewed arXiv map, or
the shared leaderboard model matcher, in that order.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from gradio_client import Client
from sqlalchemy.orm import Session

from backend.models.database import Evaluation, Paper, PaperTask
from backend.services.evaluation_service import EvaluationService
from backend.services.leaderboard_model_matching_service import (
    LeaderboardModel,
    LeaderboardModelMatcher,
)
from backend.services.leaderboard_sync_catalog import (
    is_paper_backed,
    resolve_leaderboard,
)
from backend.services.open_asr_sync_service import (
    DATASET_SLUG,
    MANAGED_METHODOLOGY_PREFIX,
    MODEL_PAPER_ARXIV_IDS,
    RTFX_METRIC,
    SPACE_APP_URL,
    SPACE_SOURCE_URL,
    TASK_SLUG,
    WER_METRIC,
    OpenAsrEntry,
    OpenAsrSyncService,
    _number,
    best_runtime_variants,
    display_model_names,
    hub_model_id,
)

MULTILINGUAL_TABLE_API = "/_render_multilingual_combined"
AVERAGE_VIEW = "Language averages"
RTFX_COLUMN = "RTFx ⬆️️"
# Label -> the Space's `?languages=<code>` deeplink code. English is the
# default `open-asr-leaderboard` board.
LANGUAGE_BOARDS = {
    "🇩🇪 German": "de",
    "🇫🇷 French": "fr",
    "🇮🇹 Italian": "it",
    "🇪🇸 Spanish": "es",
    "🇵🇹 Portuguese": "pt",
    "🇮🇳 Hindi": "hi",
    "🇳🇱 Dutch": "nl",
    "🇦🇲 Armenian": "hy",
}
MIN_EXPECTED_ENTRIES = 3
MAX_EXPECTED_ENTRIES = 150

_MODEL_LINK_RE = re.compile(
    r'<a\b[^>]*\bhref=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")
_HF_PREFIX = "https://huggingface.co/"


def language_name(label: str) -> str:
    """`🇮🇳 Hindi` -> `Hindi`."""
    return label.split(" ", 1)[1]


def language_dataset_slug(label: str) -> str:
    """`🇮🇳 Hindi` -> `open-asr-leaderboard-hindi`."""
    return f"{DATASET_SLUG}-{language_name(label).casefold()}"


@dataclass
class OpenAsrLanguageSyncStats:
    fetched: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    auto_matched: list[str] = field(default_factory=list)
    unmatched_models: list[str] = field(default_factory=list)
    no_paper_models: list[str] = field(default_factory=list)
    runtime_variants: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def parse_language_table(payload: Any, *, label: str) -> list[OpenAsrEntry]:
    """Validate one language's ranked table before it can affect rows."""
    if isinstance(payload, dict) and isinstance(payload.get("value"), dict):
        payload = payload["value"]
    if not isinstance(payload, dict):
        raise TypeError("Open ASR language response must be a dataframe object")
    headers = payload.get("headers")
    rows = payload.get("data")
    if not isinstance(headers, list) or not isinstance(rows, list):
        raise TypeError("Open ASR language response must contain headers and data")
    required = {"Rank", "Model", "Average WER ⬇️", RTFX_COLUMN, label}
    if not required.issubset(headers):
        raise ValueError(f"Open ASR {label} response is missing required columns")
    if not MIN_EXPECTED_ENTRIES <= len(rows) <= MAX_EXPECTED_ENTRIES:
        raise ValueError(
            f"Open ASR {label} returned {len(rows)} rows; expected "
            f"{MIN_EXPECTED_ENTRIES}-{MAX_EXPECTED_ENTRIES}"
        )
    indexes = {name: headers.index(name) for name in required}
    entries: list[OpenAsrEntry] = []
    names: set[str] = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != len(headers):
            raise ValueError(f"Open ASR {label} response contains a malformed row")
        link = _MODEL_LINK_RE.fullmatch(str(row[indexes["Model"]]).strip())
        if link is None:
            raise ValueError(f"Open ASR {label} row has an invalid model link")
        model_id = html.unescape(_TAG_RE.sub("", link.group(2))).strip()
        if not model_id or len(model_id) > 255 or "/" not in model_id:
            raise ValueError(f"Open ASR {label} row has an invalid model identifier")
        rank = int(_number(row[indexes["Rank"]]))
        wer = _number(row[indexes["Average WER ⬇️"]])
        rtfx = _number(row[indexes[RTFX_COLUMN]], optional=True)
        if (
            rank < 1
            or wer is None
            or not 0 <= wer <= 100
            or (rtfx is not None and rtfx <= 0)
        ):
            raise ValueError(f"Open ASR {label} row is out of bounds for {model_id}")
        if model_id.casefold() in names:
            raise ValueError(f"Open ASR {label} response lists {model_id} twice")
        names.add(model_id.casefold())
        entries.append(
            OpenAsrEntry(
                model_id=model_id,
                rank=rank,
                wer=wer,
                rtfx=rtfx,
                # Refined from the English board's license where it lists the
                # model; proprietary APIs link to vendor docs, not the Hub.
                is_open=html.unescape(link.group(1)).startswith(_HF_PREFIX),
            )
        )
    ranks = sorted(entry.rank for entry in entries)
    if ranks != list(range(1, len(entries) + 1)):
        raise ValueError(f"Open ASR {label} ranks must be contiguous from one")
    return sorted(entries, key=lambda entry: entry.rank)


def fetch_open_asr_language_leaderboards(
    client_factory: Callable[..., Any] = Client,
) -> dict[str, list[OpenAsrEntry]]:
    """Fetch each language's average view, as its deeplink shows it."""
    client = client_factory(SPACE_APP_URL, verbose=False)
    leaderboards: dict[str, list[OpenAsrEntry]] = {}
    for label in LANGUAGE_BOARDS:
        payload = client.predict(
            version_id="latest",
            search_query="",
            show_proprietary=True,
            selected=[label, RTFX_COLUMN],
            zoom=AVERAGE_VIEW,
            api_name=MULTILINGUAL_TABLE_API,
        )
        leaderboards[language_dataset_slug(label)] = parse_language_table(
            payload, label=label
        )
    return leaderboards


@dataclass(frozen=True)
class _KnownModel:
    paper_id: int
    is_open: bool
    hf_model_url: str | None
    num_parameters: int | None


class OpenAsrLanguageSyncService:
    """Replace only rows owned by the Open ASR per-language live sync."""

    def __init__(self, db: Session):
        self.db = db

    def _english_models(self) -> dict[str, _KnownModel]:
        """Papers the English board's live rows already assign to models."""
        task, dataset = resolve_leaderboard(
            self.db, "Open ASR", TASK_SLUG, DATASET_SLUG, (WER_METRIC, RTFX_METRIC)
        )
        rows = (
            self.db.query(Evaluation)
            .filter(
                Evaluation.task_id == task.id,
                Evaluation.dataset_id == dataset.id,
                Evaluation.external_source_url == SPACE_SOURCE_URL,
                Evaluation.methodology.startswith(MANAGED_METHODOLOGY_PREFIX),
            )
            .all()
        )
        models: dict[str, _KnownModel] = {}
        # Exact upstream ids win; a suffix-stripped Hub id ("org/m (runtime)"
        # -> "org/m") also finds the row when the views spell it differently.
        for exact in (False, True):
            for row in rows:
                model_id = OpenAsrSyncService._managed_model_id(row)
                key = (model_id if exact else hub_model_id(model_id)).casefold()
                models[key] = _KnownModel(
                    row.paper_id, row.is_open, row.hf_model_url, row.num_parameters
                )
        return models

    @staticmethod
    def _lookup(models: dict[str, Any], model_id: str) -> Any:
        return models.get(model_id.casefold()) or models.get(
            hub_model_id(model_id).casefold()
        )

    def _reviewed_papers(self) -> dict[str, int]:
        papers = {
            arxiv_id: paper_id
            for paper_id, arxiv_id in self.db.query(Paper.id, Paper.arxiv_id)
            .filter(
                Paper.arxiv_id.in_(set(MODEL_PAPER_ARXIV_IDS.values())),
                Paper.is_latest_version,
            )
            .all()
        }
        return {
            model_id.casefold(): papers[arxiv_id]
            for model_id, arxiv_id in MODEL_PAPER_ARXIV_IDS.items()
            if arxiv_id in papers
        }

    def sync(
        self,
        leaderboards: dict[str, list[OpenAsrEntry]],
        *,
        fetched_at: datetime | None = None,
        commit: bool = True,
    ) -> dict[str, OpenAsrLanguageSyncStats]:
        slugs = {language_dataset_slug(label): label for label in LANGUAGE_BOARDS}
        if not leaderboards or not set(leaderboards).issubset(slugs):
            raise ValueError("Open ASR language boards are not supported")
        if any(not entries for entries in leaderboards.values()):
            raise ValueError("Refusing to synchronize an empty Open ASR language board")
        now = fetched_at or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        try:
            english = self._english_models()
            reviewed = self._reviewed_papers()
            names = display_model_names(
                list(
                    {
                        entry.model_id: entry
                        for entries in leaderboards.values()
                        for entry in entries
                    }.values()
                )
            )

            def known_paper(model_id: str) -> int | None:
                if (model := self._lookup(english, model_id)) is not None:
                    return model.paper_id
                return self._lookup(reviewed, model_id)

            unknown = list(
                {
                    names[entry.model_id]: LeaderboardModel(
                        names[entry.model_id], entry.model_id.split("/", 1)[0]
                    )
                    for entries in leaderboards.values()
                    for entry in entries
                    if known_paper(entry.model_id) is None
                }.values()
            )
            matcher = LeaderboardModelMatcher(
                self.db,
                provider="open-asr",
                leaderboard_name="Open ASR",
                leaderboard_url=SPACE_SOURCE_URL,
            )
            auto_matched = matcher.match(unknown)
            stats = {
                slug: self._sync_language(
                    entries,
                    dataset_slug=slug,
                    label=slugs[slug],
                    names=names,
                    english=english,
                    known_paper=known_paper,
                    auto_matched={
                        name: match.paper_id for name, match in auto_matched.items()
                    },
                    now=now,
                )
                for slug, entries in leaderboards.items()
            }
            matcher.report_unmatched(
                [model for model in unknown if model.name not in auto_matched]
            )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise

    def _sync_language(
        self,
        entries: list[OpenAsrEntry],
        *,
        dataset_slug: str,
        label: str,
        names: dict[str, str],
        english: dict[str, _KnownModel],
        known_paper: Callable[[str], int | None],
        auto_matched: dict[str, int],
        now: datetime,
    ) -> OpenAsrLanguageSyncStats:
        stats = OpenAsrLanguageSyncStats(fetched=len(entries))
        entries, stats.runtime_variants = best_runtime_variants(entries)
        task, dataset = resolve_leaderboard(
            self.db, "Open ASR", TASK_SLUG, dataset_slug, (WER_METRIC, RTFX_METRIC)
        )
        managed_rows = (
            self.db.query(Evaluation)
            .filter(
                Evaluation.task_id == task.id,
                Evaluation.dataset_id == dataset.id,
                Evaluation.external_source_url == SPACE_SOURCE_URL,
                Evaluation.methodology.startswith(MANAGED_METHODOLOGY_PREFIX),
            )
            .all()
        )
        managed_by_id = {
            OpenAsrSyncService._managed_model_id(row).casefold(): row
            for row in managed_rows
        }
        tagged = {
            paper_id
            for (paper_id,) in self.db.query(PaperTask.paper_id)
            .filter(PaperTask.task_id == task.id)
            .all()
        }
        selected: set[str] = set()
        for entry in entries:
            name = names[entry.model_id]
            paper_id = known_paper(entry.model_id)
            if paper_id is None and (paper_id := auto_matched.get(name)) is not None:
                stats.auto_matched.append(entry.model_id)
            if paper_id is None:
                stats.unmatched_models.append(entry.model_id)
                continue
            paper = self.db.get(Paper, paper_id)
            if paper is None or not is_paper_backed(paper):
                stats.no_paper_models.append(entry.model_id)
                continue
            key = entry.model_id.casefold()
            selected.add(key)
            known = self._lookup(english, entry.model_id)
            row = managed_by_id.get(key)
            if row is None:
                row = Evaluation(
                    paper_id=paper_id, task_id=task.id, dataset_id=dataset.id
                )
                self.db.add(row)
                stats.created += 1
            else:
                stats.updated += 1
            hub_id = hub_model_id(entry.model_id)
            is_open = known.is_open if known is not None else entry.is_open
            row.paper_id = paper_id
            row.model_name = name
            row.methodology = (
                f"{MANAGED_METHODOLOGY_PREFIX} Upstream model {entry.model_id}; "
                f"rank {entry.rank}; {language_name(label)} average WER across "
                f"the Space's {language_name(label)} datasets; "
                f"fetched {now.isoformat()}."
            )
            metrics: dict[str, float] = {WER_METRIC: entry.wer}
            if entry.rtfx is not None:
                metrics[RTFX_METRIC] = entry.rtfx
            row.metrics = metrics
            row.uses_additional_data = False
            row.is_open = is_open
            row.best_metric = WER_METRIC
            row.evaluated_on = now.date()
            row.external_source_url = SPACE_SOURCE_URL
            row.source_url = SPACE_SOURCE_URL
            row.external = True
            row.updated_at = now
            row.hf_model_url = (
                known.hf_model_url
                if known is not None and known.hf_model_url
                else (f"{_HF_PREFIX}{hub_id}" if entry.is_open else None)
            )
            if known is not None and known.num_parameters is not None:
                row.num_parameters = known.num_parameters
            if paper_id not in tagged:
                self.db.add(
                    PaperTask(paper_id=paper_id, task_id=task.id, source="auto")
                )
                tagged.add(paper_id)
            stats.matched += 1

        for key, row in managed_by_id.items():
            if key not in selected:
                self.db.delete(row)
                stats.deleted += 1
        self.db.flush()
        evaluation_service = EvaluationService(self.db)
        for metric in (WER_METRIC, RTFX_METRIC):
            evaluation_service.recalculate_ranks(
                task.id, dataset.id, metric_name=metric, commit=False
            )
        return stats
