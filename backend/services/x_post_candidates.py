"""Post candidates for the agent that runs the Papers with Code X account.

An off-box writing agent (see `backend/scripts/x_post_candidates.py`) picks
at most one candidate per slot, checks it, writes the copy, and posts it.
This module only finds what is worth saying, from the catalog:

* ``new_sota``: a recent result that took first place on a leaderboard with
  enough entries, ahead of every other paper's best (see `new_sota`);
* ``open_sota``: a recent open-weights result that is the best open entry on
  such a leaderboard while a closed model still leads it;
* ``concept``: a fast-rising method with a description, for a "What is X?"
  explainer illustrated by a screenshot of its method page;
* ``lab_league`` (weekly): which organizations hold the most first places on
  active leaderboards;
* ``top_papers_week`` / ``top_papers_month``: the trending roundups.

Each candidate carries a draft, the facts the agent may use, the page link,
and a chart card (PNG bytes) or a page to screenshot. Posted subjects are
recorded in `x_insight_posts`, as for the scheduled insight posts, so no
subject is offered twice.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    Metric,
    Paper,
    PaperMethod,
    PaperXThread,
    Task,
    XInsightPost,
)
from backend.models.database import Method as DBMethod
from backend.services.method_service import MethodService
from backend.services.x_insight_cards import Bar, render_bar_card
from backend.services.x_insight_post_service import (
    ROUNDUP_CATCH_UP_DAYS,
    SITE,
    SOTA_MIN_ENTRIES,
    SOTA_PAPER_AGE_DAYS,
    SOTA_WINDOW,
    _distinct_models,
    recently_posted,
    sota_credit,
    sota_posted,
    sota_text,
    top_papers,
)
from backend.services.x_trending_post_service import (
    Row,
    fmt,
    hf_org_x_handle,
    leaderboard_rows,
)

KINDS = (
    "new_sota",
    "open_sota",
    "concept",
    "lab_league",
    "top_papers_week",
    "top_papers_month",
)
SOTA_LIMIT = 4
CONCEPT_LIMIT = 12
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
LEAGUE_ACTIVE_DAYS = 90
LEAGUE_SIZE = 8


@dataclass
class Candidate:
    kind: str
    subject_key: str
    draft: str
    link: str
    facts: dict[str, Any] = field(default_factory=dict)
    image: bytes | None = None
    screenshot_url: str | None = None
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "subject_key": self.subject_key,
            "draft": self.draft,
            "link": self.link,
            "facts": self.facts,
            "screenshot_url": self.screenshot_url,
            "score": self.score,
        }


# --- Leaderboard wins -------------------------------------------------------


@dataclass
class Board:
    rows: list[Row]  # best first
    lower: bool
    open_ids: set[int]


def load_board(db: Session, dataset_id: int, metric: str) -> Board:
    rows = leaderboard_rows(db, dataset_id, metric)
    direction = db.scalar(select(Metric.direction).where(Metric.name == metric))
    lower = direction == "lower_is_better"
    rows.sort(key=lambda row: row.value, reverse=not lower)
    ids = [row.evaluation_id for row in rows]
    open_ids = set(
        db.scalars(
            select(Evaluation.id).where(Evaluation.id.in_(ids), Evaluation.is_open)
        )
    )
    return Board(rows, lower, open_ids)


def _beats(board: Board, mine: Row, other: Row) -> bool:
    return mine.value < other.value if board.lower else mine.value > other.value


def classify_win(
    board: Board, paper_id: int, recent_ids: set[int]
) -> tuple[str, Row, Row] | None:
    """("new_sota" | "open_sota", the paper's best row, the row it beat).

    `new_sota`: the paper's best entry beats every other paper's best.
    `open_sota`: a closed model leads, and the paper's best entry is open and
    beats every other paper's best open entry. Either way the winning entry
    must be one of `recent_ids` (just added), so a new minor result never
    resurfaces an old lead.
    """
    mine = next((row for row in board.rows if row.paper_id == paper_id), None)
    others = [row for row in board.rows if row.paper_id != paper_id]
    if mine is None or not others or mine.evaluation_id not in recent_ids:
        return None
    if _beats(board, mine, others[0]):
        return "new_sota", mine, others[0]
    open_others = [row for row in others if row.evaluation_id in board.open_ids]
    if (
        mine.evaluation_id in board.open_ids
        and board.rows[0].evaluation_id not in board.open_ids
        and open_others
        and _beats(board, mine, open_others[0])
    ):
        return "open_sota", mine, open_others[0]
    return None


def open_sota_text(facts: dict[str, Any], credit: str) -> str:
    return (
        f"{facts['model']} is now the best open model on {facts['benchmark']} "
        f"({facts['value']} {facts['metric']}), ahead of "
        f"{facts['previous_best_open_model']} at "
        f"{facts['previous_best_open_value']}.\n\n"
        f"The closed leader, {facts['overall_leader']}, scores "
        f"{facts['overall_leader_value']}.\n\nCongrats {credit}!"
    )


def leaderboard_wins(
    db: Session,
    *,
    now: datetime,
    fetch_org_handle: Callable[[str], str | None] = hf_org_x_handle,
) -> list[Candidate]:
    """New overall and open-weights firsts from recently added results.

    A result counts when its paper is at most `SOTA_PAPER_AGE_DAYS` old, it
    was added in the last `SOTA_WINDOW`, and its leaderboard (all tasks, see
    `leaderboard_rows`) has `SOTA_MIN_ENTRIES` or more entries. Bigger
    leaderboards score higher.
    """
    since = now - SOTA_WINDOW
    published_after = now.date() - timedelta(days=SOTA_PAPER_AGE_DAYS)
    recent = db.execute(
        select(Evaluation, Paper, Dataset, Task)
        .join(Paper, Paper.id == Evaluation.paper_id)
        .join(Dataset, Dataset.id == Evaluation.dataset_id)
        .join(Task, Task.id == Evaluation.task_id)
        .where(
            Evaluation.best_metric.is_not(None),
            Evaluation.created_at >= since,
            Paper.is_latest_version,
            Paper.date_published >= published_after,
        )
    ).all()
    recent_ids = {evaluation.id for evaluation, *_ in recent}
    seen: set[tuple[int, str, int]] = set()
    found: list[tuple[Candidate, Paper]] = []
    for evaluation, paper, dataset, task in recent:
        metric = evaluation.best_metric
        if (dataset.id, metric, paper.id) in seen:
            continue
        seen.add((dataset.id, metric, paper.id))
        board = load_board(db, dataset.id, metric)
        if len(board.rows) < SOTA_MIN_ENTRIES:
            continue
        win = classify_win(board, paper.id, recent_ids)
        if win is None:
            continue
        kind, mine, beaten = win
        subject = f"{dataset.id}:{metric}:{paper.id}"
        if kind == "new_sota" and sota_posted(db, subject):
            continue
        if kind == "open_sota":
            subject = f"open:{subject}"
            if recently_posted(db, kind, subject, now, ever=True):
                continue
        facts: dict[str, Any] = {
            "benchmark": dataset.name,
            "task": task.name,
            "metric": metric,
            "lower_is_better": board.lower,
            "model": mine.model,
            "value": fmt(mine.value),
            "paper": paper.title,
            "paper_url": f"{SITE}/paper/{paper.id}",
            "leaderboard_entries": len(board.rows),
            "model_is_open": mine.evaluation_id in board.open_ids,
        }
        top = _distinct_models(board.rows, 6)
        if mine not in top:
            top = [*top[:5], mine]
        unit = f"{metric} ({'lower' if board.lower else 'higher'} is better)"
        if kind == "new_sota":
            facts["previous_model"] = beaten.model
            facts["previous_value"] = fmt(beaten.value)
            title, eyebrow = f"New SOTA on {dataset.name}", "New state of the art"
            labels = [row.model for row in top]
            score = float(len(board.rows))
        else:
            leader = board.rows[0]
            facts["previous_best_open_model"] = beaten.model
            facts["previous_best_open_value"] = fmt(beaten.value)
            facts["overall_leader"] = leader.model
            facts["overall_leader_value"] = fmt(leader.value)
            facts["overall_rank"] = board.rows.index(mine) + 1
            title = f"Best open model on {dataset.name}"
            eyebrow = "Open-weights state of the art"
            labels = [
                row.model + ("" if row.evaluation_id in board.open_ids else " (closed)")
                for row in top
            ]
            score = len(board.rows) * 0.8
        image = render_bar_card(
            title,
            unit,
            [
                Bar(label, row.value, fmt(row.value), row is mine)
                for label, row in zip(labels, top)
            ],
            lower_is_better=board.lower,
            eyebrow=f"{eyebrow} · {task.name}",
        )
        link = (
            f"{SITE}/benchmark/{dataset.slug}?task={task.slug}"
            f"&eval={mine.evaluation_id}"
        )
        found.append(
            (Candidate(kind, subject, "", link, facts, image, score=score), paper)
        )

    found.sort(key=lambda item: -item[0].score)
    for candidate, paper in found[:SOTA_LIMIT]:
        handles, organization = sota_credit(db, paper, fetch_org_handle)
        candidate.facts["verified_x_handles"] = [f"@{h}" for h in handles]
        candidate.facts["organization"] = organization
        candidate.facts["x_threads"] = x_threads(db, paper.id)
        if candidate.kind == "new_sota":
            candidate.draft = sota_text(
                candidate.facts, handles=handles, organization=organization
            )
        else:
            credit = (
                f"@{handles[0]}"
                if handles
                else organization or candidate.facts["model"]
            )
            candidate.draft = open_sota_text(candidate.facts, credit)
    return [candidate for candidate, _ in found[:SOTA_LIMIT]]


def x_threads(db: Session, paper_id: int) -> list[dict[str, Any]]:
    """The paper's reviewed X threads: quote-post candidates for the agent."""
    rows = db.execute(
        select(
            PaperXThread.url,
            PaperXThread.author_handle,
            PaperXThread.like_count,
            PaperXThread.posted_at,
        )
        .where(PaperXThread.paper_id == paper_id)
        .order_by(PaperXThread.position)
        .limit(5)
    ).all()
    return [
        {
            "url": url,
            "author": f"@{handle}",
            "likes": likes,
            "posted_at": posted_at.isoformat() if posted_at else None,
        }
        for url, handle, likes, posted_at in rows
    ]


# --- Concept explainers -----------------------------------------------------


def concepts(db: Session, *, now: datetime) -> list[Candidate]:
    """Fast-rising methods with a description, never explained before.

    The agent decides which are general techniques worth a "What is X?" post
    (models and products are not; see the method taxonomy rules).
    """
    trending = MethodService(db).get_trending_methods(limit=40, today=now.date())
    candidates = []
    for item in trending.results:
        if not item.slug or recently_posted(db, "concept", item.slug, now, ever=True):
            continue
        method = db.scalar(select(DBMethod).where(DBMethod.slug == item.slug))
        if method is None or len((method.description or "").strip()) < 80:
            continue
        papers = db.scalar(
            select(func.count()).where(PaperMethod.method_id == method.id)
        )
        link = f"{SITE}/methods/{method.slug}"
        description = plain_text(method.description)
        facts = {
            "method": method.name,
            "full_name": method.full_name,
            "description": description,
            "papers_using": papers,
            "papers_last_30_days": item.recent_paper_count,
            "papers_previous_180_days": item.baseline_paper_count,
            "introduced_year": method.introduced_year,
            "source_title": method.source_title,
            "has_figure": bool(method.image_url or method.image_data),
        }
        draft = (
            f"What is {method.name}?\n\n{description}\n\n"
            f"{papers} papers on Papers with Code use it."
        )
        candidates.append(
            Candidate(
                "concept",
                method.slug,
                draft,
                link,
                facts,
                screenshot_url=link,
                score=item.share_lift,
            )
        )
        if len(candidates) >= CONCEPT_LIMIT:
            break
    return candidates


def plain_text(markdown: str) -> str:
    """Method descriptions link other methods as `[name](/methods/x)`."""
    return _MARKDOWN_LINK.sub(r"\1", markdown).strip()


# --- Weekly lab league -------------------------------------------------------


def lab_league(db: Session, *, now: datetime) -> Candidate | None:
    """Organizations ranked by first places on active leaderboards.

    A benchmark+metric leaderboard is active when a paper published in the
    last `LEAGUE_ACTIVE_DAYS` reports on it; it counts with at least
    `SOTA_MIN_ENTRIES` entries, and its leader is its best entry across all
    tasks (`load_board`).
    Posted once per ISO week.
    """
    week = now.isocalendar()
    subject = f"{week.year}-W{week.week:02d}"
    if recently_posted(db, "lab_league", subject, now, ever=True):
        return None
    active_after = now.date() - timedelta(days=LEAGUE_ACTIVE_DAYS)
    pairs = db.execute(
        select(Evaluation.dataset_id, Evaluation.best_metric)
        .join(Paper, Paper.id == Evaluation.paper_id)
        .where(
            Evaluation.best_metric.is_not(None), Paper.date_published >= active_after
        )
        .distinct()
    ).all()
    # Rank each benchmark+metric across all tasks, as the SOTA posts do.
    leaders: dict[tuple[int, str], int] = {}
    for dataset_id, metric in pairs:
        board = load_board(db, dataset_id, metric)
        if len(board.rows) >= SOTA_MIN_ENTRIES:
            leaders[(dataset_id, metric)] = board.rows[0].paper_id
    if len(leaders) < 20:
        return None
    papers = {
        paper.id: paper
        for paper in db.scalars(
            select(Paper).where(Paper.id.in_(set(leaders.values())))
        )
    }
    wins: Counter[str] = Counter()
    for paper_id in leaders.values():
        paper = papers.get(paper_id)
        if paper is not None and paper.organizations:
            wins[paper.organizations[0].name] += 1
    boards = leaders
    top = wins.most_common(LEAGUE_SIZE)
    if len(top) < 5:
        return None
    facts = {
        "active_leaderboards": len(boards),
        "first_places_by_organization": dict(top),
        "window_days": LEAGUE_ACTIVE_DAYS,
    }
    image = render_bar_card(
        "Who holds the most SOTAs?",
        f"First places on {len(boards)} active leaderboards on Papers with Code",
        [Bar(name, count, str(count), count == top[0][1]) for name, count in top],
        eyebrow=f"State-of-the-art league · {now:%b %-d, %Y}",
    )
    draft = league_text(
        [name for name, count in top if count == top[0][1]], top[0][1], len(boards)
    )
    return Candidate(
        "lab_league", subject, draft, f"{SITE}/tasks", facts, image, score=50
    )


def league_text(leaders: list[str], count: int, boards: int) -> str:
    if len(leaders) == 1:
        lead = f"{leaders[0]} holds"
    else:
        lead = f"{', '.join(leaders[:-1])} and {leaders[-1]} each hold"
    return (
        f"{lead} first place on {count} of {boards} active leaderboards on "
        f"Papers with Code, more than any other lab."
    )


# --- All candidates ---------------------------------------------------------


def gather(db: Session, *, now: datetime | None = None) -> list[Candidate]:
    """Every candidate for this run, best first within each kind."""
    now = now or datetime.now(UTC)
    candidates = leaderboard_wins(db, now=now)
    if now.day <= ROUNDUP_CATCH_UP_DAYS:
        candidates.append(_roundup(db, "month", now))
    if now.weekday() < ROUNDUP_CATCH_UP_DAYS:
        candidates.append(_roundup(db, "week", now))
    candidates.append(lab_league(db, now=now))
    candidates.extend(concepts(db, now=now))
    return [candidate for candidate in candidates if candidate is not None]


def _roundup(db: Session, period: str, now: datetime) -> Candidate | None:
    insight = top_papers(db, period=period, now=now)
    if insight is None:
        return None
    return Candidate(
        insight.kind,
        insight.subject_key,
        insight.text,
        insight.link,
        insight.facts,
        insight.image,
        score=40,
    )


def record(
    db: Session,
    *,
    kind: str,
    subject_key: str,
    post_id: str,
    reply_id: str | None = None,
    now: datetime | None = None,
) -> XInsightPost:
    """Mark a subject as posted, so it is never offered again."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    if not post_id.isdigit():
        raise ValueError(f"post id must be numeric, got {post_id!r}")
    row = XInsightPost(
        kind=kind,
        subject_key=subject_key,
        post_id=post_id,
        reply_id=reply_id,
        posted_at=now or datetime.now(UTC),
    )
    db.add(row)
    db.commit()
    return row
