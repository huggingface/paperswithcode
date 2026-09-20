"""Production CRON job registry for the admin health dashboard."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, Sequence, Tuple


@dataclass(frozen=True)
class SchedulePolicy:
    """A deterministic UTC schedule contract, independent of display text."""

    kind: Literal["fixed_interval", "daily", "weekly"]
    interval_minutes: Optional[int] = None
    minute_of_day: Optional[int] = None
    weekday: Optional[int] = None

    @classmethod
    def fixed(cls, minutes: int, *, offset_minutes: int = 0) -> "SchedulePolicy":
        return cls(
            "fixed_interval",
            interval_minutes=minutes,
            minute_of_day=offset_minutes,
        )

    @classmethod
    def daily(cls, hour: int, minute: int) -> "SchedulePolicy":
        return cls("daily", minute_of_day=hour * 60 + minute)

    @classmethod
    def weekly(cls, weekday: int, hour: int, minute: int) -> "SchedulePolicy":
        return cls("weekly", minute_of_day=hour * 60 + minute, weekday=weekday)

    def slots(self, now: datetime) -> tuple[datetime, datetime]:
        now = now.astimezone(timezone.utc)
        if self.kind == "fixed_interval":
            interval = timedelta(minutes=int(self.interval_minutes or 1))
            epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
            anchor = epoch + timedelta(minutes=int(self.minute_of_day or 0))
            periods = (now - anchor) // interval
            previous = anchor + periods * interval
            return previous, previous + interval

        minute_of_day = int(self.minute_of_day or 0)
        candidate = now.replace(
            hour=minute_of_day // 60,
            minute=minute_of_day % 60,
            second=0,
            microsecond=0,
        )
        if self.kind == "daily":
            previous = candidate if candidate <= now else candidate - timedelta(days=1)
            return previous, previous + timedelta(days=1)

        days_since = (now.weekday() - int(self.weekday or 0)) % 7
        candidate -= timedelta(days=days_since)
        previous = candidate if candidate <= now else candidate - timedelta(days=7)
        return previous, previous + timedelta(days=7)


@dataclass(frozen=True)
class CronEvidenceContract:
    """Deterministic evidence expected for one declared scheduled job."""

    scheduler: Literal["github_actions", "systemd", "manual"]
    schedule_policies: Tuple[SchedulePolicy, ...]
    accepted_exit_states: Tuple[str, ...]
    accepted_log_states: Tuple[str, ...]
    log_source: Literal["file", "journal", "health_record"]
    lock_expected: bool
    lock_max_age_minutes: int
    durable_data_required: bool
    throughput_policy: Literal["work_required", "no_work_allowed"]
    throughput_source: Literal["work_metrics", "durable_data", "health_record"]
    semantic_source: Literal["output_evaluator", "health_record", "unavailable"]
    semantic_evaluator: str


@dataclass(frozen=True)
class CronJobDefinition:
    id: str
    display_name: str
    category: str
    schedule: str
    script_path: str
    log_name: str
    process_patterns: Tuple[str, ...]
    lock_file: Optional[str]
    expected_runtime_minutes: int
    stale_after_minutes: int
    critical: bool
    healthy_no_work_allowed: bool
    db_freshness_query: Optional[str] = None
    workflow_file: Optional[str] = None
    workflow_jobs: Tuple[str, ...] = ()
    workflow_freshness_required: bool = True
    log_directory: Optional[str] = None
    dashboard_group: str = "operations"
    scheduler: Literal["github_actions", "systemd", "manual"] = "github_actions"
    schedule_policies: Tuple[SchedulePolicy, ...] = ()
    schedule_grace_minutes: int = 20
    systemd_timer: Optional[str] = None
    systemd_service: Optional[str] = None
    # Additional timer/service pairs when one duty runs under several units
    # (for example the five preload_thumbnails lanes).
    systemd_extra_units: Tuple[Tuple[str, str], ...] = ()
    output_evaluator: Optional[str] = None
    work_metrics_provider: Optional[
        Literal[
            "paper_markdown_monitor",
            "chat_monitor",
            "chat_synthetic",
            "submission_review",
            "autonomous_cron",
        ]
    ] = None
    db_metrics_provider: Optional[Literal["thumbnail_cache"]] = None
    dependency_job_id: Optional[str] = None
    enablement_settings: Tuple[str, ...] = ()

    @property
    def systemd_unit_pairs(self) -> Tuple[Tuple[str, str], ...]:
        """All (timer, service) pairs owning this duty's execution evidence."""

        pairs: Tuple[Tuple[str, str], ...] = ()
        if self.systemd_timer and self.systemd_service:
            pairs = ((self.systemd_timer, self.systemd_service),)
        return pairs + self.systemd_extra_units

    @property
    def evidence_contract(self) -> CronEvidenceContract:
        """Return the seven-plane contract used by deterministic probes."""

        evaluator = self.output_evaluator or "generic"
        health_record = evaluator in {
            "autonomous_cron_operator",
            "chat_alert_monitor",
            "submission_review",
        }
        return CronEvidenceContract(
            scheduler=self.scheduler,
            schedule_policies=self.schedule_policies,
            accepted_exit_states=("success", "success_no_work"),
            accepted_log_states=("success", "success_no_work", "running"),
            log_source=(
                "health_record"
                if health_record
                else "journal"
                if self.scheduler == "systemd"
                else "file"
            ),
            lock_expected=self.lock_file is not None,
            lock_max_age_minutes=self.expected_runtime_minutes,
            durable_data_required=self.db_freshness_query is not None,
            throughput_policy=(
                "no_work_allowed" if self.healthy_no_work_allowed else "work_required"
            ),
            throughput_source=(
                "health_record"
                if health_record
                else "durable_data"
                if self.db_freshness_query
                else "work_metrics"
            ),
            semantic_source=(
                "health_record"
                if health_record
                else "output_evaluator"
                if evaluator != "generic"
                else "unavailable"
            ),
            semantic_evaluator=evaluator,
        )


CRON_JOBS: Tuple[CronJobDefinition, ...] = (
    CronJobDefinition(
        id="paper_markdown_backfill",
        display_name="Paper Markdown Backfill",
        category="hourly",
        schedule="17 * * * * (live and full backfill reconciliation)",
        script_path="hourly/backfill_paper_markdown.py",
        log_name="paper_markdown_backfill",
        process_patterns=("backfill_paper_markdown",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/paper_markdown_backfill.lock"
        ),
        expected_runtime_minutes=45,
        stale_after_minutes=150,
        critical=True,
        healthy_no_work_allowed=True,
        workflow_file="cron-paper-markdown.yml",
        workflow_jobs=("run",),
        work_metrics_provider="paper_markdown_monitor",
    ),
    CronJobDefinition(
        id="update_hot_github_trending",
        display_name="Update Hot GitHub Trending",
        category="hourly",
        schedule="*/15 * * * * (every 15 minutes)",
        script_path="hourly/update_hot_github_trending.py",
        log_name="update_hot_github_trending",
        process_patterns=("update_hot_github_trending",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "update_hot_github_trending.lock"
        ),
        expected_runtime_minutes=12,
        stale_after_minutes=45,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            WITH hot_repositories AS (
                SELECT DISTINCT r.id, r.created_at AS repository_created_at
                FROM repositories r
                JOIN paper_repositories pr
                  ON pr.repository_id = r.id
                 AND pr.is_official = TRUE
                JOIN papers p
                  ON p.id = pr.paper_id
                 AND p.is_latest_version = TRUE
                WHERE p.date_published >= now() - INTERVAL '30 days'
                  AND COALESCE(r.owner, '') != ''
                  AND COALESCE(r.name, '') != ''
            ),
            history AS (
                SELECT
                    hr.id,
                    hr.repository_created_at,
                    count(rsh.id) AS snapshot_count,
                    min(rsh.snapshot_at) AS first_snapshot_at,
                    max(rsh.snapshot_at) AS last_snapshot_at
                FROM hot_repositories hr
                LEFT JOIN repository_star_history rsh
                  ON rsh.repository_id = hr.id
                GROUP BY hr.id, hr.repository_created_at
            ),
            stale_papers AS (
                SELECT count(DISTINCT p.id) AS count
                FROM papers p
                JOIN paper_repositories pr
                  ON pr.paper_id = p.id
                 AND pr.is_official = TRUE
                JOIN hot_repositories hr ON hr.id = pr.repository_id
                JOIN repositories r ON r.id = hr.id
                WHERE p.is_latest_version = TRUE
                  AND p.date_published >= CURRENT_DATE - INTERVAL '365 days'
                  AND r.trending_score > 0
                  AND (
                    p.trending_score IS NULL
                    OR p.trending_score_updated_at < r.trending_score_updated_at
                  )
            )
            SELECT
                max(last_snapshot_at) AS last_write,
                count(*) AS hot_repository_count,
                count(*) FILTER (
                  WHERE last_snapshot_at > now() - interval '30 minutes'
                ) AS recent_writes,
                count(*) FILTER (
                  WHERE snapshot_count = 1
                    AND first_snapshot_at < now() - interval '30 minutes'
                ) AS one_snapshot_over_30m,
                (SELECT count FROM stale_papers) AS stale_paper_scores,
                COALESCE(
                  EXTRACT(EPOCH FROM (
                    now() - min(
                      COALESCE(last_snapshot_at, repository_created_at)
                    )
                      FILTER (
                        WHERE COALESCE(last_snapshot_at, repository_created_at)
                              < now() - interval '15 minutes'
                      )
                  )) / 60,
                  0
                )::bigint AS oldest_eligible_wait_minutes
            FROM history
        """,
        workflow_file="cron-update-hot-github-trending.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="update_github_stars",
        display_name="Update GitHub Stars",
        category="hourly",
        schedule="0 * * * * (hourly)",
        script_path="hourly/update_github_stars.py",
        log_name="github_stars_cron",
        process_patterns=("update_github_stars", "github_stars"),
        lock_file="/var/lib/paperswithcode/production/cron-locks/update_github_stars.lock",
        expected_runtime_minutes=55,
        stale_after_minutes=120,
        critical=True,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(num_stars_updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE num_stars_updated_at > now() - interval '6 hours'
                   ) AS recent_writes
            FROM repositories
            WHERE num_stars_updated_at IS NOT NULL
        """,
        workflow_file="cron-update-github-stars.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="update_citations",
        display_name="Update Citations",
        category="hourly",
        schedule="30 * * * * (hourly)",
        script_path="hourly/update_citations.py",
        log_name="update_citations_hourly",
        process_patterns=("update_citations",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/update_citations.lock",
        expected_runtime_minutes=170,
        stale_after_minutes=120,
        critical=True,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(citation_updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE citation_updated_at > now() - interval '6 hours'
                   ) AS recent_writes
            FROM papers
        """,
        workflow_file="cron-update-citations.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="extract_urls",
        display_name="Extract URLs",
        category="manual",
        schedule="paused (manual dispatch only; hourly schedule disabled)",
        script_path="cron-extract-urls.yml",
        log_name="extract_urls_hourly",
        process_patterns=("url_extraction_agent.database",),
        lock_file=None,
        expected_runtime_minutes=110,
        stale_after_minutes=120,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE urls_extracted = true
                       AND updated_at > now() - interval '24 hours'
                   ) AS recent_writes
            FROM papers
        """,
        workflow_file="cron-extract-urls.yml",
        workflow_jobs=("select", "discover", "persist"),
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="calculate_trending_scores",
        display_name="Calculate Repo Trending Scores",
        category="hourly",
        schedule="15 * * * * (hourly)",
        script_path="hourly/calculate_trending_scores.py",
        log_name="calculate_trending_scores",
        log_directory=("/var/lib/paperswithcode/production/trending-cron-logs"),
        process_patterns=("calculate_trending_scores",),
        lock_file=(
            "/var/lib/paperswithcode/production/trending-cron-locks/"
            "calculate_trending_scores.lock"
        ),
        expected_runtime_minutes=50,
        stale_after_minutes=120,
        critical=True,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(trending_score_updated_at) AS last_write,
                   count(*) AS eligible_population,
                   count(*) FILTER (
                     WHERE trending_score_updated_at > now() - interval '6 hours'
                   ) AS recent_writes,
                   count(*) FILTER (
                     WHERE trending_score > 0
                       AND trending_score_updated_at > now() - interval '24 hours'
                   ) AS fresh_positive_scores
            FROM repositories
        """,
        workflow_file="cron-calculate-trending-scores.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="calculate_paper_trending_scores",
        display_name="Calculate Paper Trending Scores",
        category="hourly",
        schedule="45 * * * * (hourly)",
        script_path="hourly/calculate_paper_trending_scores.py",
        log_name="calculate_paper_trending_scores",
        log_directory=("/var/lib/paperswithcode/production/trending-cron-logs"),
        process_patterns=("calculate_paper_trending_scores",),
        lock_file=(
            "/var/lib/paperswithcode/production/trending-cron-locks/"
            "calculate_paper_trending_scores.lock"
        ),
        expected_runtime_minutes=50,
        stale_after_minutes=120,
        critical=True,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(trending_score_updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE is_latest_version
                       AND date_published >= CURRENT_DATE - interval '365 days'
                   ) AS eligible_population,
                   count(*) FILTER (
                     WHERE trending_score_updated_at > now() - interval '6 hours'
                   ) AS recent_writes,
                   count(*) FILTER (
                     WHERE github_trending_component > 0
                       AND trending_score_updated_at > now() - interval '24 hours'
                   ) AS fresh_github_component_scores
            FROM papers
        """,
        workflow_file="cron-calculate-paper-trending-scores.yml",
        workflow_jobs=("run",),
        dependency_job_id="calculate_trending_scores",
    ),
    CronJobDefinition(
        id="update_hf_artifacts",
        display_name="Update Hugging Face Artifacts",
        category="hourly",
        schedule="30 * * * * (hourly)",
        script_path="hourly/update_hf_artifacts.py",
        log_name="update_hf_artifacts",
        process_patterns=("update_hf_artifacts",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/update_hf_artifacts.lock",
        expected_runtime_minutes=50,
        stale_after_minutes=120,
        critical=True,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT GREATEST(
                     COALESCE((SELECT max(fetched_at) FROM hf_artifacts), '-infinity'::timestamp),
                     COALESCE((SELECT max(hf_artifacts_scanned_at) FROM papers), '-infinity'::timestamp),
                     COALESCE((SELECT max(created_at) FROM paper_hf_artifacts), '-infinity'::timestamp)
                   ) AS last_write,
                   (
                     SELECT count(*)
                     FROM hf_artifacts
                     WHERE fetched_at > now() - interval '6 hours'
                   ) AS recent_writes,
                   (
                     SELECT count(*)
                     FROM papers
                     WHERE hf_artifacts_scanned_at > now() - interval '6 hours'
                   ) AS papers_scanned,
                   (
                     SELECT count(*)
                     FROM paper_hf_artifacts
                     WHERE created_at > now() - interval '24 hours'
                   ) AS links_created
        """,
        workflow_file="cron-update-hf-artifacts.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="sync_3d_arena",
        display_name="Sync 3D Arena",
        category="hourly",
        schedule="5 * * * * (hourly)",
        script_path="hourly/sync_3d_arena.py",
        log_name="sync_3d_arena",
        process_patterns=("scripts.hourly.sync_3d_arena",),
        lock_file=("/var/lib/paperswithcode/production/cron-locks/sync_3d_arena.lock"),
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(e.updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.updated_at > now() - interval '2 hours 30 minutes'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations
            FROM evaluations e
            JOIN datasets d ON d.id = e.dataset_id
            WHERE d.slug = '3d-arena-iso3d-living'
              AND e.best_metric = 'Elo (live, external)'
              AND e.external_source_url =
                  'https://huggingface.co/spaces/3d-arena/3d-arena'
        """,
        workflow_file="cron-sync-3d-arena.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_tabarena",
        display_name="Sync TabArena",
        category="hourly",
        schedule="55 * * * * (hourly)",
        script_path="hourly/sync_tabarena.py",
        log_name="sync_tabarena",
        process_patterns=("scripts.hourly.sync_tabarena",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/sync_tabarena.lock",
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(e.updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.updated_at > now() - interval '2 hours 30 minutes'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations
            FROM evaluations e
            JOIN datasets d ON d.id = e.dataset_id
            WHERE d.slug = 'tabarena-v0-1'
              AND e.best_metric = 'Elo'
              AND e.external_source_url =
                  'https://huggingface.co/spaces/TabArena/leaderboard'
        """,
        workflow_file="cron-sync-tabarena.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_open_asr",
        display_name="Sync Open ASR Leaderboard",
        category="hourly",
        schedule="15 * * * * (hourly)",
        script_path="hourly/sync_open_asr.py",
        log_name="sync_open_asr",
        process_patterns=("scripts.hourly.sync_open_asr",),
        lock_file=("/var/lib/paperswithcode/production/cron-locks/sync_open_asr.lock"),
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(e.updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.updated_at > now() - interval '2 hours 30 minutes'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations
            FROM evaluations e
            JOIN datasets d ON d.id = e.dataset_id
            WHERE d.slug = 'open-asr-leaderboard'
              AND e.best_metric = 'WER'
              AND e.external_source_url =
                  'https://huggingface.co/spaces/hf-audio/open_asr_leaderboard'
              AND e.methodology LIKE
                  'Managed by the Papers with Code Open ASR live sync.%'
        """,
        workflow_file="cron-sync-open-asr.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_open_tts",
        display_name="Sync Open TTS Leaderboards",
        category="hourly",
        schedule="18 * * * * (hourly)",
        script_path="hourly/sync_open_tts.py",
        log_name="sync_open_tts",
        process_patterns=("scripts.hourly.sync_open_tts",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/sync_open_tts.lock",
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(e.updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.updated_at > now() - interval '2 hours 30 minutes'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations,
                   count(DISTINCT d.slug) AS matched_benchmarks
            FROM evaluations e
            JOIN datasets d ON d.id = e.dataset_id
            WHERE d.slug IN (
                'open-tts-leaderboard',
                'open-tts-leaderboard-all-languages'
            )
              AND e.best_metric = 'WER'
              AND e.external_source_url =
                  'https://huggingface.co/spaces/hf-audio/open_tts_leaderboard'
              AND e.methodology LIKE
                  'Managed by the Papers with Code Open TTS live sync.%'
        """,
        workflow_file="cron-sync-open-tts.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_mmteb_overall",
        display_name="Sync MMTEB v2 Overall",
        category="hourly",
        schedule="7 * * * * (hourly)",
        script_path="hourly/sync_mmteb.py",
        log_name="sync_mmteb_overall",
        process_patterns=("scripts.hourly.sync_mmteb overall",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/sync_mmteb_overall.lock"
        ),
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(e.updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.updated_at > now() - interval '2 hours 30 minutes'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations
            FROM evaluations e
            JOIN tasks t ON t.id = e.task_id
            JOIN datasets d ON d.id = e.dataset_id
            WHERE t.slug = 'embedding-models'
              AND d.slug = 'mmteb-v2'
              AND e.best_metric = 'MMTEB Score'
              AND e.methodology LIKE
                  'Managed by the Papers with Code MMTEB v2 live sync.%'
        """,
        workflow_file="cron-sync-mmteb-overall.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_mmteb_retrieval",
        display_name="Sync MMTEB v2 Retrieval",
        category="hourly",
        schedule="22 * * * * (hourly)",
        script_path="hourly/sync_mmteb.py",
        log_name="sync_mmteb_retrieval",
        process_patterns=("scripts.hourly.sync_mmteb retrieval",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/sync_mmteb_retrieval.lock"
        ),
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(e.updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.updated_at > now() - interval '2 hours 30 minutes'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations
            FROM evaluations e
            JOIN tasks t ON t.id = e.task_id
            JOIN datasets d ON d.id = e.dataset_id
            WHERE t.slug = 'retrieval'
              AND d.slug = 'mmteb-v2'
              AND e.best_metric = 'Retrieval'
              AND e.methodology LIKE
                  'Managed by the Papers with Code MMTEB v2 live sync.%'
        """,
        workflow_file="cron-sync-mmteb-retrieval.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_mmteb_reranking",
        display_name="Sync MMTEB v2 Reranking",
        category="hourly",
        schedule="37 * * * * (hourly)",
        script_path="hourly/sync_mmteb.py",
        log_name="sync_mmteb_reranking",
        process_patterns=("scripts.hourly.sync_mmteb reranking",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/sync_mmteb_reranking.lock"
        ),
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(e.updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.updated_at > now() - interval '2 hours 30 minutes'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations
            FROM evaluations e
            JOIN tasks t ON t.id = e.task_id
            JOIN datasets d ON d.id = e.dataset_id
            WHERE t.slug = 'text-reranking'
              AND d.slug = 'mmteb-v2'
              AND e.best_metric = 'Rerank'
              AND e.methodology LIKE
                  'Managed by the Papers with Code MMTEB v2 live sync.%'
        """,
        workflow_file="cron-sync-mmteb-reranking.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_mmeb_v2",
        display_name="Sync MMEB-v2 Overall",
        category="hourly",
        schedule="12 * * * * (hourly)",
        script_path="hourly/sync_mmeb.py",
        log_name="sync_mmeb_v2",
        process_patterns=("scripts.hourly.sync_mmeb v2",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/sync_mmeb_v2.lock",
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(e.updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.updated_at > now() - interval '2 hours 30 minutes'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations
            FROM evaluations e
            JOIN tasks t ON t.id = e.task_id
            JOIN datasets d ON d.id = e.dataset_id
            WHERE t.slug = 'embedding-models'
              AND d.slug = 'mmeb-v2'
              AND e.best_metric = 'MMEB-v2 Score'
              AND e.methodology LIKE
                  'Managed by the Papers with Code MMEB live sync.%'
        """,
        workflow_file="cron-sync-mmeb-v2.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_mmeb_v3",
        display_name="Sync MMEB-v3 Overall",
        category="hourly",
        schedule="42 * * * * (hourly)",
        script_path="hourly/sync_mmeb.py",
        log_name="sync_mmeb_v3",
        process_patterns=("scripts.hourly.sync_mmeb v3",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/sync_mmeb_v3.lock",
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(e.updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.updated_at > now() - interval '2 hours 30 minutes'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations
            FROM evaluations e
            JOIN tasks t ON t.id = e.task_id
            JOIN datasets d ON d.id = e.dataset_id
            WHERE t.slug = 'embedding-models'
              AND d.slug = 'mmeb-v3'
              AND e.best_metric = 'MMEB-v3 Score'
              AND e.methodology LIKE
                  'Managed by the Papers with Code MMEB live sync.%'
        """,
        workflow_file="cron-sync-mmeb-v3.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_deepswe",
        display_name="Sync DeepSWE Leaderboard",
        category="hourly",
        schedule="25 * * * * (hourly)",
        script_path="hourly/sync_deepswe.py",
        log_name="sync_deepswe",
        process_patterns=("scripts.hourly.sync_deepswe",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/sync_deepswe.lock",
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(e.updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.updated_at > now() - interval '2 hours 30 minutes'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations
            FROM evaluations e
            JOIN datasets d ON d.id = e.dataset_id
            WHERE d.slug = 'deepswe'
              AND e.best_metric = 'Pass@1'
              AND e.external_source_url = 'https://deepswe.datacurve.ai/'
              AND e.methodology LIKE
                  'Managed by the Papers with Code DeepSWE live sync.%'
        """,
        workflow_file="cron-sync-deepswe.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_artificial_analysis",
        display_name="Sync Artificial Analysis Leaderboards",
        category="hourly",
        schedule="35 * * * * (hourly)",
        script_path="hourly/sync_artificial_analysis.py",
        log_name="sync_artificial_analysis",
        process_patterns=("scripts.hourly.sync_artificial_analysis",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "sync_artificial_analysis.lock"
        ),
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            WITH managed_evaluations AS (
              SELECT d.slug AS dataset_slug, e.updated_at
              FROM evaluations e
              JOIN datasets d ON d.id = e.dataset_id
              WHERE d.slug IN (
                    'artificial-analysis-intelligence-index',
                    'artificial-analysis-agentic-index',
                    'artificial-analysis-provider-voice-tts-arena'
                  )
                AND (
                    (
                      e.best_metric = 'Score'
                      AND e.external_source_url LIKE
                          'https://artificialanalysis.ai/models/%'
                      AND e.methodology LIKE
                          'Managed by the Papers with Code Artificial Analysis live sync.%'
                    )
                    OR
                    (
                      e.best_metric = 'Quality Elo'
                      AND e.external_source_url LIKE
                          'https://artificialanalysis.ai/text-to-speech/models/%'
                      AND e.methodology LIKE
                          'Managed by the Papers with Code Artificial Analysis TTS live sync.%'
                    )
                  )
            )
            SELECT max(updated_at) AS last_write,
                   LEAST(
                     count(*) FILTER (
                       WHERE dataset_slug = 'artificial-analysis-intelligence-index'
                         AND updated_at > now() - interval '2 hours 30 minutes'
                     ),
                     count(*) FILTER (
                       WHERE dataset_slug = 'artificial-analysis-agentic-index'
                         AND updated_at > now() - interval '2 hours 30 minutes'
                     ),
                     count(*) FILTER (
                       WHERE dataset_slug =
                         'artificial-analysis-provider-voice-tts-arena'
                         AND updated_at > now() - interval '2 hours 30 minutes'
                     )
                   ) AS recent_writes,
                   LEAST(
                     count(*) FILTER (
                       WHERE dataset_slug = 'artificial-analysis-intelligence-index'
                     ),
                     count(*) FILTER (
                       WHERE dataset_slug = 'artificial-analysis-agentic-index'
                     ),
                     count(*) FILTER (
                       WHERE dataset_slug =
                         'artificial-analysis-provider-voice-tts-arena'
                     )
                   ) AS matched_evaluations
            FROM managed_evaluations
        """,
        workflow_file="cron-sync-artificial-analysis.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_programbench",
        display_name="Sync ProgramBench Leaderboard",
        category="hourly",
        schedule="40 * * * * (hourly)",
        script_path="hourly/sync_programbench.py",
        log_name="sync_programbench",
        process_patterns=("scripts.hourly.sync_programbench",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/sync_programbench.lock"
        ),
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(e.updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.updated_at > now() - interval '2 hours 30 minutes'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations
            FROM evaluations e
            JOIN datasets d ON d.id = e.dataset_id
            WHERE d.slug = 'programbench'
              AND e.best_metric = 'Resolved'
              AND e.external_source_url LIKE 'https://programbench.com/run/%'
              AND e.methodology LIKE
                  'Managed by the Papers with Code ProgramBench live sync.%'
        """,
        workflow_file="cron-sync-programbench.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_parsebench",
        display_name="Sync ParseBench Leaderboard",
        category="hourly",
        schedule="20 * * * * (hourly)",
        script_path="hourly/sync_parsebench.py",
        log_name="sync_parsebench",
        process_patterns=("scripts.hourly.sync_parsebench",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/sync_parsebench.lock"
        ),
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(e.updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.updated_at > now() - interval '2 hours 30 minutes'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations
            FROM evaluations e
            JOIN datasets d ON d.id = e.dataset_id
            WHERE d.slug = 'parsebench'
              AND e.best_metric = 'Overall (ParseBench)'
              AND e.methodology LIKE
                  'Managed by the Papers with Code ParseBench live sync.%'
        """,
        workflow_file="cron-sync-parsebench.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_frontiercode",
        display_name="Sync FrontierCode Leaderboard",
        category="hourly",
        schedule="45 * * * * (hourly)",
        script_path="hourly/sync_frontiercode.py",
        log_name="sync_frontiercode",
        process_patterns=("scripts.hourly.sync_frontiercode",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/sync_frontiercode.lock"
        ),
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(e.updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.updated_at > now() - interval '2 hours 30 minutes'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations
            FROM evaluations e
            JOIN datasets d ON d.id = e.dataset_id
            WHERE d.slug IN ('frontiercode-main', 'frontiercode-extended')
              AND e.best_metric = 'Score'
              AND e.external_source_url = 'https://cognition.com/frontiercode'
              AND e.methodology LIKE
                  'Managed by the Papers with Code FrontierCode live sync.%'
        """,
        workflow_file="cron-sync-frontiercode.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_coarena",
        display_name="Sync CoArena Leaderboard",
        category="hourly",
        schedule="50 * * * * (hourly)",
        script_path="hourly/sync_coarena.py",
        log_name="sync_coarena",
        process_patterns=("scripts.hourly.sync_coarena",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/sync_coarena.lock",
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(e.updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.updated_at > now() - interval '2 hours 30 minutes'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations
            FROM evaluations e
            JOIN datasets d ON d.id = e.dataset_id
            WHERE d.slug = 'coarena'
              AND e.best_metric = 'Elo (live, external)'
              AND e.external_source_url = 'https://coarena.ai/leaderboard'
              AND e.methodology LIKE
                  'Managed by the Papers with Code CoArena live sync.%'
        """,
        workflow_file="cron-sync-coarena.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_arc_prize",
        display_name="Sync ARC Prize Leaderboards",
        category="hourly",
        schedule="10 * * * * (hourly)",
        script_path="hourly/sync_arc_prize.py",
        log_name="sync_arc_prize",
        process_patterns=("scripts.hourly.sync_arc_prize",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/sync_arc_prize.lock",
        expected_runtime_minutes=5,
        stale_after_minutes=150,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(e.updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.updated_at > now() - interval '2 hours 30 minutes'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations
            FROM evaluations e
            JOIN datasets d ON d.id = e.dataset_id
            WHERE d.slug IN ('arc-agi', 'arc-agi-2', 'arc-agi-3')
              AND e.methodology LIKE
                  'Managed by the Papers with Code ARC Prize live sync.%'
        """,
        workflow_file="cron-sync-arc-prize.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="import_hf_daily_papers",
        display_name="Import HF Daily Papers",
        category="daily",
        schedule="0 * * * * (hourly)",
        script_path="daily/import_hf_daily_papers.py",
        log_name="import_hf_daily_papers",
        process_patterns=("import_hf_daily_papers",),
        lock_file=None,
        expected_runtime_minutes=110,
        stale_after_minutes=180,
        critical=True,
        healthy_no_work_allowed=True,
        db_freshness_query=None,
        workflow_file="cron-import-hf-daily-papers.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="create_eval_verification_issues",
        display_name="GitHub Evaluation Verification Outreach",
        category="hourly",
        schedule="52 * * * *",
        script_path="backend/scripts/create_eval_verification_issues.py",
        log_name="create_eval_verification_issues",
        process_patterns=("backend.scripts.create_eval_verification_issues",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/create_eval_verification_issues.lock",
        expected_runtime_minutes=30,
        stale_after_minutes=180,
        critical=False,
        healthy_no_work_allowed=True,
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="enqueue_hf_daily_paper_curation",
        display_name="HF Daily Paper Curation",
        category="daily",
        schedule="27 * * * * (hourly reconciliation)",
        script_path="backend/scripts/enqueue_hf_daily_paper_curation.py",
        log_name="enqueue_hf_daily_paper_curation",
        process_patterns=("enqueue_hf_daily_paper_curation",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "enqueue_hf_daily_paper_curation.lock"
        ),
        expected_runtime_minutes=20,
        stale_after_minutes=180,
        critical=True,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            WITH daily_workflows AS (
                SELECT workflow.*
                FROM paper_curation_workflows AS workflow
                WHERE EXISTS (
                    SELECT 1
                    FROM paper_curation_jobs AS job
                    WHERE job.parent_workflow_id = workflow.id
                      AND job.trigger = 'hf-daily-cron'
                )
            ), workflow_metrics AS (
                SELECT max(updated_at) AS last_write,
                       count(*) FILTER (WHERE status = 'queued') AS queued_workflows,
                       count(*) FILTER (WHERE status = 'running') AS running_workflows,
                       count(*) FILTER (WHERE status = 'deferred') AS deferred_workflows,
                       count(*) FILTER (WHERE status = 'failed') AS failed_workflows,
                       count(*) FILTER (WHERE status = 'partial') AS partial_workflows
                FROM daily_workflows
            ), job_metrics AS (
                SELECT count(*) FILTER (WHERE status = 'queued') AS queued_jobs,
                       count(*) FILTER (WHERE status IN ('dispatching','running')) AS running_jobs,
                       EXTRACT(EPOCH FROM (now() - min(created_at) FILTER (
                           WHERE status = 'queued'))) / 60 AS oldest_queued_age_minutes,
                       EXTRACT(EPOCH FROM (now() - min(
                           COALESCE(started_at, created_at)
                       ) FILTER (WHERE status IN ('dispatching','running')))) / 60
                           AS oldest_running_age_minutes
                FROM paper_curation_jobs
                WHERE trigger = 'hf-daily-cron'
            )
            SELECT workflow_metrics.*,
                   job_metrics.*,
                   state.dispatch_enabled,
                   state.paused_at,
                   state.pause_condition
            FROM workflow_metrics
            CROSS JOIN job_metrics
            LEFT JOIN paper_curation_scheduler_state AS state ON state.id = 1
        """,
        workflow_file="cron-enqueue-hf-daily-paper-curation.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="enqueue_hf_trending_model_curation",
        display_name="HF Trending Model Curation",
        category="hourly",
        schedule="42 * * * * (hourly reconciliation)",
        script_path="backend/scripts/enqueue_hf_trending_model_curation.py",
        log_name="enqueue_hf_trending_model_curation",
        process_patterns=("enqueue_hf_trending_model_curation",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "enqueue_hf_trending_model_curation.lock"
        ),
        expected_runtime_minutes=20,
        stale_after_minutes=180,
        critical=True,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            WITH candidate_metrics AS (
                SELECT max(last_seen_at) AS last_write,
                   count(*) FILTER (WHERE status IN ('discovered','queued','resolving')) AS active,
                   count(*) FILTER (WHERE status = 'resolved') AS resolved,
                   count(*) FILTER (WHERE status = 'failed') AS failed
                FROM trending_model_candidates
            ), workflow_metrics AS (
                SELECT count(*) FILTER (WHERE status = 'failed') AS failed_workflows,
                       count(*) FILTER (WHERE status = 'partial') AS partial_workflows
                FROM paper_curation_workflows AS workflow
                WHERE workflow.status IN ('failed', 'partial') AND EXISTS (
                    SELECT 1 FROM paper_curation_jobs AS job
                    WHERE job.parent_workflow_id = workflow.id
                      AND job.trigger = 'hf-trending-cron'
                )
            )
            SELECT candidate_metrics.*, workflow_metrics.*
            FROM candidate_metrics CROSS JOIN workflow_metrics
        """,
        workflow_file="cron-enqueue-hf-trending-model-curation.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="export_enrichment_dashboard",
        display_name="Export Enrichment Dashboard",
        category="daily",
        schedule="10 3 * * * (daily UTC)",
        script_path="backend/scripts/export_enrichment_dashboard.py",
        log_name="export_enrichment_dashboard",
        process_patterns=("export_enrichment_dashboard",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/export_enrichment_dashboard.lock",
        expected_runtime_minutes=10,
        stale_after_minutes=30,
        critical=False,
        healthy_no_work_allowed=False,
        workflow_file="cron-export-enrichment-dashboard.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="sync_hf_organizations",
        display_name="Sync HF Organizations",
        category="daily",
        schedule="20 2 * * * (daily)",
        script_path="daily/sync_hf_organizations.py",
        log_name="sync_hf_organizations",
        process_patterns=("scripts.daily.sync_hf_organizations",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/sync_hf_organizations.lock"
        ),
        expected_runtime_minutes=90,
        stale_after_minutes=1800,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(last_hf_synced_at) AS last_write,
                   count(*) FILTER (
                     WHERE last_hf_synced_at > now() - interval '30 hours'
                   ) AS recent_writes
            FROM organizations
            WHERE is_featured = TRUE
              AND slug IN (
                'microsoft','google','nvidia','anthropic','deepseek-ai','facebook',
                'qwen','black-forest-labs','stabilityai','moonshotai','zai-org',
                'bytedance','bytedance-seed','mistralai','allenai','xai-org',
                'openai','apple','tencent','minimaxai','baidu','sensenova',
                'ultralytics','openbmb'
              )
        """,
        workflow_file="cron-sync-hf-organizations.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="calculate_organization_trending_scores",
        display_name="Calculate Organization Trending Scores",
        category="daily",
        schedule="40 3 * * * (daily)",
        script_path="daily/calculate_organization_trending_scores.py",
        log_name="calculate_organization_trending_scores",
        process_patterns=("scripts.daily.calculate_organization_trending_scores",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "calculate_organization_trending_scores.lock"
        ),
        expected_runtime_minutes=20,
        stale_after_minutes=1800,
        critical=False,
        healthy_no_work_allowed=False,
        db_freshness_query="""
            SELECT max(o.trending_score_updated_at) AS last_write,
                   count(h.organization_id) FILTER (
                     WHERE h.snapshot_date = CURRENT_DATE
                   ) AS recent_writes,
                   count(DISTINCT o.id) AS featured_organizations,
                   count(DISTINCT o.id) FILTER (
                     WHERE h.organization_id IS NULL
                   ) AS missing_today_snapshots
            FROM organizations o
            LEFT JOIN organization_trending_history h
              ON h.organization_id = o.id
             AND h.snapshot_date = CURRENT_DATE
            WHERE o.is_featured = TRUE
              AND o.slug IN (
                'microsoft','google','nvidia','anthropic','deepseek-ai','facebook',
                'qwen','black-forest-labs','stabilityai','moonshotai','zai-org',
                'bytedance','bytedance-seed','mistralai','allenai','xai-org',
                'openai','apple','tencent','minimaxai','baidu','sensenova',
                'ultralytics','openbmb'
              )
        """,
        workflow_file="cron-calculate-organization-trending-scores.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="refresh_paper_embeddings",
        display_name="Refresh Paper Embeddings",
        category="hourly",
        schedule="15 * * * * (hourly)",
        script_path="hourly/refresh_paper_embeddings.py",
        log_name="refresh_paper_embeddings",
        process_patterns=("refresh_paper_embeddings",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/refresh_paper_embeddings.lock",
        expected_runtime_minutes=20,
        stale_after_minutes=120,
        critical=True,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            WITH active_generation AS (
                SELECT id
                FROM paper_embedding_generations
                WHERE status = 'active'
            )
            SELECT max(e.created_at) AS last_write,
                   count(*) FILTER (
                     WHERE e.created_at > now() - interval '6 hours'
                   ) AS recent_writes,
                   (
                     SELECT count(*)
                     FROM papers p
                     CROSS JOIN active_generation g
                     LEFT JOIN paper_embeddings missing
                       ON missing.paper_id = p.id
                      AND missing.generation_id = g.id
                     WHERE p.is_latest_version
                       AND missing.paper_id IS NULL
                   ) AS missing_embeddings,
                   COALESCE((
                     SELECT (run.details ->> 'content_hash_mismatches')::bigint
                     FROM embedding_pipeline_runs AS run
                     CROSS JOIN active_generation AS latest_generation
                     WHERE run.generation_id = latest_generation.id
                       AND run.kind = 'import'
                       AND run.status = 'complete'
                     ORDER BY run.completed_at DESC NULLS LAST
                     LIMIT 1
                   ), 0) AS content_hash_mismatches
            FROM paper_embeddings e
            JOIN active_generation g ON g.id = e.generation_id
        """,
        workflow_file="cron-refresh-paper-embeddings.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="preload_thumbnails",
        display_name="Preload Thumbnails",
        category="daily",
        schedule="0 */3 * * *; daily 04:00–04:45 UTC",
        script_path="daily/preload_thumbnails.py",
        log_name="preload_thumbnails",
        process_patterns=("preload_thumbnails",),
        lock_file=None,
        expected_runtime_minutes=180,
        stale_after_minutes=240,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query=None,
        workflow_file="cron-preload-thumbnails.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="mirror_thumbnails_to_disk",
        display_name="Mirror Thumbnails To Disk",
        category="daily",
        schedule="0 5 * * * (daily)",
        script_path="daily/mirror_thumbnails_to_disk.py",
        log_name="mirror_thumbnails_to_disk",
        process_patterns=("mirror_thumbnails_to_disk",),
        lock_file=None,
        expected_runtime_minutes=120,
        stale_after_minutes=1560,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query=None,
        workflow_file="cron-mirror-thumbnails-to-disk.yml",
        workflow_jobs=("run",),
        db_metrics_provider="thumbnail_cache",
    ),
    CronJobDefinition(
        id="link_methods_by_references",
        display_name="Link Methods By References",
        category="weekly",
        schedule="0 4 * * 0 (Sun 04:00 UTC)",
        script_path="weekly/link_methods_by_references.py",
        log_name="link_methods_by_references_weekly",
        process_patterns=("link_methods_by_references",),
        lock_file=None,
        expected_runtime_minutes=360,
        stale_after_minutes=11520,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(methods_scanned_at) AS last_write,
                   count(*) FILTER (
                     WHERE methods_scanned_at > now() - interval '8 days'
                   ) AS recent_writes
            FROM papers
        """,
        workflow_file="cron-link-methods-by-references.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="backfill_method_keywords",
        display_name="Backfill Method Keywords",
        category="backfill",
        schedule="10 1 * * * (daily 01:10 UTC)",
        script_path="backfill/backfill_method_keywords.py",
        log_name="backfill_method_keywords",
        process_patterns=("backfill_method_keywords",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "backfill_method_keywords.lock"
        ),
        expected_runtime_minutes=60,
        stale_after_minutes=1560,
        critical=False,
        healthy_no_work_allowed=True,
        workflow_file="cron-backfill-method-keywords.yml",
        workflow_jobs=("run",),
        db_freshness_query="""
            WITH current_run AS (
                SELECT keyword_catalog_sha256
                FROM method_keyword_backfill_runs
                ORDER BY started_at DESC NULLS LAST, updated_at DESC
                LIMIT 1
            )
            SELECT max(updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE updated_at > now() - interval '26 hours'
                   ) AS recent_writes,
                   count(*) FILTER (
                     WHERE status = 'running'
                       AND updated_at < now() - interval '26 hours'
                   ) AS stale_running,
                   count(*) FILTER (WHERE status = 'running') AS running_runs,
                   count(*) FILTER (WHERE status = 'failed') AS failed_runs,
                   COALESCE(EXTRACT(EPOCH FROM (
                     now() - min(started_at) FILTER (WHERE status = 'running')
                   )) / 60, 0)::bigint AS blocking_run_age_minutes,
                   COALESCE(EXTRACT(EPOCH FROM (
                     now() - max(updated_at) FILTER (WHERE status = 'running')
                   )) / 60, 0)::bigint AS checkpoint_age_minutes,
                   max(cursor_paper_id) FILTER (WHERE status = 'running') AS resume_cursor
            FROM method_keyword_backfill_runs
            WHERE keyword_catalog_sha256 = (
                SELECT keyword_catalog_sha256 FROM current_run
            )
        """,
    ),
    CronJobDefinition(
        id="backfill_method_references",
        display_name="Backfill Method References",
        category="backfill",
        schedule="15 * * * * (hourly at :15 UTC)",
        script_path="backfill/backfill_method_references.py",
        log_name="backfill_method_references",
        process_patterns=("backfill_method_references",),
        lock_file=None,
        expected_runtime_minutes=330,
        stale_after_minutes=720,
        critical=False,
        healthy_no_work_allowed=True,
        workflow_file="cron-backfill-method-references.yml",
        workflow_jobs=("run",),
        db_freshness_query="""
            WITH frontier AS (
                SELECT min(month_start) AS month_start
                FROM method_reference_backfill_months
                WHERE status != 'complete'
            )
            SELECT max(updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE updated_at > now() - interval '12 hours'
                   ) AS recent_writes,
                   count(*) FILTER (
                     WHERE status = 'running'
                       AND month_start = (SELECT month_start FROM frontier)
                       AND updated_at < now() - interval '7 hours'
                   ) AS stale_running,
                   count(*) FILTER (
                     WHERE status = 'failed'
                       AND month_start = (SELECT month_start FROM frontier)
                   ) AS failed_runs,
                   sum(retryable_failures) FILTER (
                     WHERE month_start = (SELECT month_start FROM frontier)
                   ) AS retryable_failures,
                   count(*) FILTER (
                     WHERE month_start = (SELECT month_start FROM frontier)
                       AND last_error ILIKE '%429%'
                   ) AS provider_429_rows,
                   COALESCE(EXTRACT(EPOCH FROM (
                     now() - min(started_at) FILTER (
                       WHERE status = 'running'
                         AND month_start = (SELECT month_start FROM frontier)
                     )
                   )) / 60, 0)::bigint AS blocking_run_age_minutes,
                   max(cursor_paper_id) FILTER (
                     WHERE status = 'running'
                       AND month_start = (SELECT month_start FROM frontier)
                   ) AS resume_cursor
            FROM method_reference_backfill_months
        """,
    ),
    CronJobDefinition(
        id="link_papers_by_task_keywords",
        display_name="Link Papers By Task Keywords",
        category="weekly",
        schedule="0 5 * * 0 (Sun 05:00 UTC)",
        script_path="weekly/link_papers_by_task_keywords.py",
        log_name="link_papers_by_task_keywords_weekly",
        process_patterns=("link_papers_by_task_keywords",),
        lock_file=None,
        expected_runtime_minutes=360,
        stale_after_minutes=11520,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query=None,
        workflow_file="cron-link-papers-by-task-keywords.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="autonomous_cron_health",
        display_name="Autonomous CRON Strict Snapshot",
        category="systemd",
        schedule="every 15 minutes with bounded jitter (systemd)",
        script_path=".github/workflows/scripts/autonomous_cron_health.py",
        log_name="autonomous_cron_health",
        process_patterns=("autonomous_cron_health.py --mode strict",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/autonomous_cron_health.lock"
        ),
        expected_runtime_minutes=360,
        stale_after_minutes=390,
        critical=True,
        healthy_no_work_allowed=True,
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(15),),
        schedule_grace_minutes=10,
        systemd_timer="autonomous-cron-health.timer",
        systemd_service="autonomous-cron-health.service",
        output_evaluator="autonomous_cron_operator",
        work_metrics_provider="autonomous_cron",
    ),
    CronJobDefinition(
        id="autonomous_cron_audit",
        display_name="Autonomous CRON Daily Audit",
        category="systemd",
        schedule="daily at 02:20 UTC with bounded jitter (systemd)",
        script_path=".github/workflows/scripts/autonomous_cron_health.py",
        log_name="autonomous_cron_audit",
        process_patterns=("autonomous_cron_health.py --mode daily",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/autonomous_cron_audit.lock"
        ),
        expected_runtime_minutes=360,
        stale_after_minutes=1800,
        critical=False,
        healthy_no_work_allowed=True,
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.daily(2, 20),),
        schedule_grace_minutes=45,
        systemd_timer="autonomous-cron-audit.timer",
        systemd_service="autonomous-cron-audit.service",
        output_evaluator="autonomous_cron_operator",
        work_metrics_provider="autonomous_cron",
    ),
    CronJobDefinition(
        id="review_submissions",
        display_name="Autonomous Submission Review",
        category="systemd",
        schedule="hourly with up to 15 minutes randomized delay (systemd)",
        script_path=".github/workflows/scripts/review_submissions.py",
        log_name="review_submissions",
        process_patterns=("review_submissions",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/review_submissions.lock"
        ),
        expected_runtime_minutes=45,
        stale_after_minutes=135,
        critical=True,
        healthy_no_work_allowed=True,
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60),),
        schedule_grace_minutes=20,
        systemd_timer="submission-review.timer",
        systemd_service="submission-review.service",
        output_evaluator="submission_review",
        work_metrics_provider="submission_review",
        enablement_settings=(
            "autonomous_submission_enabled",
            "autonomous_submission_jobs_enabled",
        ),
    ),
    CronJobDefinition(
        id="monitor_chat_operational_alerts",
        display_name="Chat Operational Alert Monitor",
        category="systemd",
        schedule="every minute (systemd)",
        script_path="backend/scripts/monitor_chat_operational_alerts.py",
        log_name="monitor_chat_operational_alerts",
        process_patterns=("monitor_chat_operational_alerts",),
        lock_file=None,
        expected_runtime_minutes=1,
        stale_after_minutes=5,
        critical=False,
        healthy_no_work_allowed=True,
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(1),),
        schedule_grace_minutes=3,
        systemd_timer="pwc-chat-alert-monitor.timer",
        systemd_service="pwc-chat-alert-monitor.service",
        output_evaluator="chat_alert_monitor",
        work_metrics_provider="chat_monitor",
    ),
    CronJobDefinition(
        id="run_chat_synthetic_probe",
        display_name="Chat Synthetic Reliability Probe",
        category="systemd",
        schedule="every minute with an internal four-hour gate (systemd)",
        script_path="backend/scripts/run_chat_synthetic_probe.py",
        log_name="run_chat_synthetic_probe",
        process_patterns=("run_chat_synthetic_probe",),
        lock_file=None,
        expected_runtime_minutes=6,
        stale_after_minutes=10,
        critical=False,
        healthy_no_work_allowed=True,
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(1),),
        schedule_grace_minutes=3,
        systemd_timer="pwc-cron-run-chat-synthetic-probe.timer",
        systemd_service="pwc-cron-run-chat-synthetic-probe.service",
        output_evaluator="chat_alert_monitor",
        work_metrics_provider="chat_synthetic",
    ),
    CronJobDefinition(
        id="process_curation_thumbnails",
        display_name="Curation Thumbnail Queue",
        category="systemd",
        schedule="every minute (systemd)",
        script_path="hourly/process_curation_thumbnails.py",
        log_name="process_curation_thumbnails",
        process_patterns=("process_curation_thumbnails",),
        lock_file=None,
        expected_runtime_minutes=30,
        stale_after_minutes=35,
        critical=False,
        healthy_no_work_allowed=True,
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(1),),
        schedule_grace_minutes=3,
        systemd_timer="pwc-curation-thumbnails.timer",
        systemd_service="pwc-curation-thumbnails.service",
        output_evaluator="curation_thumbnails",
        db_freshness_query="""
            SELECT max(COALESCE(thumbnail_finished_at, thumbnail_requested_at)) AS last_write,
                   count(*) FILTER (
                     WHERE thumbnail_finished_at > now() - interval '35 minutes'
                   ) AS recent_writes,
                   count(*) FILTER (WHERE thumbnail_status = 'queued') AS queued,
                   count(*) FILTER (WHERE thumbnail_status = 'processing') AS processing,
                   count(*) FILTER (
                     WHERE thumbnail_status = 'processing'
                       AND thumbnail_claimed_at < now() - interval '30 minutes'
                   ) AS stale_processing,
                   count(*) FILTER (WHERE thumbnail_status = 'failed') AS failed,
                   COALESCE(EXTRACT(EPOCH FROM (
                     now() - min(thumbnail_requested_at)
                       FILTER (WHERE thumbnail_status = 'queued')
                   )) / 60, 0)::bigint AS oldest_wait_minutes
            FROM paper_curation_jobs
            WHERE thumbnail_status IS NOT NULL
        """,
    ),
)


# Explicit machine-readable scheduler contracts.  Keeping them separate from the
# human label makes schedule-boundary behavior deterministic and reviewable.
_SCHEDULE_CONTRACTS: dict[str, tuple[tuple[SchedulePolicy, ...], int]] = {
    "paper_markdown_backfill": (
        (SchedulePolicy.fixed(60, offset_minutes=17),),
        20,
    ),
    "update_hot_github_trending": ((SchedulePolicy.fixed(15),), 10),
    "update_github_stars": ((SchedulePolicy.fixed(60),), 20),
    "update_citations": ((SchedulePolicy.fixed(60, offset_minutes=30),), 20),
    "calculate_trending_scores": ((SchedulePolicy.fixed(60, offset_minutes=15),), 20),
    "calculate_paper_trending_scores": (
        (SchedulePolicy.fixed(60, offset_minutes=45),),
        20,
    ),
    "update_hf_artifacts": ((SchedulePolicy.fixed(60, offset_minutes=30),), 20),
    "sync_3d_arena": ((SchedulePolicy.fixed(60, offset_minutes=5),), 20),
    "sync_tabarena": ((SchedulePolicy.fixed(60, offset_minutes=55),), 20),
    "sync_open_asr": ((SchedulePolicy.fixed(60, offset_minutes=15),), 20),
    "sync_open_tts": ((SchedulePolicy.fixed(60, offset_minutes=18),), 20),
    "sync_mmteb_overall": ((SchedulePolicy.fixed(60, offset_minutes=7),), 20),
    "sync_mmteb_retrieval": ((SchedulePolicy.fixed(60, offset_minutes=22),), 20),
    "sync_mmteb_reranking": ((SchedulePolicy.fixed(60, offset_minutes=37),), 20),
    "sync_mmeb_v2": ((SchedulePolicy.fixed(60, offset_minutes=12),), 20),
    "sync_mmeb_v3": ((SchedulePolicy.fixed(60, offset_minutes=42),), 20),
    "sync_deepswe": ((SchedulePolicy.fixed(60, offset_minutes=25),), 20),
    "sync_artificial_analysis": ((SchedulePolicy.fixed(60, offset_minutes=35),), 20),
    "sync_programbench": ((SchedulePolicy.fixed(60, offset_minutes=40),), 20),
    "sync_parsebench": ((SchedulePolicy.fixed(60, offset_minutes=20),), 20),
    "sync_frontiercode": ((SchedulePolicy.fixed(60, offset_minutes=45),), 20),
    "sync_coarena": ((SchedulePolicy.fixed(60, offset_minutes=50),), 20),
    "sync_arc_prize": ((SchedulePolicy.fixed(60, offset_minutes=10),), 20),
    "import_hf_daily_papers": ((SchedulePolicy.fixed(60),), 20),
    "create_eval_verification_issues": (
        (SchedulePolicy.fixed(60, offset_minutes=52),),
        20,
    ),
    "enqueue_hf_daily_paper_curation": (
        (SchedulePolicy.fixed(60, offset_minutes=27),),
        20,
    ),
    "enqueue_hf_trending_model_curation": (
        (SchedulePolicy.fixed(60, offset_minutes=42),),
        20,
    ),
    "export_enrichment_dashboard": ((SchedulePolicy.daily(3, 10),), 60),
    "sync_hf_organizations": ((SchedulePolicy.daily(2, 20),), 60),
    "calculate_organization_trending_scores": ((SchedulePolicy.daily(3, 40),), 60),
    "refresh_paper_embeddings": ((SchedulePolicy.fixed(60, offset_minutes=15),), 20),
    # The three-hour lane and the four reviewed daily slots intentionally share
    # a one-hour grace because GitHub runs them as one workflow duty.
    "preload_thumbnails": (
        (
            SchedulePolicy.fixed(180),
            SchedulePolicy.daily(4, 15),
            SchedulePolicy.daily(4, 30),
            SchedulePolicy.daily(4, 45),
        ),
        60,
    ),
    "mirror_thumbnails_to_disk": ((SchedulePolicy.daily(5, 0),), 60),
    "link_methods_by_references": ((SchedulePolicy.weekly(6, 4, 0),), 180),
    "backfill_method_keywords": ((SchedulePolicy.daily(1, 10),), 60),
    "backfill_method_references": ((SchedulePolicy.fixed(60, offset_minutes=15),), 60),
    "link_papers_by_task_keywords": ((SchedulePolicy.weekly(6, 5, 0),), 180),
}

_OUTPUT_EVALUATORS: dict[str, str] = {
    "update_github_stars": "github_stars",
    "update_hot_github_trending": "hot_github_trending",
    "calculate_trending_scores": "repository_trending",
    "calculate_paper_trending_scores": "paper_trending",
    "import_hf_daily_papers": "hf_paper_import",
    "enqueue_hf_daily_paper_curation": "daily_curation",
    "enqueue_hf_trending_model_curation": "trending_curation",
    "update_citations": "citations",
    "update_hf_artifacts": "hf_artifacts",
    "paper_markdown_backfill": "paper_markdown",
    "refresh_paper_embeddings": "paper_embeddings",
    "sync_hf_organizations": "organization_sync",
    "calculate_organization_trending_scores": "organization_trending",
    "backfill_method_keywords": "backfill",
    "backfill_method_references": "backfill",
    "preload_thumbnails": "thumbnail_preload",
    "mirror_thumbnails_to_disk": "thumbnail_mirror",
    "link_methods_by_references": "weekly_linker",
    "link_papers_by_task_keywords": "weekly_linker",
}


# Host systemd timers own scheduled execution for the previously
# GitHub-scheduled jobs.  GitHub Actions schedule: triggers proved unreliable
# (delayed or missing scheduled events with no catch-up), so the units in
# deploy/systemd/cron/ are now the execution authority; the workflows remain
# workflow_dispatch-only for manual recovery.
def _systemd_unit(job_id: str) -> str:
    return "pwc-cron-" + job_id.replace("_", "-")


_PRELOAD_LANES = ("visible", "task-top", "method-top", "recent", "external")

_SYSTEMD_MIGRATED: dict[str, tuple[tuple[str, str], ...]] = {
    job_id: ((f"{_systemd_unit(job_id)}.timer", f"{_systemd_unit(job_id)}.service"),)
    for job_id, (_policies, _grace) in _SCHEDULE_CONTRACTS.items()
    if job_id != "preload_thumbnails"
}
_SYSTEMD_MIGRATED["preload_thumbnails"] = tuple(
    (
        f"pwc-cron-preload-thumbnails-{lane}.timer",
        f"pwc-cron-preload-thumbnails-{lane}.service",
    )
    for lane in _PRELOAD_LANES
)


def _migrated_scheduler(job: CronJobDefinition) -> str:
    if job.id == "extract_urls":
        return "manual"
    if job.id in _SYSTEMD_MIGRATED:
        return "systemd"
    return job.scheduler


CRON_JOBS = tuple(
    replace(
        job,
        scheduler=_migrated_scheduler(job),
        systemd_timer=(
            _SYSTEMD_MIGRATED[job.id][0][0]
            if job.id in _SYSTEMD_MIGRATED
            else job.systemd_timer
        ),
        systemd_service=(
            _SYSTEMD_MIGRATED[job.id][0][1]
            if job.id in _SYSTEMD_MIGRATED
            else job.systemd_service
        ),
        systemd_extra_units=(
            _SYSTEMD_MIGRATED[job.id][1:]
            if job.id in _SYSTEMD_MIGRATED
            else job.systemd_extra_units
        ),
        schedule_policies=_SCHEDULE_CONTRACTS.get(
            job.id, (job.schedule_policies, job.schedule_grace_minutes)
        )[0],
        schedule_grace_minutes=_SCHEDULE_CONTRACTS.get(
            job.id, (job.schedule_policies, job.schedule_grace_minutes)
        )[1],
        output_evaluator=job.output_evaluator
        or _OUTPUT_EVALUATORS.get(job.id, "generic"),
    )
    for job in CRON_JOBS
)


def get_cron_job(job_id: str) -> Optional[CronJobDefinition]:
    for job in CRON_JOBS:
        if job.id == job_id:
            return job
    return None


def list_cron_jobs() -> Sequence[CronJobDefinition]:
    return CRON_JOBS
