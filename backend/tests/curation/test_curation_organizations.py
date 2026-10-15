"""Curator-proposed paper affiliations: linking and HF-backed org creation."""

import pytest
from pydantic import ValidationError
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.curation import CurationOrganization, EnrichPaperMutation
from backend.models.database import Base, Organization, Paper, PaperOrganization
from backend.services.curation_organization_service import (
    CurationOrganizationService,
    names_match,
)
from backend.services.hf_organization_service import (
    HFOrganizationProfile,
    parse_org_website,
)


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
        tables=[Paper.__table__, Organization.__table__, PaperOrganization.__table__],
    )
    session = Session(engine)
    session.add(
        Paper(
            id=1,
            title="Paper",
            abstract="Abstract",
            arxiv_id="2610.18861",
            source="arxiv",
            version="v1",
            is_latest_version=True,
        )
    )
    session.add(Organization(id=11, name="Meta", slug="facebook", hf_slug="facebook"))
    session.commit()
    return session


def _profile(handle, name, *, verified=False, followers=0):
    return HFOrganizationProfile(
        hf_slug=handle,
        name=name,
        logo_url=f"https://cdn-avatars.huggingface.co/{handle}.png",
        website_url=f"https://{handle.lower()}.example",
        is_verified=verified,
        followers=followers,
    )


class FakeHF:
    def __init__(self, *profiles, search=None):
        self.profiles = {item.hf_slug.lower(): item for item in profiles}
        self.results = search or {}
        self.closed = False

    def fetch_profile(self, handle):
        return self.profiles.get(handle.lower())

    def search(self, query):
        return self.results.get(query, [])

    def fetch_logo(self, url):
        return b"\x89PNG", "image/png"

    def close(self):
        self.closed = True


def _org(**values):
    return CurationOrganization(evidence="1 Affiliation", **values)


def test_existing_and_new_organizations_are_linked_without_removals():
    db = _session()
    db.add(Organization(id=12, name="Old", slug="old"))
    db.add(PaperOrganization(paper_id=1, organization_id=12, source="manual"))
    db.commit()
    hf = FakeHF(_profile("togethercomputer", "Together", verified=True))

    result = CurationOrganizationService(db, hf).link(
        1,
        [
            _org(organization_id=11, name="Meta"),
            _org(hf_slug="togethercomputer", name="Together AI"),
            _org(organization_id=12, name="Old"),
        ],
    )
    db.commit()

    created = db.query(Organization).filter_by(hf_slug="togethercomputer").one()
    assert created.slug == "together"
    assert created.website_url == "https://togethercomputer.example"
    assert created.logo_mime_type == "image/png" and created.logo_sha256
    assert result.linked == [11, created.id]
    assert result.already_linked == [12]
    links = {link.organization_id: link.source for link in db.query(PaperOrganization)}
    assert links == {11: "curation", 12: "manual", created.id: "curation"}


def test_known_hf_slug_links_existing_row_even_when_hf_has_no_profile():
    db = _session()
    result = CurationOrganizationService(db, FakeHF()).link(
        1, [_org(hf_slug="FACEBOOK", name="Meta")]
    )
    assert result.linked == [11]
    assert db.query(Organization).count() == 1


def test_squatted_catalog_row_yields_to_the_canonical_handle():
    db = _session()
    db.add(
        Organization(
            id=606,
            name="Stanford University",
            slug="stanforduniversity",
            hf_slug="StanfordUniversity",
        )
    )
    db.add(
        Organization(
            id=607,
            name="Stanford University",
            slug="stanforduniversityy",
            hf_slug="StanfordUniversityy",
        )
    )
    db.commit()
    hf = FakeHF(
        _profile("StanfordUniversityy", "Stanford University", followers=2),
        _profile("StanfordUniversity", "Stanford University", verified=True),
        search={"Stanford University": ["StanfordUniversity"]},
    )
    result = CurationOrganizationService(db, hf).link(
        1, [_org(hf_slug="StanfordUniversityy", name="Stanford University")]
    )
    assert result.linked == [606]


def test_lookalike_handle_resolves_to_the_established_organization():
    db = _session()
    hf = FakeHF(
        _profile("StanfordUniversityy", "Stanford University", followers=2),
        _profile("StanfordUniversity", "Stanford University", verified=True),
        search={"Stanford University": ["StanfordUniversity", "Stanford-Univ"]},
    )
    CurationOrganizationService(db, hf).link(
        1, [_org(hf_slug="StanfordUniversityy", name="Stanford University")]
    )
    assert (
        db.query(Organization).filter_by(slug="stanford-university").one().hf_slug
        == "StanfordUniversity"
    )


@pytest.mark.parametrize(
    "profile, name, reason",
    [
        (None, "Ghost Lab", "hf_organization_not_found"),
        (
            _profile("tinylab", "Tiny Lab", followers=3),
            "Tiny Lab",
            "hf_organization_not_established",
        ),
        (_profile("acme", "Acme Robotics", verified=True), "MIT", "name_mismatch"),
    ],
)
def test_unverifiable_organizations_are_skipped_not_created(profile, name, reason):
    db = _session()
    hf = FakeHF(*([profile] if profile else []))
    handle = profile.hf_slug if profile else "ghost"
    result = CurationOrganizationService(db, hf).link(
        1, [_org(hf_slug=handle, name=name)]
    )
    assert result.linked == []
    assert result.skipped[0]["reason"].startswith(reason)
    assert db.query(Organization).count() == 1


def test_same_named_row_without_hf_handle_is_completed_not_duplicated():
    db = _session()
    db.add(
        Organization(id=765, name="University of Chicago", slug="university-of-chicago")
    )
    db.commit()
    hf = FakeHF(_profile("Uchicago", "University of Chicago", verified=True))
    result = CurationOrganizationService(db, hf).link(
        1, [_org(hf_slug="Uchicago", name="University of Chicago")]
    )
    row = db.get(Organization, 765)
    assert result.linked == [765] and result.created == []
    assert row.hf_slug == "Uchicago" and row.website_url == "https://uchicago.example"


def test_new_organization_creation_is_capped_per_paper():
    db = _session()
    profiles = [_profile(f"lab{i}", f"Lab {i}", verified=True) for i in range(4)]
    result = CurationOrganizationService(db, FakeHF(*profiles)).link(
        1, [_org(hf_slug=f"lab{i}", name=f"Lab {i}") for i in range(4)]
    )
    assert len(result.created) == 3
    assert result.skipped[0]["reason"] == "new_organization_limit"


def test_unknown_organization_id_is_a_correctable_validation_error():
    with pytest.raises(ValueError, match="Invalid organization ID"):
        CurationOrganizationService(_session(), FakeHF()).link(
            1, [_org(organization_id=999, name="Nope")]
        )


def test_proposal_requires_exactly_one_target_and_evidence():
    with pytest.raises(ValidationError):
        CurationOrganization(name="Meta", evidence="FAIR")
    with pytest.raises(ValidationError):
        CurationOrganization(
            organization_id=11, hf_slug="facebook", name="Meta", evidence="x"
        )
    with pytest.raises(ValidationError):
        CurationOrganization(organization_id=11, name="Meta", evidence="")
    mutation = EnrichPaperMutation(
        organizations=[
            {"organization_id": 11, "name": "Meta", "evidence": "FAIR at Meta"}
        ]
    )
    assert mutation.organizations[0].organization_id == 11


@pytest.mark.parametrize(
    "proposed, hf_name, expected",
    [
        ("Together AI", "Together", True),
        ("Meta", "AI at Meta", True),
        ("The University of Tokyo", "University of Tokyo", True),
        ("MIT", "Massachusetts Institute of Technology", False),
        ("Acme", "Stanford University", False),
    ],
)
def test_names_match(proposed, hf_name, expected):
    assert names_match(proposed, hf_name) is expected


def test_parse_org_website_reads_first_external_link():
    page = '<a rel="nofollow" target="_blank">https://www.stanford.edu/</a>'
    assert parse_org_website(page) == "https://www.stanford.edu/"
    assert parse_org_website("<html></html>") is None


def test_same_named_row_with_another_handle_is_not_reused():
    db = _session()
    db.add(
        Organization(
            id=607,
            name="Stanford University",
            slug="stanforduniversityy",
            hf_slug="StanfordUniversityy",
        )
    )
    db.commit()
    hf = FakeHF(_profile("StanfordUniversity", "Stanford University", verified=True))
    result = CurationOrganizationService(db, hf).link(
        1, [_org(hf_slug="StanfordUniversity", name="Stanford University")]
    )
    assert result.created[0]["hf_slug"] == "StanfordUniversity"
    assert result.linked == [result.created[0]["id"]]
