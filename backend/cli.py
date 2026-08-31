"""Command-line interface for Papers with Code maintenance workflows."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from sqlalchemy import text

from backend.cli_admin import (
    register_admin_commands,
)
from backend.cli_contributors import register_contributor_commands
from backend.cli_papers import (
    register_paper_commands,
    register_search_command,
)
from backend.cli_submissions import register_submission_commands
from backend.database.connection import db_manager
from backend.services.autonomous_capabilities import CAPABILITY_MANIFESTS
from backend.services.autonomous_codex_runner import (
    CodexRequest,
    codex_result_schema,
    run_codex,
)
from backend.services.autonomous_operations_repository import Operator, RunContext
from backend.services.cron_health import build_cron_dashboard
from backend.services.cron_registry import get_cron_job, list_cron_jobs
from backend.services.cron_token_probe import TOKEN_PROBES, probe_cron_token
from backend.services.embedding_contracts import EmbeddingRunManifest
from backend.services.entity_image_service import add_entity_image
from backend.services.github_issue_body_service import generate_github_issue_draft
from backend.services.github_issue_publish_service import publish_github_issue
from backend.services.method_admin_service import add_or_update_method
from backend.services.paper_embedding_pipeline import (
    activate_generation,
    build_generation_index,
    bucket_retention_plan,
    create_generation,
    embedding_status,
    export_papers,
    import_embeddings,
    mark_generation_ready,
)
from backend.services.paper_lineage_service import (
    add_lineage_chain,
    get_paper_lineage,
    remove_lineage_edge,
)
from backend.services.paper_thumbnail_service import regenerate_paper_thumbnail


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pwc",
        description="Papers with Code maintenance CLI",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    register_search_command(commands)

    github_issue = commands.add_parser(
        "github-issue",
        help="Generate and manage paper evaluation outreach issues",
    )
    github_issue_commands = github_issue.add_subparsers(
        dest="github_issue_command",
        required=True,
    )
    body = github_issue_commands.add_parser(
        "body",
        help="Generate a rule-based GitHub issue body from paper evaluations",
    )
    body.add_argument(
        "paper",
        help="Papers with Code paper URL, arXiv ID, or numeric external-paper ID",
    )
    body.add_argument(
        "--task",
        help="Restrict evaluations and rankings to one task slug",
    )
    body.add_argument(
        "--verified",
        action="store_true",
        help="State that a human verification pass has been completed",
    )
    body.add_argument(
        "--json",
        action="store_true",
        help="Return metadata, repository candidates, placements, and body as JSON",
    )
    body.set_defaults(handler=generate_github_issue_body)

    create = github_issue_commands.add_parser(
        "create",
        help="Create a duplicate-safe issue on the paper's official repository",
    )
    create.add_argument(
        "paper",
        help="Papers with Code paper URL, arXiv ID, or numeric external-paper ID",
    )
    create.add_argument(
        "--task",
        help="Restrict evaluations and rankings to one task slug",
    )
    create.add_argument(
        "--verified",
        action="store_true",
        help="State that a human verification pass has been completed",
    )
    create.add_argument(
        "--repository",
        help="Select one canonical repository when several are marked official",
    )
    create.add_argument(
        "--token-env",
        default="GITHUB_CLASSIC_TOKEN",
        help="Environment variable holding an issue-write token",
    )
    create.add_argument(
        "--confirm",
        required=True,
        choices=["PUBLISH"],
        help="Required explicit confirmation for the external write",
    )
    create.add_argument(
        "--json",
        action="store_true",
        help="Return the reconciled publication result as JSON",
    )
    create.set_defaults(handler=create_github_issue)

    thumbnail = commands.add_parser(
        "thumbnail",
        help="Regenerate and validate a paper thumbnail",
    )
    thumbnail.add_argument(
        "paper",
        help="Papers with Code paper URL, arXiv ID, or numeric external-paper ID",
    )
    thumbnail.add_argument(
        "--no-force",
        action="store_true",
        help="Reuse an existing valid thumbnail instead of forcing regeneration",
    )
    thumbnail.add_argument(
        "--json",
        action="store_true",
        help="Return old/new dimensions, URL, validation, and warnings as JSON",
    )
    thumbnail.set_defaults(handler=regenerate_thumbnail)

    image = commands.add_parser(
        "image",
        help="Manage DB-backed task, method, and conference images",
    )
    image_commands = image.add_subparsers(dest="image_command", required=True)
    image_add = image_commands.add_parser(
        "add",
        help="Download and attribute an entity hero image",
    )
    image_add.add_argument("entity", choices=["task", "method", "conference"])
    image_add.add_argument("slug", help="Entity slug to update")
    image_add.add_argument("image_url", help="Direct http(s) URL of the image")
    image_add.add_argument(
        "--source",
        required=True,
        help="Source credit stored with the image (URL, text, or Markdown link)",
    )
    image_add.add_argument("--json", action="store_true")
    image_add.set_defaults(handler=add_image)

    method = commands.add_parser("method", help="Manage method taxonomy rows")
    method_commands = method.add_subparsers(dest="method_command", required=True)
    method_add = method_commands.add_parser(
        "add",
        help="Idempotently add or update a method and its introducing-paper link",
    )
    method_add.add_argument("slug")
    method_add.add_argument("--name", required=True)
    method_add.add_argument("--full-name", required=True)
    description = method_add.add_mutually_exclusive_group(required=True)
    description.add_argument("--description")
    description.add_argument("--description-file", type=Path)
    method_add.add_argument("--keywords", required=True)
    method_add.add_argument("--area", required=True)
    method_add.add_argument("--introduced-year", type=int, required=True)
    source = method_add.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-paper")
    source.add_argument("--source-url")
    method_add.add_argument("--source-title", required=True)
    method_add.add_argument("--code-snippet-url")
    method_add.add_argument("--image-credit")
    method_add.add_argument("--json", action="store_true")
    method_add.set_defaults(handler=add_method)

    register_admin_commands(commands)
    register_contributor_commands(commands)
    register_submission_commands(commands)

    autonomous = commands.add_parser(
        "autonomous", help="Run bounded autonomous-operations diagnostics"
    )
    autonomous_commands = autonomous.add_subparsers(
        dest="autonomous_command", required=True
    )
    autonomous_run = autonomous_commands.add_parser("run")
    autonomous_run.add_argument("operator", choices=[value.value for value in Operator])
    autonomous_run.add_argument("--dry-run", action="store_true")
    autonomous_run.add_argument("--budget-usd", type=Decimal, default=Decimal("0.25"))
    autonomous_run.set_defaults(handler=run_autonomous_operator)

    paper_commands = register_paper_commands(commands)

    lineage = paper_commands.add_parser(
        "lineage",
        help="Manage directed predecessor/successor paper links",
    )
    lineage_commands = lineage.add_subparsers(dest="lineage_command", required=True)
    lineage_add = lineage_commands.add_parser(
        "add",
        help="Add an idempotent predecessor-to-successor chain",
    )
    lineage_add.add_argument(
        "papers",
        nargs="+",
        help="Two or more PwC URLs, arXiv IDs, or numeric external-paper IDs",
    )
    lineage_add.add_argument("--json", action="store_true")
    lineage_add.set_defaults(handler=add_paper_lineage)

    lineage_list = lineage_commands.add_parser(
        "list",
        help="List a paper's predecessors and successors",
    )
    lineage_list.add_argument("paper")
    lineage_list.add_argument("--json", action="store_true")
    lineage_list.set_defaults(handler=list_paper_lineage)

    lineage_remove = lineage_commands.add_parser(
        "remove",
        help="Remove one predecessor-to-successor edge",
    )
    lineage_remove.add_argument("predecessor")
    lineage_remove.add_argument("successor")
    lineage_remove.add_argument(
        "--confirm",
        required=True,
        choices=["DELETE"],
        help="Required explicit confirmation for deletion",
    )
    lineage_remove.add_argument("--json", action="store_true")
    lineage_remove.set_defaults(handler=remove_paper_lineage)

    cron = commands.add_parser("cron", help="Inspect scheduled-job health")
    cron_commands = cron.add_subparsers(dest="cron_command", required=True)
    cron_health = cron_commands.add_parser(
        "health",
        help="Triangulate logs, processes, locks, database writes, and Actions",
    )
    cron_health.add_argument(
        "job",
        nargs="?",
        choices=[job.id for job in list_cron_jobs()],
        help="Show only one registered job",
    )
    cron_health.add_argument("--json", action="store_true")
    cron_health.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero for degraded or unknown jobs as well as broken/stuck jobs",
    )
    cron_health.set_defaults(handler=show_cron_health)

    token_check = cron_commands.add_parser(
        "token-check",
        help="Probe a CRON credential without displaying its value",
    )
    token_check.add_argument("environment_variable", choices=sorted(TOKEN_PROBES))
    token_check.add_argument("--json", action="store_true")
    token_check.set_defaults(handler=check_cron_token)

    embeddings = commands.add_parser(
        "embeddings", help="Plan and operate the versioned paper embedding pipeline"
    )
    embedding_commands = embeddings.add_subparsers(
        dest="embeddings_command", required=True
    )
    export = embedding_commands.add_parser(
        "export", help="Export a checksummed snapshot"
    )
    export.add_argument("--output-root", type=Path, required=True)
    export.add_argument("--run-id", required=True)
    export.add_argument("--model", required=True)
    export.add_argument("--revision", required=True)
    export.add_argument("--dimensions", type=int, required=True)
    export.add_argument("--generation-id", type=int)
    export.add_argument("--shard-rows", type=int, default=5000)
    export.add_argument("--max-rows", type=int)
    export.set_defaults(handler=export_embeddings)

    run = embedding_commands.add_parser(
        "run", help="Print or explicitly launch a pinned HF Job"
    )
    run.add_argument("--input", required=True, help="Bucket-mounted input directory")
    run.add_argument("--output", required=True, help="Bucket-mounted output directory")
    run.add_argument("--volume", required=True, help="hf://buckets/...:/bucket mount")
    run.add_argument("--model", required=True)
    run.add_argument("--revision", required=True)
    run.add_argument("--dimensions", type=int, required=True)
    run.add_argument("--flavor", default="l4x1")
    run.add_argument("--timeout", default="6h")
    run.add_argument("--allow-matryoshka", action="store_true")
    run.add_argument("--reuse-snapshot", action="store_true")
    run.add_argument("--execute", action="store_true")
    run.add_argument("--confirm", choices=["RUN_HF_JOB"])
    run.set_defaults(handler=run_embedding_job)

    endpoint = embedding_commands.add_parser(
        "endpoint-plan",
        help="Print or explicitly deploy an authenticated scale-to-zero TEI endpoint",
    )
    endpoint.add_argument("--name", required=True)
    endpoint.add_argument("--namespace", required=True)
    endpoint.add_argument("--model", required=True)
    endpoint.add_argument("--revision", required=True)
    endpoint.add_argument("--accelerator", default="gpu")
    endpoint.add_argument("--scale-to-zero-timeout", type=int, default=15)
    endpoint.add_argument("--execute", action="store_true")
    endpoint.add_argument("--confirm", choices=["DEPLOY_HF_ENDPOINT"])
    endpoint.set_defaults(handler=plan_query_endpoint)

    load = embedding_commands.add_parser(
        "import", help="Validate and import output shards"
    )
    load.add_argument("--output", type=Path, required=True)
    load.add_argument("--input-manifest", type=Path, required=True)
    load.add_argument("--bucket-run-uri", required=True)
    load.add_argument("--generation-id", type=int)
    load.set_defaults(handler=import_embedding_generation)

    status = embedding_commands.add_parser(
        "status", help="Show generation freshness and coverage"
    )
    status.add_argument("--json", action="store_true")
    status.set_defaults(handler=show_embedding_status)

    activate = embedding_commands.add_parser(
        "activate", help="Atomically activate a ready generation"
    )
    activate.add_argument("generation_id", type=int)
    activate.add_argument("--confirm", required=True, choices=["ACTIVATE"])
    activate.set_defaults(handler=activate_embedding_generation)

    lexemes = embedding_commands.add_parser(
        "refresh-lexeme-stats",
        help="Refresh bounded related-paper lexical term statistics",
    )
    lexemes.add_argument("--confirm", required=True, choices=["REFRESH"])
    lexemes.set_defaults(handler=refresh_embedding_lexeme_stats)

    retention = embedding_commands.add_parser(
        "retention-plan", help="Create a non-destructive Bucket retention plan"
    )
    retention.add_argument("--runs", type=Path, required=True)
    retention.add_argument("--output", type=Path)
    retention.set_defaults(handler=plan_embedding_retention)

    retention_apply = embedding_commands.add_parser(
        "retention-apply", help="Apply a reviewed retention plan through hf buckets"
    )
    retention_apply.add_argument("--plan", type=Path, required=True)
    retention_apply.add_argument(
        "--confirm", required=True, choices=["DELETE_BUCKET_ARTIFACTS"]
    )
    retention_apply.set_defaults(handler=apply_embedding_retention)
    return parser


def export_embeddings(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        result = export_papers(
            db,
            args.output_root,
            run_id=args.run_id,
            model_name=args.model,
            model_revision=args.revision,
            dimensions=args.dimensions,
            shard_rows=args.shard_rows,
            generation_id=args.generation_id,
            max_rows=args.max_rows,
        )
        db.rollback()
        db.execute(
            text(
                """INSERT INTO embedding_pipeline_runs
                   (run_id, generation_id, kind, status, row_count, artifact_uri, completed_at)
                   VALUES (:run_id, :generation_id, 'export', 'complete', :rows, :uri, now())
                   ON CONFLICT (run_id, kind) DO UPDATE SET
                     status='complete', row_count=EXCLUDED.row_count,
                     artifact_uri=EXCLUDED.artifact_uri, completed_at=now()"""
            ),
            {
                "run_id": args.run_id,
                "generation_id": args.generation_id,
                "rows": result.manifest.row_count,
                "uri": str(result.run_dir),
            },
        )
        db.commit()
    print(
        json.dumps(
            {"run_dir": str(result.run_dir), **result.manifest.to_dict()}, indent=2
        )
    )
    return 0


def _embedding_job_command(args: argparse.Namespace) -> list[str]:
    command = [
        "hf",
        "jobs",
        "uv",
        "run",
        "--flavor",
        args.flavor,
        "--timeout",
        args.timeout,
        "--detach",
        "--label",
        "app=pwc-paper-embeddings",
        "--secrets",
        "HF_TOKEN",
        "--volume",
        args.volume,
        "backend/scripts/embed_papers_job.py",
        "--input",
        args.input,
        "--output",
        args.output,
        "--model",
        args.model,
        "--revision",
        args.revision,
        "--dimensions",
        str(args.dimensions),
    ]
    if args.allow_matryoshka:
        command.append("--allow-matryoshka")
    if args.reuse_snapshot:
        command.append("--reuse-snapshot")
    return command


def run_embedding_job(args: argparse.Namespace) -> int:
    command = _embedding_job_command(args)
    if not args.execute:
        print(json.dumps({"dry_run": True, "command": command}, indent=2))
        return 0
    if args.confirm != "RUN_HF_JOB":
        raise ValueError("--execute requires --confirm RUN_HF_JOB")
    return subprocess.run(command, check=False).returncode


def plan_query_endpoint(args: argparse.Namespace) -> int:
    """Deploy from the embedding catalog, then pin revision and scaling."""
    # Catalog deployment is important here: for compatible embedding models it
    # selects TEI, including Matryoshka ``dimensions`` support. A generic
    # pytorch endpoint uses the inference toolkit and ignores that parameter.
    deploy_command = [
        "hf",
        "endpoints",
        "catalog",
        "deploy",
        "--repo",
        args.model,
        "--name",
        args.name,
        "--accelerator",
        args.accelerator,
        "--namespace",
        args.namespace,
        "--format",
        "json",
    ]
    pin_command = [
        "hf",
        "endpoints",
        "update",
        args.name,
        "--namespace",
        args.namespace,
        "--revision",
        args.revision,
        "--min-replica",
        "0",
        "--max-replica",
        "1",
        "--scale-to-zero-timeout",
        str(args.scale_to_zero_timeout),
        "--format",
        "json",
    ]
    if not args.execute:
        print(
            json.dumps(
                {"dry_run": True, "commands": [deploy_command, pin_command]},
                indent=2,
            )
        )
        return 0
    if args.confirm != "DEPLOY_HF_ENDPOINT":
        raise ValueError("--execute requires --confirm DEPLOY_HF_ENDPOINT")
    for command in (deploy_command, pin_command):
        result = subprocess.run(command, check=False)
        if result.returncode:
            return result.returncode
    return 0


def import_embedding_generation(args: argparse.Namespace) -> int:
    manifest = EmbeddingRunManifest.read(args.input_manifest)
    manifest.validate_files(args.input_manifest.parent)
    created_generation = args.generation_id is None
    with db_manager.session_local() as db:
        generation_id = args.generation_id or create_generation(
            db, manifest, args.bucket_run_uri
        )
        result = import_embeddings(db, args.output, generation_id=generation_id)
        db.execute(
            text(
                """INSERT INTO embedding_pipeline_runs
                   (run_id, generation_id, kind, status, row_count, artifact_uri,
                    details, completed_at)
                   VALUES (:run_id, :generation_id, 'import', 'complete', :rows,
                           :uri, CAST(:details AS jsonb), now())
                   ON CONFLICT (run_id, kind) DO UPDATE SET
                     generation_id=EXCLUDED.generation_id, status='complete',
                     row_count=EXCLUDED.row_count, artifact_uri=EXCLUDED.artifact_uri,
                     details=EXCLUDED.details, completed_at=now()"""
            ),
            {
                "run_id": manifest.run_id,
                "generation_id": generation_id,
                "rows": result["imported"],
                "uri": args.bucket_run_uri,
                "details": json.dumps(result),
            },
        )
        db.commit()
    if created_generation:
        build_generation_index(db_manager.engine, generation_id)
        with db_manager.session_local() as db:
            mark_generation_ready(db, generation_id)
    print(json.dumps({"generation_id": generation_id, **result}, indent=2))
    return 0


def show_embedding_status(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        result = embedding_status(db)
    print(json.dumps(result, indent=2, default=str))
    return 0


def activate_embedding_generation(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        activate_generation(db, args.generation_id)
    print(f"activated generation {args.generation_id}")
    return 0


def refresh_embedding_lexeme_stats(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        count = db.execute(
            text("SELECT refresh_paper_lexeme_document_frequencies()")
        ).scalar_one()
        db.commit()
    print(json.dumps({"lexemes": count}, indent=2))
    return 0


def plan_embedding_retention(args: argparse.Namespace) -> int:
    runs = json.loads(args.runs.read_text(encoding="utf-8"))
    plan = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "deletions": bucket_retention_plan(runs),
    }
    rendered = json.dumps(plan, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


def apply_embedding_retention(args: argparse.Namespace) -> int:
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    for deletion in plan.get("deletions", []):
        result = subprocess.run(
            ["hf", "buckets", "remove", deletion["prefix"], "--recursive", "--yes"],
            check=False,
        )
        if result.returncode:
            return result.returncode
    return 0


def generate_github_issue_body(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        draft = generate_github_issue_draft(
            db,
            args.paper,
            task_slug=args.task,
            verified=args.verified,
        )
    if args.json:
        print(json.dumps(draft.to_dict(), indent=2))
    else:
        print(draft.body)
    return 0


def create_github_issue(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        draft = generate_github_issue_draft(
            db,
            args.paper,
            task_slug=args.task,
            verified=args.verified,
        )
    result = publish_github_issue(
        draft,
        token_environment_variable=args.token_env,
        requested_repository=args.repository,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"{result.status}: {result.issue_url}")
    return 0


def regenerate_thumbnail(args: argparse.Namespace) -> int:
    async def run():
        with db_manager.session_local() as db:
            return await regenerate_paper_thumbnail(
                db,
                args.paper,
                force=not args.no_force,
            )

    result = asyncio.run(run())
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        old_size = (
            f"{result.previous.width}x{result.previous.height}"
            if result.previous
            else "missing"
        )
        print(
            f"paper_id={result.paper_id} arxiv_id={result.arxiv_id} "
            f"old_size={old_size} "
            f"new_size={result.generated.width}x{result.generated.height} "
            f"valid={result.generated.valid} url={result.thumbnail_url}"
        )
        for warning in result.warnings:
            print(f"WARNING: {warning}", file=sys.stderr)
    return 0 if result.success else 1


def add_image(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        result = add_entity_image(
            db,
            args.entity,
            args.slug,
            args.image_url,
            args.source,
        )
        db.commit()

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(
            f"stored {result.byte_count} bytes as {result.mime_type} for "
            f"{result.entity}({result.slug}); source={result.source}; "
            f"seed={result.seed_path}"
        )
    return 0


def add_method(args: argparse.Namespace) -> int:
    description = args.description
    if args.description_file:
        description = args.description_file.read_text().strip()
    with db_manager.session_local() as db:
        result = add_or_update_method(
            db,
            slug=args.slug,
            name=args.name,
            full_name=args.full_name,
            description=description,
            keywords=args.keywords,
            area_name=args.area,
            introduced_year=args.introduced_year,
            source_paper=args.source_paper,
            source_url=args.source_url,
            source_title=args.source_title,
            code_snippet_url=args.code_snippet_url,
            image_credit=args.image_credit,
        )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(
            f"{result.status}: method={result.slug} id={result.id} "
            f"source={result.source_reference or args.source_url} "
            f"source_link={result.source_link_status}"
        )
    return 0


def add_paper_lineage(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        edges = add_lineage_chain(db, args.papers)
    if args.json:
        print(json.dumps({"edges": [edge.to_dict() for edge in edges]}, indent=2))
    else:
        for edge in edges:
            print(f"{edge.status}: {edge.predecessor.title} -> {edge.successor.title}")
    return 0


def list_paper_lineage(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        lineage = get_paper_lineage(db, args.paper)
    if args.json:
        print(json.dumps(lineage.to_dict(), indent=2))
    else:
        print(f"Paper: {lineage.paper.title} ({lineage.paper.reference})")
        print("Predecessors:")
        for paper in lineage.predecessors:
            print(f"  {paper.reference}  {paper.title}")
        if not lineage.predecessors:
            print("  none")
        print("Successors:")
        for paper in lineage.successors:
            print(f"  {paper.reference}  {paper.title}")
        if not lineage.successors:
            print("  none")
    return 0


def remove_paper_lineage(args: argparse.Namespace) -> int:
    with db_manager.session_local() as db:
        edge = remove_lineage_edge(db, args.predecessor, args.successor)
    if args.json:
        print(json.dumps(edge.to_dict(), indent=2))
    else:
        print(f"{edge.status}: {edge.predecessor.title} -> {edge.successor.title}")
    return 0 if edge.status == "removed" else 1


def _selected_cron_payload(job_id: str | None) -> dict:
    payload = build_cron_dashboard()
    if job_id is None:
        return payload
    job = get_cron_job(job_id)
    if job is None:
        raise ValueError(f"Unknown CRON job: {job_id}")
    matches = [item for item in payload["jobs"] if item["job_name"] == job_id]
    return {"timestamp": payload["timestamp"], "jobs": matches}


def show_cron_health(args: argparse.Namespace) -> int:
    payload = _selected_cron_payload(args.job)
    jobs = payload["jobs"]
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print("JOB\tSCHEDULE\tSTATUS\tLAST COMPLETED\tNOTES")
        for job in jobs:
            last_completed = job.get("last_db_write") or job.get("last_run") or "-"
            print(
                f"{job['job_name']}\t{job.get('schedule') or '-'}\t"
                f"{job['status']}\t{last_completed}\t{job['status_reason']}"
            )
            if job.get("diagnostics"):
                print(f"  next: {job['diagnostics']}", file=sys.stderr)

    failure_statuses = {"broken", "stuck"}
    if args.strict:
        failure_statuses.update({"degraded", "unknown"})
    return 1 if any(job["status"] in failure_statuses for job in jobs) else 0


def check_cron_token(args: argparse.Namespace) -> int:
    result = probe_cron_token(args.environment_variable)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        state = "valid" if result.success else "invalid"
        suffix = (
            f" rate_limit_remaining={result.rate_limit_remaining}"
            if result.rate_limit_remaining is not None
            else ""
        )
        print(
            f"{result.environment_variable}: {state} "
            f"service={result.service} http_status={result.http_status}{suffix}"
        )
        if result.error:
            print(f"ERROR: {result.error}", file=sys.stderr)
    return 0 if result.success else 1


def run_autonomous_operator(args: argparse.Namespace) -> int:
    if not args.dry_run:
        raise ValueError("autonomous run currently requires --dry-run")
    operator = Operator(args.operator)
    capabilities = tuple(sorted(CAPABILITY_MANIFESTS[operator], key=str))
    schema = codex_result_schema(capabilities)
    revision_source = json.dumps(
        {
            "capabilities": [value.value for value in capabilities],
            "schema": schema,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    context = RunContext(
        run_id=uuid.uuid4(),
        operator=operator,
        dry_run=True,
        manifest_revision=f"autonomous-v1:{sha256(revision_source.encode()).hexdigest()}",
    )
    request = CodexRequest(
        context=context,
        evidence=(),
        capabilities=capabilities,
        output_schema=schema,
        budget_usd=args.budget_usd,
    )
    with db_manager.session_local() as db:
        result = run_codex(request, db=db)
        db.commit()
    print(
        json.dumps(
            {
                "run_id": str(result.run_id),
                "operator": operator.value,
                "status": result.status,
                "exit_classification": result.exit_classification,
                "usage": {
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                    "cost_usd": format(result.usage.cost_usd, "f"),
                },
                "proposed_actions": [
                    {
                        "capability": action.capability.value,
                        "resource_kind": action.resource.kind.value,
                        "resource_identifier": action.resource.identifier,
                        "reason_code": action.reason_code,
                    }
                    for action in result.proposed_actions
                ],
                "result_digest": result.result_digest,
            },
            indent=2,
        )
    )
    return 0 if result.status in {"completed", "rejected"} else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
