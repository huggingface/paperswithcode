"""Link authors to verified Google Scholar profiles (weekly CRON).

Each run:

1. Reads Wikidata people with a Google Scholar ID (P1960) and finds PwC
   authors with at least `--min-papers` papers whose name fits one.
2. Checks up to `--s2-authors` authors not checked before on Semantic Scholar
   (the Wikidata person's ORCID or S2 author ID on a sample of their papers),
   largest first.
3. Spends the SerpAPI searches left this month, minus `--serpapi-reserve`, on
   the Scholar profiles of candidates with any S2 match, largest authors first.
4. Stores every proposed link whose Scholar profile lists most of the author's
   papers (see `decide`). Existing links are never removed.

Progress lives in `author_google_scholar_candidates`, so a candidate costs one
S2 check and at most one profile read; on the free SerpAPI plan (250 searches
a month) a weekly run confirms about 100 authors after each monthly reset.
`--dry-run` checks Semantic Scholar and reports, but reads no Scholar profiles
and writes nothing.

    python -m backend.scripts.link_google_scholar_profiles
    python -m backend.scripts.link_google_scholar_profiles --dry-run --s2-authors 50
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter

import httpx
from sqlalchemy import text

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.services.google_scholar_link_service import (
    AuthorPaper,
    SemanticScholarBatch,
    SerpApiQuotaExhausted,
    SerpApiScholar,
    candidate_people,
    decide,
    evidence_json,
    fetch_wikidata_tsv,
    full_profile_evidence,
    index_people_by_name,
    iter_chunks,
    parse_wikidata_tsv,
    s2_evidence,
    sample_papers,
)

logger = logging.getLogger("link_google_scholar_profiles")

AUTHORS_SQL = text(
    """
    SELECT a.id, a.name, count(*) AS papers
    FROM authors a
    JOIN paper_authors pa ON pa.author_id = a.id
    JOIN papers p ON p.id = pa.paper_id AND p.is_latest_version
    GROUP BY a.id, a.name
    HAVING count(*) >= :min_papers
    """
)

PAPERS_SQL = text(
    """
    SELECT pa.author_id, p.id, p.title, p.arxiv_id, p.semantic_scholar_id, pa.author_order
    FROM paper_authors pa
    JOIN papers p ON p.id = pa.paper_id AND p.is_latest_version
    WHERE pa.author_id = ANY(:ids)
    """
)

INSERT_CANDIDATE_SQL = text(
    """
    INSERT INTO author_google_scholar_candidates
        (author_id, scholar_id, wikidata_qid, s2_evidence)
    VALUES (:author_id, :scholar_id, :wikidata_qid, cast(:s2_evidence AS jsonb))
    ON CONFLICT DO NOTHING
    """
)

# Several Wikidata people fitting the name make it a common name.
PENDING_PROFILES_SQL = text(
    """
    SELECT DISTINCT c.author_id, c.scholar_id, n.papers,
           (SELECT count(*) FROM author_google_scholar_candidates o
            WHERE o.author_id = c.author_id) > 1 AS common_name
    FROM author_google_scholar_candidates c
    JOIN (
        SELECT author_id, count(*) AS papers FROM paper_authors GROUP BY author_id
    ) n ON n.author_id = c.author_id
    WHERE c.serpapi_evidence IS NULL AND (c.s2_evidence->>'matched')::int > 0
    ORDER BY n.papers DESC, c.author_id, c.scholar_id
    """
)

STORE_PROFILE_EVIDENCE_SQL = text(
    """
    UPDATE author_google_scholar_candidates
    SET serpapi_evidence = cast(:evidence AS jsonb), serpapi_checked_at = now()
    WHERE author_id = :author_id AND scholar_id = :scholar_id
    """
)

UPSERT_LINK_SQL = text(
    """
    INSERT INTO author_google_scholar_profiles (
        author_id, scholar_id, wikidata_qid, evidence_source,
        matched_papers, considered_papers, matched_paper_ids, verified_at
    )
    VALUES (
        :author_id, :scholar_id, :wikidata_qid, 'serpapi',
        :matched, :considered, :matched_paper_ids, now()
    )
    ON CONFLICT (author_id) DO UPDATE SET
        scholar_id = EXCLUDED.scholar_id,
        wikidata_qid = EXCLUDED.wikidata_qid,
        evidence_source = EXCLUDED.evidence_source,
        matched_papers = EXCLUDED.matched_papers,
        considered_papers = EXCLUDED.considered_papers,
        matched_paper_ids = EXCLUDED.matched_paper_ids,
        verified_at = EXCLUDED.verified_at
    """
)


def load_papers(author_ids: list[int]) -> dict[int, list[AuthorPaper]]:
    papers_by_author: dict[int, list[AuthorPaper]] = {i: [] for i in author_ids}
    with db_manager.session_local() as db:
        for r in db.execute(PAPERS_SQL, {"ids": author_ids}):
            papers_by_author[r.author_id].append(
                AuthorPaper(
                    r.id, r.title, r.arxiv_id, r.semantic_scholar_id, r.author_order
                )
            )
    return papers_by_author


def check_new_authors(
    client: httpx.Client, s2_key: str, args: argparse.Namespace
) -> None:
    """Record S2 evidence for name candidates of authors not checked before."""
    index = index_people_by_name(parse_wikidata_tsv(fetch_wikidata_tsv(client)))
    with db_manager.session_local() as db:
        authors = db.execute(AUTHORS_SQL, {"min_papers": args.min_papers}).all()
        done = set(
            db.execute(
                text("SELECT DISTINCT author_id FROM author_google_scholar_candidates")
            ).scalars()
        )
    pending = sorted(
        (
            (author, people)
            for author in authors
            if author.id not in done
            and (people := candidate_people(author.name, index))
        ),
        key=lambda pair: -pair[0].papers,
    )
    logger.info("Authors with a new Wikidata candidate: %d", len(pending))

    s2 = SemanticScholarBatch(s2_key, client)
    for chunk in iter_chunks(pending[: args.s2_authors], 300):
        papers_by_author = load_papers([author.id for author, _ in chunk])
        # Only people with an ORCID or S2 ID can be confirmed through S2.
        s2_papers = {
            paper.paper_id: paper
            for author, people in chunk
            if any(person.orcids or person.s2_ids for person in people)
            for paper in sample_papers(papers_by_author[author.id], args.s2_sample)
        }
        s2_authors = s2.authors(list(s2_papers.values()))
        evidence = [
            (
                author,
                person,
                evidence_json(
                    s2_evidence(
                        author.name, papers_by_author[author.id], s2_authors, person
                    )
                ),
            )
            for author, people in chunk
            for person in people
        ]
        logger.info(
            "Checked %d authors on S2: %d candidates, %d with a match",
            len(chunk),
            len(evidence),
            sum(e["matched"] > 0 for _, _, e in evidence),
        )
        if args.dry_run:
            continue
        with db_manager.session_local() as db:
            db.execute(
                INSERT_CANDIDATE_SQL,
                [
                    {
                        "author_id": author.id,
                        "scholar_id": person.scholar_id,
                        "wikidata_qid": person.qid,
                        "s2_evidence": json.dumps(e),
                    }
                    for author, person, e in evidence
                ],
            )
            db.commit()


def read_profiles(client: httpx.Client, serp_key: str, reserve: int) -> None:
    """Spend this month's spare SerpAPI searches on the largest S2 matches."""
    serp = SerpApiScholar(serp_key, client)
    budget = serp.searches_left() - reserve
    with db_manager.session_local() as db:
        pending = db.execute(PENDING_PROFILES_SQL).all()
    logger.info(
        "Scholar profiles to read: %d; SerpAPI searches to spend: %d",
        len(pending),
        max(budget, 0),
    )
    read = 0
    for row in pending:
        # A profile costs up to three searches before any borderline re-read.
        if budget - serp.requests < serp.max_pages:
            break
        papers = load_papers([row.author_id])[row.author_id]
        try:
            profile, evidence = full_profile_evidence(
                serp, row.scholar_id, papers, row.common_name
            )
        except SerpApiQuotaExhausted as exc:
            logger.warning("%s; stopping", exc)
            break
        with db_manager.session_local() as db:
            db.execute(
                STORE_PROFILE_EVIDENCE_SQL,
                {
                    "author_id": row.author_id,
                    "scholar_id": row.scholar_id,
                    "evidence": json.dumps(evidence_json(evidence)),
                },
            )
            db.commit()
        read += 1
        logger.info(
            "Author %s -> %s (%s): %d/%d papers on profile -> %s",
            row.author_id,
            row.scholar_id,
            profile["name"],
            len(evidence.matched_paper_ids),
            evidence.considered,
            evidence.verdict,
        )
    logger.info("Read %d profiles with %d SerpAPI searches", read, serp.requests)


def store_links(dry_run: bool) -> None:
    """Store each proposed link that the Scholar profile itself confirmed."""
    with db_manager.session_local() as db:
        rows = [
            {
                "author_id": r.author_id,
                "scholar_id": r.scholar_id,
                "wikidata_qid": r.wikidata_qid,
                "s2": r.s2_evidence,
                "serpapi": r.serpapi_evidence,
            }
            for r in db.execute(
                text(
                    "SELECT author_id, scholar_id, wikidata_qid, s2_evidence, "
                    "serpapi_evidence FROM author_google_scholar_candidates"
                )
            )
        ]
        decide(rows)
        logger.info("Candidate statuses: %s", dict(Counter(r["status"] for r in rows)))
        # One row per author: two Wikidata items can share the same Scholar ID.
        confirmed = {
            r["author_id"]: r
            for r in rows
            if r["status"] == "proposed"
            and r["serpapi"]
            and r["serpapi"]["verdict"] == "verified"
        }
        linked = dict(
            db.execute(
                text("SELECT author_id, scholar_id FROM author_google_scholar_profiles")
            ).all()
        )
        owners = {scholar_id: author_id for author_id, scholar_id in linked.items()}
        new = 0
        for row in confirmed.values():
            owner = owners.get(row["scholar_id"], row["author_id"])
            if owner != row["author_id"]:
                logger.warning(
                    "Skipping author %s: %s is linked to author %s",
                    row["author_id"],
                    row["scholar_id"],
                    owner,
                )
                continue
            new += linked.get(row["author_id"]) != row["scholar_id"]
            if not dry_run:
                db.execute(
                    UPSERT_LINK_SQL,
                    {
                        "author_id": row["author_id"],
                        "scholar_id": row["scholar_id"],
                        "wikidata_qid": row["wikidata_qid"],
                        "matched": row["serpapi"]["matched"],
                        "considered": row["serpapi"]["considered"],
                        "matched_paper_ids": row["serpapi"]["matched_paper_ids"],
                    },
                )
        if not dry_run:
            db.commit()
    logger.info(
        "%s %d new links (%d Scholar-confirmed authors)",
        "Would store" if dry_run else "Stored",
        new,
        len(confirmed),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-papers", type=int, default=3)
    parser.add_argument(
        "--s2-authors", type=int, default=600, help="New authors checked on S2 per run"
    )
    parser.add_argument(
        "--s2-sample", type=int, default=15, help="Papers per author checked on S2"
    )
    parser.add_argument(
        "--serpapi-reserve",
        type=int,
        default=10,
        help="SerpAPI searches left unspent each month",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = get_settings()
    if not settings.serpapi_api_key and not args.dry_run:
        raise SystemExit("PWC_SERPAPI_API_KEY is not set")
    with httpx.Client() as client:
        check_new_authors(client, settings.semantic_scholar_api_key, args)
        if not args.dry_run:
            read_profiles(client, settings.serpapi_api_key, args.serpapi_reserve)
    store_links(args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
