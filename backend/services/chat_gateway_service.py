"""Allowlisted read-only catalog operations for the private chat gateway."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.services.dataset_service import DatasetService
from backend.services.paper_lineage_service import get_paper_lineage
from backend.services.paper_markdown_service import read_paper_markdown
from backend.services.paper_service import PaperService
from backend.models.database import Task

CATALOG_OPERATIONS = frozenset(
    {
        "search",
        "paper_info",
        "paper_read",
        "paper_list",
        "paper_recent",
        "paper_trending",
        "paper_related",
        "paper_lineage_list",
        "benchmark_list",
    }
)


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_dump(item) for item in value]
    return value


def _boolean(value: Any) -> bool:
    return value is True or (
        isinstance(value, str) and value.strip().lower() in {"1", "true", "yes"}
    )


class ChatGatewayService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def catalog(self, operation: str, arguments: dict[str, Any]) -> Any:
        if operation not in CATALOG_OPERATIONS:
            raise ValueError("Unsupported catalog operation")
        paper = PaperService(self.db)
        if operation == "search":
            return _dump(
                paper.search_papers_page(
                    str(arguments["query"])[:300],
                    max(1, min(int(arguments.get("page", 1)), 100)),
                    max(1, min(int(arguments.get("limit", 10)), 100)),
                    mode=arguments.get("mode"),
                )
            )
        if operation == "paper_info":
            return _dump(
                paper.get_paper_by_id_or_arxiv(
                    str(arguments["paper"])[:200],
                    include_resources=_boolean(arguments.get("include_resources")),
                )
            )
        if operation == "paper_read":
            markdown = read_paper_markdown(
                str(arguments["paper"])[:64],
                bucket_id=self.settings.paper_markdown_hf_bucket_id,
                token=self.settings.hf_token or None,
            )
            return {"markdown": markdown[: 256 * 1024]}
        if operation == "paper_list":
            return _dump(
                paper.get_papers(
                    page=max(1, min(int(arguments.get("page", 1)), 100)),
                    page_size=max(1, min(int(arguments.get("page_size", 20)), 100)),
                    search=arguments.get("search"),
                    published_after=arguments.get("published_after"),
                    published_before=arguments.get("published_before"),
                    conference=arguments.get("conference"),
                    latest_only=not _boolean(arguments.get("all_versions")),
                    order_by=arguments.get("order_by", "trending"),
                    order_dir=arguments.get("order_dir", "desc"),
                    time_window=arguments.get("time", "all_time"),
                    include_resources=_boolean(arguments.get("include_resources")),
                )
            )
        if operation == "paper_recent":
            return _dump(
                paper.get_recent_papers(
                    max(1, min(int(arguments.get("limit", 10)), 100))
                )
            )
        if operation == "paper_trending":
            return _dump(
                paper.get_papers(
                    page=1,
                    page_size=max(1, min(int(arguments.get("limit", 20)), 100)),
                    latest_only=True,
                    order_by="trending",
                    order_dir="desc",
                    time_window="all_time",
                )
            )
        if operation == "paper_related":
            return _dump(
                paper.get_related_papers(
                    str(arguments["paper"])[:200],
                    max(1, min(int(arguments.get("limit", 4)), 20)),
                )
            )
        if operation == "paper_lineage_list":
            return get_paper_lineage(self.db, str(arguments["paper"])[:200]).to_dict()
        if operation == "benchmark_list":
            task_id = None
            task = arguments.get("task")
            if task is not None:
                try:
                    task_id = int(task)
                except (TypeError, ValueError):
                    task_id = (
                        self.db.query(Task.id)
                        .filter(Task.slug == str(task)[:255])
                        .scalar()
                    )
            open_value = arguments.get("is_open")
            is_open = (
                open_value
                if isinstance(open_value, bool)
                else {"true": True, "false": False}.get(str(open_value).lower())
                if open_value is not None
                else None
            )
            return _dump(
                DatasetService(self.db).get_datasets(
                    page=max(1, min(int(arguments.get("page", 1)), 100)),
                    page_size=max(1, min(int(arguments.get("page_size", 50)), 100)),
                    search=arguments.get("search"),
                    task_id=task_id,
                    include_descendants=_boolean(arguments.get("include_descendants")),
                    order_by=arguments.get("order_by", "name"),
                    order_dir=arguments.get("order_dir", "asc"),
                    min_eval_count=(
                        max(1, int(arguments["min_eval_count"]))
                        if arguments.get("min_eval_count") is not None
                        else None
                    ),
                    is_open=is_open,
                )
            )
        raise ValueError("Catalog operation is not available through this gateway")
