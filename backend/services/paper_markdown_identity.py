"""Map public catalog paper identifiers to the keys Paper Markdown is stored under."""

from sqlalchemy.orm import Session

from backend.database.paper_merge import lookup_paper_merge_redirect
from backend.models.database import Paper as DBPaper


def resolve_markdown_paper_id(db: Session, paper_id: str) -> str:
    if not paper_id.isdigit():
        return paper_id
    catalog_id = int(paper_id)
    redirect = lookup_paper_merge_redirect(db, catalog_id)
    if redirect:
        return resolve_markdown_paper_id(db, redirect)
    arxiv_id = (
        db.query(DBPaper.arxiv_id)
        .filter(DBPaper.id == catalog_id, DBPaper.source == "arxiv")
        .scalar()
    )
    return arxiv_id or paper_id
