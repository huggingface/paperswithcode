"""Slugs from the legacy paperswithcode.com site, kept so old links resolve."""

from sqlalchemy import CheckConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.database.base import Base

LEGACY_SLUG_KINDS = ("paper", "sota", "dataset", "method")


class LegacyPwcSlug(Base):
    """One legacy URL slug and what it named.

    ``target`` is the arXiv id for ``paper`` rows and the legacy dataset or
    method name for ``sota``, ``dataset`` and ``method`` rows; routes resolve
    it against the live catalog at request time.
    """

    __tablename__ = "legacy_pwc_slugs"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('paper', 'sota', 'dataset', 'method')",
            name="legacy_pwc_slugs_kind_check",
        ),
    )

    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    slug: Mapped[str] = mapped_column(Text, primary_key=True)
    target: Mapped[str] = mapped_column(Text, nullable=False)
