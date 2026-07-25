"""Parser registration and handlers for taxonomy and benchmark administration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.database.connection import db_manager
from backend.services.benchmark_admin_service import add_benchmark
from backend.services.dataset_service import DatasetService
from backend.services.metric_admin_service import add_or_update_metric
from backend.services.task_admin_service import add_or_update_task


def register_admin_commands(commands) -> None:
    task = commands.add_parser("task", help="Manage task taxonomy rows")
    task_commands = task.add_subparsers(dest="task_command", required=True)
    task_add = task_commands.add_parser("add", help="Idempotently add or update a task")
    task_add.add_argument("slug")
    task_add.add_argument("--name", required=True)
    task_description = task_add.add_mutually_exclusive_group(required=True)
    task_description.add_argument("--description")
    task_description.add_argument("--description-file", type=Path)
    task_add.add_argument("--keywords", required=True)
    task_add.add_argument("--area", required=True)
    task_add.add_argument("--parent", help="Existing parent task slug or ID")
    task_add.add_argument("--hidden", action="store_true")
    task_add.add_argument("--json", action="store_true")
    task_add.set_defaults(handler=add_task)

    metric = commands.add_parser("metric", help="Manage evaluation metrics")
    metric_commands = metric.add_subparsers(dest="metric_command", required=True)
    metric_add = metric_commands.add_parser(
        "add", help="Idempotently create or update a metric definition"
    )
    metric_add.add_argument("name")
    metric_add.add_argument(
        "--direction",
        required=True,
        choices=["higher_is_better", "lower_is_better"],
    )
    metric_add.add_argument("--full-name")
    metric_add.add_argument("--scale")
    metric_add.add_argument("--description")
    metric_add.add_argument("--json", action="store_true")
    metric_add.set_defaults(handler=add_metric_command)

    benchmark = commands.add_parser("benchmark", help="Manage benchmark datasets")
    benchmark_commands = benchmark.add_subparsers(
        dest="benchmark_command", required=True
    )
    benchmark_add = benchmark_commands.add_parser(
        "add", help="Idempotently create and configure a benchmark"
    )
    benchmark_add.add_argument("name")
    benchmark_description = benchmark_add.add_mutually_exclusive_group(required=True)
    benchmark_description.add_argument("--description")
    benchmark_description.add_argument("--description-file", type=Path)
    benchmark_add.add_argument(
        "--task", action="append", required=True, help="Existing task slug or ID"
    )
    benchmark_add.add_argument(
        "--metric", action="append", required=True, help="Existing metric name"
    )
    benchmark_add.add_argument(
        "--source-paper",
        required=True,
        help="PwC URL, ArXiv ID, or numeric external-paper ID",
    )
    benchmark_add.add_argument("--full-name")
    benchmark_add.add_argument("--url")
    benchmark_add.add_argument("--hf-url")
    benchmark_add.add_argument("--homepage")
    benchmark_add.add_argument("--supports-harness", action="store_true")
    benchmark_add.add_argument("--json", action="store_true")
    benchmark_add.set_defaults(handler=add_benchmark_command)

    benchmark_list = benchmark_commands.add_parser(
        "list", help="List and filter benchmark datasets"
    )
    benchmark_list.add_argument("--page", type=int, default=1)
    benchmark_list.add_argument("--page-size", type=int, default=50)
    benchmark_list.add_argument("--search")
    benchmark_list.add_argument("--name")
    benchmark_list.add_argument("--full-name")
    benchmark_list.add_argument("--task")
    benchmark_list.add_argument("--include-descendants", action="store_true")
    benchmark_list.add_argument("--min-eval-count", type=int)
    benchmark_list.add_argument(
        "--is-open", choices=["true", "false"], help="Filter best-model selection"
    )
    benchmark_list.add_argument(
        "--order-by",
        choices=["name", "full_name", "created_at", "paper_count"],
        default="name",
    )
    benchmark_list.add_argument("--order-dir", choices=["asc", "desc"], default="asc")
    benchmark_list.add_argument("--json", action="store_true")
    benchmark_list.set_defaults(handler=list_benchmarks)


def add_task(args: argparse.Namespace) -> int:
    description = args.description
    if args.description_file:
        description = args.description_file.read_text(encoding="utf-8").strip()
    with db_manager.session_local() as db:
        result = add_or_update_task(
            db,
            slug=args.slug,
            name=args.name,
            description=description,
            keywords=args.keywords,
            area_name=args.area,
            parent_reference=args.parent,
            is_visible=not args.hidden,
        )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        hierarchy = result.parent_slug or "top-level"
        print(
            f"{result.status}: task={result.slug} id={result.id} "
            f"area={result.area} parent={hierarchy} level={result.level}"
        )
        print(f"https://paperswithcode.co/tasks/{result.slug}")
    return 0


def add_benchmark_command(args: argparse.Namespace) -> int:
    description = args.description
    if args.description_file:
        description = args.description_file.read_text(encoding="utf-8").strip()
    with db_manager.session_local() as db:
        result = add_benchmark(
            db,
            name=args.name,
            description=description,
            task_references=args.task,
            metric_names=args.metric,
            source_paper=args.source_paper,
            full_name=args.full_name,
            url=args.url,
            hf_url=args.hf_url,
            homepage=args.homepage,
            supports_harness=args.supports_harness,
        )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(
            f"{result.status}: benchmark={result.slug} id={result.id} "
            f"tasks={','.join(result.tasks)} metrics={','.join(result.metrics)} "
            f"source={result.source_url}"
        )
        print(f"https://paperswithcode.co/benchmark/{result.slug}")
    return 0


def add_metric_command(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        result = add_or_update_metric(
            db,
            name=args.name,
            direction=args.direction,
            full_name=args.full_name,
            scale=args.scale,
            description=args.description,
        )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(
            f"{result.status}: metric={result.name} id={result.id} "
            f"direction={result.direction} scale={result.scale or '-'}"
        )
    return 0


def list_benchmarks(args: argparse.Namespace) -> int:
    if args.page < 1 or not 1 <= args.page_size <= 100:
        raise ValueError("--page must be positive and --page-size must be 1-100")
    if args.min_eval_count is not None and args.min_eval_count < 1:
        raise ValueError("--min-eval-count must be positive")
    with db_manager.session_local() as db:
        task_id = None
        if args.task:
            try:
                task_id = int(args.task)
            except ValueError:
                from backend.models.database import Task

                task = db.query(Task).filter(Task.slug == args.task).first()
                if task is None:
                    raise ValueError(f"Task not found: {args.task}")
                task_id = task.id

        service = DatasetService(db)
        is_open = None if args.is_open is None else args.is_open == "true"
        if args.search:
            page = service.search_datasets(
                query=args.search,
                page=args.page,
                page_size=args.page_size,
                task_id=task_id,
                include_descendants=args.include_descendants,
                min_eval_count=args.min_eval_count,
                is_open=is_open,
            )
        else:
            page = service.get_datasets(
                page=args.page,
                page_size=args.page_size,
                name=args.name,
                full_name=args.full_name,
                task_id=task_id,
                include_descendants=args.include_descendants,
                order_by=args.order_by,
                order_dir=args.order_dir,
                min_eval_count=args.min_eval_count,
                is_open=is_open,
            )
    if args.json:
        print(json.dumps(page.model_dump(mode="json"), indent=2))
    else:
        print(f"{page.count} benchmarks")
        for benchmark in page.results:
            details = f" ({benchmark.full_name})" if benchmark.full_name else ""
            print(f"{benchmark.id}\t{benchmark.name}{details}")
    return 0
