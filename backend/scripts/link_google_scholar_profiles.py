"""Propose, and on `--apply` store, Google Scholar profile links for authors.

Candidates are Wikidata people with a Google Scholar ID (P1960) whose name fits
a PwC author with at least `--min-papers` papers. Each candidate is checked on
the author's papers through Semantic Scholar (ORCID / S2 author ID), and, with
SERPAPI_API_KEY set, against the Scholar profile's own publication list.

Writes `<out>/candidates.jsonl` (every candidate with evidence) and
`<out>/summary.md`; nothing reaches the database without `--apply`, which
stores the reviewed `proposed` links that the Scholar profile itself confirmed.

    python -m backend.scripts.link_google_scholar_profiles --out reports/scholar
    python -m backend.scripts.link_google_scholar_profiles --author-ids 117356
    python -m backend.scripts.link_google_scholar_profiles --out reports/scholar --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections import Counter, defaultdict
from pathlib import Path

import httpx
from sqlalchemy import text

from backend.database.connection import db_manager
from backend.services.google_scholar_link_service import (
    AuthorPaper,
    Evidence,
    SemanticScholarBatch,
    SerpApiQuotaExhausted,
    SerpApiScholar,
    candidate_people,
    fetch_wikidata_tsv,
    index_people_by_name,
    iter_chunks,
    parse_wikidata_tsv,
    s2_evidence,
    full_profile_evidence,
)

logger = logging.getLogger("link_google_scholar_profiles")

AUTHORS_SQL = text(
    """
    SELECT a.id, a.name, count(*) AS papers
    FROM authors a
    JOIN paper_authors pa ON pa.author_id = a.id
    JOIN papers p ON p.id = pa.paper_id AND p.is_latest_version
    WHERE (cast(:ids AS bigint[]) IS NULL OR a.id = ANY(:ids))
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


def load_people(path: Path):
    if not path.exists():
        with httpx.Client() as client:
            path.write_text(fetch_wikidata_tsv(client))
    return parse_wikidata_tsv(path.read_text())


def sample_papers(papers: list[AuthorPaper], size: int) -> list[AuthorPaper]:
    papers = sorted(papers, key=lambda p: p.paper_id)
    if len(papers) <= size:
        return papers
    step = len(papers) / size
    return [papers[int(i * step)] for i in range(size)]


def evidence_json(evidence: Evidence | None) -> dict | None:
    if evidence is None:
        return None
    return {
        "verdict": evidence.verdict,
        "considered": evidence.considered,
        "matched": len(evidence.matched_paper_ids),
        "share": round(evidence.share, 2),
        "matched_paper_ids": evidence.matched_paper_ids,
        "conflicting_paper_ids": evidence.conflicting_paper_ids,
    }


def decide(rows: list[dict]) -> None:
    """Set each candidate's status; only a sole verified person is proposed."""
    for row in rows:
        verdicts = [row["s2"]["verdict"]]
        if row["serpapi"]:
            # Scholar's own list is the stronger proof; it decides when present.
            verdicts = [row["serpapi"]["verdict"]]
        row["status"] = verdicts[0]
    by_author = defaultdict(list)
    for row in rows:
        by_author[row["author_id"]].append(row)
    for author_rows in by_author.values():
        verified = {r["scholar_id"] for r in author_rows if r["status"] == "verified"}
        for row in author_rows:
            if row["status"] == "verified":
                row["status"] = "proposed" if len(verified) == 1 else "ambiguous"
    by_scholar = defaultdict(list)
    for row in rows:
        if row["status"] == "proposed":
            by_scholar[row["scholar_id"]].append(row)
    for scholar_rows in by_scholar.values():
        if len(scholar_rows) > 1:
            # Several PwC rows for one person: likely duplicates to merge first.
            for row in scholar_rows:
                row["status"] = "shared_scholar_id"


def write_summary(path: Path, rows: list[dict], stats: dict) -> None:
    counts = Counter(r["status"] for r in rows)
    lines = [
        "# Google Scholar link dry run",
        "",
        *(f"- {k}: {v}" for k, v in stats.items()),
        "",
        "| status | candidates |",
        "|---|---|",
        *(f"| {k} | {v} |" for k, v in counts.most_common()),
        "",
    ]
    for status in ("proposed", "partial", "ambiguous", "shared_scholar_id"):
        sample = [r for r in rows if r["status"] == status][:40]
        if not sample:
            continue
        lines += [
            f"## {status} (first {len(sample)})",
            "",
            "| PwC author | papers | Scholar | Wikidata | S2 matched/considered | SerpAPI matched |",
            "|---|---|---|---|---|---|",
        ]
        for r in sample:
            serp = r["serpapi"]
            lines.append(
                f"| [{r['author_name']}](https://paperswithcode.co/authors/{r['author_id']}) "
                f"| {r['author_papers']} "
                f"| [{r['scholar_id']}](https://scholar.google.com/citations?user={r['scholar_id']}) "
                f"| [{r['qid']}](https://www.wikidata.org/wiki/{r['qid']}) "
                f"| {r['s2']['matched']}/{r['s2']['considered']}"
                f"{' (conflict)' if r['s2']['conflicting_paper_ids'] else ''} "
                f"| {f'{serp["matched"]}/{serp["considered"]}' if serp else '—'} |"
            )
        lines.append("")
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Report directory")
    parser.add_argument("--wikidata-tsv", type=Path, help="Cached P1960 export")
    parser.add_argument("--author-ids", type=int, nargs="*")
    parser.add_argument("--min-papers", type=int, default=3)
    parser.add_argument("--limit", type=int, help="Check at most this many authors")
    parser.add_argument(
        "--s2-sample", type=int, default=15, help="Papers per author checked on S2"
    )
    parser.add_argument(
        "--serpapi-pass",
        action="store_true",
        help="Only check Scholar profiles of candidates with any S2 match",
    )
    parser.add_argument(
        "--serpapi-limit", type=int, default=50, help="Max SerpAPI requests"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Store Scholar-confirmed proposed links from <out>/candidates.jsonl",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.apply:
        return apply_links(args.out)

    args.out.mkdir(parents=True, exist_ok=True)
    people = load_people(args.wikidata_tsv or args.out / "wikidata_p1960.tsv")
    index = index_people_by_name(people)
    logger.info("Wikidata people with Scholar IDs: %d", len(people))

    with db_manager.session_local() as db:
        authors = db.execute(
            AUTHORS_SQL, {"ids": args.author_ids, "min_papers": args.min_papers}
        ).all()
    candidates = {
        a.id: (a, people_for)
        for a in authors
        if (people_for := candidate_people(a.name, index))
    }
    author_ids = sorted(candidates, key=lambda i: -candidates[i][0].papers)[
        : args.limit
    ]
    logger.info(
        "Authors checked: %d, with name candidates: %d", len(authors), len(author_ids)
    )

    if args.serpapi_pass:
        return serpapi_pass(args.out, args.serpapi_limit)

    s2_key = (
        os.environ.get("PWC_SEMANTIC_SCHOLAR_API_KEY")
        or os.environ["SEMANTIC_SCHOLAR_API_KEY"]
    )
    # Rows are appended per chunk, so a rerun with the same --out resumes.
    rows = read_jsonl(args.out / "checked.jsonl")
    done = {row["author_id"] for row in rows}
    pending = [i for i in author_ids if i not in done]
    logger.info("Already checked: %d, remaining: %d", len(done), len(pending))
    with httpx.Client() as client, (args.out / "checked.jsonl").open("a") as checked:
        s2 = SemanticScholarBatch(s2_key, client)
        for chunk in iter_chunks(pending, 300):
            papers_by_author = load_papers(chunk)
            # Only people with an ORCID or S2 ID can be confirmed through S2,
            # and an even sample of each author's papers is enough to judge.
            s2_papers = {
                p.paper_id: p
                for author_id in chunk
                if any(
                    person.orcids or person.s2_ids
                    for person in candidates[author_id][1]
                )
                for p in sample_papers(papers_by_author[author_id], args.s2_sample)
            }
            s2_authors = s2.authors(list(s2_papers.values()))
            chunk_rows = [
                {
                    "author_id": author_id,
                    "author_name": author.name,
                    "author_papers": author.papers,
                    "qid": person.qid,
                    "scholar_id": person.scholar_id,
                    "wikidata_names": person.names,
                    "s2": evidence_json(
                        s2_evidence(
                            author.name,
                            papers_by_author[author_id],
                            s2_authors,
                            person,
                        )
                    ),
                }
                for author_id in chunk
                for author, people_for in [candidates[author_id]]
                for person in people_for
            ]
            for row in chunk_rows:
                checked.write(json.dumps(row) + "\n")
            checked.flush()
            rows += chunk_rows
            logger.info(
                "Checked %d/%d authors (%d S2 requests)",
                len({r["author_id"] for r in rows}),
                len(author_ids),
                s2.requests,
            )

    stats = {
        "Wikidata people with a valid Scholar ID": len(people),
        f"PwC authors with >= {args.min_papers} papers checked": len(authors),
        "PwC authors with a name candidate": len(candidates),
        "Semantic Scholar requests (this run)": s2.requests,
    }
    write_report(args.out, stats)
    return 0


def serpapi_pass(out: Path, limit: int) -> int:
    """Check Scholar profiles for candidates with any S2 match.

    `limit` caps SerpAPI requests across all passes into the same `out`.
    """
    rows = read_jsonl(out / "checked.jsonl")
    # Several Wikidata researchers with this name: the bar is higher.
    common = {a for a, n in Counter(r["author_id"] for r in rows).items() if n > 1}
    serp_path = out / "serpapi.jsonl"
    checked_before = read_jsonl(serp_path)
    used = sum(r.get("requests", 0) for r in checked_before)
    done = {(r["author_id"], r["scholar_id"]) for r in checked_before}
    todo = [
        r
        for r in rows
        if r["s2"]["matched"] and (r["author_id"], r["scholar_id"]) not in done
    ]
    todo.sort(key=lambda r: -r["author_papers"])
    logger.info(
        "SerpAPI candidates: %d (already done: %d, requests used: %d/%d)",
        len(todo),
        len(done),
        used,
        limit,
    )
    with httpx.Client() as client, serp_path.open("a") as f:
        serp = SerpApiScholar(os.environ["SERPAPI_API_KEY"], client)
        for row in todo:
            if used + serp.requests >= limit:
                break
            before = serp.requests
            papers = load_papers([row["author_id"]])[row["author_id"]]
            common_name = row["author_id"] in common
            try:
                profile, evidence = full_profile_evidence(
                    serp, row["scholar_id"], papers, common_name
                )
            except SerpApiQuotaExhausted as exc:
                logger.warning("%s; stopping this pass", exc)
                break
            f.write(
                json.dumps(
                    {
                        "author_id": row["author_id"],
                        "scholar_id": row["scholar_id"],
                        "profile_name": profile["name"],
                        "affiliations": profile["affiliations"],
                        "cited_by": profile["cited_by"],
                        "articles": len(profile["articles"]),
                        "complete": profile["complete"],
                        "common_name": common_name,
                        "requests": serp.requests - before,
                        "serpapi": evidence_json(evidence),
                    }
                )
                + "\n"
            )
            f.flush()
            logger.info(
                "%s -> %s (%s): %d/%d papers on profile%s -> %s",
                row["author_name"],
                row["scholar_id"],
                profile["name"],
                len(evidence.matched_paper_ids),
                evidence.considered,
                " [common name]" if common_name else "",
                evidence.verdict,
            )
        logger.info("SerpAPI requests: %d", serp.requests)
    write_report(out, {"SerpAPI requests (this run)": serp.requests})
    return 0


def write_report(out: Path, stats: dict) -> None:
    rows = read_jsonl(out / "checked.jsonl")
    serp = {
        (r["author_id"], r["scholar_id"]): r for r in read_jsonl(out / "serpapi.jsonl")
    }
    for row in rows:
        checked = serp.get((row["author_id"], row["scholar_id"]))
        row["serpapi"] = checked["serpapi"] if checked else None
        row["profile_name"] = checked["profile_name"] if checked else None
    decide(rows)
    with (out / "candidates.jsonl").open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    stats = {
        "PwC authors evidence-checked": len({r["author_id"] for r in rows}),
        "Scholar profiles checked via SerpAPI": len(serp),
        **stats,
    }
    write_summary(out / "summary.md", rows, stats)
    logger.info("Statuses: %s", dict(Counter(r["status"] for r in rows)))


UPSERT_SQL = text(
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


def apply_links(out: Path) -> int:
    """Store proposed links whose Scholar profile lists the author's papers."""
    rows = [
        r
        for r in read_jsonl(out / "candidates.jsonl")
        if r["status"] == "proposed"
        and r.get("serpapi")
        and r["serpapi"]["verdict"] == "verified"
    ]
    with db_manager.session_local() as db:
        existing = dict(
            db.execute(
                text("SELECT scholar_id, author_id FROM author_google_scholar_profiles")
            ).all()
        )
        live = set(
            db.execute(
                text("SELECT id FROM authors WHERE id = ANY(:ids)"),
                {"ids": [r["author_id"] for r in rows]},
            ).scalars()
        )
        stored = 0
        for row in rows:
            owner = existing.get(row["scholar_id"], row["author_id"])
            if row["author_id"] not in live or owner != row["author_id"]:
                logger.warning(
                    "Skipping author %s -> %s (author gone or profile linked to %s)",
                    row["author_id"],
                    row["scholar_id"],
                    owner,
                )
                continue
            evidence = row["serpapi"]
            db.execute(
                UPSERT_SQL,
                {
                    "author_id": row["author_id"],
                    "scholar_id": row["scholar_id"],
                    "wikidata_qid": row["qid"],
                    "matched": evidence["matched"],
                    "considered": evidence["considered"],
                    "matched_paper_ids": evidence["matched_paper_ids"],
                },
            )
            stored += 1
        db.commit()
    logger.info("Stored %d of %d Scholar-confirmed links", stored, len(rows))
    return 0


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open() if line.endswith("\n")]


def load_papers(author_ids: list[int]) -> dict[int, list[AuthorPaper]]:
    papers_by_author: dict[int, list[AuthorPaper]] = defaultdict(list)
    with db_manager.session_local() as db:
        for r in db.execute(PAPERS_SQL, {"ids": author_ids}):
            papers_by_author[r.author_id].append(
                AuthorPaper(
                    r.id, r.title, r.arxiv_id, r.semantic_scholar_id, r.author_order
                )
            )
    return papers_by_author


if __name__ == "__main__":
    raise SystemExit(main())
