"""Shared engine for single-metric live leaderboard syncs.

A board module parses its official leaderboard into ``LeaderboardEntry`` rows
and declares a reviewed ``ModelIdentity`` map; this engine resolves papers,
hands unreviewed names to the release radar, and creates or revises the rows
it owns. Like every live sync it never creates papers and never deletes rows:
a managed row that leaves the upstream board is only reported.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import httpx

from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    Metric,
    Paper,
    PaperTask,
    Task,
    TaskDatasetMetric,
)
from backend.services.evaluation_service import EvaluationService
from backend.services.leaderboard_model_matching_service import (
    LeaderboardModel,
    LeaderboardModelMatcher,
)
from backend.services.leaderboard_sync_ownership import managed_methodology_prefix


@dataclass(frozen=True)
class ModelIdentity:
    """A reviewed leaderboard model and the paper that introduces it."""

    model_name: str
    arxiv_id: str | None = None
    source_url: str | None = None
    is_open: bool = False
    hf_model_url: str | None = None

    def __post_init__(self) -> None:
        if (self.arxiv_id is None) == (self.source_url is None):
            raise ValueError("ModelIdentity requires exactly one paper identity")

    @property
    def paper_key(self) -> str:
        return self.arxiv_id or self.source_url or ""


@dataclass(frozen=True)
class LeaderboardEntry:
    """One official leaderboard row, already on the board's metric scale."""

    name: str
    value: float
    detail: str
    harness: str | None = None
    lab: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} ({self.harness})" if self.harness else self.name


@dataclass(frozen=True)
class LiveLeaderboard:
    """Static configuration of one synced board."""

    source: str
    provider: str
    url: str
    task_slug: str
    dataset_slug: str
    metric: str
    identities: dict[str, ModelIdentity]
    min_selected: int
    protocol: str
    # Upstream names the board deliberately leaves out, with the reason.
    excluded: dict[str, str] = field(default_factory=dict)

    @property
    def managed_prefix(self) -> str:
        return managed_methodology_prefix(self.source)


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

    def _leaderboard_identity(self) -> tuple[Task, Dataset]:
        board = self.board
        task = self.db.query(Task).filter(Task.slug == board.task_slug).one_or_none()
        dataset = (
            self.db.query(Dataset)
            .filter(Dataset.slug == board.dataset_slug)
            .one_or_none()
        )
        if task is None or dataset is None:
            raise RuntimeError(f"{board.source} task or benchmark is not configured")
        configured = (
            self.db.query(TaskDatasetMetric)
            .join(Metric, Metric.id == TaskDatasetMetric.metric_id)
            .filter(
                TaskDatasetMetric.task_id == task.id,
                TaskDatasetMetric.dataset_id == dataset.id,
                Metric.name == board.metric,
            )
            .count()
        )
        if configured != 1:
            raise RuntimeError(f"{board.source} metric is not linked to the task")
        return task, dataset

    def _paper_ids(self) -> dict[str, int]:
        """Resolve reviewed paper identities without ever creating papers."""
        identities = self.board.identities.values()
        arxiv_ids = {i.arxiv_id for i in identities if i.arxiv_id}
        source_urls = {i.source_url for i in identities if i.source_url}
        papers = (
            self.db.query(Paper.id, Paper.arxiv_id, Paper.source_url)
            .filter(
                Paper.is_latest_version,
                (Paper.arxiv_id.in_(arxiv_ids))
                | ((Paper.source == "external") & Paper.source_url.in_(source_urls)),
            )
            .order_by(Paper.id)
            .all()
        )
        resolved: dict[str, int] = {}
        for paper_id, arxiv_id, source_url in papers:
            resolved[arxiv_id if arxiv_id in arxiv_ids else source_url] = paper_id
        return resolved

    def _methodology(self, entry: LeaderboardEntry) -> str:
        board = self.board
        return (
            f"{board.managed_prefix} Official leaderboard entry "
            f'"{entry.label}": {entry.detail}, listed at {board.url}. '
            f"{board.protocol}"
        )

    def sync(
        self,
        entries: list[LeaderboardEntry],
        *,
        evaluated_on: date | None = None,
        commit: bool = True,
    ) -> LiveSyncStats:
        board = self.board
        fetched = len(entries)
        entries = [e for e in entries if e.name not in board.excluded]
        reviewed = [e for e in entries if e.name in board.identities]
        if len(reviewed) < board.min_selected:
            raise RuntimeError(
                f"{board.source} has only {len(reviewed)} reviewed entries; "
                "refusing to update the managed leaderboard"
            )
        stats = LiveSyncStats(fetched=fetched, excluded=fetched - len(entries))
        try:
            task, dataset = self._leaderboard_identity()
            paper_ids = self._paper_ids()
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
                        identity.model_name,
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
                        match.model_name,
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

            rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                )
                .order_by(Evaluation.id)
                .all()
            )
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
                metrics = {board.metric: entry.value}
                methodology = self._methodology(entry)
                # A hand-imported row may record the harness as "Not reported".
                row = rows_by_identity.get(key)
                if row is None:
                    fallback = unmanaged_by_model.get((paper_id, model_name))
                    if fallback is not None and id(fallback) not in published:
                        row = fallback
                if row is None:
                    row = Evaluation(
                        paper_id=paper_id,
                        task_id=task.id,
                        dataset_id=dataset.id,
                        model_name=model_name,
                        harness=entry.harness,
                        is_open=is_open,
                        hf_model_url=hf_model_url,
                        external_source_url=board.url,
                        source_url=board.url,
                        external=True,
                        uses_additional_data=False,
                    )
                    self.db.add(row)
                    rows_by_identity[key] = row
                    stats.created += 1
                elif not (row.methodology or "").startswith(board.managed_prefix):
                    # A hand-imported row for the same model becomes managed.
                    row.external_source_url = board.url
                    row.source_url = board.url
                    row.harness = entry.harness
                    stats.adopted += 1
                elif row.metrics != metrics or row.methodology != methodology:
                    stats.changed += 1
                row.metrics = metrics
                row.methodology = methodology
                row.best_metric = board.metric
                if evaluated_on is not None:
                    row.evaluated_on = evaluated_on
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
