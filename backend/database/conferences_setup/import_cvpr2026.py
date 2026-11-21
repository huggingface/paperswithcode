#!/usr/bin/env python3
"""
Import CVPR 2026 papers from data/cvpr2026_papers.csv into the database.

1. Upserts the CVPR 2026 conference row.
2. Creates missing papers (title, abstract, authors) or updates existing ones.
3. Sets proceeding='CVPR 2026' and conference URLs.
4. Links papers to the conference via paper_conferences.
5. Links GitHub repos and project pages when present.
6. Runs the task keyword matcher (add-only) for auto task tagging.
"""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.database.tasks_setup.link_papers_by_task_keywords import (
    link_papers_by_task_keywords,
)
from backend.models.database import Author
from backend.models.database import Conference
from backend.models.database import Paper
from backend.models.database import PaperAuthor
from backend.models.database import PaperConference
from backend.models.database import PaperProjectPage
from backend.models.database import PaperRepository
from backend.models.database import ProjectPage
from backend.models.database import Repository
from backend.services.repository_service import find_repository_by_url
from backend.utils.github_utils import normalize_github_url, parse_github_url

CSV_PATH = Path(__file__).resolve().parents[3] / "data" / "cvpr2026_papers.csv"
PROCEEDING = "CVPR 2026"
CONFERENCE_SLUG = "cvpr-2026"
CONFERENCE_IMAGE_URL = "https://paperswithcode.co/images/conferences/cvpr-2026.png"
CONFERENCE_IMAGE_CREDIT = "[CVPR 2026](https://cvpr.thecvf.com/)"
CONFERENCE_HF_URL = "https://huggingface.co/datasets/ai-conferences/CVPR2026"
CONFERENCE_DESCRIPTION = (
    "CVPR (IEEE/CVF Conference on Computer Vision and Pattern Recognition) is a "
    "flagship venue for computer vision, video understanding, and related machine "
    "learning research. Browse accepted papers from CVPR 2026 in Denver, grouped by "
    "research area and task, with code, project links, evals and Hugging Face "
    "artifacts where available."
)


def proceeding_for_row(row: dict) -> str:
    presentation_type = (row.get("presentation_type") or "").strip().lower()
    if presentation_type == "oral":
        return f"{PROCEEDING} Oral"
    if presentation_type == "highlight":
        return f"{PROCEEDING} Spotlight"
    return PROCEEDING


def upsert_conference(db: Session) -> Conference:
    conference = db.query(Conference).filter(Conference.slug == CONFERENCE_SLUG).first()
    if conference is None:
        conference = Conference(
            name=PROCEEDING,
            slug=CONFERENCE_SLUG,
            short_name="CVPR",
            year=2026,
            url="https://cvpr.thecvf.com/",
            start_date=date(2026, 6, 3),
            end_date=date(2026, 6, 7),
            venue="Colorado Convention Center",
            location="Denver, USA",
            description=CONFERENCE_DESCRIPTION,
            image_url=CONFERENCE_IMAGE_URL,
            image_credit=CONFERENCE_IMAGE_CREDIT,
            hf_url=CONFERENCE_HF_URL,
        )
        db.add(conference)
        db.flush()
    else:
        conference.name = PROCEEDING
        conference.short_name = "CVPR"
        conference.year = 2026
        conference.url = "https://cvpr.thecvf.com/"
        conference.start_date = date(2026, 6, 3)
        conference.end_date = date(2026, 6, 7)
        conference.venue = "Colorado Convention Center"
        conference.location = "Denver, USA"
        conference.description = CONFERENCE_DESCRIPTION
        conference.image_url = CONFERENCE_IMAGE_URL
        conference.image_credit = CONFERENCE_IMAGE_CREDIT
        conference.hf_url = CONFERENCE_HF_URL
    db.commit()
    db.refresh(conference)
    return conference


def get_or_create_paper(db: Session, row: dict) -> tuple[Paper, bool]:
    arxiv_id = (row.get("arxiv_id") or "").strip()
    if not arxiv_id:
        raise ValueError("Missing arxiv_id")

    paper = (
        db.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version)
        .order_by(Paper.id.desc())
        .first()
    )
    created = False
    if paper is None:
        paper = Paper(
            arxiv_id=arxiv_id,
            title=(row.get("title") or "").strip(),
            abstract=(row.get("abstract") or "").strip() or None,
            version="v1",
            is_latest_version=True,
            source="arxiv",
        )
        db.add(paper)
        db.flush()
        created = True

    paper.proceeding = proceeding_for_row(row)
    cvf_html = (row.get("cvf_html_url") or "").strip()
    pdf_url = (row.get("pdf_url") or "").strip()
    if cvf_html:
        paper.conference_url_abs = cvf_html
    if pdf_url:
        paper.conference_url_pdf = pdf_url

    return paper, created


def link_authors(db: Session, paper: Paper, authors_str: str) -> int:
    if not authors_str:
        return 0

    added = 0
    seen: set[str] = set()
    for order, raw_name in enumerate(authors_str.split(";"), start=1):
        name = raw_name.strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        author = db.query(Author).filter(Author.name == name).first()
        if author is None:
            author = Author(name=name)
            db.add(author)
            db.flush()

        link = (
            db.query(PaperAuthor)
            .filter(
                PaperAuthor.paper_id == paper.id,
                PaperAuthor.author_id == author.id,
            )
            .first()
        )
        if link is None:
            db.add(
                PaperAuthor(
                    paper_id=paper.id,
                    author_id=author.id,
                    author_order=order,
                )
            )
            added += 1

    return added


def link_github_repo(db: Session, paper: Paper, github_url: str) -> bool:
    normalized = normalize_github_url(github_url.strip())
    if not normalized:
        return False

    owner, name = parse_github_url(normalized)
    repo = find_repository_by_url(db, normalized)
    if repo is None:
        repo = Repository(
            url=normalized,
            owner=owner,
            name=name,
            num_stars=0,
            source="cvpr2026_import",
        )
        db.add(repo)
        db.flush()
    elif repo.url != normalized:
        repo.url = normalized
        repo.owner = repo.owner or owner
        repo.name = repo.name or name

    variant_links = (
        db.query(PaperRepository)
        .join(Repository, Repository.id == PaperRepository.repository_id)
        .filter(
            PaperRepository.paper_id == paper.id,
            func.lower(Repository.url) == normalized.lower(),
            PaperRepository.repository_id != repo.id,
        )
        .all()
    )
    for variant_link in variant_links:
        db.delete(variant_link)

    link = (
        db.query(PaperRepository)
        .filter(
            PaperRepository.paper_id == paper.id,
            PaperRepository.repository_id == repo.id,
        )
        .first()
    )
    if link is None:
        db.add(
            PaperRepository(
                paper_id=paper.id,
                repository_id=repo.id,
                is_official=True,
            )
        )
        return True
    if not link.is_official:
        link.is_official = True
    return False


def link_project_page(db: Session, paper: Paper, project_url: str) -> bool:
    url = project_url.strip()
    if not url:
        return False

    page = db.query(ProjectPage).filter(ProjectPage.url == url).first()
    if page is None:
        page = ProjectPage(url=url, is_official=True, source="cvpr2026_import")
        db.add(page)
        db.flush()

    link = (
        db.query(PaperProjectPage)
        .filter(
            PaperProjectPage.paper_id == paper.id,
            PaperProjectPage.project_page_id == page.id,
        )
        .first()
    )
    if link is None:
        db.add(PaperProjectPage(paper_id=paper.id, project_page_id=page.id))
        return True
    return False


def link_conference(db: Session, paper: Paper, conference: Conference) -> bool:
    link = (
        db.query(PaperConference)
        .filter(
            PaperConference.paper_id == paper.id,
            PaperConference.conference_id == conference.id,
        )
        .first()
    )
    if link is None:
        db.add(
            PaperConference(
                paper_id=paper.id,
                conference_id=conference.id,
                source="manual",
            )
        )
        return True
    return False


def update_proceedings_from_csv(db: Session) -> dict[str, int]:
    stats = {"rows": 0, "updated": 0, "skipped_no_arxiv": 0, "skipped_not_found": 0}
    with CSV_PATH.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            stats["rows"] += 1
            arxiv_id = (row.get("arxiv_id") or "").strip()
            if not arxiv_id:
                stats["skipped_no_arxiv"] += 1
                continue
            paper = (
                db.query(Paper)
                .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version)
                .order_by(Paper.id.desc())
                .first()
            )
            if paper is None:
                stats["skipped_not_found"] += 1
                continue
            paper.proceeding = proceeding_for_row(row)
            stats["updated"] += 1
    db.commit()
    return stats


def import_csv(db: Session, conference: Conference) -> dict[str, int]:
    stats = {
        "rows": 0,
        "papers_created": 0,
        "papers_updated": 0,
        "conference_links_added": 0,
        "authors_added": 0,
        "repos_linked": 0,
        "project_pages_linked": 0,
        "errors": 0,
    }

    with CSV_PATH.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats["rows"] += 1
            try:
                paper, created = get_or_create_paper(db, row)
                if created:
                    stats["papers_created"] += 1
                else:
                    stats["papers_updated"] += 1

                stats["authors_added"] += link_authors(
                    db, paper, row.get("authors") or ""
                )

                github_url = (row.get("github_url") or "").strip()
                if github_url and link_github_repo(db, paper, github_url):
                    stats["repos_linked"] += 1

                project_url = (row.get("project_page_url") or "").strip()
                if project_url and link_project_page(db, paper, project_url):
                    stats["project_pages_linked"] += 1

                if link_conference(db, paper, conference):
                    stats["conference_links_added"] += 1

                if stats["rows"] % 500 == 0:
                    db.commit()
                    print(f"  processed {stats['rows']} rows...")
            except Exception as exc:
                stats["errors"] += 1
                print(f"  error on row {stats['rows']}: {exc}")

    db.commit()
    return stats


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Import CVPR 2026 papers")
    parser.add_argument(
        "--proceedings-only",
        action="store_true",
        help="Only update proceeding labels (Oral/Spotlight) from CSV",
    )
    args = parser.parse_args()

    if not CSV_PATH.exists():
        print(f"CSV not found: {CSV_PATH}")
        sys.exit(1)

    print("=" * 80)
    if args.proceedings_only:
        print("Updating CVPR 2026 proceeding labels")
    else:
        print("Importing CVPR 2026 papers")
    print("=" * 80)

    session = db_manager.session_local()
    try:
        if args.proceedings_only:
            stats = update_proceedings_from_csv(session)
            print("\n" + "=" * 80)
            print("Proceeding update complete")
            print("=" * 80)
            for key, value in stats.items():
                print(f"  {key}: {value}")
            return

        print("\n1. Upserting conference row...")
        conference = upsert_conference(session)
        print(f"   conference id={conference.id} slug={conference.slug}")

        print(f"\n2. Importing papers from {CSV_PATH}...")
        stats = import_csv(session, conference)

        print("\n3. Running task keyword matcher (add-only)...")
        link_papers_by_task_keywords(rebuild=False)

        print("\n" + "=" * 80)
        print("Import complete")
        print("=" * 80)
        for key, value in stats.items():
            print(f"  {key}: {value}")
    except Exception as exc:
        session.rollback()
        print(f"Import failed: {exc}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
