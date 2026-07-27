"""Explicit read-only parser and deterministic compact output."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from typing import Any, Callable
from urllib.parse import quote

from pwc_cli import API_CONTRACT_VERSION, __version__
from pwc_cli.transport import Client, ResponseError, TransportError

Handler = Callable[[argparse.Namespace, Client], int]


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}; run '{self.prog} --help'\n")


def _bounded(value: int, minimum: int, maximum: int, flag: str) -> int:
    if not minimum <= value <= maximum:
        raise argparse.ArgumentTypeError(f"{flag} must be {minimum}-{maximum}")
    return value


def _limit(maximum: int = 100):
    return lambda value: _bounded(int(value), 1, maximum, "--limit")


def _page(value: str) -> int:
    return _bounded(int(value), 1, 100, "--page")


def _page_size(value: str) -> int:
    return _bounded(int(value), 1, 100, "--page-size")


def _clean(value: object) -> str:
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def _rows(payload: Any) -> tuple[list[dict[str, Any]], int | None]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)], None
    if not isinstance(payload, dict):
        raise ResponseError("API returned an unexpected response shape")
    values = payload.get("results")
    if values is None:
        values = payload.get("items")
    if not isinstance(values, list):
        raise ResponseError("API response did not contain a result list")
    total = payload.get("count") or payload.get("total")
    return [item for item in values if isinstance(item, dict)], int(
        total
    ) if total is not None else None


def _paper_id(item: dict[str, Any]) -> str:
    return _clean(item.get("arxiv_id") or item.get("id"))


def _paper_rows(items: list[dict[str, Any]]) -> None:
    print("id\ttitle\tyear\tcitations")
    for item in items:
        published = _clean(item.get("published") or item.get("date_published"))
        print(
            "\t".join(
                (
                    _paper_id(item),
                    _clean(item.get("title")),
                    published[:4],
                    _clean(item.get("citation_count")),
                )
            )
        )


def _emit_page(
    payload: Any,
    args: argparse.Namespace,
    renderer: Callable[[list[dict[str, Any]]], None],
) -> int:
    if args.json:
        print(
            json.dumps(
                {"schema_version": API_CONTRACT_VERSION, "data": payload},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 0
    items, total = _rows(payload)
    renderer(items)
    page = getattr(args, "page", 1)
    page_size = getattr(args, "page_size", getattr(args, "limit", len(items) or 1))
    if total is not None and page * page_size < total:
        print(f"# more: rerun with --page {page + 1}", file=sys.stderr)
    return 0


def search(args: argparse.Namespace, client: Client) -> int:
    payload = client.get(
        "papers/search",
        {
            "q": args.query,
            "page": args.page,
            "page_size": args.limit,
            "mode": args.mode,
        },
    ).json()
    return _emit_page(payload, args, _paper_rows)


def paper_info(args: argparse.Namespace, client: Client) -> int:
    payload = client.get(
        f"papers/{args.paper}", {"include_resources": args.include_resources}
    ).json()
    if args.json:
        print(
            json.dumps(
                {"schema_version": API_CONTRACT_VERSION, "data": payload},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 0
    fields = (
        ("id", payload.get("arxiv_id") or payload.get("id")),
        ("title", payload.get("title")),
        ("published", payload.get("published")),
        ("authors", ", ".join(payload.get("authors") or [])),
        ("conference", payload.get("conference_name") or payload.get("conference")),
        ("citations", payload.get("citation_count")),
        ("url", payload.get("url_abs") or payload.get("source_url")),
    )
    for label, value in fields:
        if value not in (None, "", []):
            print(f"{label}: {_clean(value)}")
    return 0


def paper_read(args: argparse.Namespace, client: Client) -> int:
    response = client.get(f"research/papers/{args.paper}/read")
    markdown = response.body.decode("utf-8", errors="replace")
    if args.json:
        print(
            json.dumps(
                {
                    "schema_version": API_CONTRACT_VERSION,
                    "data": {"paper": args.paper, "markdown": markdown},
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 0
    sys.stdout.write(markdown)
    if markdown and not markdown.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def paper_list(args: argparse.Namespace, client: Client) -> int:
    payload = client.get(
        "papers/",
        {
            "page": args.page,
            "page_size": args.page_size,
            "search": args.search,
            "published_after": args.published_after,
            "published_before": args.published_before,
            "conference": args.conference,
            "latest_only": not args.all_versions,
            "order_by": args.order_by,
            "order_dir": args.order_dir,
            "time": args.time,
            "include_resources": args.include_resources,
        },
    ).json()
    return _emit_page(payload, args, _paper_rows)


def paper_recent(args: argparse.Namespace, client: Client) -> int:
    return _emit_page(
        client.get("papers/recent", {"limit": args.limit}).json(), args, _paper_rows
    )


def paper_trending(args: argparse.Namespace, client: Client) -> int:
    return _emit_page(
        client.get(
            "papers/trending",
            {
                "limit": args.limit,
                "max_age_days": args.max_age_days,
                "min_velocity": args.min_velocity,
            },
        ).json(),
        args,
        _paper_rows,
    )


def paper_related(args: argparse.Namespace, client: Client) -> int:
    return _emit_page(
        client.get(f"papers/{args.paper}/related", {"limit": args.limit}).json(),
        args,
        _paper_rows,
    )


def paper_lineage(args: argparse.Namespace, client: Client) -> int:
    payload = client.get(f"research/papers/{args.paper}/lineage").json()
    if args.json:
        print(
            json.dumps(
                {"schema_version": API_CONTRACT_VERSION, "data": payload},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 0
    paper = payload.get("paper") or {}
    print(f"paper: {_clean(paper.get('reference'))}\t{_clean(paper.get('title'))}")
    for relationship in ("predecessors", "successors"):
        for item in payload.get(relationship) or []:
            print(
                f"{relationship[:-1]}: {_clean(item.get('reference'))}"
                f"\t{_clean(item.get('title'))}"
            )
    return 0


def benchmark_list(args: argparse.Namespace, client: Client) -> int:
    if args.task and args.order_by in (None, "trending"):
        trend_payload = client.get(
            f"tasks/{quote(args.task, safe='')}/trending-benchmarks",
            {
                "limit": 100,
                "min_recent_papers": 0,
                "include_descendants": args.include_descendants,
                "is_open": args.is_open,
            },
        ).json()
        if not isinstance(trend_payload, dict) or not isinstance(
            trend_payload.get("results"), list
        ):
            raise ResponseError("API response did not contain benchmark trends")
        items = [
            item
            for item in trend_payload["results"]
            if isinstance(item, dict)
            and (
                not args.search
                or args.search.casefold()
                in " ".join(
                    str(item.get(field) or "")
                    for field in ("name", "full_name", "slug")
                ).casefold()
            )
            and (
                args.min_eval_count is None
                or int(item.get("all_time_paper_count") or 0) >= args.min_eval_count
            )
        ]
        start = (args.page - 1) * args.page_size
        payload = {
            **trend_payload,
            "count": len(items),
            "results": items[start : start + args.page_size],
        }

        def render_trends(rows: list[dict[str, Any]]) -> None:
            print("id\tname\trecent_papers\ttrend_score\tbest_model")
            for item in rows:
                print(
                    "\t".join(
                        (
                            _clean(item.get("id")),
                            _clean(item.get("name")),
                            _clean(item.get("recent_paper_count")),
                            _clean(item.get("trend_score")),
                            _clean(item.get("best_model_name")),
                        )
                    )
                )

        return _emit_page(payload, args, render_trends)

    if args.order_by == "trending":
        raise ResponseError("--order-by trending requires --task")
    ordering = f"-{args.order_by}" if args.order_dir == "desc" else args.order_by
    payload = client.get(
        "datasets/",
        {
            "page": args.page,
            "page_size": args.page_size,
            "q": args.search,
            "task": args.task,
            "include_descendants": args.include_descendants,
            "min_eval_count": args.min_eval_count,
            "is_open": args.is_open,
            "ordering": ordering or "name",
        },
    ).json()

    def render(items: list[dict[str, Any]]) -> None:
        print("id\tname\tfull_name\tevals")
        for item in items:
            print(
                "\t".join(
                    (
                        _clean(item.get("id")),
                        _clean(item.get("name")),
                        _clean(item.get("full_name")),
                        _clean(item.get("paper_count")),
                    )
                )
            )

    return _emit_page(payload, args, render)


def _benchmark_match(name: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    target = name.strip().casefold()
    for field in ("name", "full_name", "slug", "id"):
        for item in items:
            if str(item.get(field) or "").strip().casefold() == target:
                return item
    return None


def _merged_evaluations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    for item in items:
        key = tuple(
            str(item.get(field) or "")
            for field in (
                "paper_id",
                "task_id",
                "dataset_id",
                "model_name",
                "harness",
            )
        )
        existing = merged.get(key)
        if existing is None:
            existing = {**item, "metrics": dict(item.get("metrics") or {})}
            merged[key] = existing
            continue
        existing["metrics"].update(item.get("metrics") or {})
        ranks = [
            rank
            for rank in (existing.get("best_rank"), item.get("best_rank"))
            if isinstance(rank, int)
        ]
        existing["best_rank"] = min(ranks) if ranks else None
        if not existing.get("best_metric") and item.get("best_metric"):
            existing["best_metric"] = item["best_metric"]
    return sorted(
        merged.values(),
        key=lambda item: (
            item.get("best_rank")
            if isinstance(item.get("best_rank"), int)
            else sys.maxsize,
            str(item.get("model_name") or "").casefold(),
            str(item.get("paper_id") or ""),
        ),
    )


def _markdown_text(value: object) -> str:
    return (
        str(value or "—")
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _metric_summary(item: dict[str, Any]) -> str:
    metrics = item.get("metrics") or {}
    if not isinstance(metrics, dict) or not metrics:
        return "—"
    best_metric = item.get("best_metric")
    names = sorted(
        metrics,
        key=lambda name: (
            0 if name == best_metric else 1,
            str(name).casefold(),
        ),
    )
    return ", ".join(f"{name}: {metrics[name]}" for name in names)


def _paper_markdown(item: dict[str, Any]) -> str:
    title = _markdown_text(
        item.get("paper_title")
        or item.get("paper_arxiv_id")
        or f"Paper {item.get('paper_id')}"
    )
    reference = item.get("paper_arxiv_id") or item.get("paper_id")
    if not reference:
        return title
    url = f"https://paperswithcode.co/paper/{quote(str(reference), safe='.')}"
    return f"[{title}]({url})"


def benchmark_detail(args: argparse.Namespace, client: Client) -> int:
    if not args.name:
        raise ResponseError("benchmark inspection requires --name")
    search_payload = client.get(
        "datasets/",
        {"q": args.name, "page": 1, "page_size": 100},
    ).json()
    candidates, _total = _rows(search_payload)
    benchmark = _benchmark_match(args.name, candidates)
    if benchmark is None:
        suggestions = ", ".join(
            str(item.get("name")) for item in candidates[:3] if item.get("name")
        )
        suffix = f"; closest results: {suggestions}" if suggestions else ""
        raise ResponseError(f"Benchmark not found: {args.name}{suffix}")

    evaluations_payload = client.get(
        f"datasets/{quote(str(benchmark['id']), safe='')}/evaluations/",
        {
            "page": 1,
            "page_size": 100,
            "ordering": "best_rank",
            "is_open": args.is_open,
        },
    ).json()
    evaluations, total = _rows(evaluations_payload)
    rows = _merged_evaluations(evaluations)[: args.limit]
    data = {
        "benchmark": benchmark,
        "count": total if total is not None else len(evaluations),
        "results": rows,
    }
    if args.json:
        print(
            json.dumps(
                {"schema_version": API_CONTRACT_VERSION, "data": data},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 0

    title = _markdown_text(benchmark.get("name"))
    full_name = benchmark.get("full_name")
    print(f"# {title}")
    if full_name and str(full_name).casefold() != str(benchmark.get("name")).casefold():
        print(f"\n{_markdown_text(full_name)}")
    if benchmark.get("description"):
        print(f"\n{_markdown_text(benchmark['description'])}")
    slug = benchmark.get("slug") or benchmark.get("id")
    benchmark_url = f"https://paperswithcode.co/benchmark/{quote(str(slug), safe='-')}"
    print(f"\n[View benchmark]({benchmark_url})")
    print(f"\nTop {len(rows)} of {data['count']} evaluation rows.\n")
    print("| Rank | Model | Scores | Task | Paper | Published | Open |")
    print("| ---: | --- | --- | --- | --- | --- | :---: |")
    for item in rows:
        model = item.get("model_name") or "—"
        if item.get("harness"):
            model = f"{model} ({item['harness']})"
        print(
            "| "
            + " | ".join(
                (
                    _markdown_text(item.get("best_rank")),
                    _markdown_text(model),
                    _markdown_text(_metric_summary(item)),
                    _markdown_text(item.get("task_name")),
                    _paper_markdown(item),
                    _markdown_text(item.get("paper_published_date")),
                    "yes" if item.get("is_open", True) else "no",
                )
            )
            + " |"
        )
    return 0


def version(_args: argparse.Namespace, _client: Client) -> int:
    print(f"pwc {__version__}\tapi {API_CONTRACT_VERSION}")
    return 0


def _json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json", action="store_true", help="emit stable versioned JSON"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(
        prog="pwc",
        description="Read-only Papers With Code research CLI",
        epilog=(
            'Examples:\n  pwc search "small VLMs" --limit 10\n'
            "  pwc paper info 2501.01234\n"
            "  pwc benchmark list --task OCR\n"
            '  pwc benchmark --name "SWE-Bench Pro"'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"pwc {__version__}\tapi {API_CONTRACT_VERSION}",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    search_parser = commands.add_parser(
        "search",
        help="search papers",
        description="Search the paper catalog. Default output is compact TSV.",
    )
    search_parser.add_argument("query", help="title, topic, author, or ArXiv ID")
    search_parser.add_argument(
        "--limit",
        type=_limit(),
        default=10,
        help="results per page, 1-100 (default: 10)",
    )
    search_parser.add_argument(
        "--page", type=_page, default=1, help="page, 1-100 (default: 1)"
    )
    search_parser.add_argument(
        "--mode", choices=("hybrid", "keyword", "semantic"), default="hybrid"
    )
    _json(search_parser)
    search_parser.set_defaults(handler=search)

    paper = commands.add_parser("paper", help="inspect papers")
    paper_commands = paper.add_subparsers(dest="paper_command", required=True)
    info = paper_commands.add_parser("info", help="show concise paper metadata")
    info.add_argument("paper", help="ArXiv ID or external-paper numeric ID")
    info.add_argument("--include-resources", action="store_true")
    _json(info)
    info.set_defaults(handler=paper_info)
    read = paper_commands.add_parser("read", help="print stored paper Markdown")
    read.add_argument("paper", help="modern ArXiv ID")
    _json(read)
    read.set_defaults(handler=paper_read)
    listing = paper_commands.add_parser("list", help="list and filter papers")
    listing.add_argument("--page", type=_page, default=1)
    listing.add_argument("--page-size", type=_page_size, default=20)
    listing.add_argument("--search")
    listing.add_argument("--published-after", type=date.fromisoformat)
    listing.add_argument("--published-before", type=date.fromisoformat)
    listing.add_argument("--conference")
    listing.add_argument("--all-versions", action="store_true")
    listing.add_argument(
        "--order-by",
        choices=("trending", "date_published", "citation_count"),
        default="trending",
    )
    listing.add_argument("--order-dir", choices=("asc", "desc"), default="desc")
    listing.add_argument(
        "--time", choices=("today", "week", "month", "all_time"), default="all_time"
    )
    listing.add_argument("--include-resources", action="store_true")
    _json(listing)
    listing.set_defaults(handler=paper_list)
    for name, handler, default_limit, maximum in (
        ("recent", paper_recent, 10, 100),
        ("trending", paper_trending, 20, 100),
    ):
        leaf = paper_commands.add_parser(name, help=f"list {name} papers")
        leaf.add_argument("--limit", type=_limit(maximum), default=default_limit)
        if name == "trending":
            leaf.add_argument(
                "--max-age-days",
                type=lambda value: _bounded(int(value), 1, 365, "--max-age-days"),
                default=180,
            )
            leaf.add_argument("--min-velocity", type=float)
        _json(leaf)
        leaf.set_defaults(handler=handler)
    related = paper_commands.add_parser("related", help="list related papers")
    related.add_argument("paper", help="ArXiv or external paper ID")
    related.add_argument("--limit", type=_limit(20), default=4)
    _json(related)
    related.set_defaults(handler=paper_related)
    lineage = paper_commands.add_parser("lineage", help="inspect paper lineage")
    lineage_commands = lineage.add_subparsers(dest="lineage_command", required=True)
    lineage_list = lineage_commands.add_parser(
        "list", help="list predecessors and successors"
    )
    lineage_list.add_argument("paper", help="ArXiv or external paper ID")
    _json(lineage_list)
    lineage_list.set_defaults(handler=paper_lineage)

    benchmark = commands.add_parser("benchmark", help="inspect benchmarks")
    benchmark.add_argument(
        "--name", help="exact benchmark name, full name, slug, or ID"
    )
    benchmark.add_argument(
        "--limit",
        type=_limit(),
        default=20,
        help="maximum leaderboard rows, 1-100 (default: 20)",
    )
    benchmark.add_argument("--is-open", choices=("true", "false"))
    _json(benchmark)
    benchmark.set_defaults(handler=benchmark_detail)
    benchmark_commands = benchmark.add_subparsers(dest="benchmark_command")
    benchmarks = benchmark_commands.add_parser(
        "list", help="list and filter benchmarks"
    )
    benchmarks.add_argument("--page", type=_page, default=1)
    benchmarks.add_argument(
        "--page-size",
        "--limit",
        dest="page_size",
        type=_page_size,
        default=50,
        help="results per page, 1-100 (default: 50)",
    )
    benchmarks.add_argument("--search")
    benchmarks.add_argument("--task")
    benchmarks.add_argument("--include-descendants", action="store_true")
    benchmarks.add_argument("--min-eval-count", type=int)
    benchmarks.add_argument("--is-open", choices=("true", "false"))
    benchmarks.add_argument(
        "--order-by",
        choices=("trending", "name", "full_name", "created_at", "paper_count"),
        help="defaults to trending for task lists and name otherwise",
    )
    benchmarks.add_argument("--order-dir", choices=("asc", "desc"), default="asc")
    _json(benchmarks)
    benchmarks.set_defaults(handler=benchmark_list)
    version_parser = commands.add_parser(
        "version", help="show CLI and API contract versions"
    )
    version_parser.set_defaults(handler=version)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args, Client())
    except TransportError as error:
        print(f"pwc: {error}", file=sys.stderr)
        return 3
    except ResponseError as error:
        print(f"pwc: {error}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
