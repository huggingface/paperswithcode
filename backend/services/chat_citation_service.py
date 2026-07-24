"""Authoritative resolution of internal ``paper:`` citations."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from backend.services.paper_service import PaperNotFoundError, PaperService

_PAPER_LINK = re.compile(r"\[[^\]\n]{1,500}\]\(paper:([^) \t\n]{1,200})\)")


def cited_route_ids(text: str, maximum: int = 20) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for match in _PAPER_LINK.finditer(text):
        route_id = match.group(1)
        if route_id not in seen:
            seen.add(route_id)
            result.append(route_id)
        if len(result) >= maximum:
            break
    return result


def resolve_citations(db: Session, text: str, maximum: int = 20) -> list[dict]:
    service = PaperService(db)
    resolved: list[dict] = []
    for route_id in cited_route_ids(text, maximum):
        try:
            paper = service.get_paper_by_id_or_arxiv(route_id)
        except PaperNotFoundError:
            continue
        resolved.append(
            {
                "position": len(resolved),
                "route_id": paper.arxiv_id or str(paper.id),
                "title": paper.title,
                "source_url": paper.source_url or paper.url_abs,
                "authors": paper.authors[:50],
                "published": paper.published.isoformat() if paper.published else None,
                "conference": paper.conference_name or paper.conference,
            }
        )
    return resolved
