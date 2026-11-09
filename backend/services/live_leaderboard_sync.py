"""Shared engine for single-metric live leaderboard syncs.

A board module parses its official leaderboard into ``LeaderboardEntry`` rows
and declares a reviewed ``ModelIdentity`` map; this engine resolves papers,
hands unreviewed names to the release radar, and creates or revises the rows
it owns. Like every live sync it never creates papers and never deletes rows:
a managed row that leaves the upstream board is only reported.

A managed methodology is the sync's head followed by any reviewer notes. The
engine rewrites the head on every run and keeps the notes; adopting a
hand-imported row keeps its methodology as the notes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.models.database import (
    Evaluation,
    PaperTask,
)
from backend.services.evaluation_service import EvaluationService
from backend.services.leaderboard_model_matching_service import (
    LeaderboardModel,
    LeaderboardModelMatcher,
)
from backend.services.leaderboard_sync_catalog import (
    ModelIdentity,
    resolve_identity_papers,
    resolve_leaderboard,
    score_matches,
)
from backend.services.leaderboard_sync_ownership import managed_methodology_prefix


@dataclass(frozen=True)
class LeaderboardEntry:
    """One official leaderboard row, already on the board's metric scale."""

    name: str
    # A Decimal keeps the precision the board publishes (65.40, not 65.4).
    value: float | Decimal
    detail: str
    harness: str | None = None
    lab: str = ""
    # Where this entry's result is reported, when not the board page itself.
    source_url: str | None = None
    # When the board added this entry; otherwise the day the sync creates it.
    evaluated_on: date | None = None

    @property
    def label(self) -> str:
        return f"{self.name} ({self.harness})" if self.harness else self.name


@dataclass(frozen=True)
class LiveLeaderboard:
    """Static configuration of one synced board.

    Several boards may share a benchmark when each publishes its own metric
    (Physics-IQ Verified's I2V and V2V tracks): a board only reads and writes
    rows that carry its metric.
    """

    source: str
    provider: str
    url: str
    task_slug: str
    dataset_slug: str
    metric: str
    identities: dict[str, ModelIdentity]
    min_selected: int
    # Board-wide evaluation setup appended to every managed head.
    protocol: str = ""
    # Appended to every catalog model name on the board, e.g. " (no tools)".
    model_name_suffix: str = ""
    # Upstream names the board deliberately leaves out, with the reason.
    excluded: dict[str, str] = field(default_factory=dict)
    # Whether a hand-imported row for the same paper and model name becomes
    # managed. Off for third-party reruns that must sit beside self-reported
    # rows instead of overwriting them.
    adopt_unmanaged: bool = True

    @property
    def managed_prefix(self) -> str:
        return managed_methodology_prefix(self.source)

    @property
    def managed_head(self) -> re.Pattern[str]:
        """Match a managed methodology, capturing the reviewer notes after it."""
        protocol = f" {re.escape(self.protocol)}" if self.protocol else ""
        return re.compile(
            f"{re.escape(self.managed_prefix)} Official leaderboard entry "
            # Physics-IQ Verified heads before 2026-11-09 end "reported at".
            rf".*?, (?:listed|reported) at \S+\.{protocol}(?: (?P<notes>.*))?$",
            re.DOTALL,
        )


@dataclass
class LiveSyncStats:
    fetched: int = 0
    excluded: int = 0
    matched: int = 0
    created: int = 0
    changed: int = 0
    adopted: int = 0
    # Names outside the reviewed map that the catalog matched on its own.
    auto_matched: list[str] = field(default_factory=list)
    # Names with no paper yet; each is a release signal for the radar.
    unreviewed: list[str] = field(default_factory=list)
    missing_papers: list[str] = field(default_factory=list)
    missing_upstream: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


_BARE_KEY = re.compile(r"([{,])\s*([A-Za-z_$][\w$]*)\s*:")
_SINGLE_QUOTED = re.compile(r"'((?:[^'\\]|\\.)*)'")
_BARE_DECIMAL = re.compile(r"(?<![\w.])(-?)\.(\d)")
_LINE_COMMENT = re.compile(r"(?m)^\s*//.*$")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def js_literal(source: str, start: int, what: str) -> Any:
    """Decode the plain-data JS object or array literal that begins at ``start``.

    Handles the minifier and hand-written forms these sites use: bare and
    single-quoted keys, single-quoted strings, ``.5`` numbers, comments, and
    trailing commas. Anything else (calls, identifiers) fails loudly.
    """
    if source[start : start + 1] not in ("{", "["):
        raise ValueError(f"{what} does not start with an object or array")
    depth = 0
    quote = ""
    escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth == 0:
                literal = source[start : index + 1]
                break
    else:
        raise ValueError(f"{what} literal is unterminated")
    literal = _BLOCK_COMMENT.sub("", _LINE_COMMENT.sub("", literal))
    literal = _SINGLE_QUOTED.sub(
        lambda match: json.dumps(match[1].replace("\\'", "'")), literal
    )
    literal = _BARE_DECIMAL.sub(r"\g<1>0.\2", _BARE_KEY.sub(r'\1"\2":', literal))
    try:
        return json.loads(_TRAILING_COMMA.sub(r"\1", literal))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{what} literal is not plain data") from exc


USER_AGENT = (
    "Mozilla/5.0 (compatible; PapersWithCodeLeaderboardSync/1.0; "
    "+https://paperswithcode.co)"
)


def fetch_text(
    url: str, client: httpx.Client | None = None, *, user_agent: str = USER_AGENT
) -> str:
    owned_client = client is None
    active_client = client or httpx.Client(
        timeout=httpx.Timeout(30, connect=5), follow_redirects=True
    )
    try:
        response = active_client.get(url, headers={"User-Agent": user_agent})
        response.raise_for_status()
        return response.text
    finally:
        if owned_client:
            active_client.close()


def check_entry_count(entries: list, what: str, low: int, high: int) -> None:
    if not low <= len(entries) <= high:
        raise ValueError(f"{what} has {len(entries)} entries; expected {low}-{high}")


class LiveLeaderboardSyncService:
    """Create and revise one board's managed rows; never create papers."""

    def __init__(self, db: Session, board: LiveLeaderboard):
        self.db = db
        self.board = board

    def _methodology(self, entry: LeaderboardEntry, notes: str) -> str:
        board = self.board
        parts = [
            f"{board.managed_prefix} Official leaderboard entry "
            f'"{entry.label}": {entry.detail}, listed at {board.url}.',
            board.protocol,
            notes,
        ]
        return " ".join(part for part in parts if part)

    def _managed_notes(self, row: Evaluation) -> str:
        """Return the reviewer notes kept beneath a managed row's head."""
        head = self.board.managed_head.match((row.methodology or "").strip())
        return (head and head.group("notes")) or ""

    def sync(
        self,
        entries: list[LeaderboardEntry],
        *,
        commit: bool = True,
    ) -> LiveSyncStats:
        board = self.board
        fetched = len(entries)
        entries = [e for e in entries if e.name not in board.excluded]
        reviewed = [e for e in entries if e.name in board.identities]
        # Several labels (settings, prompt variants) can name one model, so
        # the floor counts the distinct models the board would publish.
        reviewed_models = {
            (
                board.identities[e.name].paper_key,
                board.identities[e.name].model_name,
                e.harness,
            )
            for e in reviewed
        }
        if len(reviewed_models) < board.min_selected:
            raise RuntimeError(
                f"{board.source} has only {len(reviewed_models)} reviewed models; "
                "refusing to update the managed leaderboard"
            )
        stats = LiveSyncStats(fetched=fetched, excluded=fetched - len(entries))
        try:
            task, dataset = resolve_leaderboard(
                self.db,
                board.source,
                board.task_slug,
                board.dataset_slug,
                (board.metric,),
            )
            paper_ids = resolve_identity_papers(self.db, board.identities.values())
            new_entries = [e for e in entries if e.name not in board.identities]
            matcher = LeaderboardModelMatcher(
                self.db,
                provider=board.provider,
                leaderboard_name=board.source,
                leaderboard_url=board.url,
            )
            matched = matcher.match(
                [LeaderboardModel(e.name, e.lab) for e in new_entries]
            )
            # (paper id, catalog model name, is_open, HF model URL, entry)
            selected = []
            for entry in reviewed:
                identity = board.identities[entry.name]
                selected.append(
                    (
                        paper_ids.get(identity.paper_key),
                        identity.model_name + board.model_name_suffix,
                        identity.is_open,
                        identity.hf_model_url,
                        entry,
                    )
                )
            for entry in new_entries:
                if (match := matched.get(entry.name)) is None:
                    stats.unreviewed.append(entry.label)
                    continue
                selected.append(
                    (
                        match.paper_id,
                        match.model_name + board.model_name_suffix,
                        match.is_open,
                        match.hf_model_url,
                        entry,
                    )
                )
                stats.auto_matched.append(entry.label)
            matcher.report_unmatched(
                [
                    LeaderboardModel(e.name, e.lab)
                    for e in new_entries
                    if e.name not in matched
                ]
            )
            # Several upstream rows (reasoning settings, providers) can name
            # one catalog model; the board keeps that model's best row.
            best: dict[tuple[int, str, str | None], tuple] = {}
            for item in selected:
                paper_id, model_name, _, _, entry = item
                if paper_id is None:
                    stats.missing_papers.append(entry.label)
                    continue
                key = (paper_id, model_name, entry.harness)
                if key not in best or entry.value > best[key][4].value:
                    best[key] = item

            rows = [
                row
                for row in self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                )
                .order_by(Evaluation.id)
                .all()
                if board.metric in (row.metrics or {})
            ]
            rows_by_identity: dict[tuple[int, str, str | None], Evaluation] = {}
            unmanaged_by_model: dict[tuple[int, str], Evaluation] = {}
            for row in rows:
                rows_by_identity.setdefault(
                    (row.paper_id, row.model_name, row.harness), row
                )
                if not (row.methodology or "").startswith(board.managed_prefix):
                    unmanaged_by_model.setdefault((row.paper_id, row.model_name), row)
            linked_paper_ids = {
                paper_id
                for (paper_id,) in self.db.query(PaperTask.paper_id)
                .filter(PaperTask.task_id == task.id)
                .all()
            }
            now = datetime.now(UTC)
            published: set[int] = set()
            for key, (
                paper_id,
                model_name,
                is_open,
                hf_model_url,
                entry,
            ) in best.items():
                # A hand-imported row may record the harness as "Not reported".
                row = rows_by_identity.get(key)
                if row is None and board.adopt_unmanaged:
                    fallback = unmanaged_by_model.get((paper_id, model_name))
                    if fallback is not None and id(fallback) not in published:
                        row = fallback
                source_url = entry.source_url or board.url
                if row is None:
                    row = Evaluation(
                        paper_id=paper_id,
                        task_id=task.id,
                        dataset_id=dataset.id,
                        model_name=model_name,
                        harness=entry.harness,
                        is_open=is_open,
                        hf_model_url=hf_model_url,
                        external_source_url=source_url,
                        source_url=source_url,
                        external=True,
                        uses_additional_data=False,
                        # The leaderboard's year column reads this date.
                        evaluated_on=entry.evaluated_on or now.date(),
                    )
                    self.db.add(row)
                    rows_by_identity[key] = row
                    stats.created += 1
                    notes, managed = "", False
                elif not (row.methodology or "").startswith(board.managed_prefix):
                    # A hand-imported row for the same model becomes managed;
                    # its reviewer methodology stays as notes beneath the head.
                    notes, managed = (row.methodology or "").strip(), False
                    row.external_source_url = source_url
                    row.source_url = source_url
                    row.harness = entry.harness
                    stats.adopted += 1
                else:
                    notes, managed = self._managed_notes(row), True
                stored = (row.metrics or {}).get(board.metric)
                listed = (
                    entry.value
                    if isinstance(entry.value, Decimal)
                    else Decimal(str(entry.value))
                )
                # A reviewer may have stored the unrounded value (48.23) the
                # board lists at lower precision (48.2); that is not a revision.
                value = stored if score_matches(stored, listed) else float(entry.value)
                methodology = self._methodology(entry, notes)
                if managed and (stored, row.methodology) != (value, methodology):
                    stats.changed += 1
                # Other metrics a hand-imported row carries stay untouched.
                row.metrics = {**(row.metrics or {}), board.metric: value}
                row.methodology = methodology
                row.best_metric = board.metric
                if entry.evaluated_on is not None:
                    row.evaluated_on = entry.evaluated_on
                row.updated_at = now
                if paper_id not in linked_paper_ids:
                    self.db.add(
                        PaperTask(paper_id=paper_id, task_id=task.id, source="auto")
                    )
                    linked_paper_ids.add(paper_id)
                published.add(id(row))
                stats.matched += 1

            stats.missing_upstream = sorted(
                f"{row.model_name} ({row.harness})" if row.harness else row.model_name
                for row in rows
                if id(row) not in published
                and (row.methodology or "").startswith(board.managed_prefix)
            )
            self.db.flush()
            EvaluationService(self.db).recalculate_ranks(
                task.id, dataset.id, metric_name=board.metric, commit=False
            )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise
