"""Cold-start and same-day idempotency for organization rolling trends."""

from datetime import date, datetime, timezone

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from backend.config import get_settings
from backend.models.database import (
    Base,
    Organization,
    OrganizationTrendingHistory,
    Paper,
    PaperOrganization,
    PaperRepository,
    Repository,
)
from backend.services.organization_trending_service import (
    AUTO_FEATURE_MIN_PAPERS,
    OrganizationTrendingService,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


def _session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Organization.__table__,
            PaperOrganization.__table__,
            OrganizationTrendingHistory.__table__,
            Repository.__table__,
            PaperRepository.__table__,
        ],
    )
    session = sessionmaker(bind=engine, autoflush=False)()
    monkeypatch.setattr(get_settings(), "trending_ranking_mode", "composite")
    return session


def test_cold_start_writes_snapshot_and_rolling_score_with_autoflush_disabled(
    monkeypatch,
):
    session = _session(monkeypatch)
    session.add(
        Organization(
            id=1,
            name="Lab",
            slug="lab",
            hf_slug="lab",
            is_featured=True,
            display_order=1,
        )
    )
    session.add(
        Paper(
            id=1,
            title="Paper",
            abstract="Abstract",
            arxiv_id="2501.00001",
            source="arxiv",
            version="v1",
            is_latest_version=True,
            trending_score=12.5,
            trending_score_updated_at=datetime.now(timezone.utc),
        )
    )
    session.add(PaperOrganization(paper_id=1, organization_id=1, source="manual"))
    session.commit()

    service = OrganizationTrendingService(session)
    assert service.calculate(date(2026, 7, 29))["snapshots"] == 1
    organization = session.query(Organization).one()
    assert float(organization.trending_score) == 12.5
    assert organization.trending_score_updated_at is not None
    assert session.query(OrganizationTrendingHistory).count() == 1

    service.calculate(date(2026, 7, 29))
    assert session.query(OrganizationTrendingHistory).count() == 1


def test_organizations_with_enough_public_papers_are_featured(monkeypatch):
    session = _session(monkeypatch)
    session.add_all(
        [
            Organization(id=1, name="Big", slug="big", is_featured=False),
            Organization(id=2, name="Small", slug="small", is_featured=False),
            Organization(id=3, name="Kept", slug="kept", is_featured=True),
        ]
    )
    for paper_id in range(1, AUTO_FEATURE_MIN_PAPERS + 2):
        session.add(
            Paper(
                id=paper_id,
                title=f"Paper {paper_id}",
                # The last paper is not public, so "small" stays one short.
                abstract="" if paper_id == AUTO_FEATURE_MIN_PAPERS + 1 else "Abstract",
                arxiv_id=f"2501.{paper_id:05d}",
                source="arxiv",
                version="v1",
                is_latest_version=True,
            )
        )
        if paper_id <= AUTO_FEATURE_MIN_PAPERS:
            session.add(PaperOrganization(paper_id=paper_id, organization_id=1))
        if paper_id > 1:
            session.add(PaperOrganization(paper_id=paper_id, organization_id=2))
    session.commit()

    stats = OrganizationTrendingService(session).calculate(date(2026, 10, 26))

    featured = {
        organization.slug: organization.is_featured
        for organization in session.query(Organization)
    }
    assert featured == {"big": True, "small": False, "kept": True}
    assert stats["newly_featured"] == 1
    assert stats["snapshots"] == 2
