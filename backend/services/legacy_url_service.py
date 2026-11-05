"""Resolve legacy paperswithcode.com URLs to the current catalog pages."""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.models.database import Dataset, LegacyPwcSlug, Method


class LegacyUrlService:
    def __init__(self, db: Session):
        self.db = db

    def _legacy_target(self, kind: str, slug: str) -> Optional[str]:
        return (
            self.db.query(LegacyPwcSlug.target)
            .filter(LegacyPwcSlug.kind == kind, LegacyPwcSlug.slug == slug)
            .scalar()
        )

    def paper_path(self, slug: str) -> Optional[str]:
        """``/paper/<legacy-slug>`` names an arXiv paper; the paper route
        handles both indexed and not-yet-indexed ids."""
        arxiv_id = self._legacy_target("paper", slug)
        return f"/paper/{quote(arxiv_id, safe='')}" if arxiv_id else None

    def method_path(self, slug: str) -> Optional[str]:
        if self.db.query(Method.id).filter(Method.slug == slug).first():
            return f"/methods/{slug}"
        name = self._legacy_target("method", slug)
        if name is None:
            return None
        match = (
            self.db.query(Method.slug)
            .filter(func.lower(Method.name) == name.lower())
            .order_by(Method.id)
            .first()
        )
        return f"/methods/{match.slug}" if match else None

    def _dataset_slug_by_name(self, name: str) -> Optional[str]:
        match = (
            self.db.query(Dataset.slug)
            .filter(
                or_(
                    func.lower(Dataset.name) == name.lower(),
                    Dataset.aliases.any(name),
                )
            )
            .order_by(Dataset.num_papers.desc(), Dataset.id)
            .first()
        )
        return match.slug if match else None

    def _dataset_exists(self, slug: str) -> bool:
        return (
            self.db.query(Dataset.id).filter(Dataset.slug == slug).first() is not None
        )

    def dataset_path(self, slug: str) -> Optional[str]:
        if self._dataset_exists(slug):
            return f"/benchmark/{slug}"
        name = self._legacy_target("dataset", slug)
        match = self._dataset_slug_by_name(name) if name else None
        return f"/benchmark/{match}" if match else None

    def sota_path(self, slug: str) -> Optional[str]:
        """``/sota/<task>-on-<dataset>`` leaderboards map to the dataset's
        benchmark page."""
        name = self._legacy_target("sota", slug)
        match = self._dataset_slug_by_name(name) if name else None
        if match is None:
            parts = slug.split("-on-")
            for start in range(1, len(parts)):
                candidate = "-on-".join(parts[start:])
                if self._dataset_exists(candidate):
                    match = candidate
                    break
        return f"/benchmark/{match}" if match else None
