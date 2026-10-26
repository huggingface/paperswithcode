#!/usr/bin/env python3
"""Create the organizations the OpenAlex institution map names but the catalog lacks.

Each missing organization takes its Hugging Face handle and logo when a
verified or established profile carries exactly the institution's name;
otherwise it is created without a handle. The website is the institution's
OpenAlex homepage, since HF profiles often link a single lab. New rows
are not featured; the daily auto-feature rule features them once they have
enough papers.

The command is a dry run unless ``--apply`` is supplied:
  uv run --env-file backend/keys.env python \
    backend/database/organizations_setup/create_openalex_organizations.py
"""

from __future__ import annotations

import argparse
import hashlib

import httpx
from sqlalchemy import func

from backend.database.connection import db_manager
from backend.database.organizations_setup.openalex_institutions import (
    OPENALEX_INSTITUTIONS,
    OpenAlexInstitution,
)
from backend.models.database import Organization
from backend.services.curation_organization_service import (
    MIN_UNVERIFIED_FOLLOWERS,
    normalize_organization_name,
)
from backend.services.hf_organization_service import (
    HFOrganizationClient,
    HFOrganizationError,
    HFOrganizationProfile,
)

OPENALEX_API = "https://api.openalex.org/institutions"
MAX_PROFILES_PER_SEARCH = 5
# Reviewed: personal accounts that carry an institution's exact name.
REJECTED_HF_HANDLES = {"actsproject", "bupt2023213296", "jordanlee7677888"}


def missing_institutions(slugs: set[str]) -> list[OpenAlexInstitution]:
    """First map entry for every slug the catalog does not have yet."""
    missing: dict[str, OpenAlexInstitution] = {}
    for item in OPENALEX_INSTITUTIONS:
        if item.slug not in slugs:
            missing.setdefault(item.slug, item)
    return list(missing.values())


def openalex_homepages(institutions: list[OpenAlexInstitution]) -> dict[str, str]:
    homepages: dict[str, str] = {}
    for start in range(0, len(institutions), 50):
        batch = institutions[start : start + 50]
        response = httpx.get(
            OPENALEX_API,
            params={
                "filter": "openalex_id:" + "|".join(i.openalex_id for i in batch),
                "select": "id,homepage_url",
                "per_page": 50,
            },
            timeout=60,
        )
        response.raise_for_status()
        for row in response.json()["results"]:
            if row.get("homepage_url"):
                homepages[row["id"].rsplit("/", 1)[-1]] = row["homepage_url"]
    return homepages


def established_profile(
    client: HFOrganizationClient, name: str
) -> HFOrganizationProfile | None:
    """The verified or most-followed established HF profile named exactly ``name``."""
    best = None
    for handle in client.search(name)[:MAX_PROFILES_PER_SEARCH]:
        if handle.lower() in REJECTED_HF_HANDLES:
            continue
        profile = client.fetch_profile(handle)
        if profile is None or normalize_organization_name(
            profile.name
        ) != normalize_organization_name(name):
            continue
        if not profile.is_verified and profile.followers < MIN_UNVERIFIED_FOLLOWERS:
            continue
        if best is None or (profile.is_verified, profile.followers) > (
            best.is_verified,
            best.followers,
        ):
            best = profile
    return best


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    client = HFOrganizationClient()
    with db_manager.session_local() as db:
        slugs = {slug for (slug,) in db.query(Organization.slug)}
        institutions = missing_institutions(slugs)
        homepages = openalex_homepages(institutions)
        for item in institutions:
            profile = established_profile(client, item.name)
            if profile is not None:
                owner = (
                    db.query(Organization.slug)
                    .filter(func.lower(Organization.hf_slug) == profile.hf_slug.lower())
                    .scalar()
                )
                if owner is not None:
                    print(
                        f"CONFLICT {item.slug}: HF {profile.hf_slug} already "
                        f"belongs to {owner}"
                    )
                    continue
            organization = Organization(
                name=item.name,
                slug=item.slug,
                website_url=homepages.get(item.openalex_id),
                is_featured=False,
            )
            if profile is not None:
                organization.hf_slug = profile.hf_slug
                organization.hf_url = f"https://huggingface.co/{profile.hf_slug}"
                organization.website_url = (
                    organization.website_url or profile.website_url
                )
                organization.logo_url = profile.logo_url
                print(
                    f"HF       {item.slug}: {profile.hf_slug} ({profile.name!r}, "
                    f"{'verified' if profile.is_verified else 'unverified'}, "
                    f"{profile.followers} followers) {organization.website_url}"
                )
            else:
                print(f"NO HF    {item.slug}: {item.name!r} {organization.website_url}")
            if not args.apply:
                continue
            if organization.logo_url:
                try:
                    logo_data, mime_type = client.fetch_logo(organization.logo_url)
                except HFOrganizationError as exc:
                    # Placeholder avatars (gravatar) are not organization logos.
                    print(f"         {item.slug}: no logo ({exc})")
                    organization.logo_url = None
                else:
                    organization.logo_data = logo_data
                    organization.logo_mime_type = mime_type
                    organization.logo_sha256 = hashlib.sha256(logo_data).hexdigest()
            db.add(organization)
        if args.apply:
            db.commit()
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
