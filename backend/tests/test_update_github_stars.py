from pathlib import Path
import sys
from datetime import datetime
from inspect import signature
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


WORKFLOWS_DIR = Path(__file__).parents[2] / ".github" / "workflows"
if str(WORKFLOWS_DIR) not in sys.path:
    sys.path.append(str(WORKFLOWS_DIR))

from scripts.hourly.update_github_stars import (  # noqa: E402
    GitHubFetchResult,
    RateLimit,
    fetch_github_stars,
    get_next_repository_group,
    mark_repository_group_checked,
    queue_credentials,
    rate_limit_reserve_reached,
    require_successful_queues,
    run_queue,
    summarize_queues,
    store_star_snapshot,
)
from scripts.hourly.update_hot_github_trending import resolve_hot_token  # noqa: E402


def _session_with_row():
    session = Mock()
    session.execute.return_value.fetchall.return_value = [
        (
            "huggingface",
            "transformers",
            [1, 2],
            2,
            None,
            162_685,
            None,
            1,
            None,
        )
    ]
    return session


def test_fresh_queue_uses_recent_eligibility():
    session = _session_with_row()

    get_next_repository_group(session, "fresh")

    query = str(session.execute.call_args.args[0])
    assert "linked.newest_paper_date < :hot_cutoff" in query
    assert "linked.newest_paper_date >= :fresh_cutoff" in query
    assert "repo_groups.oldest_update < :threshold_recent" in query
    assert "repo_groups.oldest_update ASC NULLS FIRST" in query
    assert "array_agg(r.id ORDER BY r.id)" in query
    assert "GROUP BY LOWER(r.owner), LOWER(r.name)" in query


def test_queue_helper_binds_thresholds_by_keyword():
    session = _session_with_row()
    before = datetime.now()

    get_next_repository_group(
        session,
        "fresh",
        threshold_hours_recent=5,
        threshold_days_regular=11,
    )

    params = session.execute.call_args.args[1]
    after = datetime.now()
    assert params["group_limit"] == 1
    assert timedelta_hours(before - params["threshold_recent"]) >= 4.99
    assert timedelta_hours(after - params["threshold_recent"]) <= 5.01
    assert (before - params["threshold_regular"]).days >= 10
    assert (after - params["threshold_regular"]).days <= 11
    assert (before - params["hot_cutoff"]).days >= 29
    assert (after - params["fresh_cutoff"]).days <= 180


def timedelta_hours(value):
    return value.total_seconds() / 3600


def test_hot_fresh_boundary_is_fixed_even_if_legacy_env_override_is_set(
    monkeypatch,
):
    monkeypatch.setenv("PWC_GITHUB_HOT_WINDOW_DAYS", "7")
    hot_session = _session_with_row()
    fresh_session = _session_with_row()
    before = datetime.now()

    get_next_repository_group(hot_session, "hot")
    get_next_repository_group(fresh_session, "fresh")

    hot_cutoff = hot_session.execute.call_args.args[1]["hot_cutoff"]
    fresh_cutoff = fresh_session.execute.call_args.args[1]["hot_cutoff"]
    assert 29.99 <= timedelta_hours(before - hot_cutoff) / 24 <= 30.01
    assert abs((hot_cutoff - fresh_cutoff).total_seconds()) < 1
    assert "hot_window_days" not in signature(run_queue).parameters


def test_hot_queue_owns_only_the_hot_window():
    session = _session_with_row()

    get_next_repository_group(session, "hot")

    query = str(session.execute.call_args.args[0])
    assert "linked.newest_paper_date >= :hot_cutoff" in query
    assert "repo_groups.oldest_update < :threshold_hot" in query


def test_weekly_queue_uses_regular_eligibility():
    session = _session_with_row()

    result = get_next_repository_group(session, "weekly")

    query = str(session.execute.call_args.args[0])
    assert "linked.newest_paper_date < :fresh_cutoff" in query
    assert "OR linked.newest_paper_date IS NULL" in query
    assert "repo_groups.oldest_update < :threshold_regular" in query
    assert result["owner"] == "huggingface"
    assert result["repository_ids"] == [1, 2]


def test_unknown_queue_is_rejected():
    session = Mock()

    with pytest.raises(ValueError, match="Unknown GitHub stars queue"):
        get_next_repository_group(session, "other")

    session.execute.assert_not_called()


def test_database_errors_are_not_reported_as_an_empty_queue():
    session = Mock()
    session.execute.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        get_next_repository_group(session, "fresh")


def test_rate_limit_reserve_stops_at_boundary():
    assert rate_limit_reserve_reached(500, 500)
    assert rate_limit_reserve_reached(499, 500)
    assert not rate_limit_reserve_reached(501, 500)
    assert not rate_limit_reserve_reached(None, 500)


def test_fetch_retries_retry_after_and_retains_rate_headers():
    throttled = SimpleNamespace(
        status_code=429,
        headers={
            "Retry-After": "2",
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "700",
            "X-RateLimit-Reset": "12345",
        },
    )
    success = SimpleNamespace(
        status_code=200,
        headers={
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "699",
            "X-RateLimit-Reset": "12345",
        },
        json=lambda: {"stargazers_count": 42},
    )
    http = Mock()
    http.get.side_effect = [throttled, success]
    sleeps = []

    result = fetch_github_stars(
        "owner", "repo", "token", http=http, sleep=sleeps.append
    )

    assert result.stars == 42
    assert result.retries == 1
    assert result.http_attempts == 2
    assert sleeps == [2.0]
    assert result.rate_limit.limit == 5000
    assert result.rate_limit.remaining == 699
    assert result.rate_limit.reset == 12345


def test_fetch_uses_bounded_exponential_retry_for_server_errors(monkeypatch):
    response = SimpleNamespace(status_code=503, headers={})
    http = Mock()
    http.get.return_value = response
    sleeps = []
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.random.uniform", lambda *_: 0.0
    )

    result = fetch_github_stars(
        "owner",
        "repo",
        "token",
        http=http,
        max_retries=2,
        sleep=sleeps.append,
    )

    assert result.failure == "http_503"
    assert result.retries == 2
    assert sleeps == [1, 2]


def test_hot_token_falls_back_to_fresh_token(monkeypatch):
    monkeypatch.delenv("PWC_GITHUB_TOKEN_HOT", raising=False)
    monkeypatch.setenv("PWC_GITHUB_TOKEN", "shared")
    assert resolve_hot_token() == ("shared", True)

    monkeypatch.setenv("PWC_GITHUB_TOKEN_HOT", "dedicated")
    assert resolve_hot_token() == ("dedicated", False)


def test_snapshot_write_is_idempotent_for_same_timestamp():
    session = Mock()

    assert store_star_snapshot(session, [1, 2], 10) == 2

    statement = str(session.execute.call_args.args[0])
    assert "ON CONFLICT (repository_id, snapshot_at)" in statement
    assert "DO UPDATE SET num_stars = EXCLUDED.num_stars" in statement


def test_terminally_blocked_repository_is_marked_checked_without_overwriting_stars():
    session = Mock()
    session.execute.return_value.rowcount = 2

    assert mark_repository_group_checked(session, [1, 2]) == 2

    statement = str(session.execute.call_args.args[0])
    assert "SET num_stars_updated_at = NOW()" in statement
    assert "num_stars =" not in statement
    session.commit.assert_called_once()


def test_run_queue_does_not_hold_database_session_during_github_fetch(monkeypatch):
    selection_session = Mock()
    write_session = Mock()
    repo_service = Mock()
    sessions = iter([(selection_session, Mock()), (write_session, repo_service)])
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.get_repository_service",
        lambda: next(sessions),
    )
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.get_repository_groups",
        lambda *_args, **_kwargs: [
            {
                "owner": "huggingface",
                "name": "transformers",
                "repository_ids": [1],
                "eligible_group_count": 1,
                "oldest_eligible_paper_date": None,
            }
        ],
    )

    def fetch(*_args, **_kwargs):
        selection_session.close.assert_called_once_with()
        return GitHubFetchResult(42, 200, RateLimit(5000, 4999, 12345))

    monkeypatch.setattr("scripts.hourly.update_github_stars.fetch_github_stars", fetch)
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.update_repository_group_stars",
        lambda *_args, **_kwargs: (1, 1),
    )

    result = run_queue("fresh", "token", 1, 60, delay=0)

    assert result["successes"] == 1
    write_session.close.assert_called_once_with()


def test_queue_summary_exposes_each_credential_without_token_values():
    results = [
        {
            "queue": queue,
            "eligible_groups": 2,
            "selected_groups": 2,
            "processed_groups": 2,
            "successes": successes,
            "failures": failures,
            "credential_failures": credential_failures,
            "updated_repositories": successes,
            "snapshots_stored": successes,
            "api_calls": 2,
            "rate_limit_stops": 0,
            "rate_limit_remaining": 4998,
        }
        for queue, successes, failures, credential_failures in (
            ("fresh", 0, 2, 2),
            ("weekly", 2, 0, 0),
        )
    ]

    summary = summarize_queues(results)

    assert summary["fresh_credential"] == "PWC_GITHUB_TOKEN"
    assert summary["fresh_credential_failures"] == 2
    assert summary["weekly_successes"] == 2
    assert "secret" not in str(summary)


def test_selected_queue_with_rejected_credential_fails_job():
    results = [
        {
            "queue": "fresh",
            "selected_groups": 2,
            "successes": 0,
            "failures": 2,
            "credential_failures": 2,
            "api_calls": 2,
        },
        {
            "queue": "weekly",
            "selected_groups": 2,
            "successes": 2,
            "failures": 0,
            "credential_failures": 0,
            "api_calls": 2,
        },
    ]

    with pytest.raises(RuntimeError, match="PWC_GITHUB_TOKEN was rejected"):
        require_successful_queues(results)


def test_empty_or_partially_successful_queue_does_not_fail_job():
    require_successful_queues(
        [
            {
                "queue": "fresh",
                "selected_groups": 0,
                "successes": 0,
                "failures": 0,
                "credential_failures": 0,
                "api_calls": 0,
            },
            {
                "queue": "weekly",
                "selected_groups": 2,
                "successes": 1,
                "failures": 1,
                "credential_failures": 1,
                "api_calls": 2,
            },
        ]
    )


def test_fetch_strips_clone_suffix_from_repository_name():
    http = Mock()
    http.get.return_value = SimpleNamespace(
        status_code=200, headers={}, json=lambda: {"stargazers_count": 2}
    )

    result = fetch_github_stars("wuzimeng", "comp.git", "token", http=http)

    assert result.stars == 2
    assert http.get.call_args.args[0] == "https://api.github.com/repos/wuzimeng/comp"


@pytest.mark.parametrize("status_code", [404, 451])
def test_fetch_reports_unavailable_repository_without_star_count(status_code):
    http = Mock()
    http.get.return_value = SimpleNamespace(status_code=status_code, headers={})

    result = fetch_github_stars("psychofict", "pixcon", "token", http=http)

    assert result.stars is None
    assert result.status_code == status_code
    assert result.retries == 0


def test_run_queue_keeps_stars_on_404_and_counts_404_and_451_separately(
    monkeypatch,
):
    groups = [
        {
            "owner": "owner",
            "name": f"repo{index}",
            "repository_ids": [index],
            "eligible_group_count": 3,
            "oldest_eligible_paper_date": None,
        }
        for index in (1, 2, 3)
    ]
    responses = iter(
        [
            GitHubFetchResult(None, 404, RateLimit(), failure="unavailable"),
            GitHubFetchResult(None, 451, RateLimit(), failure="unavailable"),
            GitHubFetchResult(None, 404, RateLimit(), failure="unavailable"),
        ]
    )
    checked = []
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.get_repository_service",
        lambda: (Mock(), Mock()),
    )
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.get_repository_groups",
        lambda *_args, **_kwargs: groups,
    )
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.fetch_github_stars",
        lambda *_args, **_kwargs: next(responses),
    )
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.mark_repository_group_checked",
        lambda _session, ids: checked.extend(ids) or len(ids),
    )
    star_writes = Mock()
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.update_repository_group_stars",
        star_writes,
    )

    result = run_queue("fresh", "token", 3, 60, delay=0)

    star_writes.assert_not_called()
    assert checked == [1, 2, 3]
    assert result["not_found"] == 2
    assert result["legal_blocked"] == 1
    assert result["terminal_unavailable"] == 3
    assert result["snapshots_stored"] == 0
    assert result["failures"] == 0
    summary = summarize_queues([result])
    assert summary["fresh_not_found"] == 2
    assert summary["fresh_legal_blocked"] == 1


def test_weekly_credential_prefers_neutral_name_and_keeps_legacy_fallback(
    monkeypatch,
):
    monkeypatch.delenv("PWC_GITHUB_TOKEN_WEEKLY", raising=False)
    monkeypatch.setenv("GITHUB_CLASSIC_TOKEN_AICONSULTANCYNIELSROGGE", "legacy")
    assert (
        queue_credentials()["weekly"] == "GITHUB_CLASSIC_TOKEN_AICONSULTANCYNIELSROGGE"
    )

    monkeypatch.setenv("PWC_GITHUB_TOKEN_WEEKLY", "neutral")
    assert queue_credentials()["weekly"] == "PWC_GITHUB_TOKEN_WEEKLY"

    monkeypatch.delenv("PWC_GITHUB_TOKEN_WEEKLY")
    monkeypatch.delenv("GITHUB_CLASSIC_TOKEN_AICONSULTANCYNIELSROGGE")
    assert queue_credentials()["weekly"] == "PWC_GITHUB_TOKEN_WEEKLY"


def test_fetch_reports_classic_pat_forbidden_separately_from_credential_failure():
    http = Mock()
    http.get.return_value = SimpleNamespace(
        status_code=403,
        headers={"X-RateLimit-Remaining": "4000"},
        text=(
            '{"message":"`huggingface` forbids access via a personal access '
            'token (classic). Please use a GitHub App"}'
        ),
    )

    result = fetch_github_stars("huggingface", "transformers", "token", http=http)

    assert result.stars is None
    assert result.failure == "classic_pat_forbidden"
    assert result.retries == 0


def test_weekly_queue_retries_classic_pat_forbidden_groups_with_fallback_token(
    monkeypatch,
):
    groups = [
        {
            "owner": "huggingface",
            "name": "transformers",
            "repository_ids": [7],
            "eligible_group_count": 1,
            "oldest_eligible_paper_date": None,
        }
    ]
    responses = {
        "classic": GitHubFetchResult(
            None, 403, RateLimit(remaining=4000), failure="classic_pat_forbidden"
        ),
        "fallback": GitHubFetchResult(42, 200, RateLimit(remaining=10)),
    }
    tokens = []
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.get_repository_service",
        lambda: (Mock(), Mock()),
    )
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.get_repository_groups",
        lambda *_args, **_kwargs: groups,
    )
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.fetch_github_stars",
        lambda _owner, _name, token, **_kwargs: tokens.append(token)
        or responses[token],
    )
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.update_repository_group_stars",
        lambda _service, _session, ids, stars: (len(ids), len(ids)),
    )

    result = run_queue("weekly", "classic", 1, 60, delay=0, fallback_token="fallback")

    assert tokens == ["classic", "fallback"]
    assert result["successes"] == 1
    assert result["failures"] == 0
    assert result["credential_failures"] == 0
    assert result["classic_pat_fallbacks"] == 1
    assert result["api_calls"] == 2
    assert result["rate_limit_remaining"] == 4000
    require_successful_queues([result])


def test_rate_limited_fallback_does_not_stop_the_weekly_queue(monkeypatch):
    groups = [
        {
            "owner": owner,
            "name": "repo",
            "repository_ids": [index],
            "eligible_group_count": 2,
            "oldest_eligible_paper_date": None,
        }
        for index, owner in enumerate(("huggingface", "someone"))
    ]
    responses = iter(
        [
            GitHubFetchResult(None, 403, RateLimit(), failure="classic_pat_forbidden"),
            GitHubFetchResult(None, 429, RateLimit(remaining=0), failure="rate_limit"),
            GitHubFetchResult(5, 200, RateLimit(remaining=3000)),
        ]
    )
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.get_repository_service",
        lambda: (Mock(), Mock()),
    )
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.get_repository_groups",
        lambda *_args, **_kwargs: groups,
    )
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.fetch_github_stars",
        lambda *_args, **_kwargs: next(responses),
    )
    monkeypatch.setattr(
        "scripts.hourly.update_github_stars.update_repository_group_stars",
        lambda _service, _session, ids, stars: (len(ids), len(ids)),
    )

    result = run_queue("weekly", "classic", 2, 60, delay=0, fallback_token="fresh")

    assert result["processed_groups"] == 2
    assert result["successes"] == 1
    assert result["failures"] == 1
    assert result["rate_limit_stops"] == 0
