"""Focused validation for the private HF organization-page contract."""

import html
import json

import httpx
import pytest

from backend.database.organizations_setup.organizations import (
    FEATURED_ORGANIZATIONS,
    featured_for_hf_handle,
)
from backend.services.hf_organization_service import (
    HFOrganizationClient,
    HFOrganizationError,
    extract_balanced_array,
    parse_org_papers_html,
)


def _page(payload) -> str:
    encoded = json.dumps(payload)
    return (
        '<a rel="nofollow">https://example.com/lab</a>'
        f'<script>{{"orgPapers":{html.escape(encoded)}}}</script>'
    )


def test_manifest_is_strict_unique_and_case_insensitive():
    assert len(FEATURED_ORGANIZATIONS) == 24
    assert len({item.slug for item in FEATURED_ORGANIZATIONS}) == 24
    assert len({item.hf_slug.lower() for item in FEATURED_ORGANIZATIONS}) == 24
    assert featured_for_hf_handle("baidu").slug == "baidu"
    assert featured_for_hf_handle("sensenova").slug == "sensenova"
    assert featured_for_hf_handle("ultralytics").slug == "ultralytics"
    assert featured_for_hf_handle("openbmb").slug == "openbmb"
    assert featured_for_hf_handle("ByteDance-Seed").slug == "bytedance-seed"
    assert featured_for_hf_handle("  ANTHROPIC ").slug == "anthropic"
    assert featured_for_hf_handle("meta-llama").slug == "facebook"
    assert featured_for_hf_handle("AI-at-Meta").slug == "facebook"
    assert featured_for_hf_handle("facebook-research").slug == "facebook"
    assert featured_for_hf_handle("GoogleDeepMind").slug == "google"
    assert featured_for_hf_handle("MicrosoftResearch").slug == "microsoft"
    assert featured_for_hf_handle("metaresearch").slug == "facebook"
    assert featured_for_hf_handle("MetaSuperintelligenceLab").slug == "facebook"
    assert featured_for_hf_handle("facebook").name_override == "Meta"
    assert "64c115d1f661ace7c4022432" in (
        featured_for_hf_handle("facebook").logo_url_override or ""
    )
    assert featured_for_hf_handle("unlisted-lab") is None


def test_balanced_array_handles_nested_arrays_and_escaped_strings():
    raw = (
        'prefix "orgPapers":['
        '{"paper":{"id":"2501.00001v2"},"title":"A \\"quoted\\" title",'
        '"nested":[1,[2,3]]}] suffix'
    )
    parsed = json.loads(extract_balanced_array(raw))
    assert parsed[0]["nested"] == [1, [2, 3]]
    papers, _ = parse_org_papers_html(raw)
    assert papers[0].arxiv_id == "2501.00001"
    assert papers[0].title == 'A "quoted" title'


@pytest.mark.parametrize(
    "raw",
    [
        "<html>no payload</html>",
        '"orgPapers":',
        '"orgPapers":[{"paper":{"id":"2501.00001"}}',
        '"orgPapers":[not-json]',
        '"orgPapers":[{"title":"missing paper"}]',
    ],
)
def test_parser_fails_closed_for_missing_or_malformed_payload(raw):
    with pytest.raises(HFOrganizationError):
        parse_org_papers_html(raw)


def test_fetch_validates_overview_count():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/overview"):
            return httpx.Response(
                200,
                json={
                    "name": "test",
                    "fullname": "Test Lab",
                    "numPapers": 2,
                },
            )
        return httpx.Response(
            200,
            text=_page(
                [
                    {
                        "paper": {"id": "2501.00001"},
                        "title": "Only one paper",
                    }
                ]
            ),
        )

    client = HFOrganizationClient(httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(HFOrganizationError, match="differs"):
        client.fetch("test")


def test_fetch_retries_rate_limit_using_reset_header(monkeypatch):
    attempts = 0
    delays = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path.endswith("/overview"):
            attempts += 1
            if attempts == 1:
                return httpx.Response(429, headers={"ratelimit": '"pages";r=0;t=2'})
            return httpx.Response(
                200,
                json={"name": "test", "fullname": "Test Lab", "numPapers": 1},
            )
        return httpx.Response(
            200,
            text=_page([{"paper": {"id": "2501.00001"}, "title": "Paper"}]),
        )

    monkeypatch.setattr(
        "backend.services.hf_organization_service.time.sleep", delays.append
    )
    client = HFOrganizationClient(httpx.Client(transport=httpx.MockTransport(handler)))

    data = client.fetch("test")

    assert data.upstream_paper_count == 1
    assert attempts == 2
    assert delays == [3]
