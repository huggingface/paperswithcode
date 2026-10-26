"""Parsing rules for the OpenAlex affiliation backfill."""

from backend.database.organizations_setup.backfill_openalex_organizations import (
    work_arxiv_ids,
    work_organization_slugs,
)


def test_arxiv_ids_come_from_doi_and_merged_locations():
    work = {
        "doi": "https://doi.org/10.1016/j.padiff.2025.101074",
        "locations": [
            {"landing_page_url": "http://arxiv.org/abs/2501.00001v2"},
            {"landing_page_url": "https://doi.org/10.48550/arxiv.2501.00002"},
            {"landing_page_url": "https://arxiv.org/pdf/2501.00003v1"},
            {"landing_page_url": "http://arxiv.org/pdf/2501.00004.pdf"},
            {"landing_page_url": "https://arxiv.org/abs/2501.00005?context=cs"},
            {"landing_page_url": "https://arxiv.org/abs/2501.000067"},
            {"landing_page_url": "https://hdl.handle.net/2117/424900"},
            {"landing_page_url": None},
        ],
    }
    assert work_arxiv_ids(work) == {
        "2501.00001",
        "2501.00002",
        "2501.00003",
        "2501.00004",
        "2501.00005",
    }


def test_only_mapped_institutions_become_organizations():
    work = {
        "authorships": [
            {"institutions": [{"id": "https://openalex.org/I99065089"}]},
            {"institutions": [{"id": "https://openalex.org/I1"}]},
            {"institutions": []},
            {},
        ]
    }
    assert work_organization_slugs(work) == {"tsinghua"}
