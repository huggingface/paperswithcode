"""Shared ordering for choosing a paper's primary code repository."""

from sqlalchemy import asc, desc

from backend.models.database import PaperRepository, Repository


def primary_repository_order() -> tuple:
    """Official repositories first, then the most starred, then by URL."""
    return (
        desc(PaperRepository.is_official),
        desc(Repository.num_stars).nullslast(),
        asc(Repository.url),
    )
