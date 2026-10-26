"""Validation for the reviewed OpenAlex institution map."""

import re

from backend.database.organizations_setup.openalex_institutions import (
    OPENALEX_INSTITUTIONS,
    organization_slug_for,
)


def test_entries_are_well_formed():
    for item in OPENALEX_INSTITUTIONS:
        assert re.fullmatch(r"I\d+", item.openalex_id), item
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", item.slug), item
        assert len(item.slug) <= 100 and 0 < len(item.name) <= 200, item


def test_lookup_accepts_ids_and_urls():
    assert organization_slug_for("I99065089") == "tsinghua"
    assert organization_slug_for("https://openalex.org/I4210090411") == "deepmind"
    assert organization_slug_for("https://openalex.org/I1") is None


def test_parent_and_child_institutions_stay_separate():
    assert organization_slug_for("I1291425158") == "google"
    assert organization_slug_for("I4210090411") == "deepmind"
