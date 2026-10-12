"""Parser registration and mutation handlers for paper administration."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.services.external_resource_service import (
    ExternalResourceError,
    ExternalResourceService,
)
from backend.services.paper_association_service import PaperAssociationService
from backend.services.paper_markdown_service import read_paper_markdown
from backend.services.paper_service import PaperService
from backend.utils.paper_reference import normalize_paper_reference, resolve_paper
from backend.utils.urls import validate_arxiv_id


def search_papers(args: argparse.Namespace) -> int:
    """Search papers through the same retrieval service used by the API."""
    with db_manager.session_local() as db:
        results = PaperService(db).search_papers(
            args.query,
            limit=args.limit,
            mode=args.mode,
        )

    if args.json:
        payload = [paper.model_dump(mode="json") for paper in results]
        print(json.dumps(payload, indent=2))
    else:
        _print_paper_rows(results)
    return 0


def _print_paper_rows(papers) -> None:
    for rank, paper in enumerate(papers, 1):
        reference = paper.arxiv_id or paper.source_url or paper.id
        print(f"{rank}. {paper.title}")
        print(f"   {reference}")
        if paper.authors:
            print(f"   {', '.join(paper.authors)}")


def show_paper_info(args: argparse.Namespace) -> int:
    reference = normalize_paper_reference(args.paper)
    with db_manager.session_local() as db:
        paper = PaperService(db).get_paper_by_id_or_arxiv(
            reference, include_resources=args.include_resources
        )
    if args.json:
        print(json.dumps(paper.model_dump(mode="json"), indent=2))
    else:
        print(paper.title)
        print(f"ID: {paper.arxiv_id or paper.id}")
        print(f"Published: {paper.published or '-'}")
        print(f"Authors: {', '.join(paper.authors) or '-'}")
        print(f"Citations: {paper.citation_count}")
        print(f"URL: {paper.url_abs or paper.source_url or '-'}")
        if paper.abstract:
            print(f"\n{paper.abstract}")
        print("\n## Paper lineage")
        _print_lineage_section("Predecessors", paper.predecessor_papers)
        _print_lineage_section("Successors", paper.successor_papers)
    return 0


def _print_lineage_section(title: str, papers) -> None:
    print(f"\n### {title}")
    if not papers:
        print("- None")
        return
    for paper in papers:
        paper_title = (
            paper.title.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        )
        url = f"https://paperswithcode.co/paper/{paper.route_identifier}"
        published = f" ({paper.published})" if paper.published else ""
        print(f"- [{paper_title}]({url}){published}")


def list_papers(args: argparse.Namespace) -> int:
    if args.page < 1 or not 1 <= args.page_size <= 500:
        raise ValueError("--page must be positive and --page-size must be 1-500")
    with db_manager.session_local() as db:
        page = PaperService(db).get_papers(
            page=args.page,
            page_size=args.page_size,
            search=args.search,
            published_after=args.published_after,
            published_before=args.published_before,
            conference=args.conference,
            latest_only=not args.all_versions,
            order_by=args.order_by,
            order_dir=args.order_dir,
            time_window=args.time,
            include_resources=args.include_resources,
        )
    if args.json:
        print(json.dumps(page.model_dump(mode="json"), indent=2))
    else:
        print(f"{page.count} papers")
        _print_paper_rows(page.results)
    return 0


def list_recent_papers(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        papers = PaperService(db).get_recent_papers(args.limit)
    if args.json:
        print(json.dumps([paper.model_dump(mode="json") for paper in papers], indent=2))
    else:
        _print_paper_rows(papers)
    return 0


def list_related_papers(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        papers = PaperService(db).get_related_papers(args.arxiv_id, args.limit)
    if args.json:
        print(json.dumps([paper.model_dump(mode="json") for paper in papers], indent=2))
    else:
        _print_paper_rows(papers)
    return 0


def list_trending_papers(args: argparse.Namespace) -> int:
    if args.min_velocity is not None and args.min_velocity < 0:
        raise ValueError("--min-velocity must be non-negative")
    with db_manager.session_local() as db:
        papers = PaperService(db).get_repository_trending_papers(
            limit=args.limit,
            max_age_days=args.max_age_days,
            min_velocity=args.min_velocity,
        )
    if args.json:
        print(
            json.dumps(
                [paper.model_dump(mode="json") for paper in papers],
                indent=2,
            )
        )
    else:
        for rank, paper in enumerate(papers, 1):
            reference = paper.arxiv_id or paper.source_url
            print(f"{rank}. {paper.title}")
            print(
                f"   {reference}  score={paper.trending.trending_score:.3f} "
                f"velocity={paper.trending.velocity_24h:.3f}/h"
            )
    return 0


def add_external_paper(args: argparse.Namespace) -> int:
    published = None
    if args.date_published:
        try:
            published = date.fromisoformat(args.date_published)
        except ValueError as error:
            raise ValueError("--date-published must use YYYY-MM-DD") from error

    async def run():
        with db_manager.session_local() as db:
            return await ExternalResourceService(db).add_from_url(
                source_url=args.source_url,
                date_published=published,
                title_override=args.title,
                abstract_override=args.abstract,
                authors_override=args.author,
                thumbnail_url=args.thumbnail_url,
            )

    try:
        result = asyncio.run(run())
    except ExternalResourceError as error:
        raise ValueError(str(error)) from error
    payload = {
        "paper": result.paper.model_dump(mode="json"),
        "repositories_added": result.repositories_added,
        "repositories_existing": result.repositories_existing,
        "hf_models_added": result.hf_models_added,
        "hf_datasets_added": result.hf_datasets_added,
        "hf_spaces_added": result.hf_spaces_added,
        "hf_artifacts_existing": result.hf_artifacts_existing,
        "authors_added": result.authors_added,
        "authors_existing": result.authors_existing,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        paper = result.paper
        print(f"ingested: paper={paper.arxiv_id or paper.id} title={paper.title}")
        print(paper.url_abs or paper.source_url)
    return 0


def register_search_command(commands) -> None:
    search = commands.add_parser(
        "search",
        help="Search papers using hybrid lexical and semantic retrieval",
    )
    search.add_argument("query", help="Paper title, topic, author, or ArXiv ID")
    search.add_argument(
        "--limit",
        type=int,
        default=10,
        choices=range(1, 101),
        metavar="1-100",
        help="Maximum number of results (default: 10)",
    )
    search.add_argument(
        "--mode",
        choices=["hybrid", "keyword", "semantic"],
        default="hybrid",
        help="Retrieval mode (default: hybrid)",
    )
    search.add_argument(
        "--json",
        action="store_true",
        help="Return the relevance-ranked paper summaries as JSON",
    )
    search.set_defaults(handler=search_papers)


def register_paper_commands(commands):
    paper = commands.add_parser("paper", help="Manage paper metadata")
    paper_commands = paper.add_subparsers(dest="paper_command", required=True)

    paper_index = paper_commands.add_parser(
        "index", help="Idempotently index or refresh an ArXiv paper"
    )
    paper_index.add_argument("arxiv_id")
    paper_index.add_argument("--json", action="store_true")
    paper_index.set_defaults(handler=index_paper)

    paper_read = paper_commands.add_parser(
        "read", help="Print a paper's Markdown content"
    )
    paper_read.add_argument(
        "paper", help="Papers with Code paper URL or modern ArXiv ID"
    )
    paper_read.set_defaults(handler=read_paper)

    paper_info = paper_commands.add_parser(
        "info", help="Show metadata for an ArXiv or external paper"
    )
    paper_info.add_argument(
        "paper", help="Papers with Code URL, ArXiv ID, or numeric external-paper ID"
    )
    paper_info.add_argument("--include-resources", action="store_true")
    paper_info.add_argument("--json", action="store_true")
    paper_info.set_defaults(handler=show_paper_info)

    paper_list = paper_commands.add_parser("list", help="List and filter papers")
    paper_list.add_argument("--page", type=int, default=1)
    paper_list.add_argument("--page-size", type=int, default=20)
    paper_list.add_argument("--search")
    paper_list.add_argument("--published-after")
    paper_list.add_argument("--published-before")
    paper_list.add_argument("--conference")
    paper_list.add_argument("--all-versions", action="store_true")
    paper_list.add_argument(
        "--order-by",
        choices=["trending", "date_published", "citation_count"],
        default="trending",
    )
    paper_list.add_argument("--order-dir", choices=["asc", "desc"], default="desc")
    paper_list.add_argument(
        "--time",
        choices=["today", "week", "month", "all_time"],
        default="all_time",
    )
    paper_list.add_argument("--include-resources", action="store_true")
    paper_list.add_argument("--json", action="store_true")
    paper_list.set_defaults(handler=list_papers)

    paper_recent = paper_commands.add_parser(
        "recent", help="List the most recently published papers"
    )
    paper_recent.add_argument(
        "--limit", type=int, default=10, choices=range(1, 101), metavar="1-100"
    )
    paper_recent.add_argument("--json", action="store_true")
    paper_recent.set_defaults(handler=list_recent_papers)

    paper_trending = paper_commands.add_parser(
        "trending", help="List papers trending by GitHub star velocity"
    )
    paper_trending.add_argument(
        "--limit", type=int, default=20, choices=range(1, 101), metavar="1-100"
    )
    paper_trending.add_argument(
        "--max-age-days",
        type=int,
        default=180,
        choices=range(1, 366),
        metavar="1-365",
    )
    paper_trending.add_argument("--min-velocity", type=float)
    paper_trending.add_argument("--json", action="store_true")
    paper_trending.set_defaults(handler=list_trending_papers)

    paper_related = paper_commands.add_parser(
        "related", help="List papers related to an ArXiv paper"
    )
    paper_related.add_argument("arxiv_id")
    paper_related.add_argument(
        "--limit", type=int, default=4, choices=range(1, 21), metavar="1-20"
    )
    paper_related.add_argument("--json", action="store_true")
    paper_related.set_defaults(handler=list_related_papers)

    paper_external = paper_commands.add_parser(
        "add-external",
        help="Extract and ingest a non-ArXiv paper or research resource",
    )
    paper_external.add_argument("source_url")
    paper_external.add_argument("--date-published")
    paper_external.add_argument("--title")
    paper_external.add_argument("--abstract")
    paper_external.add_argument("--author", action="append")
    paper_external.add_argument("--thumbnail-url")
    paper_external.add_argument("--json", action="store_true")
    paper_external.set_defaults(handler=add_external_paper)

    paper_update = paper_commands.add_parser(
        "update", help="Replace one category of curated paper metadata"
    )
    paper_update.add_argument(
        "paper", help="Papers with Code URL, ArXiv ID, or numeric external-paper ID"
    )
    paper_update_commands = paper_update.add_subparsers(
        dest="paper_update_command", required=True
    )
    for target, noun in (
        ("tasks", "task"),
        ("methods", "method"),
        ("organizations", "organization"),
    ):
        update_ids = paper_update_commands.add_parser(
            target, help=f"Replace all {target} linked to the paper"
        )
        update_ids.add_argument(
            "ids", nargs="*", type=int, metavar=f"{noun.upper()}_ID"
        )
        update_ids.add_argument("--json", action="store_true")
        update_ids.set_defaults(handler=update_paper)

    for target, help_text in (
        ("repositories", "Replace all repositories linked to the paper"),
        ("project-pages", "Replace all project pages linked to the paper"),
    ):
        update_resources = paper_update_commands.add_parser(target, help=help_text)
        update_resources.add_argument("urls", nargs="*", metavar="URL")
        update_resources.add_argument(
            "--unofficial", action="append", default=[], metavar="URL"
        )
        update_resources.add_argument("--json", action="store_true")
        update_resources.set_defaults(handler=update_paper)

    update_hf = paper_update_commands.add_parser(
        "hf-artifacts", help="Replace all explicit Hugging Face artifact links"
    )
    update_hf.add_argument("--model", action="append", default=[])
    update_hf.add_argument("--dataset", action="append", default=[])
    update_hf.add_argument("--space", action="append", default=[])
    update_hf.add_argument("--json", action="store_true")
    update_hf.set_defaults(handler=update_paper)

    update_source = paper_update_commands.add_parser(
        "source-url", help="Replace an external paper's canonical source URL"
    )
    update_source.add_argument("url")
    update_source.add_argument("--json", action="store_true")
    update_source.set_defaults(handler=update_paper)
    return paper_commands


def index_paper(args: argparse.Namespace) -> int:
    if not validate_arxiv_id(args.arxiv_id):
        raise ValueError(f"Invalid ArXiv ID: {args.arxiv_id}")

    async def run():
        with db_manager.session_local() as db:
            return await PaperService(db).refresh_arxiv_paper(args.arxiv_id)

    result = asyncio.run(run())
    payload = {
        "status": "created" if result.created else "existing",
        "refreshed": result.refreshed,
        "previous_version": result.previous_version,
        "latest_version": result.latest_version,
        "paper": result.paper.model_dump(mode="json"),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"{payload['status']}: paper={result.paper.arxiv_id} "
            f"id={result.paper.id} version={result.latest_version} "
            f"refreshed={result.refreshed}"
        )
    return 0


def read_paper(args: argparse.Namespace) -> int:
    reference = args.paper
    if "://" in reference:
        reference = normalize_paper_reference(reference)
    settings = get_settings()
    markdown = read_paper_markdown(
        reference,
        bucket_id=settings.paper_markdown_hf_bucket_id,
        token=settings.hf_token or None,
    )
    print(markdown, end="" if markdown.endswith("\n") else "\n")
    return 0


def update_paper(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        paper, route_reference = resolve_paper(db, args.paper)
        paper_service = PaperService(db)
        service = PaperAssociationService(db, paper_service.get_paper_by_id)
        command = args.paper_update_command
        if command == "tasks":
            result = service.update_tasks(paper.id, args.ids)
        elif command == "methods":
            result = service.update_methods(paper.id, args.ids)
        elif command == "organizations":
            result = service.update_organizations(paper.id, args.ids)
        elif command in {"repositories", "project-pages"}:
            resources = [
                {"url": url, "is_official": is_official}
                for is_official, urls in (
                    (True, args.urls),
                    (False, args.unofficial),
                )
                for url in urls
            ]
            if command == "repositories":
                # `--unofficial` is explicit, so never promote it to official.
                result = service.update_repositories(
                    paper.id, resources, promote_lone_repository=False
                )
            else:
                result = service.update_project_pages(paper.id, resources)
        elif command == "hf-artifacts":
            result = service.update_hf_artifacts(
                paper.id, args.model, args.dataset, args.space
            )
        elif command == "source-url":
            result = service.update_source_url(paper.id, args.url)
        else:
            raise ValueError(f"Unknown paper update target: {command}")

    if args.json:
        print(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        print(f"updated: paper={route_reference} id={paper.id} target={command}")
    return 0
