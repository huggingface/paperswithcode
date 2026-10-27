"""Public API models must not fail a whole listing on one legacy-shaped row."""

from __future__ import annotations

import pytest

from backend.services.openalex_organization_linking_service import (
    OPENALEX_SOURCE,
)
from backend.models.evaluations import Dataset
from backend.models.papers import OrganizationSummary, Paper


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (None, None),
        # Legacy imports stored a JSON object for a few BARS datasets.
        ({"split": "random 8:1:1", "metrics": {"auc": "higher_is_better"}}, None),
        ("COCO test-dev", None),
        (["COCO test-dev", None, "COCO val2017"], ["COCO test-dev", "COCO val2017"]),
    ],
)
def test_dataset_variants_and_languages_tolerate_non_list_values(stored, expected):
    dataset = Dataset(
        id="1793", name="BARS Criteo_x4", variants=stored, languages=stored
    )

    assert dataset.variants == expected
    assert dataset.languages == expected


def test_paper_version_defaults_when_the_column_is_null():
    paper = Paper(id="104251", title="Untitled", authors=[], version=None)

    assert paper.version == "v1"
    assert Paper(id="1", title="T", authors=[], version="v3").version == "v3"


def test_organization_summary_accepts_openalex_affiliation_links():
    org = OrganizationSummary(id="7", name="MIT", slug="mit", source=OPENALEX_SOURCE)

    assert org.source == "openalex"
