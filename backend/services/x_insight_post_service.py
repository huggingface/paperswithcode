"""Insight posts for the Papers with Code X account.

Besides the four-hourly trending paper, the account posts twice a day about
what is moving on the site:

* ``top_papers_week`` / ``top_papers_month``: the top trending papers of the
  previous week (Mondays) or calendar month (the 1st);
* ``new_sota``: a recent paper that just took first place on a leaderboard
  with enough entries, beating the previous best from another paper;
* ``trending_benchmark`` / ``trending_method`` / ``trending_task``: the
  fastest-growing benchmark, method, or task, in rotation.

Each post is a short text (written by Luna from the exact numbers, or a fixed
template when Luna is unavailable or changes a number), a chart card, and a
reply with the page link. `x_insight_posts` keeps every posted subject so none
is repeated.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

import httpx
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    Metric,
    Paper,
    PaperXThread,
    Task,
    XInsightPost,
)
from backend.services.benchmark_trend_service import _support_weighted_score
from backend.services.metric_value_service import parse_metric_value
from backend.services.method_service import MethodService
from backend.services.task_service import TaskService
from backend.services.x_insight_cards import Bar, render_bar_card, render_list_card
from backend.services.x_thread_discovery_service import short_name
from backend.services.x_trending_post_service import (
    XPoster,
    paragraphs,
    weighted_length,
)

logger = logging.getLogger(__name__)

SITE = "https://paperswithcode.co"
ROTATION = ("trending_benchmark", "trending_method", "trending_task")
KINDS = ("top_papers_week", "top_papers_month", "new_sota", *ROTATION)
REPEAT_AFTER = timedelta(days=30)
MORNING_SLOT_ENDS_HOUR = 15
ROUNDUP_CATCH_UP_DAYS = 3
SOTA_WINDOW = timedelta(days=3)
SOTA_PAPER_AGE_DAYS = 45
SOTA_MIN_ENTRIES = 5
BENCHMARK_RECENT_DAYS = 90
BENCHMARK_BASELINE_DAYS = 180
BENCHMARK_MIN_RECENT_PAPERS = 5
LUNA_MODEL = "gpt-6-luna"
RESPONSES_URL = "https://api.openai.com/v1/responses"
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_MENTION = re.compile(r"@[A-Za-z0-9_]{1,15}")
_X_HANDLE = re.compile(r"[A-Za-z0-9_]{1,15}")
_HF_X_LINK = re.compile(
    r'href="https://(?:www\.)?(?:twitter|x)\.com/([A-Za-z0-9_]{1,15})/?"'
)
_IGNORED_HANDLES = {"huggingface", "home", "intent", "share", "x", "twitter"}

LUNA_INSTRUCTIONS = """You write posts for the Papers with Code account on X, \
read by ML researchers and engineers.

Rewrite the draft post into one post that a researcher would find worth \
reading. Lead with the most interesting fact. Plain, specific, confident; no \
hype words ("groundbreaking", "game-changer", "revolutionary"), no emojis, \
hashtags, links, or questions to the reader.

Hard rules: keep the draft's opening (such as "Congrats @team on achieving \
SOTA on X!" or "New SOTA on X") at the start, keep every @mention exactly as \
written and add none, keep every number exactly as written in the draft, add no new numbers, and state nothing that is not in the draft or the facts. Keep names \
as written. Put each sentence on its own line with an empty line between \
sentences. Stay within the character limit. Output only the post text."""


@dataclass
class Insight:
    kind: str
    subject_key: str
    text: str
    link: str
    image: bytes
    facts: dict[str, Any] = field(default_factory=dict)


def fmt(value: float) -> str:
    """Compact metric value: at most two decimals, no trailing zeros."""
    text = f"{value:.1f}" if abs(value) >= 100 else f"{value:.2f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def fmt_lift(value: float) -> str:
    return f"{value:.1f}x" if value < 10 else f"{value:.0f}x"


def paper_label(title: str, *, limit: int = 48) -> str:
    """The name before the colon ("MiMo-V2.6"), else the title, shortened."""
    title = " ".join(title.split())
    name = short_name(title) or title.split(":", 1)[0].strip()
    if ":" in title and len(name) <= 30:
        return name
    if len(title) <= limit:
        return title
    return title[: title.rfind(" ", 0, limit)].rstrip(" ,;:-") + "…"


def recently_posted(
    db: Session, kind: str, subject_key: str, now: datetime, *, ever: bool
) -> bool:
    query = select(XInsightPost.id).where(
        XInsightPost.kind == kind, XInsightPost.subject_key == subject_key
    )
    if not ever:
        query = query.where(XInsightPost.posted_at >= now - REPEAT_AFTER)
    return db.scalar(query.limit(1)) is not None


def sota_posted(db: Session, subject_key: str) -> bool:
    """Whether this paper's SOTA on this benchmark and metric was announced.

    Keys are `dataset:metric:paper`, since the comparison spans every task's
    leaderboard; posts made before that carried a `task:` prefix.
    """
    query = select(XInsightPost.id).where(
        XInsightPost.kind == "new_sota",
        or_(
            XInsightPost.subject_key == subject_key,
            XInsightPost.subject_key.endswith(f":{subject_key}", autoescape=True),
        ),
    )
    return db.scalar(query.limit(1)) is not None


# --- Top papers -----------------------------------------------------------


def top_papers(db: Session, *, period: str, now: datetime) -> Insight | None:
    today = now.date()
    if period == "week":
        end = today - timedelta(days=today.weekday())  # this Monday
        start = end - timedelta(days=7)
        subject = f"{start.isocalendar().year}-W{start.isocalendar().week:02d}"
        heading = "Top trending papers of the week"
        span = f"Published {start:%b %-d} – {end - timedelta(days=1):%b %-d, %Y}"
    else:
        end = today.replace(day=1)
        start = (end - timedelta(days=1)).replace(day=1)
        subject = f"{start:%Y-%m}"
        heading = f"Top trending papers of {start:%B}"
        span = f"Published in {start:%B %Y}"
    kind = f"top_papers_{period}"
    if recently_posted(db, kind, subject, now, ever=True):
        return None
    papers = list(
        db.scalars(
            select(Paper)
            .where(
                Paper.is_latest_version,
                Paper.date_published >= start,
                Paper.date_published < end,
                Paper.trending_score > 0,
            )
            .order_by(Paper.trending_score.desc(), Paper.id.desc())
            .limit(5)
        )
    )
    if len(papers) < 3:
        return None
    labels = [paper_label(paper.title) for paper in papers]
    text = compose_list(f"{heading} on Papers with Code:", labels)
    return Insight(
        kind=kind,
        subject_key=subject,
        text=text,
        link=SITE,
        image=render_list_card(
            heading,
            span,
            [" ".join(paper.title.split()) for paper in papers],
            eyebrow=f"Top papers · {'weekly' if period == 'week' else 'monthly'}",
        ),
        facts={"papers": [paper.title for paper in papers], "period": span},
    )


def compose_list(head: str, labels: list[str], max_chars: int = 280) -> str:
    """Numbered list, an empty line between entries, dropping entries to fit (min 3)."""
    while True:
        lines = [f"{index + 1}. {label}" for index, label in enumerate(labels)]
        text = "\n\n".join([head, *lines])
        if weighted_length(text) <= max_chars or len(labels) <= 3:
            return text
        labels = labels[:-1]


# --- New SOTA -------------------------------------------------------------


@dataclass
class Row:
    evaluation_id: int
    paper_id: int
    model: str
    value: float


def _leaderboard(db: Session, dataset_id: int, metric: str) -> list[Row]:
    """Every result for this benchmark and metric, across all tasks.

    A benchmark can have a leaderboard under several tasks (IFEval under both
    Instruction Following and Language Modeling); a new SOTA has to beat them
    all, or the site itself would contradict the post.
    """
    rows = db.execute(
        select(
            Evaluation.id,
            Evaluation.paper_id,
            Evaluation.model_name,
            Evaluation.metrics[metric].astext,
        ).where(
            Evaluation.dataset_id == dataset_id,
            Evaluation.metrics.has_key(metric),
        )
    ).all()
    parsed = [
        Row(row[0], row[1], row[2] or "Unnamed model", parse_metric_value(row[3]))
        for row in rows
    ]
    return [row for row in parsed if row.value is not None]


def _distinct_models(rows: list[Row], limit: int) -> list[Row]:
    seen: set[str] = set()
    result = []
    for row in rows:
        key = row.model.casefold()
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result[:limit]


def new_sota(
    db: Session,
    *,
    now: datetime,
    fetch_org_handle: Callable[[str], str | None] | None = None,
) -> Insight | None:
    """The most contested leaderboard a recent paper just topped.

    The post congratulates the team behind the paper (see `sota_credit`).
    """
    fetch_org_handle = fetch_org_handle or hf_org_x_handle
    since = now - SOTA_WINDOW
    published_after = now.date() - timedelta(days=SOTA_PAPER_AGE_DAYS)
    candidates = db.execute(
        select(Evaluation, Paper, Dataset, Task)
        .join(Paper, Paper.id == Evaluation.paper_id)
        .join(Dataset, Dataset.id == Evaluation.dataset_id)
        .join(Task, Task.id == Evaluation.task_id)
        .where(
            Evaluation.best_rank == 1,
            Evaluation.best_metric.is_not(None),
            Evaluation.created_at >= since,
            Paper.is_latest_version,
            Paper.date_published >= published_after,
        )
    ).all()
    best: tuple[int, Insight, Paper] | None = None
    for evaluation, paper, dataset, task in candidates:
        metric = evaluation.best_metric
        subject = f"{dataset.id}:{metric}:{paper.id}"
        if sota_posted(db, subject):
            continue
        rows = _leaderboard(db, dataset.id, metric)
        if len(rows) < SOTA_MIN_ENTRIES or (best and len(rows) <= best[0]):
            continue
        direction = db.scalar(select(Metric.direction).where(Metric.name == metric))
        lower = direction == "lower_is_better"
        rows.sort(key=lambda row: row.value, reverse=not lower)
        mine = next((row for row in rows if row.evaluation_id == evaluation.id), None)
        others = [row for row in rows if row.paper_id != paper.id]
        if mine is None or not others:
            continue
        previous = others[0]
        improves = mine.value < previous.value if lower else mine.value > previous.value
        if not improves:
            continue
        top = _distinct_models(rows, 6)
        if mine not in top:
            top = [mine, *top[:5]]
        text = ""  # written below for the chosen leaderboard only
        link = f"{SITE}/benchmark/{dataset.slug}?task={task.slug}&eval={evaluation.id}"
        image = render_bar_card(
            f"New SOTA on {dataset.name}",
            f"{metric} ({'lower' if lower else 'higher'} is better)",
            [Bar(row.model, row.value, fmt(row.value), row is mine) for row in top],
            lower_is_better=lower,
            eyebrow=f"New state of the art · {task.name}",
        )
        insight = Insight(
            kind="new_sota",
            subject_key=subject,
            text=text,
            link=link,
            image=image,
            facts={
                "benchmark": dataset.name,
                "task": task.name,
                "metric": metric,
                "lower_is_better": lower,
                "model": mine.model,
                "value": fmt(mine.value),
                "previous_model": previous.model,
                "previous_value": fmt(previous.value),
                "paper": paper.title,
                "leaderboard_entries": len(rows),
            },
        )
        best = (len(rows), insight, paper)
    if best is None:
        return None
    _, insight, paper = best
    handles, organization = sota_credit(db, paper, fetch_org_handle)
    insight.text = sota_text(insight.facts, handles=handles, organization=organization)
    insight.facts["congratulated"] = [f"@{h}" for h in handles] or organization
    return insight


def hf_org_x_handle(hf_slug: str) -> str | None:
    """The X account an organization links from its Hugging Face page."""
    try:
        response = httpx.get(f"https://huggingface.co/{hf_slug}", timeout=15)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    handles = {
        handle
        for handle in _HF_X_LINK.findall(response.text)
        if handle.casefold() not in _IGNORED_HANDLES
    }
    return handles.pop() if len(handles) == 1 else None


def sota_credit(
    db: Session, paper: Paper, fetch_org_handle: Callable[[str], str | None]
) -> tuple[list[str], str | None]:
    """X handles to congratulate, and the organization's name.

    The organization's own account comes first: a linked X thread posted by
    it, else the X link on its Hugging Face page. Without one, up to two
    authors who posted linked threads (already reviewed as the paper's own
    authors). Every handle is a public account tied to the paper itself.
    """
    organization = paper.organizations[0] if paper.organizations else None
    threads = db.execute(
        select(PaperXThread.author_handle, PaperXThread.author_name)
        .where(PaperXThread.paper_id == paper.id)
        .order_by(PaperXThread.position)
    ).all()
    handles: list[str] = []
    if organization:
        names = {organization.name.casefold(), (organization.slug or "").casefold()}
        handles = [
            handle
            for handle, name in threads
            if (name or "").casefold() in names or handle.casefold() in names
        ][:1]
        if not handles and organization.hf_slug:
            handle = fetch_org_handle(organization.hf_slug)
            handles = [handle] if handle else []
    if not handles:
        handles = [handle for handle, _ in threads][:2]
    handles = [h for h in dict.fromkeys(handles) if _X_HANDLE.fullmatch(h or "")]
    return handles, organization.name if organization else None


def sota_text(
    facts: dict[str, Any], *, handles: list[str], organization: str | None
) -> str:
    if handles:
        mentions = " and ".join(f"@{handle}" for handle in handles)
        lead = f"Congrats {mentions} on achieving SOTA on {facts['benchmark']}!"
    elif organization:
        lead = f"Congrats to {organization} on achieving SOTA on {facts['benchmark']}!"
    else:
        lead = f"New SOTA on {facts['benchmark']}!"
    return (
        f"{lead}\n\n"
        f"{facts['model']} scores {facts['value']} {facts['metric']}.\n\n"
        f"That puts it ahead of {facts['previous_model']} at "
        f"{facts['previous_value']}."
    )


# --- Trending benchmarks, methods, tasks ------------------------------------


def benchmark_growth(recent: int, baseline: int) -> str:
    """Change in monthly reporting rate, recent window vs. baseline window."""
    if not baseline:
        return "new"
    rate = (recent / BENCHMARK_RECENT_DAYS) / (baseline / BENCHMARK_BASELINE_DAYS)
    return fmt_lift(rate)


def trending_benchmark(db: Session, *, now: datetime) -> Insight | None:
    """The benchmark whose reporting rate grew the most, site-wide."""
    today = now.date()
    recent_start = today - timedelta(days=BENCHMARK_RECENT_DAYS)
    baseline_start = recent_start - timedelta(days=BENCHMARK_BASELINE_DAYS)
    published = Paper.date_published
    # Exclusive starts, as in BenchmarkTrendService: exactly 90 vs. 180 days.
    recent = func.count(func.distinct(case((published > recent_start, Paper.id))))
    baseline = func.count(func.distinct(case((published <= recent_start, Paper.id))))
    rows = db.execute(
        select(Dataset, recent.label("recent"), baseline.label("baseline"))
        .join(Evaluation, Evaluation.dataset_id == Dataset.id)
        .join(Paper, and_(Paper.id == Evaluation.paper_id, Paper.is_latest_version))
        .where(published > baseline_start, published <= today)
        .group_by(Dataset.id)
        .having(recent >= BENCHMARK_MIN_RECENT_PAPERS)
    ).all()
    scored = sorted(
        rows,
        key=lambda row: -_support_weighted_score(
            row.recent,
            row.baseline,
            recent_days=BENCHMARK_RECENT_DAYS,
            baseline_days=BENCHMARK_BASELINE_DAYS,
        ),
    )[:5]
    featured = next(
        (
            row
            for row in scored
            if not recently_posted(
                db, "trending_benchmark", row.Dataset.slug, now, ever=False
            )
        ),
        None,
    )
    if featured is None:
        return None
    dataset = featured.Dataset
    if featured.baseline:
        growth = f"up from {featured.baseline} in the 180 days before."
    else:
        growth = "after none in the 180 days before."
    text = (
        f"{dataset.name} is the fastest-growing benchmark on Papers with Code."
        f"\n\n{featured.recent} papers reported results on it in the last 90 "
        f"days, {growth}"
    )
    image = render_bar_card(
        "Fastest-growing benchmarks",
        "Papers reporting results in the last 90 days, and the change in rate",
        [
            Bar(
                row.Dataset.name,
                row.recent,
                f"{row.recent} · {benchmark_growth(row.recent, row.baseline)}",
                row is featured,
            )
            for row in scored
        ],
        eyebrow="Trending benchmarks · last 90 days",
    )
    return Insight(
        kind="trending_benchmark",
        subject_key=dataset.slug,
        text=text,
        link=f"{SITE}/benchmark/{dataset.slug}",
        image=image,
        facts={
            "benchmark": dataset.name,
            "description": (dataset.description or "")[:400],
            "papers_last_90_days": featured.recent,
            "papers_previous_180_days": featured.baseline,
        },
    )


def _trending_taxonomy(
    db: Session, *, kind: str, results: list, noun: str, path: str, now: datetime
) -> Insight | None:
    featured = next(
        (
            item
            for item in results
            if not recently_posted(db, kind, item.slug, now, ever=False)
        ),
        None,
    )
    if featured is None:
        return None
    text = (
        f"{featured.name} is the fastest-rising {noun} on Papers with Code."
        f"\n\n{featured.recent_paper_count} papers in the last 30 days: "
        f"{fmt_lift(featured.share_lift)} its share of new papers in the 180 "
        f"days before."
    )
    image = render_bar_card(
        f"Fastest-rising {noun}s",
        "Share of new papers, last 30 days vs. the 180 days before",
        [
            Bar(item.name, item.share_lift, fmt_lift(item.share_lift), item is featured)
            for item in results
        ],
        eyebrow=f"Trending {noun}s · last 30 days",
    )
    return Insight(
        kind=kind,
        subject_key=featured.slug,
        text=text,
        link=f"{SITE}/{path}/{featured.slug}",
        image=image,
        facts={
            noun: featured.name,
            "papers_last_30_days": featured.recent_paper_count,
            "papers_previous_180_days": featured.baseline_paper_count,
            "share_lift": fmt_lift(featured.share_lift),
        },
    )


def trending_method(db: Session, *, now: datetime) -> Insight | None:
    results = MethodService(db).get_trending_methods(limit=5, today=now.date()).results
    return _trending_taxonomy(
        db,
        kind="trending_method",
        results=results,
        noun="method",
        path="methods",
        now=now,
    )


def trending_task(db: Session, *, now: datetime) -> Insight | None:
    results = TaskService(db).get_trending_tasks(limit=5, today=now.date()).results
    return _trending_taxonomy(
        db, kind="trending_task", results=results, noun="task", path="tasks", now=now
    )


BUILDERS: dict[str, Callable[..., Insight | None]] = {
    "top_papers_week": lambda db, now: top_papers(db, period="week", now=now),
    "top_papers_month": lambda db, now: top_papers(db, period="month", now=now),
    "new_sota": lambda db, now: new_sota(db, now=now),
    "trending_benchmark": lambda db, now: trending_benchmark(db, now=now),
    "trending_method": lambda db, now: trending_method(db, now=now),
    "trending_task": lambda db, now: trending_task(db, now=now),
}


# --- Scheduling -----------------------------------------------------------


def plan_kinds(db: Session, now: datetime) -> list[str]:
    """Kinds to try, in order, for this run.

    Morning runs lead with the monthly and weekly roundups and then a new
    SOTA; evening runs lead with the least recently posted trending insight.
    A roundup that a run missed (throttled past the morning slot, or displaced
    by the other roundup) is caught up on the next mornings: the monthly one
    through the 3rd, the weekly one through Wednesday. Their subjects are fixed
    per month and week, so each is posted once. At most one SOTA post goes out
    per 20 hours. The morning slot ends at 15:00 UTC because a throttled
    09:43 run may start up to three hours late.
    """
    last = dict(
        db.execute(
            select(XInsightPost.kind, func.max(XInsightPost.posted_at)).group_by(
                XInsightPost.kind
            )
        ).all()
    )
    oldest = datetime.min.replace(tzinfo=UTC)
    rotation = sorted(ROTATION, key=lambda kind: last.get(kind) or oldest)
    sota_due = (last.get("new_sota") or oldest) < now - timedelta(hours=20)
    sota = ["new_sota"] if sota_due else []
    if now.hour >= MORNING_SLOT_ENDS_HOUR:
        return rotation + sota
    periodic = []
    if now.day <= ROUNDUP_CATCH_UP_DAYS:
        periodic.append("top_papers_month")
    if now.weekday() < ROUNDUP_CATCH_UP_DAYS:
        periodic.append("top_papers_week")
    return periodic + sota + rotation


# --- Writing --------------------------------------------------------------


def numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(text))


def accept_rewrite(
    draft: str, rewrite: str, *, facts: str = "", max_chars: int
) -> bool:
    """A rewrite keeps every number and @mention of the draft, adding no number
    beyond the facts and no other mention."""
    return (
        bool(rewrite)
        and weighted_length(rewrite) <= max_chars
        and numbers(draft) <= numbers(rewrite) <= numbers(draft) | numbers(facts)
        and set(_MENTION.findall(rewrite)) == set(_MENTION.findall(draft))
        and "http" not in rewrite
        and "#" not in rewrite
    )


def write_with_luna(
    client: httpx.Client, insight: Insight, *, api_key: str, max_chars: int
) -> str:
    """Luna's rewrite of the template text, or the template if it fails."""
    if insight.kind.startswith("top_papers"):
        return insight.text  # a list reads best as is
    facts = json.dumps(insight.facts, ensure_ascii=False)
    try:
        response = client.post(
            RESPONSES_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": LUNA_MODEL,
                "instructions": LUNA_INSTRUCTIONS,
                "input": (
                    f"Character limit: {max_chars}\n\nDraft:\n{insight.text}\n\n"
                    f"Facts:\n{facts}"
                ),
                "store": False,
                "max_output_tokens": 300,
                "reasoning": {"effort": "none"},
                "prompt_cache_key": "pwc-x-insight-v1",
            },
        )
        body = response.raise_for_status().json()
        rewrite = "".join(
            part["text"]
            for item in body["output"]
            if item.get("type") == "message"
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        ).strip()
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        logger.warning("x_insight_rewrite_failed kind=%s %s", insight.kind, error)
        return insight.text
    rewrite = paragraphs(rewrite)
    if accept_rewrite(insight.text, rewrite, facts=facts, max_chars=max_chars):
        return rewrite
    logger.warning("x_insight_rewrite_rejected kind=%s", insight.kind)
    return insight.text


# --- Posting --------------------------------------------------------------


@dataclass
class InsightReport:
    dry_run: bool
    kind: str | None = None
    subject_key: str | None = None
    text: str | None = None
    template: str | None = None
    url: str | None = None
    post_id: str | None = None
    reply_id: str | None = None
    tried: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def post_insight(
    db: Session,
    *,
    poster: XPoster | None,
    kinds: list[str],
    write: Callable[[Insight], str],
    max_chars: int,
    now: datetime | None = None,
    save_image: Callable[[bytes], None] | None = None,
) -> InsightReport:
    """Post the first kind in `kinds` that has something new to say."""
    now = now or datetime.now(UTC)
    report = InsightReport(dry_run=poster is None)
    for kind in kinds:
        report.tried.append(kind)
        insight = BUILDERS[kind](db, now)
        if insight is None:
            continue
        if weighted_length(insight.text) > max_chars:
            logger.warning("x_insight_template_too_long kind=%s", kind)
            continue
        report.kind, report.subject_key = insight.kind, insight.subject_key
        report.template, report.url = insight.text, insight.link
        report.text = write(insight)
        if save_image:
            save_image(insight.image)
        if poster is None:
            return report
        media_id = poster.upload_image(insight.image)
        report.post_id = poster.post(report.text, media_ids=[media_id])
        record = XInsightPost(
            kind=insight.kind,
            subject_key=insight.subject_key,
            post_id=report.post_id,
            posted_at=now,
        )
        db.add(record)
        db.commit()
        report.reply_id = poster.post(insight.link, reply_to=report.post_id)
        record.reply_id = report.reply_id
        db.commit()
        return report
    return report
