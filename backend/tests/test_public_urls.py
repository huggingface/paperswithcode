import pytest
from pydantic import ValidationError

from backend.models.papers import ProjectPageCreateRequest, ProjectPageUpdateRequest
from backend.services.pending_edit_errors import PendingEditError
from backend.services.pending_edit_payloads import validate_payload
from backend.utils.public_urls import PublicUrlValidationError, normalize_public_url


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "data:text/html,bad",
        "file:///etc/passwd",
        "//example.com/path",
        "https://user:pass@example.com/path",
        "https://example.com/ bad",
        "https://example.com/\nnext",
        "not a url",
    ],
)
def test_public_url_normalizer_rejects_unsafe_values(value):
    with pytest.raises(PublicUrlValidationError):
        normalize_public_url(value)


def test_public_url_normalizer_normalizes_scheme_host_and_outer_space():
    assert normalize_public_url("  HTTPS://Example.COM/path?q=1  ") == (
        "https://example.com/path?q=1"
    )


def test_project_page_api_models_validate_urls():
    assert ProjectPageCreateRequest(url="https://example.com").url == (
        "https://example.com"
    )
    assert ProjectPageUpdateRequest(url=None).url is None
    with pytest.raises(ValidationError):
        ProjectPageCreateRequest(url="javascript:alert(1)")


@pytest.mark.parametrize("edit_type,key", [("source_url", "source_url")])
def test_pending_payload_rejects_unsafe_links(edit_type, key):
    with pytest.raises(PendingEditError):
        validate_payload(edit_type, {key: "javascript:bad"})


def test_pending_project_page_payload_normalizes_urls():
    payload = validate_payload(
        "project_pages",
        {
            "project_pages": [
                {"url": "HTTPS://Example.COM/project", "is_official": True}
            ]
        },
    )
    assert payload["project_pages"][0]["url"] == "https://example.com/project"
