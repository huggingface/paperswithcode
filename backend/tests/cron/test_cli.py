from argparse import Namespace
from types import SimpleNamespace

from backend import cli
from backend.services import cron_token_probe


def dashboard(status="healthy"):
    return {
        "timestamp": "2026-07-17T12:00:00Z",
        "jobs": [
            {
                "job_name": "update_github_stars",
                "schedule": "0 * * * * (hourly)",
                "status": status,
                "last_db_write": "2026-07-17T11:50:00Z",
                "last_run": "2026-07-17T11:00:00Z",
                "status_reason": "fresh database writes",
                "diagnostics": None,
            }
        ],
        "summary": {"total_jobs": 1},
    }


def test_cron_health_cli_filters_and_returns_shell_friendly_status(monkeypatch, capsys):
    monkeypatch.setattr(cli, "build_cron_dashboard", lambda: dashboard())
    args = Namespace(job="update_github_stars", json=False, strict=False)

    assert cli.show_cron_health(args) == 0
    assert "fresh database writes" in capsys.readouterr().out

    monkeypatch.setattr(cli, "build_cron_dashboard", lambda: dashboard("degraded"))
    assert cli.show_cron_health(args) == 0
    args.strict = True
    assert cli.show_cron_health(args) == 1


def test_cron_health_cli_fails_for_broken_job(monkeypatch):
    monkeypatch.setattr(cli, "build_cron_dashboard", lambda: dashboard("broken"))
    args = Namespace(job=None, json=True, strict=False)
    assert cli.show_cron_health(args) == 1


def test_token_probe_uses_exact_auth_without_exposing_token(monkeypatch):
    monkeypatch.setenv("PWC_GITHUB_TOKEN", "secret-value")
    calls = []

    def fake_get(url, headers, timeout):
        calls.append((url, headers, timeout))
        return SimpleNamespace(
            status_code=200,
            headers={"x-ratelimit-remaining": "4999"},
        )

    monkeypatch.setattr(cron_token_probe.requests, "get", fake_get)
    result = cron_token_probe.probe_cron_token("PWC_GITHUB_TOKEN")

    assert result.success
    assert result.rate_limit_remaining == "4999"
    assert calls[0][1]["Authorization"] == "token secret-value"
    assert "secret-value" not in str(result.to_dict())


def test_cron_cli_parses_health_and_token_commands():
    health = cli.build_parser().parse_args(
        ["cron", "health", "update_citations", "--strict", "--json"]
    )
    token = cli.build_parser().parse_args(
        ["cron", "token-check", "PWC_HF_TOKEN", "--json"]
    )

    assert health.job == "update_citations"
    assert health.strict
    assert token.environment_variable == "PWC_HF_TOKEN"


def test_hot_token_is_registered_for_safe_probe():
    assert "PWC_GITHUB_TOKEN_HOT" in cron_token_probe.TOKEN_PROBES
