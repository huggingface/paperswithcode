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

Papers an admin asked for with "Tweet it" are not candidates here: the
agent fetches them separately (`x_post_requests.requested_candidates`) and
puts them at the front of its queue.
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
    Author,
    Dataset,
    Evaluation,
    Metric,
    Paper,
    PaperAuthor,
    PaperMethod,
    PaperProjectPage,
    PaperRepository,
    PaperXPost,
    PaperXThread,
    ProjectPage,
    Repository,
    Task,
    XInsightPost,
    XPostRequest,
)
from backend.models.database import Method as DBMethod
from backend.services.method_service import MethodService
from backend.services.paper_service import PaperService
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
    notable_handles,
    paper_results,
    paper_url,
)

KINDS = (
    "new_sota",
    "open_sota",
    "open_release",
    "trending_paper",
    "concept",
    "lab_league",
    "top_papers_week",
    "top_papers_month",
)
# Insight kinds about one paper; `subject_paper_id` reads it from the key.
PAPER_POST_KINDS = ("new_sota", "open_sota", "open_release", "trending_paper")
SOTA_LIMIT = 8
OPEN_RELEASE_DAYS = 21
OPEN_RELEASE_PAPERS = 25
OPEN_RELEASE_BOARDS = 12
OPEN_RELEASE_LIMIT = 4
TRENDING_PAPER_LIMIT = 6
TRENDING_FEED_DEPTH = 30
HOMEPAGE_RANGE_DAYS = 7
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


def open_closed_facts(board: Board, mine: Row) -> dict[str, Any]:
    """The best open and best closed entries on the board, for the open vs
    closed story. `mine` counts, so an open winner is its own best open row."""
    facts: dict[str, Any] = {}
    for label, is_open in (("open", True), ("closed", False)):
        best = next(
            (
                row
                for row in board.rows
                if (row.evaluation_id in board.open_ids) == is_open
            ),
            None,
        )
        if best is not None:
            facts[f"best_{label}_model"] = best.model
            facts[f"best_{label}_value"] = fmt(best.value)
    return facts


def sota_score(
    kind: str, entries: int, *, model_is_open: bool, beats_closed: bool
) -> float:
    """Rank open-weights stories first: an open model ahead of every closed one,
    then the best open model behind a closed leader, then closed firsts."""
    if kind == "new_sota" and model_is_open and beats_closed:
        return entries * 2.0
    if kind == "open_sota":
        return entries * 1.5
    return float(entries)


def open_beats_closed_line(facts: dict[str, Any]) -> str:
    return (
        f"Open weights, ahead of the best closed model, "
        f"{facts['best_closed_model']} ({facts['best_closed_value']})."
    )


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
        if kind == "new_sota" and mine.evaluation_id not in board.open_ids:
            continue  # the account posts open-model results only
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
            **open_closed_facts(board, mine),
        }
        top = _distinct_models(board.rows, 6)
        if mine not in top:
            top = [*top[:5], mine]
        unit = f"{metric} ({'lower' if board.lower else 'higher'} is better)"
        labels = [
            row.model + ("" if row.evaluation_id in board.open_ids else " (closed)")
            for row in top
        ]
        score = sota_score(
            kind,
            len(board.rows),
            model_is_open=facts["model_is_open"],
            beats_closed="best_closed_model" in facts,
        )
        if kind == "new_sota":
            facts["previous_model"] = beaten.model
            facts["previous_value"] = fmt(beaten.value)
            title, eyebrow = f"New SOTA on {dataset.name}", "New state of the art"
            if facts["model_is_open"]:
                eyebrow = "Open-weights model, new state of the art"
        else:
            leader = board.rows[0]
            facts["previous_best_open_model"] = beaten.model
            facts["previous_best_open_value"] = fmt(beaten.value)
            facts["overall_leader"] = leader.model
            facts["overall_leader_value"] = fmt(leader.value)
            facts["overall_rank"] = board.rows.index(mine) + 1
            title = f"Best open model on {dataset.name}"
            eyebrow = "Open-weights state of the art"
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
            if (
                candidate.facts["model_is_open"]
                and "best_closed_model" in candidate.facts
            ):
                candidate.draft += "\n\n" + open_beats_closed_line(candidate.facts)
        else:
            credit = (
                f"@{handles[0]}"
                if handles
                else organization or candidate.facts["model"]
            )
            candidate.draft = open_sota_text(candidate.facts, credit)
    return [candidate for candidate, _ in found[:SOTA_LIMIT]]


# --- New open models --------------------------------------------------------


def placement(
    board: Board, paper_id: int, eligible: set[int] | None = None
) -> dict[str, Any] | None:
    """Where the paper's best open entry lands on this board.

    Only open entries count, and only those in `eligible` (evaluation ids)
    when given. `open_rank` counts distinct papers with a better open entry,
    so a paper's own smaller variants don't push it down.
    """
    mine = next(
        (
            row
            for row in board.rows
            if row.paper_id == paper_id
            and row.evaluation_id in board.open_ids
            and (eligible is None or row.evaluation_id in eligible)
        ),
        None,
    )
    if mine is None:
        return None
    index = board.rows.index(mine)
    ahead = board.rows[:index]
    open_ahead = {
        row.paper_id
        for row in ahead
        if row.evaluation_id in board.open_ids and row.paper_id != paper_id
    }
    closed = next(
        (row for row in board.rows if row.evaluation_id not in board.open_ids), None
    )
    result: dict[str, Any] = {
        "evaluation_id": mine.evaluation_id,
        "model": mine.model,
        "value": fmt(mine.value),
        "open_rank": len(open_ahead) + 1,
        "overall_rank": len({row.paper_id for row in ahead if row.paper_id != paper_id})
        + 1,
        "entries": len(board.rows),
    }
    if closed is not None:
        result["best_closed_model"] = closed.model
        result["best_closed_value"] = fmt(closed.value)
        result["ahead_of_best_closed"] = _beats(board, mine, closed)
    return result


def subject_paper_id(subject_key: str) -> int | None:
    """The paper an insight post was about: `open_release` keys are the paper
    id, SOTA keys end with it (`[open:|task:]dataset:metric:paper`)."""
    tail = subject_key.rsplit(":", 1)[-1]
    return int(tail) if tail.isdigit() else None


def posted_paper_ids(db: Session) -> set[int]:
    """Papers the account already posted about in any form: a trending-paper
    post, a SOTA or an open release. A new model is announced only once."""
    ids = set(db.scalars(select(PaperXPost.paper_id)))
    for kind, subject_key in db.execute(
        select(XInsightPost.kind, XInsightPost.subject_key).where(
            XInsightPost.kind.in_(PAPER_POST_KINDS)
        )
    ):
        paper_id = subject_paper_id(subject_key)
        if paper_id is not None:
            ids.add(paper_id)
    return ids


def requested_paper_ids(db: Session) -> set[int]:
    """Papers an admin asked to post about ("Tweet it") that are still open;
    see `backend/services/x_post_requests.py`."""
    return set(
        db.scalars(
            select(XPostRequest.paper_id).where(XPostRequest.resolved_at.is_(None))
        )
    )


def board_sizes(db: Session, keys: set[tuple[int, str]]) -> dict[tuple[int, str], int]:
    """Result count per (dataset, metric), counted like `leaderboard_rows`
    (every evaluation carrying the metric), to visit the biggest boards first."""
    return {
        (dataset_id, metric): db.scalar(
            select(func.count()).where(
                Evaluation.dataset_id == dataset_id,
                Evaluation.metrics.has_key(metric),
            )
        )
        for dataset_id, metric in keys
    }


def open_release_score(placements: list[dict[str, Any]]) -> float:
    """Leaderboards led among open models count fully, second or third place
    among open models counts a little, anything lower not at all."""
    weights = {1: 1.0, 2: 0.3, 3: 0.3}
    return sum(p["entries"] * weights.get(p["open_rank"], 0.0) for p in placements)


def headline_placement(placements: list[dict[str, Any]]) -> dict[str, Any]:
    """The placement the draft leads with, so the card charts the same board:
    an open first, else a win over every closed model, else the best rank."""
    return next(
        (p for p in placements if p["open_rank"] == 1),
        next((p for p in placements if p.get("ahead_of_best_closed")), placements[0]),
    )


def open_release_card_rows(board: Board, mine: Row, limit: int = 6) -> list[Row]:
    """The board's top distinct models, always including the new model and the
    best closed entry the draft compares it with, in board order."""
    closed = next(
        (row for row in board.rows if row.evaluation_id not in board.open_ids), None
    )
    required = [row for row in (mine, closed) if row is not None]
    top = _distinct_models(board.rows, limit)
    others = [row for row in top if row not in required]
    keep = set(map(id, required + others[: limit - len(required)]))
    return [row for row in board.rows if id(row) in keep]


def open_release_text(facts: dict[str, Any], credit: str | None) -> str:
    size = f", {facts['parameters_b']}B" if facts.get("parameters_b") else ""
    lines = [f"New open-weights model: {facts['model']}{size}."]
    firsts = list(
        dict.fromkeys(
            p["benchmark"] for p in facts["placements"] if p["open_rank"] == 1
        )
    )
    if firsts:
        lines.append(f"Best open model on {', '.join(firsts[:3])}.")
    beats = [p for p in facts["placements"] if p.get("ahead_of_best_closed")]
    if beats:
        p = beats[0]
        lines.append(
            f"On {p['benchmark']} it beats every closed model, "
            f"{p['value']} to {p['best_closed_model']}'s {p['best_closed_value']}."
        )
    if credit:
        lines.append(f"Congrats {credit}!")
    return "\n\n".join(lines)


def open_releases(
    db: Session,
    *,
    now: datetime,
    fetch_org_handle: Callable[[str], str | None] = hf_org_x_handle,
) -> list[Candidate]:
    """New open-weights models and where they land across leaderboards.

    A model qualifies through evaluations flagged open that link a Hugging
    Face model, on a paper published in the last `OPEN_RELEASE_DAYS`.
    """
    published_after = now.date() - timedelta(days=OPEN_RELEASE_DAYS)
    rows = db.execute(
        select(Evaluation, Paper)
        .join(Paper, Paper.id == Evaluation.paper_id)
        .where(
            Evaluation.is_open,
            Evaluation.hf_model_url.is_not(None),
            Evaluation.best_metric.is_not(None),
            Paper.is_latest_version,
            Paper.date_published >= published_after,
        )
    ).all()
    by_paper: dict[int, list[Evaluation]] = {}
    papers: dict[int, Paper] = {}
    for evaluation, paper in rows:
        by_paper.setdefault(paper.id, []).append(evaluation)
        papers[paper.id] = paper
    posted = posted_paper_ids(db)
    unposted = [pid for pid in by_paper if pid not in posted]
    ranked = sorted(unposted, key=lambda pid: (-len(by_paper[pid]), pid))
    keys = {(e.dataset_id, e.best_metric) for pid in ranked for e in by_paper[pid]}
    sizes = board_sizes(db, keys)
    found: list[tuple[Candidate, Paper]] = []
    for paper_id in ranked[:OPEN_RELEASE_PAPERS]:
        paper = papers[paper_id]
        evaluations = by_paper[paper_id]
        by_id = {e.id: e for e in evaluations}
        paper_keys = sorted(
            {
                (e.dataset_id, e.best_metric)
                for e in evaluations
                if sizes.get((e.dataset_id, e.best_metric), 0) >= SOTA_MIN_ENTRIES
            },
            key=lambda key: (-sizes[key], key),
        )
        placements = []
        # Keyed by placement: one evaluation can place on several metric boards.
        boards: dict[int, tuple[Board, Dataset]] = {}
        for dataset_id, metric in paper_keys:
            if len(placements) >= OPEN_RELEASE_BOARDS:
                break
            board = load_board(db, dataset_id, metric)
            if len(board.rows) < SOTA_MIN_ENTRIES:
                continue
            place = placement(board, paper_id, set(by_id))
            if place is None:
                continue
            dataset = db.get(Dataset, dataset_id)
            place = {"benchmark": dataset.name, "metric": metric, **place}
            placements.append(place)
            boards[id(place)] = (board, dataset)
        score = open_release_score(placements)
        if not score:
            continue
        placements.sort(key=lambda p: (p["open_rank"], -p["entries"]))
        best = headline_placement(placements)
        board, dataset = boards[id(best)]
        own = by_id[best["evaluation_id"]]
        facts: dict[str, Any] = {
            "model": best["model"],
            "hf_model_url": own.hf_model_url,
            "parameters_b": round(own.num_parameters / 1e9, 1)
            if own.num_parameters
            else None,
            "paper": paper.title,
            "paper_url": f"{SITE}/paper/{paper.id}",
            "published": str(paper.date_published),
            "card_benchmark": dataset.name,
            "placements": placements,
        }
        mine = next(r for r in board.rows if r.evaluation_id == best["evaluation_id"])
        top = open_release_card_rows(board, mine)
        image = render_bar_card(
            f"{best['model']} on {dataset.name}",
            f"{best['metric']} ({'lower' if board.lower else 'higher'} is better)",
            [
                Bar(
                    row.model
                    + ("" if row.evaluation_id in board.open_ids else " (closed)"),
                    row.value,
                    fmt(row.value),
                    row is mine,
                )
                for row in top
            ],
            lower_is_better=board.lower,
            eyebrow="New open-weights model",
        )
        found.append(
            (
                Candidate(
                    "open_release",
                    str(paper.id),
                    "",
                    f"{SITE}/paper/{paper.id}",
                    facts,
                    image,
                    score=score,
                ),
                paper,
            )
        )
    found.sort(key=lambda item: -item[0].score)
    for candidate, paper in found[:OPEN_RELEASE_LIMIT]:
        handles, organization = sota_credit(db, paper, fetch_org_handle)
        candidate.facts["verified_x_handles"] = [f"@{h}" for h in handles]
        candidate.facts["organization"] = organization
        candidate.facts["x_threads"] = x_threads(db, paper.id)
        credit = f"@{handles[0]}" if handles else organization
        candidate.draft = open_release_text(candidate.facts, credit)
    return [candidate for candidate, _ in found[:OPEN_RELEASE_LIMIT]]


# --- Trending paper explainers ----------------------------------------------


def trending_papers(
    db: Session,
    *,
    now: datetime,
    fetch_org_handle: Callable[[str], str | None] = hf_org_x_handle,
) -> list[Candidate]:
    """The top of the homepage's trending feed (arXiv and external papers
    alike) that the account never posted, for an explainer post with a
    screenshot of the paper page (alphaXiv style)."""
    # The homepage's trending tab (FeedView) ranks papers published in the
    # last week by default: today and the 6 days before it, UTC.
    today = now.astimezone(UTC).date()
    feed = PaperService(db).get_papers(
        page=1,
        page_size=TRENDING_FEED_DEPTH,
        order_by="trending",
        start_date=today - timedelta(days=HOMEPAGE_RANGE_DAYS - 1),
        end_date=today,
    )
    ranks = {int(item.id): rank for rank, item in enumerate(feed.results, 1)}
    skip = posted_paper_ids(db) | requested_paper_ids(db)
    wanted = [pid for pid in ranks if pid not in skip][:TRENDING_PAPER_LIMIT]
    by_id = {p.id: p for p in db.scalars(select(Paper).where(Paper.id.in_(wanted)))}
    return [
        paper_candidate(
            db, by_id[pid], rank=ranks[pid], fetch_org_handle=fetch_org_handle
        )
        for pid in wanted
        if pid in by_id
    ]


def paper_candidate(
    db: Session,
    paper: Paper,
    *,
    rank: int | None,
    fetch_org_handle: Callable[[str], str | None] = hf_org_x_handle,
) -> Candidate:
    """A paper explainer (alphaXiv style) with a screenshot of the paper page.
    ``rank`` is the paper's place on the homepage's trending feed, if any."""
    authors = list(
        db.scalars(
            select(Author.name)
            .join(PaperAuthor, PaperAuthor.author_id == Author.id)
            .where(PaperAuthor.paper_id == paper.id)
            .order_by(PaperAuthor.author_order)
        )
    )
    organizations = [o.name for o in paper.organizations]
    facts: dict[str, Any] = {
        "title": paper.title,
        "arxiv_id": paper.arxiv_id,
        "source": paper.source,
        "homepage_trending_rank": rank,
        "published": str(paper.date_published),
        "trending_score": round(float(paper.trending_score or 0), 1),
        "authors": authors[:12],
        "author_count": len(authors),
        "organizations": organizations,
        "verified_x_handles": [
            f"@{h}" for h in notable_handles(db, paper, fetch_org_handle)
        ],
        "x_threads": x_threads(db, paper.id),
        "tldr": paper.tldr,
        "abstract": paper.abstract,
        "code": list(
            db.scalars(
                select(Repository.url)
                .join(PaperRepository, PaperRepository.repository_id == Repository.id)
                .where(PaperRepository.paper_id == paper.id)
                .order_by(
                    PaperRepository.is_official.desc(),
                    Repository.num_stars.desc(),
                    Repository.id,
                )
                .limit(2)
            )
        ),
        "project_pages": list(
            db.scalars(
                select(ProjectPage.url)
                .join(
                    PaperProjectPage,
                    PaperProjectPage.project_page_id == ProjectPage.id,
                )
                .where(PaperProjectPage.paper_id == paper.id)
                .order_by(ProjectPage.id)
                .limit(1)
            )
        ),
        "leaderboard_results": paper_results(db, paper.id),
        "paper_url": paper_url(paper),
    }
    lead = organizations[0] if organizations else (authors[0] if authors else None)
    draft = f"{lead} just released a new paper!" if lead else "New paper!"
    draft += f'\n\n"{paper.title}"'
    if paper.tldr:
        draft += f"\n\n{paper.tldr}"
    return Candidate(
        "trending_paper",
        str(paper.id),
        draft,
        paper_url(paper),
        facts,
        screenshot_url=paper_url(paper),
        score=32.0 - rank if rank else 0.0,
    )


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
    candidates.extend(open_releases(db, now=now))
    candidates.extend(trending_papers(db, now=now))
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
    paper_id = subject_paper_id(subject_key)
    if paper_id is not None and kind in PAPER_POST_KINDS:
        request = db.get(XPostRequest, paper_id)
        if request is not None and request.resolved_at is None:
            request.resolved_at = row.posted_at
            request.resolution = "posted"
    db.commit()
    return row
