#!/usr/bin/env python3
"""Host timer schedule table for production pwc-cron jobs.

This table is the single source of truth for the generated systemd units in
deploy/systemd/cron/.  Schedules preserve the minute offsets previously used
by the GitHub Actions ``schedule:`` triggers so that load stays staggered and
producer chains keep their relative ordering.  Regenerate the units with
``python deploy/generate_cron_units.py`` after editing this table.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimerSpec:
    """One systemd timer/service pair driving one pwc-cron invocation."""

    job: str
    on_calendar: tuple[str, ...]
    description: str
    # Extra pwc-cron arguments after the job name.
    args: tuple[str, ...] = ()
    # Multiple sequential pwc-cron invocations (overrides job+args when set);
    # each entry is a full argument vector passed to pwc-cron-throttled.
    commands: tuple[tuple[str, ...], ...] = ()
    # systemd After= orderings onto other generated cron services, by unit
    # base name.  A queued start job waits while the named service is still
    # activating, so never order a job after a long-running hourly service
    # (update_github_stars runs close to its full interval and re-fires
    # immediately under Persistent=, which starved the trending chain for a day
    # on 2026-09-16/17).  Order only after short producers.
    after: tuple[str, ...] = ()
    # Unit base name override; defaults to pwc-cron-<job with - for _>.
    unit_name: str = ""

    @property
    def unit(self) -> str:
        return self.unit_name or "pwc-cron-" + self.job.replace("_", "-")

    @property
    def invocations(self) -> tuple[tuple[str, ...], ...]:
        if self.commands:
            return self.commands
        return ((self.job, *self.args),)


TIMERS: tuple[TimerSpec, ...] = (
    TimerSpec(
        job="send_research_digests",
        on_calendar=("*-*-* *:00:00",),
        description="Send Monday 08:00 UTC research digests and retry within 23 hours",
    ),
    TimerSpec(
        job="create_eval_verification_issues",
        on_calendar=("*-*-* *:52:00",),
        description="Request verification of settled paper-native evaluations on GitHub",
    ),
    TimerSpec(
        job="run_chat_synthetic_probe",
        on_calendar=("*-*-* *:*:00",),
        description="Evaluate due and triggered production synthetic chat probes",
    ),
    # Trending pipeline: stars (:00) -> task trending (:15) -> paper trending
    # (:45, also consumes HF artifacts from :30).  Hot trending runs its own
    # 15-minute lane.
    TimerSpec(
        job="update_github_stars",
        on_calendar=("*-*-* *:00:00",),
        description="Update GitHub repository star counts hourly",
    ),
    TimerSpec(
        job="update_hot_github_trending",
        on_calendar=("*-*-* *:00/15:00",),
        description="Update hot GitHub trending snapshots every 15 minutes",
    ),
    TimerSpec(
        job="calculate_trending_scores",
        on_calendar=("*-*-* *:15:00",),
        description="Calculate task trending scores hourly",
    ),
    TimerSpec(
        job="update_citations",
        on_calendar=("*-*-* *:30:00",),
        description="Update citation counts hourly",
    ),
    TimerSpec(
        job="update_hf_artifacts",
        on_calendar=("*-*-* *:30:00",),
        description="Update Hugging Face artifact links hourly",
    ),
    TimerSpec(
        job="calculate_paper_trending_scores",
        on_calendar=("*-*-* *:45:00",),
        description="Calculate paper trending scores hourly",
        after=(
            "pwc-cron-update-hf-artifacts",
            "pwc-cron-calculate-trending-scores",
        ),
    ),
    # Hugging Face import and consumers.
    TimerSpec(
        job="import_hf_daily_papers",
        on_calendar=("*-*-* *:00:00",),
        description="Import Hugging Face daily papers hourly",
    ),
    TimerSpec(
        job="refresh_paper_embeddings",
        on_calendar=("*-*-* *:15:00",),
        description="Refresh paper embeddings hourly",
        after=("pwc-cron-import-hf-daily-papers",),
    ),
    TimerSpec(
        job="paper_markdown_backfill",
        on_calendar=("*-*-* *:17:00",),
        description="Reconcile paper Markdown live and full backfill lanes hourly",
        commands=(
            ("paper_markdown_backfill", "--execute", "--confirm"),
            ("paper_markdown_backfill", "--full", "--execute", "--confirm"),
        ),
        after=("pwc-cron-import-hf-daily-papers",),
    ),
    # Fresh lane: papers indexed in the last 24 hours get layout OCR on two
    # dedicated small-shard slots within minutes, under their own lane lock.
    TimerSpec(
        job="paper_markdown_backfill",
        unit_name="pwc-cron-paper-markdown-fresh",
        on_calendar=("*-*-* *:00/5:00",),
        description="Dispatch layout OCR for papers indexed in the last day",
        args=("--lane", "fresh", "--execute", "--confirm"),
    ),
    TimerSpec(
        job="enqueue_hf_daily_paper_curation",
        on_calendar=("*-*-* *:27:00",),
        description="Enqueue Hugging Face daily paper curation hourly",
        after=("pwc-cron-import-hf-daily-papers",),
    ),
    TimerSpec(
        job="enqueue_hf_trending_model_curation",
        on_calendar=("*-*-* *:42:00",),
        description="Enqueue Hugging Face trending model curation hourly",
    ),
    TimerSpec(
        job="enqueue_benchmark_gap_review",
        on_calendar=("*-*-* 06:35:00",),
        description="Review reported benchmark gaps and queue benchmark creation daily",
    ),
    TimerSpec(
        job="scan_model_releases",
        on_calendar=("*-*-* 01/3:48:00",),
        description="Scan official lab news for unindexed model releases every three hours",
    ),
    TimerSpec(
        job="sweep_conference_deadlines",
        on_calendar=("Sun *-*-* 02:35:00",),
        description="Research AI conference deadlines off-box weekly",
    ),
    TimerSpec(
        job="link_google_scholar_profiles",
        on_calendar=("Wed *-*-* 05:20:00",),
        description="Link authors to Scholar profiles confirmed by their papers weekly",
    ),
    TimerSpec(
        job="refresh_conference_deadlines",
        on_calendar=("*-*-* 07:40:00", "*-*-* 19:40:00"),
        description="Collect deadline research and check imminent deadlines daily",
    ),
    TimerSpec(
        job="discover_x_threads",
        on_calendar=("*-*-* 08,20:22:00",),
        description="Discover author X threads for trending papers twice daily",
    ),
    TimerSpec(
        job="post_trending_paper_to_x",
        on_calendar=("*-*-* 00/4:13:00",),
        description="Post a trending paper to the Papers with Code X account every four hours",
    ),
    TimerSpec(
        job="post_x_insight",
        on_calendar=("*-*-* 09,17:43:00",),
        description="Post a SOTA, trend, or roundup insight to X twice daily",
    ),
    TimerSpec(
        job="link_abstract_mentions",
        on_calendar=("*-*-* *:51:00",),
        description="Link catalog names in new and changed paper abstracts",
    ),
    TimerSpec(
        job="rescan_abstract_mentions",
        on_calendar=("*-*-* 03:21:00",),
        description="Re-link every abstract after catalog changes",
    ),
    TimerSpec(
        job="judge_research_topics",
        on_calendar=("*-*-* *:54:00",),
        description="Judge new and changed papers against followed research topics",
    ),
    TimerSpec(
        job="backfill_research_topics",
        on_calendar=("*-*-* *:*:00",),
        description="Backfill newly followed research topics",
    ),
    TimerSpec(
        job="warm_paper_suggested_questions",
        on_calendar=("*-*-* *:33:00",),
        description="Pre-generate suggested questions for the papers visitors see first",
    ),
    # Leaderboard syncs, staggered at their previous workflow minutes.
    TimerSpec(
        job="sync_3d_arena",
        on_calendar=("*-*-* *:05:00",),
        description="Sync 3D Arena leaderboard hourly",
    ),
    TimerSpec(
        job="sync_mmteb_overall",
        on_calendar=("*-*-* *:07:00",),
        description="Sync MMTEB v2 overall leaderboard hourly",
    ),
    TimerSpec(
        job="sync_arc_prize",
        on_calendar=("*-*-* *:10:00",),
        description="Sync ARC Prize leaderboards hourly",
    ),
    TimerSpec(
        job="sync_mmeb_v2",
        on_calendar=("*-*-* *:12:00",),
        description="Sync MMEB-v2 overall leaderboard hourly",
    ),
    TimerSpec(
        job="sync_open_asr",
        on_calendar=("*-*-* *:15:00",),
        description="Sync Open ASR leaderboard hourly",
    ),
    TimerSpec(
        job="sync_open_tts",
        on_calendar=("*-*-* *:18:00",),
        description="Sync Open TTS leaderboards hourly",
    ),
    TimerSpec(
        job="sync_parsebench",
        on_calendar=("*-*-* *:20:00",),
        description="Sync ParseBench leaderboard hourly",
    ),
    TimerSpec(
        job="sync_mmteb_retrieval",
        on_calendar=("*-*-* *:22:00",),
        description="Sync MMTEB v2 retrieval leaderboard hourly",
    ),
    TimerSpec(
        job="sync_deepswe",
        on_calendar=("*-*-* *:25:00",),
        description="Sync DeepSWE leaderboard hourly",
    ),
    TimerSpec(
        job="sync_extractbench",
        on_calendar=("*-*-* *:32:00",),
        description="Sync ExtractBench leaderboard hourly",
    ),
    TimerSpec(
        job="sync_vals_finance_agent",
        on_calendar=("*-*-* *:47:00",),
        description="Sync Vals AI Finance Agent v2 leaderboard hourly",
    ),
    TimerSpec(
        job="sync_surge_chartography",
        on_calendar=("*-*-* *:38:00",),
        description="Sync Surge AI Chartography leaderboard hourly",
    ),
    TimerSpec(
        job="sync_frontiercs_2",
        on_calendar=("*-*-* *:43:00",),
        description="Sync FrontierCS 2 leaderboard hourly",
    ),
    TimerSpec(
        job="sync_vals_index",
        on_calendar=("*-*-* *:03:00",),
        description="Sync Vals Index leaderboard hourly",
    ),
    TimerSpec(
        job="sync_swe_sweep",
        on_calendar=("*-*-* *:08:00",),
        description="Sync SWE-sweep leaderboard hourly",
    ),
    TimerSpec(
        job="sync_vending_bench_2",
        on_calendar=("*-*-* *:13:00",),
        description="Sync Vending-Bench 2 leaderboard hourly",
    ),
    TimerSpec(
        job="sync_blueprint_bench_2",
        on_calendar=("*-*-* *:16:00",),
        description="Sync Blueprint-Bench 2 leaderboard hourly",
    ),
    TimerSpec(
        job="sync_riemann_bench",
        on_calendar=("*-*-* *:23:00",),
        description="Sync Riemann-Bench leaderboard hourly",
    ),
    TimerSpec(
        job="sync_cwe_bench",
        on_calendar=("*-*-* *:34:00",),
        description="Sync CWE-bench leaderboard hourly",
    ),
    TimerSpec(
        job="sync_exploitgym",
        on_calendar=("*-*-* *:46:00",),
        description="Sync ExploitGym leaderboard hourly",
    ),
    TimerSpec(
        job="sync_cybergym",
        on_calendar=("*-*-* *:09:00",),
        description="Sync CyberGym leaderboard hourly",
    ),
    TimerSpec(
        job="sync_patcheval_verified",
        on_calendar=("*-*-* *:21:00",),
        description="Sync PatchEval-Verified leaderboard hourly",
    ),
    TimerSpec(
        job="sync_physics_iq_verified",
        on_calendar=("*-*-* *:28:00",),
        description="Sync Physics-IQ Verified leaderboard hourly",
    ),
    TimerSpec(
        job="sync_artificial_analysis",
        on_calendar=("*-*-* 00/2:35:00",),
        description="Sync Artificial Analysis leaderboards every two hours",
    ),
    TimerSpec(
        job="sync_mmteb_reranking",
        on_calendar=("*-*-* *:37:00",),
        description="Sync MMTEB v2 reranking leaderboard hourly",
    ),
    TimerSpec(
        job="sync_programbench",
        on_calendar=("*-*-* *:40:00",),
        description="Sync ProgramBench leaderboard hourly",
    ),
    TimerSpec(
        job="sync_mmeb_v3",
        on_calendar=("*-*-* *:42:00",),
        description="Sync MMEB-v3 overall leaderboard hourly",
    ),
    TimerSpec(
        job="sync_frontiercode",
        on_calendar=("*-*-* *:45:00",),
        description="Sync FrontierCode leaderboard hourly",
    ),
    TimerSpec(
        job="sync_coarena",
        on_calendar=("*-*-* *:50:00",),
        description="Sync CoArena leaderboard hourly",
    ),
    TimerSpec(
        job="sync_tabarena",
        on_calendar=("*-*-* *:55:00",),
        description="Sync TabArena leaderboard hourly",
    ),
    # Daily jobs.
    TimerSpec(
        job="backfill_method_keywords",
        on_calendar=("*-*-* 01:10:00",),
        description="Backfill method keyword evidence daily",
        args=(
            "--resume",
            "--limit",
            "250000",
            "--max-runtime-seconds",
            "3300",
        ),
    ),
    TimerSpec(
        job="sync_hf_organizations",
        on_calendar=("*-*-* 02:20:00",),
        description="Sync featured Hugging Face organizations daily",
    ),
    TimerSpec(
        job="sync_hf_author_profiles",
        on_calendar=("*-*-* 02:50:00",),
        description="Link authors to their claimed Hugging Face profiles daily",
    ),
    TimerSpec(
        job="export_enrichment_dashboard",
        on_calendar=("*-*-* 03:10:00",),
        description="Export the enrichment dashboard snapshot daily",
    ),
    TimerSpec(
        job="link_openalex_organizations",
        on_calendar=("*-*-* 03:20:00",),
        description="Link recent papers to OpenAlex affiliation organizations daily",
    ),
    TimerSpec(
        job="calculate_organization_trending_scores",
        on_calendar=("*-*-* 03:40:00",),
        description="Calculate organization trending scores daily",
        after=(
            "pwc-cron-sync-hf-organizations",
            "pwc-cron-calculate-paper-trending-scores",
        ),
    ),
    TimerSpec(
        job="mirror_thumbnails_to_disk",
        on_calendar=("*-*-* 05:00:00",),
        description="Mirror thumbnails to VPS disk daily",
        after=("pwc-cron-preload-thumbnails-recent",),
    ),
    # Follow the hourly paper import so trend coverage does not stay stale.
    TimerSpec(
        job="backfill_method_references",
        on_calendar=("*-*-* *:15:00",),
        description="Backfill method reference evidence hourly",
        after=("pwc-cron-import-hf-daily-papers",),
        args=(
            "--provider",
            "openalex",
            "--resume",
            "--retry-failures",
            "--limit",
            "10000",
            "--max-runtime-seconds",
            "19800",
        ),
    ),
    # Weekly linkers (Sunday, method linker before task keywords).
    TimerSpec(
        job="link_methods_by_references",
        on_calendar=("Sun *-*-* 04:00:00",),
        description="Link methods by paper references weekly",
    ),
    TimerSpec(
        job="link_papers_by_task_keywords",
        on_calendar=("Sun *-*-* 05:00:00",),
        description="Link papers by task keywords weekly",
        after=("pwc-cron-link-methods-by-references",),
    ),
    # Thumbnail preload lanes (five schedules with distinct arguments).  Each
    # --priority lane has its own launcher lock, so a long lane no longer
    # silently skips the others.  --max-runtime-seconds keeps every lane well
    # inside the 2h launcher timeout; missing-only lanes resume a backlog on
    # the next run instead of being killed mid-sweep (method-top, 2026-10-17).
    TimerSpec(
        job="preload_thumbnails",
        unit_name="pwc-cron-preload-thumbnails-visible",
        on_calendar=("*-*-* 00/3:00:00",),
        description="Preload thumbnails for visible candidate sets every three hours",
        args=(
            "--priority",
            "visible",
            "--citation-top",
            "1000",
            "--trending-top",
            "500",
            "--newest-top",
            "300",
            "--per-task",
            "20",
            "--per-method",
            "20",
            "--limit",
            "10000",
            "--missing-only",
            "--trust-local-cache",
            "--max-runtime-seconds",
            "6000",
        ),
    ),
    TimerSpec(
        job="preload_thumbnails",
        unit_name="pwc-cron-preload-thumbnails-task-top",
        on_calendar=("*-*-* 04:00:00",),
        description="Preload thumbnails for top task-page papers daily",
        args=(
            "--priority",
            "task-top",
            "--per-task",
            "50",
            "--missing-only",
            "--trust-local-cache",
            "--max-runtime-seconds",
            "6000",
        ),
    ),
    TimerSpec(
        job="preload_thumbnails",
        unit_name="pwc-cron-preload-thumbnails-method-top",
        on_calendar=("*-*-* 04:15:00",),
        description="Preload thumbnails for top method-page papers daily",
        args=(
            "--priority",
            "method-top",
            "--per-method",
            "50",
            "--missing-only",
            "--trust-local-cache",
            "--max-runtime-seconds",
            "6000",
        ),
    ),
    TimerSpec(
        job="preload_thumbnails",
        unit_name="pwc-cron-preload-thumbnails-recent",
        on_calendar=("*-*-* 04:30:00",),
        description="Preload thumbnails for recent papers daily",
        args=(
            "--priority",
            "recent",
            "--recent-days",
            "30",
            "--limit",
            "500",
            "--max-runtime-seconds",
            "6000",
        ),
        after=("pwc-cron-import-hf-daily-papers",),
    ),
    TimerSpec(
        job="preload_thumbnails",
        unit_name="pwc-cron-preload-thumbnails-external",
        on_calendar=("*-*-* 04:45:00",),
        description="Preload thumbnails for external resources daily",
        # Newest-first; ~2,400 captures fit the 2h launcher timeout, so bound
        # the sweep instead of letting a large backlog kill the unit.
        args=(
            "--priority",
            "external-missing",
            "--limit",
            "2000",
            "--request-delay-seconds",
            "2",
            "--max-failures",
            "-1",
            "--max-runtime-seconds",
            "6000",
        ),
    ),
)
