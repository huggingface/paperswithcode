"""Strict-allowlist and idempotency tests for HF organization links."""

import asyncio

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import Base, Organization, Paper, PaperOrganization
from backend.services.organization_sync_service import link_daily_paper_organizations
from backend.services.hf_organization_service import (
    HFOrganizationData,
    HFOrganizationPaper,
)
from backend.services.organization_sync_service import OrganizationSyncService


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Organization.__table__,
            PaperOrganization.__table__,
        ],
    )
    session = Session(engine)
    session.add(
        Paper(
            id=1,
            title="Paper",
            abstract="Abstract",
            arxiv_id="2501.00001",
            source="arxiv",
            version="v1",
            is_latest_version=True,
        )
    )
    session.commit()
    return session


def test_daily_payload_links_object_and_is_idempotent():
    session = _session()
    payload = {"name": "Qwen", "fullname": "Qwen", "avatar": "https://example"}
    first = link_daily_paper_organizations(session, 1, payload)
    second = link_daily_paper_organizations(session, 1, [payload])
    assert first["linked"] == 1
    assert second["already_linked"] == 1
    assert session.query(Organization).one().slug == "qwen"
    assert session.query(PaperOrganization).one().source == "hf_org_papers"


def test_unknown_payload_creates_no_rows_or_links():
    session = _session()
    result = link_daily_paper_organizations(
        session, 1, {"name": "not-in-the-launch-manifest"}
    )
    assert result["unknown_organizations_seen"] == 1
    assert session.query(Organization).count() == 0
    assert session.query(PaperOrganization).count() == 0


def test_hf_provenance_replaces_lower_confidence_existing_source():
    session = _session()
    organization = Organization(
        id=1,
        name="OpenAI",
        slug="openai",
        hf_slug="openai",
        is_featured=True,
        display_order=18,
    )
    session.add(organization)
    session.add(
        PaperOrganization(
            paper_id=1,
            organization_id=1,
            source="manual",
            added_by_hf_subject="hf-user-123",
            added_by_hf_username="curator",
        )
    )
    session.commit()
    link_daily_paper_organizations(session, 1, {"name": "openai"})
    link = session.query(PaperOrganization).one()
    assert link.source == "hf_org_papers"
    assert link.added_by_hf_subject is None
    assert link.added_by_hf_username is None


def test_arbitrary_hf_organization_sync_creates_featured_row_and_links_paper():
    session = _session()

    class FakeHFClient:
        def fetch(self, hf_slug):
            assert hf_slug == "HKUST"
            return HFOrganizationData(
                hf_slug=hf_slug,
                name="HKUST",
                logo_url=None,
                website_url="https://hkust.edu.hk",
                upstream_paper_count=1,
                papers=(HFOrganizationPaper("2501.00001", "Paper"),),
            )

    service = OrganizationSyncService(session, hf_client=FakeHFClient())
    stats = asyncio.run(service.sync_hf_slug("HKUST"))

    organization = session.query(Organization).one()
    assert organization.slug == "hkust"
    assert organization.hf_slug == "HKUST"
    assert organization.is_featured is True
    assert organization.display_order == 1
    assert stats.linked == 1
    assert session.query(PaperOrganization).one().source == "hf_org_papers"


def test_arbitrary_hf_organization_sync_rejects_slug_collision():
    session = _session()
    session.add(
        Organization(
            name="Existing Lab",
            slug="existing-lab",
            hf_slug="existing.lab",
        )
    )
    session.commit()

    class UnusedHFClient:
        def fetch(self, _hf_slug):
            raise AssertionError("Hub must not be called for a slug collision")

    service = OrganizationSyncService(session, hf_client=UnusedHFClient())

    with pytest.raises(ValueError, match="already belongs"):
        asyncio.run(service.sync_hf_slug("existing-lab"))


def test_featured_sync_combines_hf_alias_papers():
    session = _session()
    session.add(
        Paper(
            id=2,
            title="Llama Paper",
            abstract="Abstract",
            arxiv_id="2501.00002",
            source="arxiv",
            version="v1",
            is_latest_version=True,
        )
    )
    session.commit()

    seen_hf_slugs = []

    class FakeHFClient:
        def fetch(self, hf_slug):
            seen_hf_slugs.append(hf_slug)
            arxiv_id = "2501.00001" if hf_slug == "facebook" else "2501.00002"
            return HFOrganizationData(
                hf_slug=hf_slug,
                name="Meta",
                logo_url=None,
                website_url="https://meta.com",
                upstream_paper_count=1,
                papers=(HFOrganizationPaper(arxiv_id, "Paper"),),
            )

        def fetch_logo(self, url):
            assert "64c115d1f661ace7c4022432" in url
            return b"meta-models-logo", "image/webp"

    service = OrganizationSyncService(session, hf_client=FakeHFClient())
    stats = asyncio.run(service.sync("facebook"))

    organization = session.query(Organization).one()
    assert organization.name == "Meta"
    assert organization.hf_slug == "facebook"
    assert organization.hf_paper_count == 2
    assert "64c115d1f661ace7c4022432" in organization.logo_url
    assert organization.logo_data == b"meta-models-logo"
    assert organization.logo_mime_type == "image/webp"
    assert stats.fetched == 2
    assert stats.linked == 2
    assert seen_hf_slugs == [
        "facebook",
        "meta-llama",
        "AI-at-Meta",
        "facebook-research",
        "metaresearch",
        "MetaSuperintelligenceLab",
        "meta-models",
    ]
