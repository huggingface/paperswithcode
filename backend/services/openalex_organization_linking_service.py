"""Link arXiv papers to organizations from their OpenAlex author affiliations.

Affiliations reach the catalog only through the reviewed institution map, as
``paper_organizations`` rows with ``source = 'openalex'``. Links are only ever
added; ``DELETE ... WHERE source = 'openalex'`` undoes them.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.database.organizations_setup.openalex_institutions import (
    OPENALEX_INSTITUTIONS,
    organization_slug_for,
)
from backend.models.database import Organization, Paper, PaperOrganization

OPENALEX_WORKS = "https://api.openalex.org/works"
OPENALEX_SOURCE = "openalex"
BATCH_SIZE = 100
ARXIV_LOCATION = re.compile(
    r"arxiv(?:\.org/(?:abs|pdf)/|\.)(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?(?:[/?#]|$)",
    re.IGNORECASE,
)


@dataclass
class LinkingStats:
    papers: int = 0
    matched_works: int = 0
    last_id: int = 0
    linked: Counter[str] = field(default_factory=Counter)
    # HTTP status OpenAlex refused with, if the run stopped early.
    stopped_status: int | None = None


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


def next_batch_size(limit: int | None, papers_seen: int) -> int:
    return BATCH_SIZE if limit is None else min(BATCH_SIZE, limit - papers_seen)


def fetch_works(client: httpx.Client, arxiv_ids: list[str], api_key: str) -> list[dict]:
    params = {
        "filter": "doi:" + "|".join(f"10.48550/arxiv.{a}" for a in arxiv_ids),
        "select": "doi,locations,authorships",
        "per_page": BATCH_SIZE,
    }
    if api_key:
        params["api_key"] = api_key
    response = client.get(OPENALEX_WORKS, params=params)
    response.raise_for_status()
    return response.json()["results"]


def link_openalex_organizations(
    db: Session,
    client: httpx.Client,
    *,
    since: date,
    api_key: str = "",
    resume_after_id: int = 0,
    limit: int | None = None,
    apply: bool = False,
    on_batch: Callable[[LinkingStats], None] | None = None,
) -> LinkingStats:
    """Link papers published on or after ``since``, 100 per OpenAlex request.

    Papers are processed in ascending ID order and each batch is committed, so
    a run that OpenAlex stops can resume after ``stats.last_id``. A dry run
    counts pairs before deduplicating against existing links.
    """
    stats = LinkingStats(last_id=resume_after_id)
    organization_ids = dict(
        db.query(Organization.slug, Organization.id).filter(
            Organization.slug.in_({item.slug for item in OPENALEX_INSTITUTIONS})
        )
    )
    slug_by_id = {value: key for key, value in organization_ids.items()}
    while limit is None or stats.papers < limit:
        batch = (
            db.query(Paper.id, Paper.arxiv_id)
            .filter(
                Paper.is_latest_version,
                Paper.source == "arxiv",
                Paper.arxiv_id.is_not(None),
                Paper.date_published >= since,
                Paper.id > stats.last_id,
            )
            .order_by(Paper.id)
            .limit(next_batch_size(limit, stats.papers))
            .all()
        )
        if not batch:
            break
        paper_ids = {arxiv_id: paper_id for paper_id, arxiv_id in batch}
        try:
            works = fetch_works(client, list(paper_ids), api_key)
        except httpx.HTTPStatusError as exc:
            stats.stopped_status = exc.response.status_code
            break
        pairs = set()
        for work in works:
            matched = work_arxiv_ids(work) & paper_ids.keys()
            stats.matched_works += bool(matched)
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
        if apply and rows:
            inserted = db.execute(
                insert(PaperOrganization)
                .values(rows)
                .on_conflict_do_nothing()
                .returning(PaperOrganization.organization_id)
            ).all()
            db.commit()
            stats.linked.update(slug_by_id[row[0]] for row in inserted)
        else:
            stats.linked.update(slug_by_id[row["organization_id"]] for row in rows)
        stats.papers += len(batch)
        stats.last_id = batch[-1][0]
        if on_batch:
            on_batch(stats)
    return stats
