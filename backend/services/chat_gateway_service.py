"""Allowlisted read-only catalog operations for the private chat gateway."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import Task
from backend.services.area_service import AreaService
from backend.services.benchmark_trend_service import BenchmarkTrendService
from backend.services.conference_service import ConferenceService
from backend.services.dataset_service import DatasetService
from backend.services.evaluation_service import EvaluationService
from backend.services.framework_service import FrameworkService
from backend.services.method_service import MethodService
from backend.services.organization_service import OrganizationService
from backend.services.paper_lineage_service import get_paper_lineage
from backend.services.paper_markdown_service import read_paper_markdown_bounded
from backend.services.paper_service import PaperService
from backend.services.task_service import TaskService

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
        "paper_evaluations",
        "area_list",
        "area_tasks",
        "task_list",
        "task_detail",
        "task_page",
        "task_papers",
        "method_list",
        "method_detail",
        "conference_list",
        "conference_detail",
        "organization_list",
        "organization_detail",
        "framework_list",
        "benchmark_list",
        "benchmark_trending",
        "benchmark_evaluations",
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


def _optional_boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    return {"true": True, "false": False}.get(str(value).lower())


def _paper_date_range(arguments: dict[str, Any]) -> tuple[date | None, date | None]:
    start_date = (
        date.fromisoformat(str(arguments["start_date"]))
        if arguments.get("start_date")
        else None
    )
    end_date = (
        date.fromisoformat(str(arguments["end_date"]))
        if arguments.get("end_date")
        else None
    )
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must be on or before end_date")
    return start_date, end_date


class ChatGatewayService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def catalog(self, operation: str, arguments: dict[str, Any]) -> Any:
        if operation not in CATALOG_OPERATIONS:
            raise ValueError("Unsupported catalog operation")
        paper = PaperService(self.db)
        if operation == "search":
            start_date, end_date = _paper_date_range(arguments)
            return _dump(
                paper.search_papers_page(
                    str(arguments["query"])[:300],
                    max(1, min(int(arguments.get("page", 1)), 100)),
                    max(1, min(int(arguments.get("limit", 10)), 100)),
                    mode="keyword",
                    start_date=start_date,
                    end_date=end_date,
                )
            )
        if operation == "paper_info":
            include_resources = _boolean(arguments.get("include_resources"))
            result = _dump(
                paper.get_paper_by_id_or_arxiv(
                    str(arguments["paper"])[:200],
                    include_resources=include_resources,
                )
            )
            if include_resources:
                normalized = paper.get_linked_hf_artifact_urls(int(result["id"]))
                for field, urls in normalized.items():
                    result[field] = list(
                        dict.fromkeys([*(result.get(field) or []), *urls])
                    )
            return result
        if operation == "paper_read":
            markdown, truncated = read_paper_markdown_bounded(
                str(arguments["paper"])[:64],
                bucket_id=self.settings.paper_markdown_hf_bucket_id,
                token=self.settings.hf_token or None,
                max_bytes=256 * 1024,
            )
            return {"markdown": markdown, "truncated": truncated}
        if operation == "paper_list":
            start_date, end_date = _paper_date_range(arguments)
            return _dump(
                paper.get_papers(
                    page=max(1, min(int(arguments.get("page", 1)), 100)),
                    page_size=max(1, min(int(arguments.get("page_size", 20)), 100)),
                    search=arguments.get("search"),
                    start_date=start_date,
                    end_date=end_date,
                    conference=arguments.get("conference"),
                    authors=arguments.get("authors") or None,
                    **{
                        name: arguments[name]
                        for name in ("task", "method", "organization", "framework")
                        if arguments.get(name) is not None
                    },
                    latest_only=not _boolean(arguments.get("all_versions")),
                    order_by=arguments.get("order_by", "trending"),
                    order_dir=arguments.get("order_dir", "desc"),
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
        if operation == "paper_evaluations":
            ordering = str(arguments.get("ordering") or "-benchmark_popularity")
            order_by = ordering.lstrip("-")
            if order_by not in {
                "created_at",
                "best_rank",
                "evaluated_on",
                "benchmark_popularity",
            }:
                order_by = "benchmark_popularity"
            return _dump(
                EvaluationService(self.db).get_evaluations(
                    page=max(1, min(int(arguments.get("page", 1)), 100)),
                    page_size=max(1, min(int(arguments.get("page_size", 100)), 100)),
                    paper_id=int(arguments["paper"]),
                    order_by=order_by,
                    order_dir="desc" if ordering.startswith("-") else "asc",
                )
            )
        if operation == "area_list":
            ordering = str(arguments.get("ordering") or "name")
            return _dump(
                AreaService(self.db).get_areas(
                    page=max(1, min(int(arguments.get("page", 1)), 100)),
                    page_size=max(1, min(int(arguments.get("page_size", 50)), 500)),
                    order_by=ordering.lstrip("-"),
                    order_dir="desc" if ordering.startswith("-") else "asc",
                )
            )
        if operation == "area_tasks":
            return _dump(AreaService(self.db).get_areas_with_tasks())
        if operation == "task_list":
            ordering = str(arguments.get("ordering") or "name")
            area_id = arguments.get("area_id")
            level = arguments.get("level")
            return _dump(
                TaskService(self.db).get_tasks(
                    page=max(1, min(int(arguments.get("page", 1)), 100)),
                    page_size=max(1, min(int(arguments.get("page_size", 50)), 100)),
                    **(
                        {"search": arguments["q"]}
                        if arguments.get("q") is not None
                        else {}
                    ),
                    area_id=int(area_id) if area_id is not None else None,
                    level=int(level) if level is not None else None,
                    order_by=ordering.lstrip("-"),
                    order_dir="desc" if ordering.startswith("-") else "asc",
                )
            )
        if operation == "task_detail":
            task = str(arguments["task"])[:255]
            service = TaskService(self.db)
            return _dump(
                service.get_task_by_id(task)
                if task.isdigit()
                else service.get_task_by_slug(task)
            )
        if operation == "task_page":
            return _dump(
                TaskService(self.db).get_task_page(
                    str(arguments["task"])[:255],
                    is_open=_optional_boolean(arguments.get("is_open")),
                )
            )
        if operation == "task_papers":
            return _dump(
                TaskService(self.db).get_task_papers(
                    str(arguments["task"])[:255],
                    page=max(1, min(int(arguments.get("page", 1)), 100)),
                    page_size=max(1, min(int(arguments.get("page_size", 20)), 100)),
                    latest_only=not _boolean(arguments.get("all_versions")),
                    order_by=str(arguments.get("order_by") or "date_published"),
                    order_dir=str(arguments.get("order_dir") or "desc"),
                    include_resources=_boolean(arguments.get("include_resources")),
                )
            )
        if operation == "method_list":
            ordering = str(arguments.get("ordering") or "name")
            area_id = arguments.get("area_id")
            introduced_year = arguments.get("introduced_year")
            return _dump(
                MethodService(self.db).get_methods(
                    page=max(1, min(int(arguments.get("page", 1)), 100)),
                    page_size=max(1, min(int(arguments.get("page_size", 50)), 500)),
                    **(
                        {"search": arguments["q"]}
                        if arguments.get("q") is not None
                        else {}
                    ),
                    area_id=int(area_id) if area_id is not None else None,
                    introduced_year=(
                        int(introduced_year) if introduced_year is not None else None
                    ),
                    order_by=ordering.lstrip("-"),
                    order_dir="desc" if ordering.startswith("-") else "asc",
                )
            )
        if operation == "method_detail":
            method = str(arguments["method"])[:255]
            service = MethodService(self.db)
            return _dump(
                service.get_method_by_id(method)
                if method.isdigit()
                else service.get_method_by_name(method)
            )
        if operation == "conference_list":
            return _dump(ConferenceService(self.db).get_conferences())
        if operation == "conference_detail":
            return _dump(
                ConferenceService(self.db).get_conference(
                    str(arguments["conference"])[:255]
                )
            )
        if operation == "organization_list":
            return _dump(
                OrganizationService(self.db).get_organizations(
                    featured_only=_boolean(arguments.get("featured_only"))
                )
            )
        if operation == "organization_detail":
            return _dump(
                OrganizationService(self.db).get_organization(
                    str(arguments["organization"])[:255]
                )
            )
        if operation == "framework_list":
            return _dump(FrameworkService(self.db).get_catalog())
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
            is_open = _optional_boolean(arguments.get("is_open"))
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
        if operation == "benchmark_trending":
            is_open = _optional_boolean(arguments.get("is_open"))
            return _dump(
                BenchmarkTrendService(self.db).get_trending_benchmarks(
                    str(arguments["task"])[:255],
                    limit=max(1, min(int(arguments.get("limit", 100)), 100)),
                    min_recent_papers=max(
                        0, int(arguments.get("min_recent_papers", 0))
                    ),
                    include_descendants=_boolean(arguments.get("include_descendants")),
                    is_open=is_open,
                )
            )
        if operation == "benchmark_evaluations":
            is_open = _optional_boolean(arguments.get("is_open"))
            max_parameters_exclusive = arguments.get("max_parameters_exclusive")
            return _dump(
                EvaluationService(self.db).get_evaluations(
                    page=max(1, min(int(arguments.get("page", 1)), 100)),
                    page_size=max(1, min(int(arguments.get("page_size", 100)), 100)),
                    dataset_id=int(arguments["dataset"]),
                    is_open=is_open,
                    max_parameters_exclusive=(
                        int(max_parameters_exclusive)
                        if max_parameters_exclusive is not None
                        else None
                    ),
                    order_by="best_rank",
                    order_dir="asc",
                )
            )
        raise ValueError("Catalog operation is not available through this gateway")
