"""Resolve curator-proposed paper affiliations to catalog organizations.

The enrichment curator reads a paper's first page and proposes the labs and
universities behind it, either as existing catalog organizations or as Hugging
Face organization handles. Links are only ever added. A missing organization is
created from its Hugging Face profile (name, website, logo) only when that
profile is verified or established, so squatted look-alike handles never enter
the catalog.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.curation import CurationOrganization
from backend.models.database import Organization, PaperOrganization
from backend.services.hf_organization_service import (
    HFOrganizationClient,
    HFOrganizationError,
    HFOrganizationProfile,
)
from backend.utils.slug_utils import slugify

logger = logging.getLogger(__name__)

CURATION_SOURCE = "curation"
MAX_NEW_ORGANIZATIONS = 3
MIN_UNVERIFIED_FOLLOWERS = 20
MAX_LOOKALIKE_PROFILES = 3


def normalize_organization_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    text = re.sub(r"\bthe\b", "", text.lower())
    return re.sub(r"[^a-z0-9]", "", text)


def names_match(proposed: str, hf_name: str) -> bool:
    left = normalize_organization_name(proposed)
    right = normalize_organization_name(hf_name)
    if not left or not right:
        return False
    if left == right:
        return True
    if min(len(left), len(right)) >= 4 and (left in right or right in left):
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.85


@dataclass
class OrganizationLinkResult:
    linked: list[int] = field(default_factory=list)
    already_linked: list[int] = field(default_factory=list)
    created: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "linked": self.linked,
            "already_linked": self.already_linked,
            "created": self.created,
            "skipped": self.skipped,
        }


class CurationOrganizationService:
    def __init__(self, db: Session, hf_client: HFOrganizationClient | None = None):
        self.db = db
        self._hf_client = hf_client

    @property
    def hf_client(self) -> HFOrganizationClient:
        if self._hf_client is None:
            # Lookups run inside the curator's apply request; fail fast and
            # skip the organization rather than wait out long rate limits.
            self._hf_client = HFOrganizationClient(attempts=2)
        return self._hf_client

    def close(self) -> None:
        if self._hf_client is not None:
            self._hf_client.close()

    def link(
        self, paper_id: int, proposals: list[CurationOrganization]
    ) -> OrganizationLinkResult:
        """Add every resolvable proposal to the paper; never remove a link."""
        result = OrganizationLinkResult()
        current = {
            link.organization_id
            for link in self.db.query(PaperOrganization).filter(
                PaperOrganization.paper_id == paper_id
            )
        }
        for proposal in proposals:
            organization = self._resolve(proposal, result)
            if organization is None:
                continue
            if organization.id in current:
                if organization.id not in result.already_linked:
                    result.already_linked.append(organization.id)
                continue
            self.db.add(
                PaperOrganization(
                    paper_id=paper_id,
                    organization_id=organization.id,
                    source=CURATION_SOURCE,
                )
            )
            current.add(organization.id)
            result.linked.append(organization.id)
        self.db.flush()
        return result

    def _resolve(
        self, proposal: CurationOrganization, result: OrganizationLinkResult
    ) -> Organization | None:
        if proposal.organization_id is not None:
            organization = self.db.get(Organization, proposal.organization_id)
            if organization is None:
                raise ValueError(f"Invalid organization ID: {proposal.organization_id}")
            return organization

        assert proposal.hf_slug is not None

        def skip(reason: str) -> None:
            result.skipped.append(
                {"name": proposal.name, "hf_slug": proposal.hf_slug, "reason": reason}
            )

        # Settle on the canonical HF handle before consulting the catalog, which
        # already holds a few look-alike rows (for example a second "Stanford
        # University" under a squatted handle).
        try:
            profile = self.hf_client.fetch_profile(proposal.hf_slug)
            if profile is not None:
                profile = self._canonical_profile(profile)
        except (HFOrganizationError, httpx.HTTPError) as exc:
            logger.warning(
                "curation_organization_lookup_failed hf_slug=%s error=%s",
                proposal.hf_slug,
                exc,
            )
            existing = self._by_hf_slug(proposal.hf_slug)
            if existing is None:
                skip("hf_unavailable")
            return existing
        if profile is None:
            existing = self._by_hf_slug(proposal.hf_slug)
            if existing is None:
                skip("hf_organization_not_found")
            return existing

        existing = self._by_hf_slug(profile.hf_slug)
        if existing is not None:
            return existing
        if not names_match(proposal.name, profile.name):
            skip(f"name_mismatch: Hugging Face calls it {profile.name!r}")
            return None
        if not profile.is_verified and profile.followers < MIN_UNVERIFIED_FOLLOWERS:
            skip("hf_organization_not_established")
            return None

        # Only a row without a handle can be this org's catalog entry: one with
        # another handle is a look-alike or a different, same-named org.
        handleless = self._handleless_by_name(profile.name)
        if handleless is not None:
            self.apply_profile(handleless, profile)
            # Sessions run without autoflush; persist the handle so a later
            # proposal in this call no longer sees the row as handleless.
            self.db.flush()
            return handleless

        if len(result.created) >= MAX_NEW_ORGANIZATIONS:
            skip("new_organization_limit")
            return None
        slug = next(
            (
                candidate
                for candidate in (slugify(profile.name), slugify(profile.hf_slug))
                if candidate and not self._slug_taken(candidate)
            ),
            None,
        )
        if slug is None:
            skip("slug_conflict")
            return None
        organization = Organization(name=profile.name[:200], slug=slug[:100])
        self.apply_profile(organization, profile)
        self.db.add(organization)
        self.db.flush()
        result.created.append(
            {
                "id": organization.id,
                "slug": organization.slug,
                "name": organization.name,
                "hf_slug": organization.hf_slug,
                "website_url": organization.website_url,
                "has_logo": organization.logo_data is not None,
            }
        )
        logger.info(
            "curation_organization_created slug=%s hf_slug=%s",
            organization.slug,
            organization.hf_slug,
        )
        return organization

    def _canonical_profile(
        self, profile: HFOrganizationProfile
    ) -> HFOrganizationProfile:
        """Prefer the verified or most-followed handle that carries the same name."""
        name = normalize_organization_name(profile.name)
        best = profile
        handles = [
            handle
            for handle in self.hf_client.search(profile.name)
            if handle.lower() != profile.hf_slug.lower()
        ][:MAX_LOOKALIKE_PROFILES]
        for handle in handles:
            candidate = self.hf_client.fetch_profile(handle)
            if candidate is None or normalize_organization_name(candidate.name) != name:
                continue
            if (candidate.is_verified, candidate.followers) > (
                best.is_verified,
                best.followers,
            ):
                best = candidate
        return best

    def apply_profile(
        self, organization: Organization, profile: HFOrganizationProfile
    ) -> None:
        organization.hf_slug = profile.hf_slug
        organization.hf_url = f"https://huggingface.co/{profile.hf_slug}"
        if profile.website_url and not organization.website_url:
            organization.website_url = profile.website_url[:500]
        if profile.logo_url and not organization.logo_url:
            organization.logo_url = profile.logo_url
            try:
                logo_data, mime_type = self.hf_client.fetch_logo(profile.logo_url)
            except (HFOrganizationError, httpx.HTTPError, ValueError) as exc:
                logger.warning(
                    "curation_organization_logo_failed hf_slug=%s error=%s",
                    profile.hf_slug,
                    exc,
                )
            else:
                organization.logo_data = logo_data
                organization.logo_mime_type = mime_type
                organization.logo_sha256 = hashlib.sha256(logo_data).hexdigest()

    def _by_hf_slug(self, hf_slug: str) -> Organization | None:
        return (
            self.db.query(Organization)
            .filter(func.lower(Organization.hf_slug) == hf_slug.lower())
            .first()
        )

    def _handleless_by_name(self, name: str) -> Organization | None:
        normalized = normalize_organization_name(name)
        match = next(
            (
                organization_id
                for organization_id, existing in self.db.query(
                    Organization.id, Organization.name
                )
                .filter(Organization.hf_slug.is_(None))
                .order_by(Organization.id)
                if normalize_organization_name(existing) == normalized
            ),
            None,
        )
        return None if match is None else self.db.get(Organization, match)

    def _slug_taken(self, slug: str) -> bool:
        return (
            self.db.query(Organization.id).filter(Organization.slug == slug).first()
            is not None
        )
