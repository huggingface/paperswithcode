import pytest

from backend.config import get_settings
from backend.services.github_issue_body_service import GithubIssueDraft
from backend.services.github_issue_publish_service import (
    publish_github_issue,
    select_official_repository,
)


@pytest.fixture(autouse=True)
def outreach_identity(monkeypatch):
    monkeypatch.setenv("PWC_GITHUB_OUTREACH_LOGIN", "Example-Bot")
    monkeypatch.setenv("PWC_GITHUB_OUTREACH_SIGNER", "Alex")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def draft() -> GithubIssueDraft:
    return GithubIssueDraft(
        issue_title="Verify evals on Papers with Code",
        paper_id="2601.21998",
        paper_title="Paper",
        native_evaluation_count=1,
        tasks=(),
        ranking_placements=(),
        official_repositories=("owner/repository",),
        body="Body with https://paperswithcode.co/paper/2601.21998",
    )


def test_select_official_repository_uses_single_candidate():
    assert select_official_repository(("owner/repository",), None) == "owner/repository"


def test_select_official_repository_requires_choice_for_ambiguous_paper():
    with pytest.raises(ValueError, match="multiple official repositories"):
        select_official_repository(("owner/one", "owner/two"), None)


def test_select_official_repository_accepts_case_insensitive_official_override():
    assert (
        select_official_repository(
            ("Owner/Repository", "owner/second"),
            "owner/repository",
        )
        == "Owner/Repository"
    )


def test_select_official_repository_rejects_third_party_override():
    with pytest.raises(ValueError, match="not marked official"):
        select_official_repository(("owner/repository",), "third/party")


@pytest.mark.parametrize(
    "repository",
    (
        "huggingface/transformers",
        "vllm-project/vllm",
        "sgl-project/sglang",
        "ggml-org/llama.cpp",
    ),
)
def test_select_official_repository_rejects_excluded_repository(repository):
    with pytest.raises(ValueError, match="excluded from outreach"):
        select_official_repository((repository,), None)


def test_publish_reuses_recent_matching_issue_without_post(monkeypatch):
    monkeypatch.setenv("TEST_GITHUB_TOKEN", "test-token")
    calls = []

    def api(arguments, _env):
        calls.append(arguments)
        endpoint = arguments[0]
        if endpoint == "repos/owner/repository":
            return {
                "archived": False,
                "has_issues": True,
                "full_name": "owner/repository",
            }
        if endpoint == "repos/owner/repository/issues" and "POST" not in arguments:
            return [
                {
                    "number": 7,
                    "html_url": "https://github.com/owner/repository/issues/7",
                    "body": "Body with https://paperswithcode.co/paper/2601.21998",
                }
            ]
        if endpoint == "repos/owner/repository/issues/7":
            return {
                "number": 7,
                "html_url": "https://github.com/owner/repository/issues/7",
                "state": "open",
                "title": "Verify evals on Papers with Code",
                "body": "Body with https://paperswithcode.co/paper/2601.21998",
            }
        raise AssertionError(arguments)

    result = publish_github_issue(
        draft(),
        token_environment_variable="TEST_GITHUB_TOKEN",
        api=api,
    )

    assert result.status == "existing"
    assert result.issue_number == 7
    assert not any("POST" in call for call in calls)


def test_publish_creates_and_reads_back_new_issue(monkeypatch):
    monkeypatch.setenv("TEST_GITHUB_TOKEN", "test-token")
    calls = []

    def api(arguments, _env):
        calls.append(arguments)
        endpoint = arguments[0]
        if endpoint == "repos/owner/repository":
            return {
                "archived": False,
                "has_issues": True,
                "full_name": "owner/repository",
            }
        if endpoint == "repos/owner/repository/issues" and "POST" not in arguments:
            return []
        if endpoint == "search/issues":
            return {"items": []}
        if endpoint == "repos/owner/repository/issues" and "POST" in arguments:
            return {"number": 8}
        if endpoint == "repos/owner/repository/issues/8":
            return {
                "number": 8,
                "html_url": "https://github.com/owner/repository/issues/8",
                "state": "open",
                "title": "Verify evals on Papers with Code",
                "body": "Body with https://paperswithcode.co/paper/2601.21998",
            }
        raise AssertionError(arguments)

    result = publish_github_issue(
        draft(),
        token_environment_variable="TEST_GITHUB_TOKEN",
        api=api,
    )

    assert result.status == "created"
    assert result.issue_number == 8
    assert result.title_verified
    assert result.body_verified
    assert sum("POST" in call for call in calls) == 1


def test_publish_skips_repository_with_open_outreach_issue(monkeypatch):
    monkeypatch.setenv("TEST_GITHUB_TOKEN", "test-token")

    def api(arguments, _env):
        endpoint = arguments[0]
        if endpoint == "repos/owner/repository":
            return {
                "archived": False,
                "has_issues": True,
                "full_name": "owner/repository",
            }
        if endpoint == "repos/owner/repository/issues":
            return [
                {
                    "number": 12,
                    "user": {"login": "Example-Bot"},
                    "state": "open",
                }
            ]
        raise AssertionError(arguments)

    with pytest.raises(ValueError, match="open issue authored by Example-Bot"):
        publish_github_issue(
            draft(),
            token_environment_variable="TEST_GITHUB_TOKEN",
            api=api,
        )


def test_publish_requires_configured_outreach_login(monkeypatch):
    monkeypatch.setenv("TEST_GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("PWC_GITHUB_OUTREACH_LOGIN", "")
    get_settings.cache_clear()

    def api(arguments, _env):
        if arguments[0] == "repos/owner/repository":
            return {
                "archived": False,
                "has_issues": True,
                "full_name": "owner/repository",
            }
        raise AssertionError(arguments)

    with pytest.raises(RuntimeError, match="PWC_GITHUB_OUTREACH_LOGIN"):
        publish_github_issue(
            draft(),
            token_environment_variable="TEST_GITHUB_TOKEN",
            requested_repository="owner/repository",
            api=api,
        )
