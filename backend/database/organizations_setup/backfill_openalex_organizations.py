#!/usr/bin/env python3
"""Link arXiv papers to organizations from their OpenAlex author affiliations.

Affiliations reach the catalog only through the reviewed institution map, as
``paper_organizations`` rows with ``source = 'openalex'``. Links are only ever
added; ``DELETE ... WHERE source = 'openalex'`` undoes a run.

Papers are processed in ascending ID order, 100 per OpenAlex request. The
command is a dry run unless ``--apply`` is supplied. When OpenAlex refuses a
request (for example once the keyless daily budget is spent) it stops and
prints the ``--resume-after-id`` value for the next run:
  uv run --env-file backend/keys.env python \
    backend/database/organizations_setup/backfill_openalex_organizations.py \
    --since 2025-01-01 --apply
"""

from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from datetime import date

import httpx
from sqlalchemy.dialects.postgresql import insert

from backend.database.connection import db_manager
from backend.database.organizations_setup.openalex_institutions import (
    OPENALEX_INSTITUTIONS,
    organization_slug_for,
)
from backend.models.database import Organization, Paper, PaperOrganization

OPENALEX_WORKS = "https://api.openalex.org/works"
OPENALEX_SOURCE = "openalex"
BATCH_SIZE = 100
ARXIV_LOCATION = re.compile(
    r"arxiv(?:\.org/abs/|\.)(\d{4}\.\d{4,5})(?:v\d+)?$", re.IGNORECASE
)


def work_arxiv_ids(work: dict) -> set[str]:
    """arXiv IDs among a work's DOI and location URLs."""
    urls = [work.get("doi") or ""]
    urls += [location.get("landing_page_url") or "" for location in work["locations"]]
    return {match.group(1) for url in urls if (match := ARXIV_LOCATION.search(url))}


def work_organization_slugs(work: dict) -> set[str]:
    return {
        slug
        for authorship in work["authorships"]
        for institution in authorship.get("institutions") or []
        if (slug := organization_slug_for(institution["id"]))
    }


def fetch_works(client: httpx.Client, arxiv_ids: list[str]) -> list[dict]:
    params = {
        "filter": "doi:" + "|".join(f"10.48550/arxiv.{a}" for a in arxiv_ids),
        "select": "doi,locations,authorships",
        "per_page": BATCH_SIZE,
    }
    if api_key := os.environ.get("OPENALEX_API_KEY"):
        params["api_key"] = api_key
    response = client.get(OPENALEX_WORKS, params=params)
    response.raise_for_status()
    return response.json()["results"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", type=date.fromisoformat, required=True)
    parser.add_argument("--resume-after-id", type=int, default=0)
    parser.add_argument("--limit", type=int, help="Stop after this many papers.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    linked: Counter[str] = Counter()
    papers_seen = works_found = 0
    last_id = args.resume_after_id
    with db_manager.session_local() as db, httpx.Client(timeout=60) as client:
        organization_ids = dict(
            db.query(Organization.slug, Organization.id).filter(
                Organization.slug.in_({item.slug for item in OPENALEX_INSTITUTIONS})
            )
        )
        slug_by_id = {value: key for key, value in organization_ids.items()}
        while args.limit is None or papers_seen < args.limit:
            batch_size = min(BATCH_SIZE, (args.limit or BATCH_SIZE) - papers_seen)
            batch = (
                db.query(Paper.id, Paper.arxiv_id)
                .filter(
                    Paper.is_latest_version,
                    Paper.source == "arxiv",
                    Paper.arxiv_id.is_not(None),
                    Paper.date_published >= args.since,
                    Paper.id > last_id,
                )
                .order_by(Paper.id)
                .limit(batch_size)
                .all()
            )
            if not batch:
                break
            paper_ids = {arxiv_id: paper_id for paper_id, arxiv_id in batch}
            try:
                works = fetch_works(client, list(paper_ids))
            except httpx.HTTPStatusError as exc:
                print(
                    f"STOPPED: OpenAlex returned {exc.response.status_code}; "
                    f"rerun with --resume-after-id {last_id}"
                )
                break
            pairs = set()
            for work in works:
                matched = work_arxiv_ids(work) & paper_ids.keys()
                works_found += bool(matched)
                pairs.update(
                    (paper_ids[arxiv_id], organization_ids[slug])
                    for arxiv_id in matched
                    for slug in work_organization_slugs(work)
                )
            rows = [
                {
                    "paper_id": paper_id,
                    "organization_id": organization_id,
                    "source": OPENALEX_SOURCE,
                }
                for paper_id, organization_id in sorted(pairs)
            ]
            if args.apply and rows:
                inserted = db.execute(
                    insert(PaperOrganization)
                    .values(rows)
                    .on_conflict_do_nothing()
                    .returning(PaperOrganization.organization_id)
                ).all()
                db.commit()
                linked.update(slug_by_id[row[0]] for row in inserted)
            else:
                linked.update(slug_by_id[row["organization_id"]] for row in rows)
            papers_seen += len(batch)
            last_id = batch[-1][0]
            print(
                f"papers={papers_seen} matched_works={works_found} "
                f"links={sum(linked.values())} last_id={last_id}",
                flush=True,
            )
    verb = "linked" if args.apply else "would link (before existing-link dedupe)"
    print(f"{verb} {sum(linked.values())} paper-organization pairs; last_id={last_id}")
    for slug, count in linked.most_common(25):
        print(f"  {slug}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
