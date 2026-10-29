"""CRON registry inventory: every workflow, systemd unit, and allowlisted job is registered and classified."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from backend.services.cron_health import (
    _dashboard_job_summary,
)
from backend.services.cron_registry import get_cron_job, list_cron_jobs
from deploy.cron_launcher import COMMANDS


def _job(job_id: str):
    job = get_cron_job(job_id)
    assert job is not None
    return job


def test_registry_covers_workflows_systemd_and_allowlist_exactly():
    root = Path(__file__).resolve().parents[3]
    jobs = list(list_cron_jobs())
    by_id = {job.id: job for job in jobs}
    summary = _dashboard_job_summary(
        [{"category": job.category, "status": "healthy"} for job in jobs]
    )
    assert summary["total_jobs"] == 74
    assert summary["scheduled_jobs"] == 73
    assert summary["manual_jobs"] == 1
    assert len(by_id) == len(jobs), "duplicate dashboard job IDs"

    scheduled_commands = set()
    workflow_owners = {}
    for path in sorted((root / ".github" / "workflows").glob("cron-*.yml")):
        document = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        if not (document.get("on") or {}).get("schedule"):
            continue
        commands = set(re.findall(r"pwc-cron\s+([a-z0-9_]+)", path.read_text()))
        commands.discard("status")
        scheduled_commands.update(commands)
        for command in commands:
            assert command in by_id, (
                f"scheduled workflow command missing from registry: {command}"
            )
            owner = by_id[command]
            assert owner.workflow_file == path.name, (
                f"workflow ownership mismatch for {command}"
            )
            assert not (
                set(owner.workflow_jobs) - set((document.get("jobs") or {}).keys())
            )
            assert path.name not in workflow_owners, (
                f"duplicate workflow owner: {path.name}"
            )
            workflow_owners[path.name] = command

    systemd_commands = set()
    services = [
        *(root / "deploy" / "systemd").glob("pwc-*.service"),
        *(root / "deploy" / "systemd" / "cron").glob("pwc-*.service"),
        *(root / "deploy" / "autonomous").glob("*.service"),
    ]
    for service in sorted(services):
        timer = service.with_suffix(".timer")
        if not timer.exists():
            continue
        match = re.search(
            r"ExecStart=.*/pwc-cron(?:-throttled)?\s+([a-z0-9_]+)",
            service.read_text(),
        )
        if not match:
            continue
        command = match.group(1)
        systemd_commands.add(command)
        assert command in by_id, f"systemd command missing from registry: {command}"
        assert (timer.name, service.name) in by_id[command].systemd_unit_pairs, (
            f"unit pair not registered for {command}: {service.name}"
        )

    helpers = {
        "alert_submission_review_failure",
        "extract_urls_select",
        "extract_urls_persist",
    }
    manual = {"extract_urls"}
    registered = set(by_id)
    assert set(COMMANDS) == registered | helpers
    assert manual == {job.id for job in jobs if job.scheduler == "manual"}
    assert scheduled_commands | systemd_commands == {
        job.id for job in jobs if job.scheduler != "manual"
    }


def test_registry_includes_hf_artifacts_embeddings_and_method_backfills():
    job_ids = {job.id for job in list_cron_jobs()}
    assert "update_hot_github_trending" in job_ids
    assert "update_hf_artifacts" in job_ids
    assert "refresh_paper_embeddings" in job_ids
    assert "paper_markdown_backfill" in job_ids
    assert "backfill_method_keywords" in job_ids
    assert "backfill_method_references" in job_ids
    assert "sync_hf_organizations" in job_ids
    assert "sync_hf_author_profiles" in job_ids
    assert "sync_3d_arena" in job_ids
    assert "sync_tabarena" in job_ids
    assert "sync_open_asr" in job_ids
    assert "sync_open_tts" in job_ids
    assert "sync_mmteb_overall" in job_ids
    assert "sync_mmteb_retrieval" in job_ids
    assert "sync_mmteb_reranking" in job_ids
    assert "sync_mmeb_v2" in job_ids
    assert "sync_mmeb_v3" in job_ids
    assert "sync_deepswe" in job_ids
    assert "sync_artificial_analysis" in job_ids
    assert "sync_programbench" in job_ids
    assert "sync_frontiercode" in job_ids
    assert "sync_parsebench" in job_ids
    assert "sync_extractbench" in job_ids
    assert "sync_physics_iq_verified" in job_ids
    assert "sync_vals_finance_agent" in job_ids
    assert "sync_surge_chartography" in job_ids
    assert "sync_frontiercs_2" in job_ids
    assert "sync_vals_index" in job_ids
    assert "sync_swe_sweep" in job_ids
    assert "sync_vending_bench_2" in job_ids
    assert "sync_blueprint_bench_2" in job_ids
    assert "sync_riemann_bench" in job_ids
    assert "sync_cwe_bench" in job_ids
    assert "sync_exploitgym" in job_ids
    assert "sync_cybergym" in job_ids
    assert "sync_patcheval_verified" in job_ids
    assert "sync_coarena" in job_ids
    assert "sync_arc_prize" in job_ids
    assert "calculate_organization_trending_scores" in job_ids
    assert "monitor_chat_operational_alerts" in job_ids
    assert "process_curation_thumbnails" in job_ids

    artificial_analysis_job = _job("sync_artificial_analysis")
    assert artificial_analysis_job.display_name == (
        "Sync Artificial Analysis Leaderboards"
    )
    assert "artificial-analysis-provider-voice-tts-arena" in (
        artificial_analysis_job.db_freshness_query
    )
    assert "missing_fresh_datasets" in artificial_analysis_job.db_freshness_query
    assert "stale_evaluations" in artificial_analysis_job.db_freshness_query

    keyword_job = _job("backfill_method_keywords")
    assert "method_keyword_backfill_runs" in keyword_job.db_freshness_query
    assert keyword_job.lock_file == (
        "/var/lib/paperswithcode/production/cron-locks/backfill_method_keywords.lock"
    )
    assert "WITH current_run AS" in keyword_job.db_freshness_query
    assert "WHERE keyword_catalog_sha256 =" in keyword_job.db_freshness_query
    assert keyword_job.schedule.startswith("10 1")
    assert keyword_job.workflow_file == "cron-backfill-method-keywords.yml"
    reference_job = _job("backfill_method_references")
    assert "method_reference_backfill_months" in reference_job.db_freshness_query
    assert "WITH frontier AS" in reference_job.db_freshness_query
    assert "month_start = (SELECT month_start FROM frontier)" in (
        reference_job.db_freshness_query
    )
    assert reference_job.schedule == "15 * * * * (hourly at :15 UTC)"
    assert reference_job.workflow_file == "cron-backfill-method-references.yml"


def test_registry_classifies_only_recurring_leaderboard_syncs():
    leaderboard_jobs = {
        job.id for job in list_cron_jobs() if job.dashboard_group == "leaderboard_sync"
    }

    assert leaderboard_jobs == {
        "sync_3d_arena",
        "sync_tabarena",
        "sync_open_asr",
        "sync_open_tts",
        "sync_mmteb_overall",
        "sync_mmteb_retrieval",
        "sync_mmteb_reranking",
        "sync_mmeb_v2",
        "sync_mmeb_v3",
        "sync_deepswe",
        "sync_artificial_analysis",
        "sync_programbench",
        "sync_frontiercode",
        "sync_parsebench",
        "sync_extractbench",
        "sync_physics_iq_verified",
        "sync_vals_finance_agent",
        "sync_surge_chartography",
        "sync_frontiercs_2",
        "sync_vals_index",
        "sync_swe_sweep",
        "sync_vending_bench_2",
        "sync_blueprint_bench_2",
        "sync_riemann_bench",
        "sync_cwe_bench",
        "sync_exploitgym",
        "sync_cybergym",
        "sync_patcheval_verified",
        "sync_coarena",
        "sync_arc_prize",
    }
    assert _job("sync_hf_organizations").dashboard_group == "operations"


def test_hot_job_has_dedicated_lock_and_operational_metrics():
    job = _job("update_hot_github_trending")
    assert job.schedule.startswith("*/15")
    assert job.category == "hourly"
    assert job.critical is False
    assert job.lock_file.endswith("/update_hot_github_trending.lock")
    assert "one_snapshot_over_30m" in job.db_freshness_query
    assert "stale_paper_scores" in job.db_freshness_query
    assert "r.trending_score > 0" in job.db_freshness_query
    assert "r.trending_score IS NOT NULL" not in job.db_freshness_query
    assert "COALESCE(r.owner, '') != ''" in job.db_freshness_query
    assert "COALESCE(r.name, '') != ''" in job.db_freshness_query
    assert "p.date_published >= CURRENT_DATE - INTERVAL '365 days'" in (
        job.db_freshness_query
    )
    assert job.workflow_file == "cron-update-hot-github-trending.yml"


def test_action_backed_jobs_expose_workflow_health():
    paper_trending = _job("calculate_paper_trending_scores")
    github_stars = _job("update_github_stars")
    thumbnails = _job("preload_thumbnails")

    assert paper_trending.workflow_file == "cron-calculate-paper-trending-scores.yml"
    assert github_stars.workflow_file == "cron-update-github-stars.yml"
    assert thumbnails.workflow_file == "cron-preload-thumbnails.yml"
