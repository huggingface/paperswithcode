#!/usr/bin/env python3
"""Stable, allowlisted launcher for production scheduled jobs."""

from __future__ import annotations

import ctypes
import fcntl
import json
import os
import pwd
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    from deploy.runtime import runtime_id, runtime_manifest
except ModuleNotFoundError:
    from runtime import runtime_id, runtime_manifest  # type: ignore[no-redef]

CURRENT = Path("/srv/paperswithcode/environments/production/current")
RUNTIMES = Path("/srv/paperswithcode/runtimes")
LOG_DIR = Path("/var/lib/paperswithcode/production/cron-logs")
RESTRICTED_TRENDING_LOG_DIR = Path(
    "/var/lib/paperswithcode/production/trending-cron-logs"
)
RESTRICTED_TRENDING_LOCK_DIR = Path(
    "/var/lib/paperswithcode/production/trending-cron-locks"
)
RESTRICTED_TRENDING_JOBS = frozenset(
    {"calculate_trending_scores", "calculate_paper_trending_scores"}
)
RESTRICTED_TRENDING_PASSTHROUGH_KEYS = frozenset(
    {
        "LANG",
        "LC_ALL",
        "PATH",
        "PWC_DB_HOST",
        "PWC_DB_NAME",
        "PWC_DB_PORT",
        "PWC_TRENDING_PIN_ARXIV_IDS",
        "PWC_TRENDING_PIN_PAPER_IDS",
        "TZ",
    }
)
RESTRICTED_TRENDING_ENV_KEYS = RESTRICTED_TRENDING_PASSTHROUGH_KEYS | {
    "PWC_CRON_LOCK_DIR",
    "PWC_CRON_LOG_DIR",
    "PWC_DB_PASSWORD",
    "PWC_DB_USER",
    "PWC_ENVIRONMENT",
    "PWC_RELEASE_ID",
    "PYTHONPATH",
}

# production.env is shared with the web app, so general jobs would otherwise
# inherit secrets that only the app or chat runtime uses. No CRON job reads
# these (session/OAuth signing, admin API, chat providers and sandboxes), so a
# compromised job must not receive them.
APP_ONLY_SECRET_KEYS = frozenset(
    {
        "PWC_SESSION_SIGNING_PRIVATE_KEY",
        "PWC_JWT_SECRET",
        "PWC_HF_OAUTH_CLIENT_SECRET",
        "PWC_HF_OAUTH_CREDENTIAL_SECRET",
        "PWC_ADMIN_API_TOKEN",
        "PWC_CHAT_EXTERNAL_PI_WORKER_TOKEN",
        "PWC_CHAT_OPENROUTER_API_KEY",
        "PWC_CHAT_OPENROUTER_CREDENTIAL_KEYRING",
        "PWC_CHAT_OPENROUTER_USER_TRACKING_SECRET",
        "PWC_CHAT_SCOPE_GUARDRAIL_HF_TOKEN",
        "PWC_CHAT_SCOPE_GUARDRAIL_OPENAI_API_KEY",
        "PWC_CHAT_TITLE_HF_TOKEN",
        "PWC_CHAT_TRACKIO_HF_TOKEN",
        "PWC_CHAT_WEB_SEARCH_EXA_API_KEY",
        "PWC_CHAT_SANDBOX_BUDGET_ATTESTATION",
        "MODAL_TOKEN_ID",
        "MODAL_TOKEN_SECRET",
    }
)
# The manual legacy URL extractor still drives Modal from the VPS.
APP_SECRET_EXCEPTIONS = {
    "extract_urls": frozenset({"MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"}),
}


def general_environment(source: dict[str, str], job: str) -> dict[str, str]:
    """Copy the CRON environment without app-only secrets the job never uses."""

    withheld = APP_ONLY_SECRET_KEYS - APP_SECRET_EXCEPTIONS.get(job, frozenset())
    return {key: value for key, value in source.items() if key not in withheld}


def restricted_trending_environment(
    source: dict[str, str], *, release_id: str
) -> dict[str, str]:
    """Build the complete, credential-minimal environment for patched code."""
    password = source.get("PWC_TRENDING_DB_PASSWORD", "")
    if not password:
        raise RuntimeError("PWC_TRENDING_DB_PASSWORD is required")
    required = ("PWC_DB_HOST", "PWC_DB_NAME", "PWC_DB_PORT")
    missing = [key for key in required if not source.get(key)]
    if missing:
        raise RuntimeError(
            "restricted trending database configuration missing: " + ", ".join(missing)
        )
    env = {
        key: value
        for key in RESTRICTED_TRENDING_PASSTHROUGH_KEYS
        if (value := source.get(key))
    }
    env.update(
        {
            "PWC_CRON_LOCK_DIR": source.get(
                "PWC_CRON_LOCK_DIR", str(RESTRICTED_TRENDING_LOCK_DIR)
            ),
            "PWC_CRON_LOG_DIR": str(RESTRICTED_TRENDING_LOG_DIR),
            "PWC_DB_PASSWORD": password,
            "PWC_DB_USER": "pwc_cron_trending",
            "PWC_ENVIRONMENT": "production",
            "PWC_RELEASE_ID": release_id,
            "PYTHONPATH": str(CURRENT / ".github" / "workflows"),
        }
    )
    return env


@dataclass(frozen=True)
class Job:
    command: tuple[str, ...]
    timeout: str
    mutates_shared_data: bool
    idempotency: str
    health_job: str
    # Argument whose value names an independent lane with its own job lock, so
    # lanes of one job (different candidate sets) never skip each other.
    lane_arg: str | None = None


def job(
    *command: str,
    timeout: str,
    idempotency: str,
    health_job: str | None = None,
    mutates_shared_data: bool = True,
    lane_arg: str | None = None,
) -> Job:
    return Job(
        command=command,
        timeout=timeout,
        mutates_shared_data=mutates_shared_data,
        idempotency=idempotency,
        health_job=health_job or command[-1].rsplit(".", 1)[-1],
        lane_arg=lane_arg,
    )


def lock_name(job: str, spec: Job, extra: list[str]) -> str:
    """The launcher lock for one invocation: per lane when the job has lanes."""

    if spec.lane_arg is None:
        return job
    for index, arg in enumerate(extra):
        if arg == spec.lane_arg and index + 1 < len(extra):
            lane = extra[index + 1]
        elif arg.startswith(spec.lane_arg + "="):
            lane = arg.partition("=")[2]
        else:
            continue
        if lane.replace("-", "").replace("_", "").isalnum():
            return f"{job}.{lane}"
    return job


COMMANDS: dict[str, Job] = {
    "send_research_digests": job(
        "-m",
        "backend.scripts.send_research_digests",
        timeout="45m",
        health_job="send_research_digests",
        idempotency="weekly account outbox and immutable Resend key; retries stop before 24h",
    ),
    "create_eval_verification_issues": job(
        "-m",
        "backend.scripts.create_eval_verification_issues",
        "--execute",
        timeout="30m",
        health_job="create_eval_verification_issues",
        idempotency="canonical repository ledger, pre-POST checkpoint, paginated issue reconciliation; at most 30 posts",
    ),
    "autonomous_cron_health": job(
        ".github/workflows/scripts/autonomous_cron_health.py",
        "--mode",
        "strict",
        timeout="6h",
        idempotency=(
            "persist one deterministic snapshot and perform at most one fenced "
            "allowlisted recovery for one declared job"
        ),
    ),
    "autonomous_cron_audit": job(
        ".github/workflows/scripts/autonomous_cron_health.py",
        "--mode",
        "daily",
        timeout="6h",
        idempotency=(
            "persist one daily four-plane audit and perform at most one fenced "
            "allowlisted recovery for one declared job"
        ),
    ),
    "alert_submission_review_failure": job(
        "-m",
        "backend.scripts.alert_autonomous_submission_failure",
        timeout="1m",
        idempotency=(
            "send one content-free failure signal through the configured primary "
            "or fallback alert route"
        ),
        mutates_shared_data=False,
    ),
    "review_submissions": job(
        ".github/workflows/scripts/review_submissions.py",
        "--launch-remote",
        timeout="45m",
        idempotency=(
            "claim at most 25 oldest submissions once and launch one pinned "
            "database-free remote reviewer with replay-safe callbacks"
        ),
    ),
    "monitor_chat_operational_alerts": job(
        "-m",
        "backend.scripts.monitor_chat_operational_alerts",
        timeout="1m",
        idempotency=(
            "advance one content-free journal cursor and deliver each durable "
            "operational event through at most one alert route"
        ),
        mutates_shared_data=False,
    ),
    "run_chat_synthetic_probe": job(
        "-m",
        "backend.scripts.run_chat_synthetic_probe",
        timeout="6m",
        idempotency=(
            "run at most one due or release/alert-triggered content-free synthetic "
            "production chat and deliver each transition once"
        ),
    ),
    "update_hot_github_trending": job(
        "-m",
        "scripts.hourly.update_hot_github_trending",
        timeout="30m",
        idempotency="upsert hot star snapshots and targeted trending scores",
    ),
    "update_github_stars": job(
        "-m",
        "scripts.hourly.update_github_stars",
        timeout="50m",
        idempotency="upsert current repository star counts",
    ),
    "update_citations": job(
        "-m",
        "scripts.hourly.update_citations",
        timeout="50m",
        idempotency="upsert current citation counts",
    ),
    "extract_urls": job(
        "-m",
        "url_extraction_agent.runner",
        timeout="2h",
        idempotency="persist only selected unresolved paper URLs",
    ),
    "extract_urls_select": job(
        "-m",
        "url_extraction_agent.database",
        "select",
        timeout="30m",
        idempotency="read-only candidate selection",
        health_job="extract_urls",
    ),
    "extract_urls_persist": job(
        "-m",
        "url_extraction_agent.database",
        "persist",
        timeout="30m",
        idempotency="validated URL upserts",
        health_job="extract_urls",
    ),
    "calculate_trending_scores": job(
        "-m",
        "scripts.hourly.calculate_trending_scores",
        timeout="50m",
        idempotency="replace current task trending scores",
    ),
    "calculate_paper_trending_scores": job(
        "-m",
        "scripts.hourly.calculate_paper_trending_scores",
        timeout="50m",
        idempotency="replace current paper trending scores",
    ),
    "update_hf_artifacts": job(
        "-m",
        "scripts.hourly.update_hf_artifacts",
        timeout="50m",
        idempotency="upsert current Hugging Face artifact links",
    ),
    "sync_3d_arena": job(
        "-m",
        "scripts.hourly.sync_3d_arena",
        timeout="30m",
        idempotency="replace managed 3D Arena evaluation rows from validated live data",
    ),
    "sync_tabarena": job(
        "-m",
        "scripts.hourly.sync_tabarena",
        timeout="30m",
        idempotency="replace managed TabArena evaluation rows from validated live data",
    ),
    "sync_open_asr": job(
        "-m",
        "scripts.hourly.sync_open_asr",
        timeout="30m",
        idempotency="replace managed Open ASR evaluation rows from validated live data",
    ),
    "sync_open_tts": job(
        "-m",
        "scripts.hourly.sync_open_tts",
        timeout="30m",
        idempotency="replace managed Open TTS English and all-language evaluation rows from validated live data",
    ),
    "sync_mmteb_overall": job(
        "-m",
        "scripts.hourly.sync_mmteb",
        "overall",
        timeout="30m",
        idempotency=(
            "replace arXiv-backed managed MMTEB v2 overall evaluation rows "
            "from the official API"
        ),
    ),
    "sync_mmteb_retrieval": job(
        "-m",
        "scripts.hourly.sync_mmteb",
        "retrieval",
        timeout="30m",
        idempotency=(
            "replace arXiv-backed managed MMTEB v2 retrieval evaluation rows "
            "from the official API"
        ),
    ),
    "sync_mmteb_reranking": job(
        "-m",
        "scripts.hourly.sync_mmteb",
        "reranking",
        timeout="30m",
        idempotency=(
            "replace arXiv-backed managed MMTEB v2 reranking evaluation rows "
            "from the official API"
        ),
    ),
    "sync_mmeb_v2": job(
        "-m",
        "scripts.hourly.sync_mmeb",
        "v2",
        timeout="30m",
        idempotency=(
            "replace linked managed MMEB-v2 overall evaluation rows from the "
            "official leaderboard Space"
        ),
    ),
    "sync_mmeb_v3": job(
        "-m",
        "scripts.hourly.sync_mmeb",
        "v3",
        timeout="30m",
        idempotency=(
            "replace linked managed MMEB-v3 overall evaluation rows from the "
            "official leaderboard Space"
        ),
    ),
    "sync_deepswe": job(
        "-m",
        "scripts.hourly.sync_deepswe",
        timeout="30m",
        idempotency="replace managed DeepSWE evaluation rows from validated live data",
    ),
    "sync_frontiercode": job(
        "-m",
        "scripts.hourly.sync_frontiercode",
        timeout="30m",
        idempotency="replace managed FrontierCode 1.1 evaluation rows from validated live data",
    ),
    "sync_artificial_analysis": job(
        "-m",
        "scripts.hourly.sync_artificial_analysis",
        timeout="30m",
        idempotency=(
            "index reviewed model releases and upsert Artificial Analysis "
            "Intelligence, Agentic Index, and TTS Quality Elo scores from "
            "validated live data"
        ),
    ),
    "sync_programbench": job(
        "-m",
        "scripts.hourly.sync_programbench",
        timeout="30m",
        idempotency=(
            "replace managed ProgramBench evaluation rows from validated live data"
        ),
    ),
    "sync_parsebench": job(
        "-m",
        "scripts.hourly.sync_parsebench",
        timeout="30m",
        idempotency=(
            "replace managed ParseBench evaluation rows from the validated leaderboard.csv"
        ),
    ),
    "sync_extractbench": job(
        "-m",
        "scripts.hourly.sync_extractbench",
        timeout="30m",
        idempotency=(
            "replace managed ExtractBench evaluation rows from the validated leaderboard.csv"
        ),
    ),
    "sync_vals_finance_agent": job(
        "-m",
        "scripts.hourly.sync_vals_finance_agent",
        timeout="30m",
        idempotency=(
            "create or revise reviewed Finance Agent v2 evaluation rows from the "
            "validated Vals AI leaderboard table; never creates papers"
        ),
    ),
    "sync_surge_chartography": job(
        "-m",
        "scripts.hourly.sync_surge_chartography",
        timeout="30m",
        idempotency=(
            "create or revise reviewed Chartography (no tools) evaluation rows "
            "from the validated Surge AI leaderboard; never creates papers"
        ),
    ),
    "sync_frontiercs_2": job(
        "-m",
        "scripts.hourly.sync_frontiercs_2",
        timeout="30m",
        idempotency=(
            "create or revise reviewed FrontierCS 2 evaluation rows from the "
            "validated frontier-cs.org leaderboard data; never creates papers"
        ),
    ),
    "sync_physics_iq_verified": job(
        "-m",
        "scripts.hourly.sync_physics_iq_verified",
        timeout="30m",
        idempotency=(
            "create or revise reviewed Physics-IQ Verified evaluation rows from "
            "the validated README table; never creates papers"
        ),
    ),
    "sync_coarena": job(
        "-m",
        "scripts.hourly.sync_coarena",
        timeout="30m",
        idempotency="replace managed CoArena evaluation rows from validated live data",
    ),
    "sync_arc_prize": job(
        "-m",
        "scripts.hourly.sync_arc_prize",
        timeout="30m",
        idempotency=(
            "upsert strongest paper-linked ARC-AGI-1, ARC-AGI-2, and ARC-AGI-3 "
            "results from validated live data"
        ),
    ),
    "import_hf_daily_papers": job(
        "-m",
        "scripts.daily.import_hf_daily_papers",
        timeout="2h",
        idempotency="upsert papers by stable source identity",
    ),
    "enqueue_hf_daily_paper_curation": job(
        "-m",
        "backend.scripts.enqueue_hf_daily_paper_curation",
        timeout="30m",
        idempotency=(
            "reconcile the rolling seven-day HF cohort into versioned per-paper "
            "workflows and the shared bounded curation queue"
        ),
    ),
    "enqueue_hf_trending_model_curation": job(
        "-m",
        "backend.scripts.enqueue_hf_trending_model_curation",
        timeout="30m",
        idempotency=(
            "reconcile the global HF trending-model feed into pinned, bounded "
            "model-resolution and paper-curation workflows"
        ),
    ),
    "enqueue_benchmark_gap_review": job(
        "-m",
        "backend.scripts.enqueue_benchmark_gap_review",
        timeout="30m",
        idempotency=(
            "queue at most one daily overseer review of eligible benchmark-gap "
            "candidates and at most 40 add-benchmark jobs per UTC day"
        ),
    ),
    "scan_model_releases": job(
        "-m",
        "backend.scripts.scan_model_releases",
        timeout="30m",
        idempotency=(
            "scan lab news feeds, unmapped Artificial Analysis models, and web "
            "news for releases without a paper row; upsert one signal per "
            "release and queue at most 6 scoped resolution jobs per UTC day"
        ),
    ),
    "discover_x_threads": job(
        "-m",
        "backend.scripts.discover_x_threads",
        timeout="30m",
        idempotency=(
            "search X once per bounded candidate paper; link author posts only "
            "when PWC_X_THREAD_DISCOVERY_APPLY=true, through the audited x_threads "
            "section"
        ),
    ),
    "post_trending_paper_to_x": job(
        "-m",
        "backend.scripts.post_trending_paper_to_x",
        timeout="30m",
        idempotency=(
            "post at most one never-posted trending paper per run; paper_x_posts "
            "is written right after the post, so a paper is never posted twice"
        ),
    ),
    "post_x_insight": job(
        "-m",
        "backend.scripts.post_x_insight",
        timeout="30m",
        idempotency=(
            "post at most one insight per run; x_insight_posts is written right "
            "after the post, so a subject is never posted twice"
        ),
    ),
    "link_abstract_mentions": job(
        "-m",
        "backend.scripts.link_abstract_mentions",
        timeout="45m",
        idempotency=(
            "judge only papers whose stored mentions are missing or stale for the "
            "current abstract; each paper's rows are replaced in one transaction"
        ),
    ),
    "rescan_abstract_mentions": job(
        "-m",
        "backend.scripts.link_abstract_mentions",
        "--rescan",
        "--limit",
        "1000000",
        timeout="2h",
        idempotency=(
            "reuse earlier verdicts for unchanged abstracts and rewrite a paper's "
            "rows only when its links changed"
        ),
        health_job="link_abstract_mentions",
    ),
    "judge_research_topics": job(
        "-m",
        "backend.scripts.judge_research_topics",
        timeout="45m",
        idempotency=(
            "judge only topic/paper pairs without a verdict for the current paper "
            "card and prompt; each verdict is an upsert"
        ),
    ),
    "backfill_research_topics": job(
        "-m",
        "backend.scripts.judge_research_topics",
        "--backfill",
        timeout="2h",
        idempotency=(
            "claim topics with skip-locked semantics; pairs already judged for the "
            "current card are skipped on retries"
        ),
        health_job="backfill_research_topics",
    ),
    "warm_paper_suggested_questions": job(
        "-m",
        "backend.scripts.warm_paper_suggested_questions",
        timeout="45m",
        idempotency=(
            "generate questions only for papers without a paper_suggested_questions "
            "row; inserts ignore rows written concurrently by paper pages"
        ),
    ),
    "sweep_conference_deadlines": job(
        "-m",
        "backend.scripts.sweep_conference_deadlines",
        timeout="30m",
        idempotency=(
            "apply finished off-box deadline research Jobs through the guarded, "
            "audited writer (no deletes, past editions immutable), then launch "
            "at most one Hugging Face Job"
        ),
    ),
    "link_google_scholar_profiles": job(
        "-m",
        "backend.scripts.link_google_scholar_profiles",
        # Up to 600 new authors on the shared, throttled Semantic Scholar key.
        timeout="3h",
        idempotency=(
            "check each Wikidata Scholar candidate once on Semantic Scholar and "
            "once on its Scholar profile within the monthly SerpAPI quota, then "
            "upsert confirmed author links; never deletes links"
        ),
    ),
    "refresh_conference_deadlines": job(
        "-m",
        "backend.scripts.refresh_conference_deadlines",
        timeout="30m",
        idempotency=(
            "apply finished off-box deadline research Jobs through the guarded, "
            "audited writer, then launch at most one light Job per 20 hours"
        ),
    ),
    "export_enrichment_dashboard": job(
        "-m",
        "backend.scripts.export_enrichment_dashboard",
        "--upload",
        timeout="30m",
        idempotency="publish one daily enrichment dashboard snapshot",
        mutates_shared_data=False,
    ),
    "sync_hf_organizations": job(
        "-m",
        "scripts.daily.sync_hf_organizations",
        timeout="2h",
        idempotency="append featured HF organization paper links",
    ),
    "sync_hf_author_profiles": job(
        "-m",
        "scripts.daily.sync_hf_author_profiles",
        # A one-off `--days 10000` backfill walks all of HF in about an hour.
        timeout="2h",
        idempotency=(
            "move each claimed paper link to the claiming account's author and "
            "mark it claimed; already claimed links and accounts are unchanged"
        ),
    ),
    "link_openalex_organizations": job(
        "-m",
        "scripts.daily.link_openalex_organizations",
        timeout="30m",
        idempotency=(
            "insert missing openalex paper_organizations links for the last 60 "
            "days of arXiv papers; never deletes links"
        ),
    ),
    "calculate_organization_trending_scores": job(
        "-m",
        "scripts.daily.calculate_organization_trending_scores",
        timeout="30m",
        idempotency="upsert one daily snapshot and rolling mean per organization",
    ),
    "preload_thumbnails": job(
        "-m",
        "scripts.daily.preload_thumbnails",
        timeout="2h",
        idempotency="skip valid existing thumbnail objects",
        # Five daily/3-hourly lanes with different candidate sets; one shared
        # lock let a long lane silently skip the others (2026-10-16/17).
        lane_arg="--priority",
    ),
    "mirror_thumbnails_to_disk": job(
        "-m",
        "scripts.daily.mirror_thumbnails_to_disk",
        timeout="2h",
        idempotency="replace local mirror files by object key",
    ),
    "link_methods_by_references": job(
        "-m",
        "scripts.weekly.link_methods_by_references",
        timeout="6h",
        idempotency="insert missing paper-method relationships",
    ),
    "backfill_method_keywords": job(
        "-m",
        "scripts.backfill.backfill_method_keywords",
        timeout="6h",
        idempotency="resume versioned paper-id cursor and upsert keyword evidence",
    ),
    "backfill_method_references": job(
        "-m",
        "scripts.backfill.backfill_method_references",
        timeout="6h",
        idempotency="resume stable monthly paper cursor and upsert reference evidence",
    ),
    "link_papers_by_task_keywords": job(
        "-m",
        "scripts.weekly.link_papers_by_task_keywords",
        timeout="6h",
        idempotency="insert missing paper-task relationships",
    ),
    "refresh_paper_embeddings": job(
        "-m",
        "scripts.hourly.refresh_paper_embeddings",
        timeout="6h",
        idempotency="resume generation and activate only complete embeddings",
    ),
    "paper_markdown_backfill": job(
        "-m",
        "scripts.hourly.backfill_paper_markdown",
        timeout="45m",
        idempotency=(
            "copy immutable upstream Markdown or dispatch one manifest per "
            "missing arXiv identity"
        ),
        lane_arg="--lane",
    ),
    "process_curation_thumbnails": job(
        "-m",
        "scripts.hourly.process_curation_thumbnails",
        timeout="30m",
        idempotency=(
            "claim one queued job row with skip-locked semantics; recover stale "
            "claims and record terminal thumbnail results"
        ),
    ),
}


def apply_release_features(env: dict[str, str], manifest: dict) -> None:
    """Make CRON capability flags follow the active immutable release."""
    features = manifest["backend_features"]
    add_evals = bool(features.get("codex_add_evals"))
    enrich_paper = bool(features.get("codex_enrich_paper"))
    env["PWC_CODEX_ADD_EVALS_ENABLED"] = "true" if add_evals else "false"
    env["PWC_CODEX_ENRICH_PAPER_ENABLED"] = "true" if enrich_paper else "false"
    env["PWC_CODEX_JOBS_ENABLED"] = "true" if add_evals or enrich_paper else "false"


def cron_python(current: Path = CURRENT, runtimes: Path = RUNTIMES) -> Path:
    """Resolve and validate the immutable runtime recorded by the active release."""
    runtime = runtimes / runtime_id(current)
    runtime_manifest(runtime)
    return runtime / "bin" / "python"


def append_launcher_record(log_dir: Path, record: dict) -> None:
    with (log_dir / "launcher.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def terminal_record(start: dict, event: str, *, returncode: int) -> dict:
    """A compact record pairing a launch with how it ended.

    The CRON dashboard reads these to count recent failures and lock skips,
    which the latest systemd exit alone cannot show.
    """

    return {
        "at": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "job": start["job"],
        "health_job": start["health_job"],
        "git_sha": start["git_sha"],
        "started_at": start["at"],
        "returncode": returncode,
    }


PR_SET_DUMPABLE = 4


def hide_launcher_environment() -> None:
    """Keep the launcher's full environment away from the jobs it starts.

    systemd hands the launcher every configured secret, while jobs get a
    filtered copy. Jobs run as the same user, so they could otherwise read the
    launcher's /proc/<pid>/environ. A non-dumpable process's /proc entries are
    owned by root.
    """

    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def main() -> int:
    hide_launcher_environment()
    manifest = json.loads((CURRENT / "release.json").read_text())
    if len(sys.argv) == 2 and sys.argv[1] == "status":
        print(
            json.dumps(
                {
                    "environment": "production",
                    "release_id": manifest["release_id"],
                    "git_sha": manifest["git_sha"],
                    "uid": os.getuid(),
                    "jobs": {
                        name: asdict(spec) for name, spec in sorted(COMMANDS.items())
                    },
                },
                indent=2,
            )
        )
        return 0
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(
            "usage: pwc-cron status | <registered-job> [permitted arguments]",
            file=sys.stderr,
        )
        return 2
    job = sys.argv[1]
    spec = COMMANDS[job]
    extra = sys.argv[2:]
    if job in {"autonomous_cron_health", "autonomous_cron_audit"} and extra:
        print(
            "autonomous CRON operator does not accept runtime arguments",
            file=sys.stderr,
        )
        return 2
    if any("\n" in arg or "\x00" in arg for arg in extra):
        print("invalid argument", file=sys.stderr)
        return 2
    log_dir = (
        RESTRICTED_TRENDING_LOG_DIR if job in RESTRICTED_TRENDING_JOBS else LOG_DIR
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "at": datetime.now(timezone.utc).isoformat(),
        "job": job,
        "release_id": manifest["release_id"],
        "git_sha": manifest["git_sha"],
        "target_environment": "production",
        "timeout": spec.timeout,
        "mutates_shared_data": spec.mutates_shared_data,
        "idempotency": spec.idempotency,
        "health_job": spec.health_job,
    }
    append_launcher_record(log_dir, record)
    command = spec.command
    if job in RESTRICTED_TRENDING_JOBS:
        if pwd.getpwuid(os.getuid()).pw_name != "pwc-cron-trending":
            print("restricted trending job requires pwc-cron-trending", file=sys.stderr)
            return 2
        try:
            env = restricted_trending_environment(
                os.environ.copy(), release_id=manifest["release_id"]
            )
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    else:
        env = general_environment(dict(os.environ), job)
        env["PWC_ENVIRONMENT"] = "production"
        env["PWC_RELEASE_ID"] = manifest["release_id"]
        env["PWC_CRON_LOG_DIR"] = str(log_dir)
        env["PYTHONPATH"] = str(CURRENT / ".github" / "workflows")
        apply_release_features(env, manifest)
    if job in {
        "preload_thumbnails",
        "mirror_thumbnails_to_disk",
        "process_curation_thumbnails",
    }:
        env["PWC_THUMBNAIL_MUTATIONS_ENABLED"] = "true"
    argv = [str(cron_python()), *command, *extra]
    lock_dir = Path(
        env.get("PWC_CRON_LOCK_DIR", "/var/lib/paperswithcode/production/cron-locks")
    )
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_id = lock_name(job, spec, extra)
    with (lock_dir / f"{lock_id}.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"{lock_id} is already running; skipped this run", file=sys.stderr)
            append_launcher_record(
                log_dir,
                {
                    **terminal_record(record, "lock_skipped", returncode=0),
                    "lock": lock_id,
                },
            )
            return 0
        returncode = subprocess.run(
            ["timeout", "-k", "60s", spec.timeout, *argv],
            cwd=CURRENT,
            env=env,
            check=False,
        ).returncode
        append_launcher_record(
            log_dir, terminal_record(record, "exit", returncode=returncode)
        )
        return returncode


if __name__ == "__main__":
    raise SystemExit(main())
