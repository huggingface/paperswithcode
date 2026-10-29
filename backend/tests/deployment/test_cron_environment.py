"""CRON wrappers, restricted job environments, timers, and release-bound jobs."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import deploy.configure_host_env as configure_host_env
import deploy.configure_db_roles as configure_db_roles
import deploy.cron_launcher as cron_launcher
from deploy.install_deploy_tools import (
    cron_wrapper,
    reconcile_submission_review_timer,
    submission_review_timer_action,
)


def test_cron_wrapper_grants_journal_access_only_to_chat_monitor():
    wrapper = cron_wrapper()

    assert 'if [ "$1" = "monitor_chat_operational_alerts" ]' in wrapper
    assert wrapper.count("SupplementaryGroups=systemd-journal") == 1
    assert wrapper.count("cron_launcher.py") == 3


def test_cron_wrapper_isolates_source_repairable_trending_jobs():
    wrapper = cron_wrapper()
    restricted_branch = wrapper.split('case "$1" in', 1)[1].split("esac", 1)[0]

    assert "calculate_trending_scores|calculate_paper_trending_scores)" in wrapper
    assert "--uid=pwc-cron-trending --gid=pwc-cron-trending" in wrapper
    assert "EnvironmentFile=/etc/paperswithcode/trending-cron.env" in restricted_branch
    assert "production.env" not in restricted_branch
    assert "production-cron.env" not in restricted_branch
    assert "SupplementaryGroups" not in restricted_branch


def test_restricted_trending_environment_drops_broad_credentials():
    source = {
        "PATH": "/usr/bin",
        "LANG": "C.UTF-8",
        "PWC_DB_HOST": "db",
        "PWC_DB_PORT": "5432",
        "PWC_DB_NAME": "paperswithcode",
        "PWC_DB_USER": "paperswithcode_user",
        "PWC_DB_PASSWORD": "broad-secret",
        "PWC_TRENDING_DB_PASSWORD": "restricted-secret",
        "PWC_TRENDING_PIN_ARXIV_IDS": "2601.00001:72",
        "PWC_GITHUB_TOKEN": "must-not-leak",
        "OPENAI_API_KEY": "must-not-leak",
        "PWC_CHAT_LANGFUSE_SECRET_KEY": "must-not-leak",
    }

    environment = cron_launcher.restricted_trending_environment(
        source,
        release_id="a" * 12 + "-production",
    )

    assert environment["PWC_DB_USER"] == "pwc_cron_trending"
    assert environment["PWC_DB_PASSWORD"] == "restricted-secret"
    assert environment["PWC_TRENDING_PIN_ARXIV_IDS"] == "2601.00001:72"
    assert "PWC_TRENDING_DB_PASSWORD" not in environment
    assert "PWC_GITHUB_TOKEN" not in environment
    assert "OPENAI_API_KEY" not in environment
    assert "PWC_CHAT_LANGFUSE_SECRET_KEY" not in environment
    assert set(environment) <= cron_launcher.RESTRICTED_TRENDING_ENV_KEYS
    assert environment["PWC_CRON_LOG_DIR"] == str(
        cron_launcher.RESTRICTED_TRENDING_LOG_DIR
    )
    assert environment["PWC_CRON_LOCK_DIR"] == str(
        cron_launcher.RESTRICTED_TRENDING_LOCK_DIR
    )


def test_restricted_trending_environment_fails_closed_without_role_password():
    with pytest.raises(RuntimeError, match="PWC_TRENDING_DB_PASSWORD"):
        cron_launcher.restricted_trending_environment(
            {
                "PWC_DB_HOST": "db",
                "PWC_DB_PORT": "5432",
                "PWC_DB_NAME": "paperswithcode",
            },
            release_id="a" * 12 + "-production",
        )


def test_trending_database_role_has_only_scoring_capabilities():
    sql = configure_db_roles.trending_role_sql(
        database="paperswithcode",
        password="restricted-secret",
    )

    assert "NOINHERIT" in sql
    assert "pg_auth_members" in sql
    assert "EXECUTE 'REVOKE ' || granted_role" in sql
    assert "trending role retains a role membership" in sql
    assert "REVOKE ALL ON ALL TABLES IN SCHEMA public" in sql
    assert "REVOKE CREATE ON SCHEMA public" in sql
    assert (
        "GRANT SELECT ON papers, paper_repositories, repositories, "
        "repository_star_history, paper_hf_artifacts, hf_artifacts"
    ) in sql
    assert (
        "GRANT UPDATE (trending_score, trending_score_updated_at, updated_at) "
        "ON repositories"
    ) in sql
    assert (
        "GRANT UPDATE (trending_score, github_trending_component, "
        "hf_trending_component, trending_score_updated_at, updated_at) ON papers"
    ) in sql
    for taxonomy_table in ("tasks", "methods", "datasets", "metrics", "conferences"):
        assert f"'{taxonomy_table}'" in sql
    assert "has_table_privilege(" in sql
    assert "taxonomy_table" in sql


def test_trending_environment_rotation_preserves_existing_role_password():
    current = {
        "PWC_TRENDING_DB_PASSWORD": "PWC_TRENDING_DB_PASSWORD=stable-secret",
        "PWC_TRENDING_PIN_ARXIV_IDS": "PWC_TRENDING_PIN_ARXIV_IDS=2601.1:72",
    }
    password = configure_host_env.existing_or_random(
        current, "PWC_TRENDING_DB_PASSWORD"
    )

    values = configure_host_env.trending_cron_values(
        {
            "PWC_DB_HOST": "PWC_DB_HOST=localhost",
            "PWC_DB_NAME": "PWC_DB_NAME=paperswithcode_hf",
            "PWC_DB_PORT": "PWC_DB_PORT=5432",
        },
        current,
        password=password,
    )

    assert values["PWC_TRENDING_DB_PASSWORD"] == "stable-secret"
    assert values["PWC_TRENDING_PIN_ARXIV_IDS"] == "2601.1:72"


@pytest.mark.parametrize(
    ("review_enabled", "jobs_enabled", "primary_alert_url", "fallback_alert_url"),
    [
        (False, False, "https://primary", "https://fallback"),
        (True, False, "https://primary", "https://fallback"),
        (False, True, "https://primary", "https://fallback"),
        (True, True, "", "https://fallback"),
        (True, True, "https://primary", ""),
        (True, True, "https://same", "https://same"),
    ],
)
def test_submission_review_timer_stays_disabled_without_complete_configuration(
    review_enabled: bool,
    jobs_enabled: bool,
    primary_alert_url: str,
    fallback_alert_url: str,
):
    assert submission_review_timer_action(
        review_enabled=review_enabled,
        jobs_enabled=jobs_enabled,
        primary_alert_url=primary_alert_url,
        fallback_alert_url=fallback_alert_url,
    ) == ["systemctl", "disable", "--now", "submission-review.timer"]


def test_submission_review_timer_can_run_only_with_alert_delivery():
    assert submission_review_timer_action(
        review_enabled=True,
        jobs_enabled=True,
        primary_alert_url="https://primary",
        fallback_alert_url="https://fallback",
    ) == ["systemctl", "enable", "--now", "submission-review.timer"]


def test_submission_timer_reconciliation_merges_cron_env_and_writes_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environment = tmp_path / "production.env"
    cron_environment = tmp_path / "production-cron.env"
    state = tmp_path / "submission-review-schedule.json"
    environment.write_text(
        "PWC_AUTONOMOUS_SUBMISSION_ENABLED=true\n"
        "PWC_AUTONOMOUS_SUBMISSION_JOBS_ENABLED=false\n"
        "PWC_AUTONOMOUS_ALERT_SLACK_WEBHOOK_URL=https://primary\n"
    )
    cron_environment.write_text(
        "PWC_AUTONOMOUS_SUBMISSION_JOBS_ENABLED=true\n"
        "PWC_AUTONOMOUS_ALERT_FALLBACK_WEBHOOK_URL=https://fallback\n"
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: None)

    reconcile_submission_review_timer(environment, cron_environment, state)

    assert json.loads(state.read_text()) == {
        "enabled": True,
        "reason": "complete configuration",
    }
    assert state.stat().st_mode & 0o777 == 0o644


def test_chat_alert_timer_uses_only_the_allowlisted_cron_interface():
    systemd = Path(__file__).resolve().parents[3] / "deploy" / "systemd"
    service = (systemd / "pwc-chat-alert-monitor.service").read_text()
    timer = (systemd / "pwc-chat-alert-monitor.timer").read_text()

    assert (
        "ExecStart=/usr/local/sbin/pwc-cron monitor_chat_operational_alerts" in service
    )
    assert "backend.scripts" not in service
    assert "OnUnitActiveSec=1m" in timer
    assert "WantedBy=timers.target" in timer


def test_chat_synthetic_timer_uses_the_bounded_allowlisted_job():
    systemd = Path(__file__).resolve().parents[3] / "deploy" / "systemd" / "cron"
    service = (systemd / "pwc-cron-run-chat-synthetic-probe.service").read_text()
    timer = (systemd / "pwc-cron-run-chat-synthetic-probe.timer").read_text()

    assert "pwc-cron-throttled run_chat_synthetic_probe" in service
    assert "OnCalendar=*-*-* *:*:00" in timer
    assert "Persistent=true" in timer


def test_cron_jobs_declare_bounded_execution_contracts():
    assert cron_launcher.COMMANDS
    assert cron_launcher.COMMANDS["monitor_chat_operational_alerts"].timeout == "1m"
    assert cron_launcher.COMMANDS["run_chat_synthetic_probe"].timeout == "6m"
    read_only_jobs = {
        "alert_submission_review_failure",
        "export_enrichment_dashboard",
        "monitor_chat_operational_alerts",
    }
    for name, spec in cron_launcher.COMMANDS.items():
        assert spec.command
        assert spec.timeout in {"1m", "6m", "30m", "45m", "50m", "2h", "6h"}
        assert spec.mutates_shared_data is (name not in read_only_jobs)
        assert spec.idempotency
        assert spec.health_job


def test_cron_python_uses_active_release_immutable_runtime(tmp_path: Path, monkeypatch):
    current = tmp_path / "current"
    current.mkdir()
    (current / "uv.lock").write_text("locked dependencies\n")
    runtimes = tmp_path / "runtimes"
    validated = []
    monkeypatch.setattr(
        cron_launcher,
        "runtime_manifest",
        lambda runtime: validated.append(runtime),
    )

    python = cron_launcher.cron_python(current, runtimes)

    assert python == runtimes / cron_launcher.runtime_id(current) / "bin" / "python"
    assert validated == [python.parent.parent]


@pytest.mark.parametrize(
    ("features", "expected"),
    [
        (
            {"codex_add_evals": True, "codex_enrich_paper": True},
            ("true", "true", "true"),
        ),
        ({"chat": False}, ("false", "false", "false")),
    ],
)
def test_cron_codex_flags_follow_active_release(features, expected):
    env = {
        "PWC_CODEX_ADD_EVALS_ENABLED": "stale",
        "PWC_CODEX_ENRICH_PAPER_ENABLED": "stale",
        "PWC_CODEX_JOBS_ENABLED": "stale",
    }

    cron_launcher.apply_release_features(env, {"backend_features": features})

    assert (
        env["PWC_CODEX_ADD_EVALS_ENABLED"],
        env["PWC_CODEX_ENRICH_PAPER_ENABLED"],
        env["PWC_CODEX_JOBS_ENABLED"],
    ) == expected


def test_hot_workflow_runs_on_the_activated_production_schedule():
    root = Path(__file__).resolve().parents[3]
    workflow = (
        root / ".github" / "workflows" / "cron-update-hot-github-trending.yml"
    ).read_text()
    # Scheduled execution moved to the host timer; the workflow remains
    # dispatch-only for manual recovery.
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    timer = (
        root
        / "deploy"
        / "systemd"
        / "cron"
        / "pwc-cron-update-hot-github-trending.timer"
    ).read_text()
    assert "OnCalendar=*-*-* *:00/15:00" in timer
    assert "Persistent=true" in timer

    cron_env_example = (
        Path(__file__).resolve().parents[3]
        / "deploy"
        / "env"
        / "production-cron.env.example"
    ).read_text()
    assert "PWC_GITHUB_HOT_WINDOW_DAYS" not in cron_env_example


def test_cron_status_reports_exact_production_release(
    tmp_path: Path, monkeypatch, capsys
):
    current = tmp_path / "current"
    current.mkdir()
    (current / "release.json").write_text(
        json.dumps(
            {
                "release_id": "a" * 12 + "-production",
                "git_sha": "a" * 40,
            }
        )
    )
    monkeypatch.setattr(cron_launcher, "CURRENT", current)
    monkeypatch.setattr(cron_launcher.sys, "argv", ["pwc-cron", "status"])

    assert cron_launcher.main() == 0
    status = json.loads(capsys.readouterr().out)
    assert status["environment"] == "production"
    assert status["release_id"] == "a" * 12 + "-production"
    assert status["git_sha"] == "a" * 40
    assert status["jobs"]["refresh_paper_embeddings"]["timeout"] == "6h"
    assert status["jobs"]["update_hot_github_trending"]["timeout"] == "30m"
    assert status["jobs"]["sync_3d_arena"]["timeout"] == "30m"
    assert status["jobs"]["sync_tabarena"]["timeout"] == "30m"
    assert status["jobs"]["sync_open_asr"]["timeout"] == "30m"
    assert status["jobs"]["sync_open_tts"]["timeout"] == "30m"
    assert status["jobs"]["sync_mmteb_overall"]["timeout"] == "30m"
    assert status["jobs"]["sync_mmteb_retrieval"]["timeout"] == "30m"
    assert status["jobs"]["sync_mmteb_reranking"]["timeout"] == "30m"
    assert status["jobs"]["sync_mmeb_v2"]["timeout"] == "30m"
    assert status["jobs"]["sync_mmeb_v3"]["timeout"] == "30m"
    assert status["jobs"]["sync_artificial_analysis"]["timeout"] == "30m"
    assert (
        "TTS Quality Elo" in status["jobs"]["sync_artificial_analysis"]["idempotency"]
    )
    assert status["jobs"]["sync_programbench"]["timeout"] == "30m"
    assert status["jobs"]["sync_frontiercode"]["timeout"] == "30m"
    assert status["jobs"]["sync_parsebench"]["timeout"] == "30m"
    assert status["jobs"]["sync_extractbench"]["timeout"] == "30m"
    assert status["jobs"]["sync_physics_iq_verified"]["timeout"] == "30m"
    assert status["jobs"]["sync_vals_finance_agent"]["timeout"] == "30m"
    assert status["jobs"]["sync_surge_chartography"]["timeout"] == "30m"
    assert status["jobs"]["sync_frontiercs_2"]["timeout"] == "30m"
    assert status["jobs"]["sync_vals_index"]["timeout"] == "30m"
    assert status["jobs"]["sync_swe_sweep"]["timeout"] == "30m"
    assert status["jobs"]["sync_vending_bench_2"]["timeout"] == "30m"
    assert status["jobs"]["sync_blueprint_bench_2"]["timeout"] == "30m"
    assert status["jobs"]["sync_riemann_bench"]["timeout"] == "30m"
    assert status["jobs"]["sync_cwe_bench"]["timeout"] == "30m"
    assert status["jobs"]["sync_exploitgym"]["timeout"] == "30m"
    assert status["jobs"]["sync_cybergym"]["timeout"] == "30m"
    assert status["jobs"]["sync_patcheval_verified"]["timeout"] == "30m"
    assert status["jobs"]["sync_coarena"]["timeout"] == "30m"
    assert status["jobs"]["sync_arc_prize"]["timeout"] == "30m"


def test_launcher_records_each_exit_and_lock_skip(tmp_path: Path, monkeypatch):
    import fcntl
    from types import SimpleNamespace

    current = tmp_path / "current"
    current.mkdir()
    (current / "release.json").write_text(
        json.dumps(
            {
                "release_id": "a" * 12 + "-production",
                "git_sha": "a" * 40,
                "backend_features": {},
            }
        )
    )
    logs, locks = tmp_path / "logs", tmp_path / "locks"
    monkeypatch.setattr(cron_launcher, "CURRENT", current)
    monkeypatch.setattr(cron_launcher, "LOG_DIR", logs)
    monkeypatch.setattr(cron_launcher, "cron_python", lambda: Path("/bin/true"))
    monkeypatch.setattr(
        cron_launcher.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=3),
    )
    monkeypatch.setenv("PWC_CRON_LOCK_DIR", str(locks))
    monkeypatch.setattr(cron_launcher.sys, "argv", ["pwc-cron", "sync_tabarena"])

    assert cron_launcher.main() == 3
    with (locks / "sync_tabarena.lock").open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert cron_launcher.main() == 0

    records = [
        json.loads(line) for line in (logs / "launcher.jsonl").read_text().splitlines()
    ]
    assert [record.get("event") for record in records] == [
        None,
        "exit",
        None,
        "lock_skipped",
    ]
    assert records[1]["returncode"] == 3
    assert records[1]["started_at"] == records[0]["at"]
    assert records[3]["health_job"] == "sync_tabarena"


def test_preload_thumbnail_lanes_hold_separate_launcher_locks(
    tmp_path: Path, monkeypatch
):
    import fcntl
    from types import SimpleNamespace

    current = tmp_path / "current"
    current.mkdir()
    (current / "release.json").write_text(
        json.dumps(
            {
                "release_id": "a" * 12 + "-production",
                "git_sha": "a" * 40,
                "backend_features": {},
            }
        )
    )
    logs, locks = tmp_path / "logs", tmp_path / "locks"
    monkeypatch.setattr(cron_launcher, "CURRENT", current)
    monkeypatch.setattr(cron_launcher, "LOG_DIR", logs)
    monkeypatch.setattr(cron_launcher, "cron_python", lambda: Path("/bin/true"))
    monkeypatch.setattr(
        cron_launcher.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    monkeypatch.setenv("PWC_CRON_LOCK_DIR", str(locks))
    locks.mkdir()

    def launch(*args: str) -> int:
        monkeypatch.setattr(
            cron_launcher.sys, "argv", ["pwc-cron", "preload_thumbnails", *args]
        )
        return cron_launcher.main()

    with (locks / "preload_thumbnails.task-top.lock").open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert launch("--priority", "method-top") == 0
        assert launch("--priority=recent") == 0
        assert launch("--priority", "task-top") == 0

    records = [
        json.loads(line) for line in (logs / "launcher.jsonl").read_text().splitlines()
    ]
    assert [record.get("event") for record in records[1::2]] == [
        "exit",
        "exit",
        "lock_skipped",
    ]
    assert records[-1]["lock"] == "preload_thumbnails.task-top"


def test_lock_name_ignores_lanes_for_jobs_without_lane_arg():
    spec = cron_launcher.COMMANDS["preload_thumbnails"]
    assert cron_launcher.lock_name("preload_thumbnails", spec, []) == (
        "preload_thumbnails"
    )
    assert (
        cron_launcher.lock_name("preload_thumbnails", spec, ["--priority", "../x"])
        == "preload_thumbnails"
    )
    other = cron_launcher.COMMANDS["sync_tabarena"]
    assert cron_launcher.lock_name("sync_tabarena", other, ["--priority", "a"]) == (
        "sync_tabarena"
    )


def test_paper_markdown_fresh_lane_has_its_own_lock():
    spec = cron_launcher.COMMANDS["paper_markdown_backfill"]
    hourly = ["--execute", "--confirm"]
    assert cron_launcher.lock_name("paper_markdown_backfill", spec, hourly) == (
        "paper_markdown_backfill"
    )
    assert cron_launcher.lock_name(
        "paper_markdown_backfill", spec, ["--full", *hourly]
    ) == ("paper_markdown_backfill")
    assert cron_launcher.lock_name(
        "paper_markdown_backfill", spec, ["--lane", "fresh", *hourly]
    ) == ("paper_markdown_backfill.fresh")


def test_general_cron_environment_withholds_app_only_secrets():
    source = {
        "PATH": "/usr/bin",
        "PWC_DB_PASSWORD": "jobs-need-this",
        "PWC_RESEND_API_KEY": "research-digests-need-this",
        "PWC_CHAT_SANDBOX_SLACK_WEBHOOK_URL": "chat-monitor-needs-this",
        "LANGFUSE_SECRET_KEY": "chat-monitor-needs-this",
        "PWC_OPENAI_API_KEY": "tldr-import-needs-this",
        **{key: "must-not-leak" for key in cron_launcher.APP_ONLY_SECRET_KEYS},
    }

    environment = cron_launcher.general_environment(source, "update_github_stars")

    assert not cron_launcher.APP_ONLY_SECRET_KEYS & environment.keys()
    assert "must-not-leak" not in environment.values()
    assert environment["PWC_DB_PASSWORD"] == "jobs-need-this"
    assert environment["PWC_RESEND_API_KEY"] == "research-digests-need-this"
    assert environment["LANGFUSE_SECRET_KEY"] == "chat-monitor-needs-this"


def test_general_cron_environment_covers_session_and_oauth_signing():
    assert {
        "PWC_SESSION_SIGNING_PRIVATE_KEY",
        "PWC_JWT_SECRET",
        "PWC_HF_OAUTH_CLIENT_SECRET",
        "PWC_HF_OAUTH_CREDENTIAL_SECRET",
        "PWC_ADMIN_API_TOKEN",
    } <= cron_launcher.APP_ONLY_SECRET_KEYS


def test_legacy_url_extractor_keeps_only_its_modal_credentials():
    source = {key: "secret" for key in cron_launcher.APP_ONLY_SECRET_KEYS}

    environment = cron_launcher.general_environment(source, "extract_urls")

    assert environment.keys() == {"MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"}


def test_cron_user_is_not_added_to_the_production_group():
    source = Path(configure_host_env.__file__).read_text(encoding="utf-8")

    assert "usermod" not in source


def test_host_layout_grants_cron_traversal_and_drops_production_group(monkeypatch):
    import deploy.install_host_layout as host_layout

    calls: list[list[str]] = []
    monkeypatch.setattr(
        host_layout.subprocess, "run", lambda command, check: calls.append(command)
    )
    monkeypatch.setattr(
        host_layout.grp,
        "getgrnam",
        lambda name: type("Group", (), {"gr_mem": ["pwc-cron"]})(),
    )

    host_layout.restrict_cron_access()

    assert calls == [
        [
            "setfacl",
            "--modify",
            "user:pwc-cron:--x,user:pwc-cron-trending:--x",
            "/var/lib/paperswithcode/production",
        ],
        ["gpasswd", "--delete", "pwc-cron", "pwc-production"],
    ]


def test_launcher_hides_its_environment_from_same_user_jobs(tmp_path: Path):
    # Run in a child so the test process itself stays dumpable.
    script = tmp_path / "probe.py"
    script.write_text(
        "import ctypes, sys\n"
        f"sys.path.insert(0, {str(Path(cron_launcher.__file__).parent)!r})\n"
        "import cron_launcher\n"
        "cron_launcher.hide_launcher_environment()\n"
        "libc = ctypes.CDLL(None)\n"
        "print(libc.prctl(3, 0, 0, 0, 0))\n",  # PR_GET_DUMPABLE
        encoding="utf-8",
    )
    result = subprocess.run(
        ["python3", "-I", str(script)], check=True, capture_output=True, text=True
    )
    assert result.stdout.strip() == "0"
