"""Explicit read-only parser and deterministic compact output."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable

from s2_cli import API_CONTRACT_VERSION, __version__
from s2_cli.resolve import (
    ResolvedPaper,
    arxiv_from_external_ids,
    encode_paper_path,
    resolve_paper,
)
from s2_cli.transport import (
    Client,
    MissingKeyError,
    NotFoundError,
    ResponseError,
    TransportError,
)

CITATIONS_HARD_CAP = 9999
DEFAULT_REF_FIELDS = (
    "citedPaper.paperId,citedPaper.title,citedPaper.year,"
    "citedPaper.citationCount,citedPaper.externalIds"
)
DEFAULT_CITATION_FIELDS = (
    "citingPaper.paperId,citingPaper.title,citingPaper.year,"
    "citingPaper.citationCount,citingPaper.externalIds"
)
DEFAULT_SEARCH_FIELDS = "title,year,citationCount,externalIds,url,authors,abstract"
Handler = Callable[[argparse.Namespace, Client], int]


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}; run '{self.prog} --help'\n")


def _bounded(value: int, minimum: int, maximum: int, flag: str) -> int:
    if not minimum <= value <= maximum:
        raise argparse.ArgumentTypeError(f"{flag} must be {minimum}-{maximum}")
    return value


def _limit(maximum: int) -> Callable[[str], int]:
    return lambda value: _bounded(int(value), 1, maximum, "--limit")


def _offset(value: str) -> int:
    return _bounded(int(value), 0, 100000, "--offset")


def _clean(value: object) -> str:
    return (
        str(value if value is not None else "")
        .replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def _emit_json(payload: Any, paper: ResolvedPaper | None = None) -> int:
    body: dict[str, Any] = {"schema_version": API_CONTRACT_VERSION, "data": payload}
    if paper is not None:
        body["paper"] = paper.as_dict()
    print(json.dumps(body, ensure_ascii=False, separators=(",", ":")))
    return 0


def _emit_jsonl(items: list[dict[str, Any]]) -> None:
    for item in items:
        print(json.dumps(item, ensure_ascii=False, separators=(",", ":")))


def _paper_from_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "paperId": item.get("paperId"),
        "title": item.get("title"),
        "year": item.get("year"),
        "citationCount": item.get("citationCount"),
        "arxiv": arxiv_from_external_ids(item.get("externalIds")),
    }


def _print_paper_rows(items: list[dict[str, Any]]) -> None:
    print("paperId\tyear\tcites\tarxiv\ttitle")
    for item in items:
        paper = _paper_from_item(item)
        print(
            "\t".join(
                (
                    _clean(paper.get("paperId")),
                    _clean(paper.get("year")),
                    _clean(paper.get("citationCount")),
                    _clean(paper.get("arxiv")),
                    _clean(paper.get("title")),
                )
            )
        )


def _print_header(paper: ResolvedPaper) -> None:
    if paper.title:
        print(
            "# paper:\t"
            + "\t".join(
                (
                    _clean(paper.title),
                    _clean(paper.id),
                    _clean(paper.arxiv),
                    _clean(paper.match_score),
                )
            ),
            file=sys.stderr,
        )
        return
    print(f"# paper:\t{_clean(paper.id)}", file=sys.stderr)


def _print_more(payload: dict[str, Any]) -> None:
    nxt = payload.get("next")
    if nxt is None or nxt == "":
        return
    print(f"# more: rerun with --offset {nxt}", file=sys.stderr)


def _select_items(
    args: argparse.Namespace, items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    selected = items
    if args.sort_by == "citation-count":
        selected = sorted(
            selected,
            key=lambda item: (
                item.get("citationCount")
                if isinstance(item.get("citationCount"), (int, float))
                else -1
            ),
            reverse=True,
        )
        print(
            "# scope: citation-count order applies only to the "
            f"{len(items)} results returned at offset {args.offset}; "
            "this is not a global citation ranking",
            file=sys.stderr,
        )
    if args.top is not None:
        selected = selected[: args.top]
    return selected


def _emit_items(args: argparse.Namespace, items: list[dict[str, Any]]) -> None:
    selected = _select_items(args, items)
    if args.jsonl:
        _emit_jsonl(selected)
    else:
        _print_paper_rows(selected)


def _edge_items(
    payload: Any, nested_key: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ResponseError("API returned an unexpected response shape")
    values = payload.get("data")
    if not isinstance(values, list):
        raise ResponseError("API response did not contain a result list")
    items = []
    for value in values:
        if not isinstance(value, dict):
            continue
        nested = value.get(nested_key)
        if isinstance(nested, dict) and nested.get("paperId"):
            items.append(nested)
    return items, payload


def search(args: argparse.Namespace, client: Client) -> int:
    payload = client.get(
        "paper/search",
        {
            "query": args.query,
            "limit": args.limit,
            "offset": args.offset,
            "year": args.year,
            "fields": args.fields or DEFAULT_SEARCH_FIELDS,
        },
    ).json()
    if args.json:
        return _emit_json(payload)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ResponseError("API response did not contain a result list")
    items = [item for item in payload["data"] if isinstance(item, dict)]
    _emit_items(args, items)
    _print_more(payload)
    return 0


def _graph_list(
    args: argparse.Namespace,
    client: Client,
    endpoint: str,
    nested_key: str,
    default_fields: str,
) -> int:
    if endpoint == "citations" and args.offset + args.limit > CITATIONS_HARD_CAP:
        print(
            "s2: error: --offset + --limit must be <= "
            f"{CITATIONS_HARD_CAP} for citations",
            file=sys.stderr,
        )
        return 2
    paper = resolve_paper(client, args.paper)
    payload = client.get(
        f"paper/{encode_paper_path(paper.id)}/{endpoint}",
        {
            "limit": args.limit,
            "offset": args.offset,
            "fields": args.fields or default_fields,
        },
    ).json()
    if args.json:
        return _emit_json(payload, paper)
    _print_header(paper)
    items, body = _edge_items(payload, nested_key)
    _emit_items(args, items)
    _print_more(body)
    return 0


def refs(args: argparse.Namespace, client: Client) -> int:
    return _graph_list(args, client, "references", "citedPaper", DEFAULT_REF_FIELDS)


def citations(args: argparse.Namespace, client: Client) -> int:
    return _graph_list(
        args, client, "citations", "citingPaper", DEFAULT_CITATION_FIELDS
    )


def version(_args: argparse.Namespace, _client: Client) -> int:
    print(f"s2 {__version__}\tapi {API_CONTRACT_VERSION}")
    return 0


def _output_flags(parser: argparse.ArgumentParser) -> None:
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--json", action="store_true", help="emit stable versioned JSON"
    )
    output.add_argument(
        "--jsonl",
        action="store_true",
        help="emit one unnested Semantic Scholar paper object per line",
    )
    parser.add_argument(
        "--sort-by",
        choices=("citation-count",),
        help="sort only the fetched page (not a global ranking)",
    )
    parser.add_argument(
        "--top",
        type=_limit(1000),
        help="return the first N sorted results; requires --sort-by",
    )


def _fields_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fields",
        help="Semantic Scholar fields override (comma-separated)",
    )


def _add_graph_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "paper",
        help="title, arXiv ID, DOI, Semantic Scholar paper ID, or URL",
    )
    parser.add_argument(
        "--limit",
        type=_limit(1000),
        default=20,
        help="results per page, 1-1000 (default: 20)",
    )
    parser.add_argument(
        "--offset",
        type=_offset,
        default=0,
        help="pagination offset (default: 0)",
    )
    _fields_flag(parser)
    _output_flags(parser)


def build_parser() -> argparse.ArgumentParser:
    parser = Parser(
        prog="s2",
        description="Read-only Semantic Scholar research CLI",
        epilog=(
            "Examples:\n"
            '  s2 refs "Attention is All You Need"\n'
            "  s2 citations ARXIV:1706.03762 --limit 1000 "
            "--sort-by citation-count --top 20\n"
            '  s2 search "image dehazing" --year 2025-2026 --limit 100 --jsonl'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"s2 {__version__}\tapi {API_CONTRACT_VERSION}",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    search_parser = commands.add_parser(
        "search",
        help="search the Semantic Scholar graph",
        description=(
            "Relevance-search Semantic Scholar. This is a broader corpus than "
            "`pwc search`, which only returns papers already in Papers With Code."
        ),
    )
    search_parser.add_argument("query", help="title, topic, or keywords")
    search_parser.add_argument(
        "--limit",
        type=_limit(100),
        default=20,
        help="results per page, 1-100 (default: 20)",
    )
    search_parser.add_argument(
        "--offset",
        type=_offset,
        default=0,
        help="pagination offset (default: 0)",
    )
    search_parser.add_argument(
        "--year",
        help="year or inclusive range, e.g. 2025 or 2025-2026",
    )
    _fields_flag(search_parser)
    _output_flags(search_parser)
    search_parser.set_defaults(handler=search)

    refs_parser = commands.add_parser(
        "refs",
        help="list papers cited by this paper",
        description="Fetch the bibliography (outgoing references) for a paper.",
    )
    _add_graph_flags(refs_parser)
    refs_parser.set_defaults(handler=refs)

    citations_parser = commands.add_parser(
        "citations",
        help="list papers that cite this paper",
        description=(
            "Fetch incoming citations. Semantic Scholar refuses "
            f"offset+limit > {CITATIONS_HARD_CAP}; highly cited papers are not "
            "fully enumerable."
        ),
    )
    _add_graph_flags(citations_parser)
    citations_parser.set_defaults(handler=citations)

    version_parser = commands.add_parser("version", help="show CLI version")
    version_parser.set_defaults(handler=version)
    return parser


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.command == "version":
        return
    if args.top is not None and args.sort_by is None:
        parser.error("--top requires --sort-by citation-count")
    if args.top is not None and args.top > args.limit:
        parser.error("--top cannot exceed --limit")
    if args.sort_by and args.json:
        parser.error("--sort-by cannot be combined with raw --json; use --jsonl")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_args(parser, args)
    try:
        if args.command == "version":
            return version(args, None)  # type: ignore[arg-type]
        return args.handler(args, Client())
    except MissingKeyError as error:
        print(f"s2: {error}", file=sys.stderr)
        return 2
    except TransportError as error:
        print(f"s2: {error}", file=sys.stderr)
        return 3
    except NotFoundError as error:
        print(f"s2: {error}", file=sys.stderr)
        return 4
    except ResponseError as error:
        print(f"s2: {error}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
