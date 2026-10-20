"""
Backfill and validate explicit method source paper links.

Dry run:
uv run --env-file backend/keys.env python backend/database/methods_setup/check_method_source_links.py

Write:
uv run --env-file backend/keys.env python backend/database/methods_setup/check_method_source_links.py --write
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import Sequence
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Method, Paper, PaperMethod
from backend.utils.urls import local_paper_source_hosts


ARXIV_HOSTS = {"arxiv.org", "www.arxiv.org"}
LOCAL_PAPER_PATH_RE = re.compile(r"^/(?:paper|abs|pdf)/(.+?)(?:\.pdf)?/?$")
ARXIV_PAPER_PATH_RE = re.compile(r"^/(?:abs|pdf)/(.+?)(?:\.pdf)?/?$")
VERSION_RE = re.compile(r"v\d+$")
SAMPLE_LIMIT = 10


@dataclass(frozen=True)
class SourcePaperRef:
    arxiv_id: str
    version: str | None


@dataclass(frozen=True)
class ResolvedSource:
    method: Method
    source_ref: SourcePaperRef
    papers: Sequence[Paper]


@dataclass
class SourceLinkPlan:
    methods_with_source_url: int = 0
    trusted_source_urls: int = 0
    resolvable: list[ResolvedSource] = field(default_factory=list)
    unresolved: list[ResolvedSource] = field(default_factory=list)
    conflicting: list[ResolvedSource] = field(default_factory=list)
    mismatched_existing: list[tuple[Method, Paper]] = field(default_factory=list)
    source_paper_updates: list[tuple[Method, Paper]] = field(default_factory=list)
    paper_method_inserts: list[tuple[int, int]] = field(default_factory=list)


def _split_version(source_ref: str) -> SourcePaperRef:
    source_ref = source_ref.strip().removesuffix(".pdf")
    version_match = VERSION_RE.search(source_ref)
    version = version_match.group(0) if version_match else None
    arxiv_id = VERSION_RE.sub("", source_ref)
    return SourcePaperRef(arxiv_id=arxiv_id, version=version)


def parse_trusted_source_url(source_url: str | None) -> SourcePaperRef | None:
    if not source_url:
        return None

    parsed = urlparse(source_url)
    host = parsed.hostname or ""

    if host in ARXIV_HOSTS:
        match = ARXIV_PAPER_PATH_RE.match(parsed.path.rstrip("/"))
        return _split_version(match.group(1)) if match else None

    if parsed.scheme and host not in local_paper_source_hosts():
        return None

    path = parsed.path if parsed.scheme or parsed.netloc else source_url
    path = path.split("?", 1)[0].split("#", 1)[0]
    path = path.rstrip("/")
    match = LOCAL_PAPER_PATH_RE.match(path)
    if not match:
        return None

    return _split_version(match.group(1))


# Backwards-compatible alias for older focused tests/imports.
parse_local_source_url = parse_trusted_source_url


def _resolve_source_ref(db: Session, source_ref: SourcePaperRef) -> list[Paper]:
    query = db.query(Paper).filter(Paper.arxiv_id == source_ref.arxiv_id)
    if source_ref.version:
        query = query.filter(Paper.version == source_ref.version)
    else:
        query = query.filter(Paper.is_latest_version)
    return query.order_by(Paper.id).all()


def build_source_link_plan(db: Session) -> SourceLinkPlan:
    plan = SourceLinkPlan()

    methods = db.query(Method).filter(Method.source_url.isnot(None)).order_by(Method.id)
    paper_methods = {
        (paper_id, method_id)
        for paper_id, method_id in db.query(
            PaperMethod.paper_id,
            PaperMethod.method_id,
        ).all()
    }

    for method in methods:
        plan.methods_with_source_url += 1
        source_ref = parse_trusted_source_url(method.source_url)
        if source_ref is None:
            continue

        plan.trusted_source_urls += 1
        papers = _resolve_source_ref(db, source_ref)
        resolved_source = ResolvedSource(
            method=method, source_ref=source_ref, papers=papers
        )

        if not papers:
            plan.unresolved.append(resolved_source)
            continue

        if len(papers) > 1:
            plan.conflicting.append(resolved_source)
            continue

        paper = papers[0]
        plan.resolvable.append(resolved_source)

        if method.source_paper_id is None:
            plan.source_paper_updates.append((method, paper))
        elif method.source_paper_id != paper.id:
            plan.mismatched_existing.append((method, paper))

        source_paper_id = method.source_paper_id or paper.id
        if (source_paper_id, method.id) not in paper_methods:
            plan.paper_method_inserts.append((source_paper_id, method.id))

    return plan


def apply_source_link_plan(db: Session, plan: SourceLinkPlan) -> None:
    from backend.services.paper_method_link_service import sync_method_source_evidence

    for method, paper in plan.source_paper_updates:
        method.source_paper_id = paper.id
        sync_method_source_evidence(db, method_id=method.id, source_paper_id=paper.id)
    for paper_id, method_id in plan.paper_method_inserts:
        sync_method_source_evidence(db, method_id=method_id, source_paper_id=paper_id)

    db.commit()


def validate_method_source_links(db: Session) -> list[str]:
    errors: list[str] = []

    methods = db.query(Method).all()
    paper_methods = {
        (paper_id, method_id)
        for paper_id, method_id in db.query(
            PaperMethod.paper_id,
            PaperMethod.method_id,
        ).all()
    }
    papers_by_id = {paper.id: paper for paper in db.query(Paper).all()}

    for method in methods:
        local_source_ref = parse_trusted_source_url(method.source_url)

        if method.source_paper_id is not None:
            if (method.source_paper_id, method.id) not in paper_methods:
                errors.append(
                    f"Method {method.id} ({method.name}) has source_paper_id={method.source_paper_id} "
                    "but no matching paper_methods row."
                )

            source_paper = papers_by_id.get(method.source_paper_id)
            if (
                local_source_ref
                and local_source_ref.version is None
                and source_paper
                and not source_paper.is_latest_version
            ):
                errors.append(
                    f"Method {method.id} ({method.name}) source_url omits a version but "
                    f"source_paper_id={method.source_paper_id} points to non-latest paper "
                    f"{source_paper.arxiv_id}{source_paper.version}."
                )

        if local_source_ref and method.source_paper_id is None:
            errors.append(
                f"Method {method.id} ({method.name}) has local source_url={method.source_url!r} "
                "but no source_paper_id."
            )

    return errors


def _format_method(method: Method) -> str:
    return f"{method.id} ({method.name}) source_url={method.source_url!r}"


def _print_plan(plan: SourceLinkPlan, write: bool) -> None:
    mode = "write" if write else "dry-run"
    print(f"Method source link backfill ({mode})")
    print(f"- methods with source_url: {plan.methods_with_source_url}")
    print(f"- trusted local/arXiv source URLs: {plan.trusted_source_urls}")
    print(f"- resolvable trusted URLs: {len(plan.resolvable)}")
    print(f"- unresolved trusted URLs: {len(plan.unresolved)}")
    print(f"- conflicting trusted URLs: {len(plan.conflicting)}")
    print(f"- source_paper_id updates: {len(plan.source_paper_updates)}")
    print(f"- paper_methods inserts: {len(plan.paper_method_inserts)}")
    print(
        f"- mismatched existing source_paper_id rows: {len(plan.mismatched_existing)}"
    )

    if plan.unresolved:
        print("\nUnresolved samples:")
        for item in plan.unresolved[:SAMPLE_LIMIT]:
            ref = item.source_ref
            print(
                f"- {_format_method(item.method)} -> {ref.arxiv_id}{ref.version or ''}"
            )

    if plan.conflicting:
        print("\nConflicting samples:")
        for item in plan.conflicting[:SAMPLE_LIMIT]:
            paper_ids = ", ".join(str(paper.id) for paper in item.papers)
            ref = item.source_ref
            print(
                f"- {_format_method(item.method)} -> {ref.arxiv_id}{ref.version or ''} "
                f"matched papers [{paper_ids}]"
            )

    if plan.mismatched_existing:
        print("\nMismatched existing samples:")
        for method, paper in plan.mismatched_existing[:SAMPLE_LIMIT]:
            print(
                f"- {_format_method(method)} has source_paper_id={method.source_paper_id}, "
                f"resolved paper_id={paper.id}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Apply source_paper_id updates and missing paper_methods inserts.",
    )
    args = parser.parse_args()

    with db_manager.session_local() as db:
        plan = build_source_link_plan(db)
        _print_plan(plan, write=args.write)

        if args.write:
            apply_source_link_plan(db, plan)
            print("\nBackfill writes committed.")

        errors = validate_method_source_links(db)

    if errors:
        print("\nMethod source link integrity check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nMethod source link integrity check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
