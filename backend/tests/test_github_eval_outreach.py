import subprocess

import pytest

from backend.services.github_eval_outreach_catalog import OutreachPaper
from backend.services.github_eval_outreach_service import (
    OutreachRunner,
    SEARCH_PACE_SECONDS,
    matches_paper,
)
from backend.services.github_eval_outreach_state import OutreachState
from backend.services.github_issue_body_service import (
    GithubIssueDraft,
    ISSUE_TITLE,
    normalize_repository_url,
)
from backend.services.github_issue_publish_service import (
    GithubApiError,
    _is_excluded_repository,
)


class Github:
    def __init__(self):
        self.calls = []
        self.rows = []
        self.aliases = {"old/name": "lab/code"}
        self.post_error = None
        self.metadata = {
            "id": 42,
            "full_name": "lab/code",
            "has_issues": True,
            "archived": False,
        }
        self.login = "NielsRogge"

    def __call__(self, args):
        self.calls.append(args)
        if args == ["user"]:
            return {"login": self.login}
        if "/issues" not in args[0]:
            return self.metadata.copy()
        if "POST" in args:
            if self.post_error:
                raise self.post_error
            fields = dict(
                value.split("=", 1)
                for value in args
                if value.startswith(("body=", "title="))
            )
            issue = {
                **fields,
                "number": len(self.rows) + 1,
                "state": "open",
                "user": {"login": "NielsRogge"},
                "html_url": f"https://github.com/lab/code/issues/{len(self.rows) + 1}",
            }
            self.rows.append(issue)
            return issue.copy()
        if args[0].split("/")[-1].isdigit():
            return self.rows[int(args[0].split("/")[-1]) - 1].copy()
        rows = self.rows
        if args[0] == "search/issues":
            page = int(next(value[5:] for value in args if value.startswith("page=")))
            items = [
                row
                for row in rows
                if "paperswithcode.co/paper/" in (row.get("body") or "")
            ]
            return {
                "total_count": len(items),
                "items": items[(page - 1) * 100 : page * 100],
            }
        if "creator=NielsRogge" in args:
            rows = [
                row
                for row in rows
                if row.get("user", {}).get("login", "").lower() == "nielsrogge"
            ]
        if "state=open" in args:
            rows = [row for row in rows if row.get("state") == "open"]
        page = int(next(value[5:] for value in args if value.startswith("page=")))
        return rows[(page - 1) * 100 : page * 100]

    @property
    def posts(self):
        return [call for call in self.calls if "POST" in call]


def draft(paper_id):
    url = f"https://paperswithcode.co/paper/{paper_id}"
    return GithubIssueDraft(
        ISSUE_TITLE,
        str(paper_id),
        f"Paper {paper_id}",
        1,
        (),
        (),
        ("lab/code",),
        f"Hi,\n\n[Paper]({url}) [1 paper-native evaluation]({url}#results)\n\nNiels",
    )


@pytest.fixture
def state(tmp_path):
    state = OutreachState(tmp_path / "state.sqlite3")
    yield state
    state.close()


def runner(state, github, cohort=None, **kwargs):
    cohort = cohort or {"lab/code": {1: OutreachPaper(1, "2601.00001v2", True)}}
    return OutreachRunner(
        state,
        github,
        lambda: cohort,
        draft,
        sleep=lambda _: None,
        now=lambda: 1_000_000,
        **kwargs,
    )


def test_groups_redirects_posts_once_and_restart_is_idempotent(state):
    github = Github()
    cohort = {
        "lab/code": {1: OutreachPaper(1, "2601.00001", True)},
        "old/name": {2: OutreachPaper(2, "2601.00002", True)},
    }
    result = runner(state, github, cohort).run()
    assert result["counts"]["verified"] == 1
    assert len(github.posts) == 1
    assert "paper/1#results" in github.rows[0]["body"]
    assert "paper/2#results" in github.rows[0]["body"]
    assert state.get("repo:42")["covered"] == [1, 2]
    runner(state, github, cohort).run()
    assert len(github.posts) == 1


def test_open_author_issue_beyond_first_page_blocks(state):
    github = Github()
    github.rows = [{"state": "open", "user": {"login": "someone"}, "body": ""}] * 150
    github.rows.append(
        {"state": "open", "user": {"login": "NielsRogge"}, "body": "unrelated"}
    )
    assert runner(state, github).run()["counts"]["open_issue"] == 1
    assert not github.posts


def test_closed_arxiv_url_among_many_unrelated_issues_blocks_via_search(state):
    github = Github()
    github.rows = [{"state": "closed", "body": "unrelated"}] * 101
    github.rows.append(
        {
            "state": "closed",
            "body": "https://paperswithcode.co/paper/2601.00001v1#results",
        }
    )
    assert runner(state, github).run()["counts"]["already_contacted"] == 1
    assert not github.posts
    # Coverage detection must not walk the repository-wide issue list, which
    # rejects page-based pagination on large repositories (HTTP 422).
    assert any(call[0] == "search/issues" for call in github.calls)
    assert not any(
        call[0] == "repos/lab/code/issues" and "creator=NielsRogge" not in call
        for call in github.calls
    )


def test_site_issue_search_is_paced_under_the_search_rate_limit(state):
    github = Github()
    github.rows = [
        {
            "state": "closed",
            "body": "https://paperswithcode.co/paper/2601.00001v1#results",
        }
    ]
    sleeps = []
    cohort = {"lab/code": {1: OutreachPaper(1, "2601.00001v2", True)}}
    result = OutreachRunner(
        state,
        github,
        lambda: cohort,
        draft,
        sleep=sleeps.append,
        now=lambda: 1_000_000,
    ).run()
    assert result["counts"]["already_contacted"] == 1
    searches = sum(call[0] == "search/issues" for call in github.calls)
    assert searches == 1
    assert sleeps.count(SEARCH_PACE_SECONDS) == searches


def test_site_issue_search_paginates_past_one_hundred_matches(state):
    github = Github()
    github.rows = [
        {"state": "closed", "body": "https://paperswithcode.co/paper/9999#results"}
    ] * 100
    github.rows.append(
        {
            "state": "closed",
            "body": "https://paperswithcode.co/paper/2601.00001v1#results",
        }
    )
    assert runner(state, github).run()["counts"]["already_contacted"] == 1
    assert any(call[0] == "search/issues" and "page=2" in call for call in github.calls)


@pytest.mark.parametrize(
    "body,expected",
    [
        ("https://paperswithcode.co/paper/1#results", True),
        ("https://paperswithcode.co/paper/10", False),
        ("https://paperswithcode.co/paper/2601.00001v3)", True),
        ("https://paperswithcode.co/paper/2601.000010", False),
    ],
)
def test_paper_alias_boundaries(body, expected):
    assert matches_paper(body, OutreachPaper(1, "2601.00001v2", True)) is expected


def test_pulls_do_not_block_outreach(state):
    github = Github()
    github.rows = [
        {
            "state": "open",
            "user": {"login": "NielsRogge"},
            "pull_request": {},
            "body": "https://paperswithcode.co/paper/1",
        }
    ]
    runner(state, github).run()
    assert len(github.posts) == 1


def test_rejected_repository_has_month_cooldown(state):
    github = Github()
    github.post_error = GithubApiError("interactions restricted to collaborators", 422)
    result = runner(state, github).run()
    assert result["counts"]["rejected"] == 1
    assert not state.get("repo:42").get("pending")
    assert state.get("repo:42")["next_check"] == 1_000_000 + 30 * 86400
    runner(state, github).run()
    assert len(github.posts) == 1


def test_unknown_post_outcome_never_blindly_retries(state):
    github = Github()
    github.post_error = subprocess.TimeoutExpired("gh", 60)
    with pytest.raises(subprocess.TimeoutExpired):
        runner(state, github).run()
    assert state.get("repo:42")["pending"]
    github.post_error = None
    assert runner(state, github).run()["counts"]["needs_review"] == 1
    assert len(github.posts) == 1


def test_post_that_succeeded_before_timeout_is_reconciled(state):
    github = Github()
    real_api = github.__call__

    def timeout_after_post(args):
        result = real_api(args)
        if "POST" in args:
            raise subprocess.TimeoutExpired("gh", 60)
        return result

    with pytest.raises(subprocess.TimeoutExpired):
        runner(state, timeout_after_post).run()
    assert runner(state, github).run()["counts"]["verified"] == 1
    assert len(github.posts) == 1


def test_readback_mismatch_is_held_for_review(state):
    github = Github()
    real_api = github.__call__

    def edited(args):
        result = real_api(args)
        if args[0].endswith("/issues/1"):
            return {**result, "body": "Edited by maintainer"}
        return result

    assert runner(state, edited).run()["counts"]["needs_review"] == 1
    runner(state, edited).run()
    assert len(github.posts) == 1


def test_unready_paper_delays_entire_repository(state):
    github = Github()
    cohort = {
        "lab/code": {1: OutreachPaper(1, "1", True), 2: OutreachPaper(2, "2", False)}
    }
    assert runner(state, github, cohort).run()["counts"]["curating"] == 1
    assert not github.posts


def test_refresh_drops_removed_official_link(state):
    github = Github()
    cohort = {"lab/code": {1: OutreachPaper(1, "1", True)}}
    job = runner(state, github, cohort)
    values = iter([cohort, {}])
    job.catalog = lambda: next(values)
    assert job.run()["counts"]["catalog_changed"] == 1
    assert not github.posts


def test_wrong_identity_fails_before_any_repository_request(state):
    github = Github()
    github.login = "other"
    with pytest.raises(ValueError, match="NielsRogge"):
        runner(state, github).run()
    assert github.calls == [["user"]]


@pytest.mark.parametrize(
    "repository",
    [
        "HuggingFace/transformers",
        "TensorFlow/models",
        "PyTorch/vision",
        "openai/foo",
        "anthropic/sdk",
        "anthropics/claude-code",
        "google-research/google-research",
        "pwc-1/Paper-9",
        "any/vllm",
        "any/sglang",
        "any/llama.cpp",
        "any/tensorflow",
        "any/pytorch",
    ],
)
def test_exclusions(repository):
    assert _is_excluded_repository(repository)


def test_canonical_redirect_to_excluded_owner_cannot_post(state):
    github = Github()
    github.metadata["full_name"] = "openai/model"
    runner(state, github).run()
    assert not github.posts


def test_no_blanket_stars_or_age_exclusion(state):
    github = Github()
    github.metadata.update(stargazers_count=100000, created_at="2010-01-01T00:00:00Z")
    runner(state, github).run()
    assert len(github.posts) == 1


def test_preview_writes_neither_github_nor_durable_state(tmp_path):
    path = tmp_path / "state.sqlite3"
    state = OutreachState(path, dry_run=True)
    github = Github()
    try:
        assert runner(state, github, dry_run=True).run()["counts"]["would_create"] == 1
        assert not github.posts
        assert not path.exists()
    finally:
        state.close()


def test_alias_discovery_is_bounded_and_finishes_before_posting(state):
    github = Github()
    cohort = {f"lab/repo{n}": {n: OutreachPaper(n, str(n), True)} for n in range(11)}
    result = runner(state, github, cohort, limit=1).run()
    assert result["counts"]["aliases_remaining"] == 1
    assert not github.posts
    runner(state, github, cohort, limit=1).run()
    assert len(github.posts) == 1
    assert "paper/10#results" in github.rows[0]["body"]


def test_normalization_rejects_non_github_and_strips_git():
    assert (
        normalize_repository_url("https://github.com/Owner/Repo.git/tree/main")
        == "Owner/Repo"
    )
    with pytest.raises(ValueError):
        normalize_repository_url("https://example.com/owner/repo")


def test_rate_limit_cooldown_skips_even_identity_request(state):
    state.put("rate_limit", {"not_before": 1_000_001})
    github = Github()
    assert runner(state, github).run()["counts"]["rate_limited"] == 1
    assert github.calls == []


def test_not_ready_repository_does_not_starve_other_candidates(state):
    github = Github()
    cohort = {"lab/code": {1: OutreachPaper(1, "1", False)}}
    runner(state, github, cohort).run()
    assert state.get("repo:42")["checked_at"] == 1_000_000
    assert state.get("repo:42")["next_check"] == 1_003_600


def test_post_cap_applies_to_distinct_canonical_repositories(state):
    github = Github()
    cohort = {f"lab/repo{n}": {n: OutreachPaper(n, str(n), True)} for n in (1, 2)}

    def api(args):
        if args[0].startswith("repos/") and "/issues" not in args[0]:
            name = args[0].removeprefix("repos/")
            return {**github.metadata, "id": int(name[-1]), "full_name": name}
        return github(args)

    runner(state, api, cohort, max_create=1).run()
    assert len(github.posts) == 1


def test_http_error_retains_rejection_details_and_retry_headers(monkeypatch):
    from backend.services.github_issue_publish_service import gh_json

    response = subprocess.CompletedProcess(
        [],
        1,
        'HTTP/2.0 429 Too Many Requests\nRetry-After: 7200\n\n{"message":"slow down"}',
        "gh: slow down (HTTP 429)",
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: response)
    with pytest.raises(GithubApiError) as caught:
        gh_json(["user"], {})
    assert caught.value.status == 429
    assert "slow down" in str(caught.value)
    import time

    assert caught.value.retry_at > time.time() + 7100


def test_cron_outreach_contract_is_consistent():
    from backend.services.cron_registry import get_cron_job
    from deploy.cron_launcher import COMMANDS
    from deploy.cron_schedules import TIMERS

    job = get_cron_job("create_eval_verification_issues")
    assert job.scheduler == "systemd"
    assert job.schedule_policies[0].minute_of_day == 52
    spec = next(timer for timer in TIMERS if timer.job == job.id)
    assert spec.on_calendar == ("*-*-* *:52:00",)
    assert "--execute" in COMMANDS[job.id].command
    assert COMMANDS[job.id].health_job == job.id
    assert COMMANDS[job.id].timeout == "30m"


@pytest.mark.parametrize(
    "headers,body,limited",
    [
        (
            "X-Ratelimit-Remaining: 4999\nX-Ratelimit-Reset: 9999999999",
            "Forbidden",
            False,
        ),
        (
            "X-Ratelimit-Remaining: 0\nX-Ratelimit-Reset: 9999999999",
            "API rate limit exceeded",
            True,
        ),
        ("Retry-After: 7200", "slow down", True),
        (
            "X-Ratelimit-Remaining: 4999",
            "You have exceeded a secondary rate limit",
            True,
        ),
    ],
)
def test_permission_403_is_distinct_from_rate_limiting(
    monkeypatch, headers, body, limited
):
    from backend.services.github_issue_publish_service import gh_json

    response = subprocess.CompletedProcess(
        [],
        1,
        f"HTTP/2.0 403 Forbidden\n{headers}\n\n{body}",
        "gh: Forbidden (HTTP 403)",
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: response)
    with pytest.raises(GithubApiError) as caught:
        gh_json(["repos/lab/code"], {})
    assert caught.value.is_rate_limited is limited
    assert caught.value.repository_unavailable is not limited
    if not limited:
        assert caught.value.retry_at == 0


def test_forbidden_alias_is_cached_and_does_not_stall_other_repositories(state):
    github = Github()
    cohort = {
        "a/forbidden": {2: OutreachPaper(2, "2", True)},
        "lab/code": {1: OutreachPaper(1, "1", True)},
    }
    forbidden_calls = []

    def api(args):
        if args == ["repos/a/forbidden"]:
            forbidden_calls.append(args)
            raise GithubApiError("Resource not accessible", 403)
        return github(args)

    result = runner(state, api, cohort).run()
    assert result["counts"]["unavailable"] == 1
    assert result["counts"]["verified"] == 1
    runner(state, api, cohort).run()
    assert len(forbidden_calls) == 1
    assert not state.get("rate_limit")


def test_rate_limited_alias_is_not_cached_as_unavailable(state):
    github = Github()

    def api(args):
        if args == ["repos/lab/code"]:
            raise GithubApiError("API rate limit exceeded", 403, is_rate_limited=True)
        return github(args)

    with pytest.raises(GithubApiError):
        runner(state, api).run()
    assert not state.get("alias:lab/code")
    assert not github.posts


def test_forbidden_post_is_a_definitive_rejection_with_cooldown(state):
    github = Github()
    github.post_error = GithubApiError("Resource not accessible", 403)
    assert runner(state, github).run()["counts"]["rejected"] == 1
    assert not state.get("repo:42").get("pending")
    runner(state, github).run()
    assert len(github.posts) == 1
