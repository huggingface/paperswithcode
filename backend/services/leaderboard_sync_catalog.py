"""Catalog lookups shared by the live leaderboard syncs.

A sync resolves its board (task, benchmark, linked metrics) and the papers
behind its reviewed model identities here. These helpers only read the
catalog and never create papers.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from backend.models.database import Dataset, Metric, Paper, Task, TaskDatasetMetric


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


def resolve_leaderboard(
    db: Session,
    source: str,
    task_slug: str,
    dataset_slug: str,
    metric_names: Iterable[str],
) -> tuple[Task, Dataset]:
    """Return a board's task and benchmark, failing unless every metric is linked."""
    task = db.query(Task).filter(Task.slug == task_slug).one_or_none()
    dataset = db.query(Dataset).filter(Dataset.slug == dataset_slug).one_or_none()
    if task is None or dataset is None:
        raise RuntimeError(f"{source} task or benchmark is not configured")
    wanted = set(metric_names)
    linked = {
        name
        for (name,) in db.query(Metric.name)
        .join(TaskDatasetMetric, TaskDatasetMetric.metric_id == Metric.id)
        .filter(
            TaskDatasetMetric.task_id == task.id,
            TaskDatasetMetric.dataset_id == dataset.id,
            Metric.name.in_(wanted),
        )
        .all()
    }
    if missing := sorted(wanted - linked):
        raise RuntimeError(
            f"{source} metrics are not linked to the task: {', '.join(missing)}"
        )
    return task, dataset


def resolve_identity_papers(
    db: Session, identities: Iterable[ModelIdentity]
) -> dict[str, int]:
    """Map each reviewed ``paper_key`` to its paper; never create papers."""
    identities = list(identities)
    arxiv_ids = {i.arxiv_id for i in identities if i.arxiv_id}
    source_urls = {i.source_url for i in identities if i.source_url}
    papers = (
        db.query(Paper.id, Paper.arxiv_id, Paper.source_url)
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


def score_matches(stored: Any, published: Decimal) -> bool:
    """A stored value is current when it rounds to the published one.

    Reviewers sometimes import an unrounded value (48.23) that the board lists
    at lower precision (48.2); that is not a revision.
    """
    if isinstance(stored, bool) or not isinstance(stored, (int, float)):
        return False
    exponent = published.as_tuple().exponent
    places = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    return Decimal(str(stored)).quantize(Decimal(1).scaleb(-places)) == published
