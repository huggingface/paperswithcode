"""Rule-based GitHub issue bodies for Papers with Code evaluation outreach."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable
from urllib.parse import urlparse

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.database import (
    Dataset,
    Evaluation,
    Metric,
    PaperRepository,
    Repository,
    Task,
)
from backend.services.contributor_evaluations import contributor_evaluation_ids
from backend.services.metric_value_service import parse_metric_value
from backend.utils.paper_reference import resolve_paper


SITE_ORIGIN = "https://paperswithcode.co"
ISSUE_TITLE = "Verify evals on Papers with Code"
ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth"}
MAX_RANKING_LINKS = 4
MAX_BADGES = 6
COUNT_WORDS = {
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}


@dataclass(frozen=True)
class PaperEvaluation:
    id: int
    paper_id: int
    task_id: int
    task_name: str
    task_slug: str
    dataset_id: int
    dataset_name: str
    dataset_slug: str
    model_name: str | None
    best_metric: str | None
    metrics: dict[str, Any]


@dataclass(frozen=True)
class RankingPlacement:
    evaluation_id: int
    task_slug: str
    dataset_name: str
    dataset_slug: str
    model_name: str | None
    metric_name: str
    rank: int
    leaderboard_entries: int


@dataclass(frozen=True)
class TaskLink:
    name: str
    slug: str
    evaluation_count: int


@dataclass(frozen=True)
class GithubIssueDraft:
    issue_title: str
    paper_id: str
    paper_title: str
    native_evaluation_count: int
    tasks: tuple[TaskLink, ...]
    ranking_placements: tuple[RankingPlacement, ...]
    official_repositories: tuple[str, ...]
    body: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_repository_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname not in {"github.com", "www.github.com"}:
        raise ValueError(f"Invalid GitHub repository URL: {url}")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub repository URL: {url}")
    return "/".join(parts[:2]).removesuffix(".git")


def compute_placement(
    target: PaperEvaluation,
    leaderboard_evaluations: Iterable[PaperEvaluation],
    metric_direction: str,
) -> RankingPlacement | None:
    """Compute competition rank for one exact task/dataset/metric leaderboard."""
    if not target.best_metric:
        return None
    target_score = parse_metric_value(target.metrics.get(target.best_metric))
    if target_score is None:
        return None

    scores = []
    for evaluation in leaderboard_evaluations:
        score = parse_metric_value(evaluation.metrics.get(target.best_metric))
        if score is not None:
            scores.append(score)
    if not scores:
        return None

    if metric_direction == "lower_is_better":
        better_count = sum(score < target_score for score in scores)
    else:
        better_count = sum(score > target_score for score in scores)

    return RankingPlacement(
        evaluation_id=target.id,
        task_slug=target.task_slug,
        dataset_name=target.dataset_name,
        dataset_slug=target.dataset_slug,
        model_name=target.model_name,
        metric_name=target.best_metric,
        rank=better_count + 1,
        leaderboard_entries=len(scores),
    )


def _markdown_list(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def render_task_sentence(tasks: tuple[TaskLink, ...]) -> str:
    if len(tasks) == 1:
        task = tasks[0]
        return (
            f"The paper is part of the [{task.name}]"
            f"({SITE_ORIGIN}/tasks/{task.slug}) task page."
        )

    displayed = tasks[:3]
    links = [f"[{task.name}]({SITE_ORIGIN}/tasks/{task.slug})" for task in displayed]
    if len(tasks) <= len(displayed):
        return f"The paper has results on {_markdown_list(links)} task pages."
    remaining = len(tasks) - len(displayed)
    page_noun = "page" if remaining == 1 else "pages"
    return (
        f"The paper has results on {', '.join(links)}, and {remaining} "
        f"additional task {page_noun}."
    )


def render_ranking_paragraphs(
    placements: Iterable[RankingPlacement],
    max_links: int = MAX_RANKING_LINKS,
) -> list[str]:
    """Group top-four, multi-entry placements into at most four links."""
    eligible = [
        placement
        for placement in placements
        if placement.rank in ORDINALS and placement.leaderboard_entries > 1
    ]
    eligible.sort(
        key=lambda item: (
            item.rank,
            item.model_name or "",
            item.dataset_name,
            item.metric_name,
            item.evaluation_id,
        )
    )

    grouped: dict[tuple[str | None, int], list[RankingPlacement]] = defaultdict(list)
    for placement in eligible:
        grouped[(placement.model_name, placement.rank)].append(placement)

    paragraphs = []
    remaining_links = max_links
    for (model_name, rank), group in grouped.items():
        if remaining_links == 0:
            break

        by_dataset: dict[tuple[str, str, str], list[RankingPlacement]] = defaultdict(
            list
        )
        for placement in group:
            by_dataset[
                (
                    placement.task_slug,
                    placement.dataset_slug,
                    placement.dataset_name,
                )
            ].append(placement)

        links = []
        included_rows = 0
        dataset_groups = sorted(
            by_dataset.items(),
            key=lambda item: (-len(item[1]), item[0][2], item[0][0]),
        )
        for (task_slug, dataset_slug, dataset_name), dataset_rows in dataset_groups:
            if remaining_links == 0:
                break
            representative = min(dataset_rows, key=lambda item: item.evaluation_id)
            label = dataset_name
            if len(dataset_rows) > 1:
                count = COUNT_WORDS.get(len(dataset_rows), str(len(dataset_rows)))
                label = f"{count} metrics on {dataset_name}"
            url = (
                f"{SITE_ORIGIN}/benchmark/{dataset_slug}"
                f"?task={task_slug}&eval={representative.evaluation_id}"
            )
            links.append(f"[{label}]({url})")
            included_rows += len(dataset_rows)
            remaining_links -= 1

        if not links:
            continue
        subject = f"The {model_name}" if model_name else "The reported"
        noun = "result" if included_rows == 1 else "results"
        verb = "ranks" if included_rows == 1 else "rank"
        paragraphs.append(
            f"{subject} {noun} currently {verb} {ORDINALS[rank]} on "
            f"{_markdown_list(links)}."
        )
    return paragraphs


def render_badge_markdown(
    paper_id: str,
    placements: Iterable[RankingPlacement],
    max_badges: int = MAX_BADGES,
) -> list[str]:
    """Render the same live, clickable top-three badges copied by the frontend."""
    eligible = sorted(
        (placement for placement in placements if placement.rank <= 3),
        key=lambda item: (
            item.rank,
            item.dataset_name,
            item.metric_name,
            item.evaluation_id,
        ),
    )
    badges = []
    seen_datasets = set()
    for placement in eligible:
        if placement.dataset_slug in seen_datasets:
            continue
        seen_datasets.add(placement.dataset_slug)
        placement_label = "SOTA" if placement.rank == 1 else f"#{placement.rank}"
        badge_url = (
            f"{SITE_ORIGIN}/api/v1/papers/{paper_id}/leaderboard-badge.svg"
            f"?eval={placement.evaluation_id}&live=1"
        )
        badge_link_url = (
            f"{SITE_ORIGIN}/api/v1/papers/{paper_id}/leaderboard-badge-link"
            f"?eval={placement.evaluation_id}"
        )
        alt = f"Papers with Code: {placement_label} on {placement.dataset_name}"
        badges.append(f"[![{alt}]({badge_url})]({badge_link_url})")
        if len(badges) == max_badges:
            break
    return badges


def outreach_signer() -> str:
    """Name that introduces and signs outreach issues (``PWC_GITHUB_OUTREACH_SIGNER``)."""
    signer = get_settings().github_outreach_signer.strip()
    if not signer:
        raise RuntimeError(
            "Evaluation outreach requires PWC_GITHUB_OUTREACH_SIGNER, the name "
            "that signs outreach issues"
        )
    return signer


def render_issue_body(
    paper_id: str,
    native_evaluation_count: int,
    tasks: tuple[TaskLink, ...],
    ranking_placements: tuple[RankingPlacement, ...],
    verified: bool,
) -> str:
    if native_evaluation_count < 1:
        raise ValueError("At least one paper-native evaluation is required")
    if not tasks:
        raise ValueError("At least one task is required")

    signer = outreach_signer()
    paper_url = f"{SITE_ORIGIN}/paper/{paper_id}"
    evaluation_noun = "evaluation" if native_evaluation_count == 1 else "evaluations"
    provenance = "verified paper-native" if verified else "paper-native"
    badges = render_badge_markdown(paper_id, ranking_placements)
    badge_paragraphs = []
    if badges:
        badge_paragraphs = [
            (
                "If you'd like to showcase the results in your repository README, "
                "you can copy these live leaderboard badges (or use the “Copy PwC "
                "badge” button in the Results section):"
            ),
            "\n".join(badges),
        ]
    paragraphs = [
        "Hi,",
        f"{signer} here from the open-source team at Hugging Face. Congratulations on your work!",
        (
            f"I've made the [paper]({paper_url}) and "
            f"[{native_evaluation_count} {provenance} {evaluation_noun}]"
            f"({paper_url}#results) available on Papers with Code."
        ),
        render_task_sentence(tasks),
        *render_ranking_paragraphs(ranking_placements),
        (
            "Would it be possible to verify these results and let me know if any "
            "score, model name, benchmark protocol, or openness metadata should be "
            "corrected?"
        ),
        (
            "You can also edit the task, methods, project page, and GitHub URL "
            "directly from the paper page using your Hugging Face account."
        ),
        *badge_paragraphs,
        "Kind regards,",
        signer,
    ]
    body = "\n\n".join(paragraphs)
    validate_issue_body(body, paper_id)
    return body


def validate_issue_body(body: str, paper_id: str) -> None:
    errors = []
    paper_url = f"{SITE_ORIGIN}/paper/{paper_id}"
    if "**" in body:
        errors.append("bold Markdown is not allowed")
    if "rank #" in body:
        errors.append("hash-form ranks are not allowed")
    if "only entry" in body.lower():
        errors.append("single-entry ranking claims are not allowed")
    if paper_url not in body or f"{paper_url}#results" not in body:
        errors.append("paper and results links are required")
    badge_count = body.count("/leaderboard-badge.svg")
    if badge_count > MAX_BADGES:
        errors.append("too many badges")
    if badge_count and "Copy PwC badge" not in body:
        errors.append("Copy PwC badge nudge is required when badges are present")
    if not badge_count and (
        "Copy PwC badge" in body or "View and copy the live badges" in body
    ):
        errors.append("badge messaging is not allowed without a live badge")
    if body.count(f"{SITE_ORIGIN}/benchmark/") > MAX_RANKING_LINKS + badge_count:
        errors.append("too many ranking links")
    if errors:
        raise ValueError("; ".join(errors))


def _evaluation_from_row(row: tuple[Evaluation, Task, Dataset]) -> PaperEvaluation:
    evaluation, task, dataset = row
    if not task.slug or not dataset.slug:
        raise ValueError(
            f"Evaluation {evaluation.id} has a task or dataset without a slug"
        )
    return PaperEvaluation(
        id=evaluation.id,
        paper_id=evaluation.paper_id,
        task_id=evaluation.task_id,
        task_name=task.name,
        task_slug=task.slug,
        dataset_id=evaluation.dataset_id,
        dataset_name=dataset.name,
        dataset_slug=dataset.slug,
        model_name=evaluation.model_name,
        best_metric=evaluation.best_metric,
        metrics=dict(evaluation.metrics or {}),
    )


def generate_github_issue_draft(
    db: Session,
    paper_reference: str,
    *,
    task_slug: str | None = None,
    verified: bool = False,
) -> GithubIssueDraft:
    """Generate a complete issue draft from current database state."""
    paper, route_id = resolve_paper(db, paper_reference)
    native_statement = (
        select(Evaluation, Task, Dataset)
        .join(Task, Task.id == Evaluation.task_id)
        .join(Dataset, Dataset.id == Evaluation.dataset_id)
        .where(Evaluation.paper_id == paper.id, ~Evaluation.external)
    )
    if task_slug:
        native_statement = native_statement.where(Task.slug == task_slug)
    native_rows = db.execute(
        native_statement.order_by(Task.name, Dataset.name, Evaluation.id)
    ).all()
    contributed = contributor_evaluation_ids(db)
    native_evaluations = [
        _evaluation_from_row(row) for row in native_rows if row[0].id not in contributed
    ]
    if not native_evaluations:
        scope = f" for task {task_slug}" if task_slug else ""
        if native_rows:
            raise ValueError(
                f"All paper-native evaluations{scope} came from contributors"
            )
        raise ValueError(f"No paper-native evaluations found{scope}")

    task_counts = Counter(
        (evaluation.task_name, evaluation.task_slug)
        for evaluation in native_evaluations
    )
    tasks = tuple(
        TaskLink(name=name, slug=slug, evaluation_count=count)
        for (name, slug), count in sorted(
            task_counts.items(), key=lambda item: (-item[1], item[0][0])
        )
    )

    pairs = {(item.task_id, item.dataset_id) for item in native_evaluations}
    pair_filter = or_(
        *(
            and_(Evaluation.task_id == task_id, Evaluation.dataset_id == dataset_id)
            for task_id, dataset_id in pairs
        )
    )
    leaderboard_rows = db.execute(
        select(Evaluation, Task, Dataset)
        .join(Task, Task.id == Evaluation.task_id)
        .join(Dataset, Dataset.id == Evaluation.dataset_id)
        .where(pair_filter)
    ).all()
    leaderboard_evaluations = [_evaluation_from_row(row) for row in leaderboard_rows]
    by_pair: dict[tuple[int, int], list[PaperEvaluation]] = defaultdict(list)
    for evaluation in leaderboard_evaluations:
        by_pair[(evaluation.task_id, evaluation.dataset_id)].append(evaluation)

    metric_names = {
        evaluation.best_metric
        for evaluation in native_evaluations
        if evaluation.best_metric
    }
    directions = {
        metric.name: metric.direction
        for metric in db.execute(
            select(Metric).where(Metric.name.in_(metric_names))
        ).scalars()
    }
    placements = tuple(
        placement
        for evaluation in native_evaluations
        if (
            placement := compute_placement(
                evaluation,
                by_pair[(evaluation.task_id, evaluation.dataset_id)],
                directions.get(evaluation.best_metric or "", "higher_is_better"),
            )
        )
        is not None
    )

    repository_rows = db.execute(
        select(Repository.url)
        .join(PaperRepository, PaperRepository.repository_id == Repository.id)
        .where(
            PaperRepository.paper_id == paper.id,
            PaperRepository.is_official,
        )
        .order_by(Repository.num_stars.desc(), Repository.url)
    ).scalars()
    github_repositories = []
    for url in repository_rows:
        try:
            github_repositories.append(normalize_repository_url(url))
        except ValueError:
            # A paper can also have official GitLab/Bitbucket or malformed links.
            # These are not GitHub outreach targets and do not invalidate its draft.
            continue
    repositories = tuple(dict.fromkeys(github_repositories))

    body = render_issue_body(
        route_id,
        len(native_evaluations),
        tasks,
        placements,
        verified,
    )
    return GithubIssueDraft(
        issue_title=ISSUE_TITLE,
        paper_id=route_id,
        paper_title=paper.title,
        native_evaluation_count=len(native_evaluations),
        tasks=tasks,
        ranking_placements=placements,
        official_repositories=repositories,
        body=body,
    )
