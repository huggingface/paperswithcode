"""Rank the methods shown as "Related methods" on a method page.

Candidates come from three signals, in priority order:

1. Hand-curated siblings for methods whose co-tagging is too sparse or noisy.
2. Methods linked from either method's description (``[Name](/methods/slug)``),
   which curators write to name a method's closest relatives.
3. Methods tagged on the same papers, scored by cosine similarity of their
   paper sets so that ubiquitous methods (Transformer, LLM) do not dominate.

Within the description-link tier, candidates are ordered by co-tagging score.
"""

import math
import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.database import Method as DBMethod, PaperMethod
from backend.models.taxonomy import RelatedMethod
from backend.services.catalog_errors import CatalogNotFoundError

CURATED_RELATED_METHODS: dict[str, list[str]] = {
    "on-policy-distillation": [
        "fine-tuning",
        "post-training",
        "rlvr",
        "rlhf",
        "direct-preference-optimization-dpo",
    ],
    "mcp": ["agent-skills"],
    "agent-skills": ["mcp"],
}

# A co-tagged method must share at least this many papers and reach this
# cosine score; below that the overlap is dominated by generic components.
MIN_SHARED_PAPERS = 3
MIN_COSINE = 0.05

METHOD_LINK_RE = re.compile(r"\]\(/methods/([a-z0-9-]+)\)")


class MethodRelatedService:
    def __init__(self, db: Session):
        self.db = db

    def get_related_methods(self, identifier: str, limit: int) -> list[RelatedMethod]:
        methods = self.db.query(
            DBMethod.id, DBMethod.name, DBMethod.slug, DBMethod.description
        ).all()
        target = next(
            (
                m
                for m in methods
                if identifier in (str(m.id), m.slug)
                or m.name.lower() == identifier.lower()
            ),
            None,
        )
        if target is None:
            raise CatalogNotFoundError(f"Method '{identifier}' not found")
        by_slug = {m.slug: m for m in methods if m.slug}

        scores = self._co_tagging_scores(target.id)
        linked = set(METHOD_LINK_RE.findall(target.description or ""))
        linked.update(
            m.slug
            for m in methods
            if f"](/methods/{target.slug})" in (m.description or "")
        )

        ordered: list[str] = list(CURATED_RELATED_METHODS.get(target.slug, []))
        ordered += sorted(
            (slug for slug in linked if slug in by_slug),
            key=lambda slug: (-scores.get(by_slug[slug].id, 0.0), slug),
        )
        id_to_slug = {m.id: m.slug for m in methods}
        ordered += [
            id_to_slug[method_id]
            for method_id, score in sorted(scores.items(), key=lambda item: -item[1])
            if score >= MIN_COSINE and id_to_slug.get(method_id)
        ]

        results: list[RelatedMethod] = []
        seen = {target.slug}
        for slug in ordered:
            if slug in seen or slug not in by_slug:
                continue
            seen.add(slug)
            method = by_slug[slug]
            results.append(RelatedMethod(id=method.id, name=method.name, slug=slug))
            if len(results) == limit:
                break
        return results

    def _co_tagging_scores(self, method_id: int) -> dict[int, float]:
        target_papers = (
            self.db.query(PaperMethod.paper_id)
            .filter(PaperMethod.method_id == method_id)
            .subquery()
        )
        shared = dict(
            self.db.query(PaperMethod.method_id, func.count())
            .join(target_papers, target_papers.c.paper_id == PaperMethod.paper_id)
            .filter(PaperMethod.method_id != method_id)
            .group_by(PaperMethod.method_id)
            .having(func.count() >= MIN_SHARED_PAPERS)
            .all()
        )
        if not shared:
            return {}
        totals = dict(
            self.db.query(PaperMethod.method_id, func.count())
            .filter(PaperMethod.method_id.in_([method_id, *shared]))
            .group_by(PaperMethod.method_id)
            .all()
        )
        target_total = totals[method_id]
        return {
            other_id: count / math.sqrt(target_total * totals[other_id])
            for other_id, count in shared.items()
        }
