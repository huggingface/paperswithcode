"""Production CRON job registry for the admin health dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, Sequence, Tuple

from backend.services.conference_deadline_service import FRESHNESS_SQL


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
            "enrichment_snapshot",
        ]
    ] = None
    db_metrics_provider: Optional[Literal["thumbnail_cache"]] = None
    dependency_job_id: Optional[str] = None
    enablement_settings: Tuple[str, ...] = ()
    # True when runs differ in their work (lanes sharing one launcher lock), so
    # a lock-skipped run is missed work rather than a harmless overlap.
    lock_skip_misses_work: bool = False

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


def validate_cron_jobs(jobs: Sequence[CronJobDefinition]) -> None:
    """Reject incomplete declarations before dashboard or probe consumers use them."""
    seen: set[str] = set()
    for job in jobs:
        if not job.id or job.id in seen:
            raise ValueError(f"Invalid or duplicate CRON job ID: {job.id!r}")
        seen.add(job.id)
        if job.scheduler not in {"github_actions", "systemd", "manual"}:
            raise ValueError(f"{job.id}: unknown scheduler {job.scheduler!r}")
        if not job.output_evaluator or not job.output_evaluator.strip():
            raise ValueError(f"{job.id}: output evaluator must be explicit")
        if job.schedule_grace_minutes < 0:
            raise ValueError(f"{job.id}: schedule grace must be nonnegative")
        if job.scheduler != "manual" and not job.schedule_policies:
            raise ValueError(f"{job.id}: scheduled jobs require schedule policies")
        if job.scheduler == "github_actions" and not job.workflow_file:
            raise ValueError(f"{job.id}: GitHub Actions jobs require a workflow")
        if job.scheduler == "systemd":
            if not job.systemd_timer or not job.systemd_service:
                raise ValueError(f"{job.id}: systemd jobs require a timer/service pair")
        elif job.systemd_timer or job.systemd_service or job.systemd_extra_units:
            raise ValueError(f"{job.id}: non-systemd jobs cannot own systemd units")
        for timer, service in job.systemd_unit_pairs:
            if not timer.endswith(".timer") or not service.endswith(".service"):
                raise ValueError(f"{job.id}: invalid timer/service pair")
        for policy in job.schedule_policies:
            if policy.kind == "fixed_interval":
                valid = (
                    policy.interval_minutes is not None
                    and policy.interval_minutes > 0
                    and policy.minute_of_day is not None
                    and 0 <= policy.minute_of_day < policy.interval_minutes
                    and policy.weekday is None
                )
            else:
                valid = (
                    policy.kind in {"daily", "weekly"}
                    and policy.interval_minutes is None
                    and policy.minute_of_day is not None
                    and 0 <= policy.minute_of_day < 24 * 60
                    and (
                        policy.weekday is None
                        if policy.kind == "daily"
                        else policy.weekday is not None and 0 <= policy.weekday < 7
                    )
                )
            if not valid:
                raise ValueError(f"{job.id}: invalid schedule policy {policy!r}")


CRON_JOBS: Tuple[CronJobDefinition, ...] = (
    CronJobDefinition(
        id="send_research_digests",
        display_name="Weekly Research Digests",
        category="hourly",
        schedule="0 * * * *",
        script_path="backend/scripts/send_research_digests.py",
        log_name="send_research_digests",
        process_patterns=("backend.scripts.send_research_digests",),
        lock_file="/var/lib/paperswithcode/production/cron-locks/send_research_digests.lock",
        expected_runtime_minutes=45,
        stale_after_minutes=180,
        critical=False,
        healthy_no_work_allowed=True,
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60),),
        systemd_timer="pwc-cron-send-research-digests.timer",
        systemd_service="pwc-cron-send-research-digests.service",
        output_evaluator="generic",
        workflow_freshness_required=False,
        enablement_settings=("research_email_enabled",),
    ),
    CronJobDefinition(
        id="paper_markdown_backfill",
        scheduler="systemd",
        schedule_policies=(
            SchedulePolicy.fixed(60, offset_minutes=17),
            SchedulePolicy.fixed(5),
        ),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-paper-markdown-backfill.timer",
        systemd_service="pwc-cron-paper-markdown-backfill.service",
        systemd_extra_units=(
            (
                "pwc-cron-paper-markdown-fresh.timer",
                "pwc-cron-paper-markdown-fresh.service",
            ),
        ),
        output_evaluator="paper_markdown",
        display_name="Paper Markdown Backfill",
        category="hourly",
        schedule=(
            "17 * * * * (live and full backfill reconciliation); "
            "*/5 * * * * (fresh lane, papers indexed in the last day)"
        ),
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(15),),
        schedule_grace_minutes=10,
        systemd_timer="pwc-cron-update-hot-github-trending.timer",
        systemd_service="pwc-cron-update-hot-github-trending.service",
        systemd_extra_units=(),
        output_evaluator="hot_github_trending",
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
                SELECT DISTINCT
                    r.id,
                    r.created_at AS repository_created_at,
                    r.num_stars_updated_at
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
                    max(rsh.snapshot_at) AS last_snapshot_at,
                    -- 404/451 repositories get no snapshot, but the job still
                    -- stamps num_stars_updated_at, which also drives selection.
                    COALESCE(
                        GREATEST(max(rsh.snapshot_at), hr.num_stars_updated_at),
                        hr.repository_created_at
                    ) AS last_checked_at
                FROM hot_repositories hr
                LEFT JOIN repository_star_history rsh
                  ON rsh.repository_id = hr.id
                GROUP BY hr.id, hr.repository_created_at, hr.num_stars_updated_at
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
                    now() - min(last_checked_at)
                      FILTER (
                        WHERE last_checked_at < now() - interval '15 minutes'
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-update-github-stars.timer",
        systemd_service="pwc-cron-update-github-stars.service",
        systemd_extra_units=(),
        output_evaluator="github_stars",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=30),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-update-citations.timer",
        systemd_service="pwc-cron-update-citations.service",
        systemd_extra_units=(),
        output_evaluator="citations",
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
        scheduler="manual",
        schedule_policies=(),
        schedule_grace_minutes=20,
        systemd_timer=None,
        systemd_service=None,
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="Extract URLs",
        category="manual",
        schedule="paused (manual dispatch only; hourly schedule disabled)",
        script_path="cron-extract-urls.yml",
        log_name="extract_urls_hourly",
        process_patterns=("url_extraction_agent.database",),
        lock_file=None,
        expected_runtime_minutes=110,
        # Manual dispatch only: expect a run about weekly, not hourly.
        stale_after_minutes=7 * 24 * 60,
        critical=False,
        healthy_no_work_allowed=True,
        # Only rows the extraction agent created prove it ran; papers.updated_at
        # moves for every catalog edit.
        db_freshness_query="""
            WITH extracted AS (
                SELECT created_at FROM repositories WHERE source = 'ai_extraction'
                UNION ALL
                SELECT created_at FROM project_pages WHERE source = 'ai_extraction'
            )
            SELECT max(created_at) AS last_write,
                   count(*) FILTER (
                     WHERE created_at > now() - interval '7 days'
                   ) AS recent_writes
            FROM extracted
        """,
        workflow_file="cron-extract-urls.yml",
        workflow_jobs=("select", "discover", "persist"),
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="calculate_trending_scores",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=15),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-calculate-trending-scores.timer",
        systemd_service="pwc-cron-calculate-trending-scores.service",
        systemd_extra_units=(),
        output_evaluator="repository_trending",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=45),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-calculate-paper-trending-scores.timer",
        systemd_service="pwc-cron-calculate-paper-trending-scores.service",
        systemd_extra_units=(),
        output_evaluator="paper_trending",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=30),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-update-hf-artifacts.timer",
        systemd_service="pwc-cron-update-hf-artifacts.service",
        systemd_extra_units=(),
        output_evaluator="hf_artifacts",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=5),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-3d-arena.timer",
        systemd_service="pwc-cron-sync-3d-arena.service",
        systemd_extra_units=(),
        output_evaluator="generic",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=55),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-tabarena.timer",
        systemd_service="pwc-cron-sync-tabarena.service",
        systemd_extra_units=(),
        output_evaluator="tabarena",
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
                   count(*) AS matched_evaluations,
                   min(e.updated_at) AS oldest_write,
                   count(*) FILTER (
                     WHERE e.updated_at IS NULL OR
                           e.updated_at <= now() - interval '2 hours 30 minutes'
                   ) AS stale_evaluations
            FROM evaluations e
            JOIN datasets d ON d.id = e.dataset_id
            JOIN tasks t ON t.id = e.task_id
            WHERE d.slug = 'tabarena-v0-1'
              AND t.slug = 'tabular-learning'
              AND e.methodology LIKE
                  'Managed by the Papers with Code TabArena live sync.%'
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=15),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-open-asr.timer",
        systemd_service="pwc-cron-sync-open-asr.service",
        systemd_extra_units=(),
        output_evaluator="generic",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=18),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-open-tts.timer",
        systemd_service="pwc-cron-sync-open-tts.service",
        systemd_extra_units=(),
        output_evaluator="generic",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=7),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-mmteb-overall.timer",
        systemd_service="pwc-cron-sync-mmteb-overall.service",
        systemd_extra_units=(),
        output_evaluator="generic",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=22),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-mmteb-retrieval.timer",
        systemd_service="pwc-cron-sync-mmteb-retrieval.service",
        systemd_extra_units=(),
        output_evaluator="generic",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=37),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-mmteb-reranking.timer",
        systemd_service="pwc-cron-sync-mmteb-reranking.service",
        systemd_extra_units=(),
        output_evaluator="generic",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=12),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-mmeb-v2.timer",
        systemd_service="pwc-cron-sync-mmeb-v2.service",
        systemd_extra_units=(),
        output_evaluator="generic",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=42),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-mmeb-v3.timer",
        systemd_service="pwc-cron-sync-mmeb-v3.service",
        systemd_extra_units=(),
        output_evaluator="generic",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=25),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-deepswe.timer",
        systemd_service="pwc-cron-sync-deepswe.service",
        systemd_extra_units=(),
        output_evaluator="generic",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(120, offset_minutes=35),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-artificial-analysis.timer",
        systemd_service="pwc-cron-sync-artificial-analysis.service",
        systemd_extra_units=(),
        output_evaluator="artificial_analysis",
        display_name="Sync Artificial Analysis Leaderboards",
        category="hourly",
        schedule="35 */2 * * * (every two hours)",
        script_path="hourly/sync_artificial_analysis.py",
        log_name="sync_artificial_analysis",
        process_patterns=("scripts.hourly.sync_artificial_analysis",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "sync_artificial_analysis.lock"
        ),
        expected_runtime_minutes=5,
        stale_after_minutes=270,
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
                   count(*) FILTER (
                     WHERE updated_at > now() - interval '3 hours'
                   ) AS recent_writes,
                   count(*) AS matched_evaluations,
                   count(*) FILTER (
                     WHERE updated_at IS NULL
                        OR updated_at <= now() - interval '3 hours'
                   ) AS stale_evaluations,
                   3 - count(DISTINCT dataset_slug) FILTER (
                     WHERE updated_at > now() - interval '3 hours'
                   ) AS missing_fresh_datasets
            FROM managed_evaluations
        """,
        workflow_file="cron-sync-artificial-analysis.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_programbench",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=40),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-programbench.timer",
        systemd_service="pwc-cron-sync-programbench.service",
        systemd_extra_units=(),
        output_evaluator="generic",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=20),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-parsebench.timer",
        systemd_service="pwc-cron-sync-parsebench.service",
        systemd_extra_units=(),
        output_evaluator="generic",
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
        id="sync_extractbench",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=32),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-extractbench.timer",
        systemd_service="pwc-cron-sync-extractbench.service",
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="Sync ExtractBench Leaderboard",
        category="hourly",
        schedule="32 * * * * (hourly)",
        script_path="hourly/sync_extractbench.py",
        log_name="sync_extractbench",
        process_patterns=("scripts.hourly.sync_extractbench",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/sync_extractbench.lock"
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
            WHERE d.slug = 'extractbench'
              AND e.best_metric = 'Value F1'
              AND e.methodology LIKE
                  'Managed by the Papers with Code ExtractBench live sync.%'
        """,
        workflow_file="cron-sync-extractbench.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_physics_iq_verified",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=28),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-physics-iq-verified.timer",
        systemd_service="pwc-cron-sync-physics-iq-verified.service",
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="Sync Physics-IQ Verified Leaderboard",
        category="hourly",
        schedule="28 * * * * (hourly)",
        script_path="hourly/sync_physics_iq_verified.py",
        log_name="sync_physics_iq_verified",
        process_patterns=("scripts.hourly.sync_physics_iq_verified",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "sync_physics_iq_verified.lock"
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
            WHERE d.slug = 'physics-iq-verified'
              AND e.methodology LIKE
                  'Managed by the Papers with Code Physics-IQ Verified live sync.%'
        """,
        workflow_file="cron-sync-physics-iq-verified.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_vals_finance_agent",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=47),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-vals-finance-agent.timer",
        systemd_service="pwc-cron-sync-vals-finance-agent.service",
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="Sync Vals AI Finance Agent v2 Leaderboard",
        category="hourly",
        schedule="47 * * * * (hourly)",
        script_path="hourly/sync_vals_finance_agent.py",
        log_name="sync_vals_finance_agent",
        process_patterns=("scripts.hourly.sync_vals_finance_agent",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/sync_vals_finance_agent.lock"
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
            WHERE d.slug = 'finance-agent-v2'
              AND e.methodology LIKE
                  'Managed by the Papers with Code Vals AI Finance Agent v2 live sync.%'
        """,
        workflow_file="cron-sync-vals-finance-agent.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_surge_chartography",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=38),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-surge-chartography.timer",
        systemd_service="pwc-cron-sync-surge-chartography.service",
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="Sync Surge AI Chartography Leaderboard",
        category="hourly",
        schedule="38 * * * * (hourly)",
        script_path="hourly/sync_surge_chartography.py",
        log_name="sync_surge_chartography",
        process_patterns=("scripts.hourly.sync_surge_chartography",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/sync_surge_chartography.lock"
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
            WHERE d.slug = 'chartography-no-tools'
              AND e.methodology LIKE
                  'Managed by the Papers with Code Surge AI Chartography live sync.%'
        """,
        workflow_file="cron-sync-surge-chartography.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_frontiercs_2",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=43),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-frontiercs-2.timer",
        systemd_service="pwc-cron-sync-frontiercs-2.service",
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="Sync FrontierCS 2 Leaderboard",
        category="hourly",
        schedule="43 * * * * (hourly)",
        script_path="hourly/sync_frontiercs_2.py",
        log_name="sync_frontiercs_2",
        process_patterns=("scripts.hourly.sync_frontiercs_2",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/sync_frontiercs_2.lock"
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
            WHERE d.slug = 'frontiercs-2'
              AND e.methodology LIKE
                  'Managed by the Papers with Code FrontierCS 2 live sync.%'
        """,
        workflow_file="cron-sync-frontiercs-2.yml",
        workflow_jobs=("run",),
        dashboard_group="leaderboard_sync",
    ),
    CronJobDefinition(
        id="sync_frontiercode",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=45),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-frontiercode.timer",
        systemd_service="pwc-cron-sync-frontiercode.service",
        systemd_extra_units=(),
        output_evaluator="generic",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=50),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-coarena.timer",
        systemd_service="pwc-cron-sync-coarena.service",
        systemd_extra_units=(),
        output_evaluator="generic",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=10),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-sync-arc-prize.timer",
        systemd_service="pwc-cron-sync-arc-prize.service",
        systemd_extra_units=(),
        output_evaluator="generic",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-import-hf-daily-papers.timer",
        systemd_service="pwc-cron-import-hf-daily-papers.service",
        systemd_extra_units=(),
        output_evaluator="hf_paper_import",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=52),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-create-eval-verification-issues.timer",
        systemd_service="pwc-cron-create-eval-verification-issues.service",
        systemd_extra_units=(),
        output_evaluator="generic",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=27),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-enqueue-hf-daily-paper-curation.timer",
        systemd_service="pwc-cron-enqueue-hf-daily-paper-curation.service",
        systemd_extra_units=(),
        output_evaluator="daily_curation",
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
                SELECT workflow.*,
                       workflow.cohort_date >= CURRENT_DATE - 7 AS in_cohort
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
                       -- Only the rolling seven-day cohort the enqueuer revisits;
                       -- older partials are settled validator rejections.
                       count(*) FILTER (
                           WHERE status = 'failed' AND in_cohort
                       ) AS failed_workflows,
                       count(*) FILTER (
                           WHERE status = 'partial' AND in_cohort
                       ) AS partial_workflows
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=42),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-enqueue-hf-trending-model-curation.timer",
        systemd_service="pwc-cron-enqueue-hf-trending-model-curation.service",
        systemd_extra_units=(),
        output_evaluator="trending_curation",
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
                   count(*) FILTER (
                       WHERE status = 'failed'
                         AND last_seen_at > now() - interval '7 days'
                   ) AS failed
                FROM trending_model_candidates
            ), workflow_metrics AS (
                SELECT count(*) FILTER (WHERE status = 'failed') AS failed_workflows,
                       count(*) FILTER (WHERE status = 'partial') AS partial_workflows
                FROM paper_curation_workflows AS workflow
                WHERE workflow.status IN ('failed', 'partial')
                  AND workflow.cohort_date >= CURRENT_DATE - 7
                  AND EXISTS (
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
        id="enqueue_benchmark_gap_review",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.daily(6, 35),),
        schedule_grace_minutes=60,
        systemd_timer="pwc-cron-enqueue-benchmark-gap-review.timer",
        systemd_service="pwc-cron-enqueue-benchmark-gap-review.service",
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="Benchmark Gap Review",
        category="daily",
        schedule="35 6 * * * (daily UTC)",
        script_path="backend/scripts/enqueue_benchmark_gap_review.py",
        log_name="enqueue_benchmark_gap_review",
        process_patterns=("backend.scripts.enqueue_benchmark_gap_review",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "enqueue_benchmark_gap_review.lock"
        ),
        expected_runtime_minutes=5,
        stale_after_minutes=1560,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(reviewed_at) AS last_write,
                   count(*) FILTER (WHERE status = 'approved') AS approved,
                   count(*) FILTER (WHERE status = 'promoted') AS promoted,
                   count(*) FILTER (WHERE status = 'rejected') AS rejected
            FROM benchmark_curation_candidates
        """,
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="scan_model_releases",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(180, offset_minutes=108),),
        schedule_grace_minutes=30,
        systemd_timer="pwc-cron-scan-model-releases.timer",
        systemd_service="pwc-cron-scan-model-releases.service",
        systemd_extra_units=(),
        # The radar JSON goes to the journal and unindexed releases become
        # queued resolution jobs. The job exits 1 only when every source
        # failed, so a clean exit proves the scan.
        output_evaluator="report_only",
        display_name="Model Release Radar",
        category="hourly",
        schedule="48 1/3 * * * (every three hours)",
        script_path="backend/scripts/scan_model_releases.py",
        log_name="scan_model_releases",
        process_patterns=("backend.scripts.scan_model_releases",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/scan_model_releases.lock"
        ),
        expected_runtime_minutes=5,
        stale_after_minutes=420,
        critical=False,
        healthy_no_work_allowed=True,
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="sweep_conference_deadlines",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.weekly(6, 2, 35),),
        schedule_grace_minutes=60,
        systemd_timer="pwc-cron-sweep-conference-deadlines.timer",
        systemd_service="pwc-cron-sweep-conference-deadlines.service",
        systemd_extra_units=(),
        output_evaluator="conference_deadlines",
        display_name="Conference Deadlines Weekly Sweep",
        category="weekly",
        schedule="35 2 * * 0 (Sun 02:35 UTC)",
        script_path="backend/scripts/sweep_conference_deadlines.py",
        log_name="sweep_conference_deadlines",
        process_patterns=("backend.scripts.sweep_conference_deadlines",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "sweep_conference_deadlines.lock"
        ),
        expected_runtime_minutes=30,
        stale_after_minutes=11520,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query=FRESHNESS_SQL,
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="link_google_scholar_profiles",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.weekly(2, 5, 20),),
        schedule_grace_minutes=180,
        systemd_timer="pwc-cron-link-google-scholar-profiles.timer",
        systemd_service="pwc-cron-link-google-scholar-profiles.service",
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="Link Google Scholar Profiles",
        category="weekly",
        schedule="20 5 * * 3 (Wed 05:20 UTC)",
        script_path="backend/scripts/link_google_scholar_profiles.py",
        log_name="link_google_scholar_profiles",
        process_patterns=("backend.scripts.link_google_scholar_profiles",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "link_google_scholar_profiles.lock"
        ),
        expected_runtime_minutes=60,
        stale_after_minutes=11520,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT count(*) AS candidates,
                   count(*) FILTER (WHERE serpapi_evidence IS NOT NULL)
                     AS profiles_read,
                   (SELECT count(*) FROM author_google_scholar_profiles)
                     AS linked_authors,
                   max(s2_checked_at) AS last_s2_check,
                   max(serpapi_checked_at) AS last_profile_read
            FROM author_google_scholar_candidates
        """,
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="refresh_conference_deadlines",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(720, offset_minutes=460),),
        schedule_grace_minutes=30,
        systemd_timer="pwc-cron-refresh-conference-deadlines.timer",
        systemd_service="pwc-cron-refresh-conference-deadlines.service",
        systemd_extra_units=(),
        output_evaluator="conference_deadlines",
        display_name="Conference Deadlines Daily Refresh",
        category="daily",
        schedule="40 7,19 * * * (collect twice daily, launch once daily)",
        script_path="backend/scripts/refresh_conference_deadlines.py",
        log_name="refresh_conference_deadlines",
        process_patterns=("backend.scripts.refresh_conference_deadlines",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "refresh_conference_deadlines.lock"
        ),
        expected_runtime_minutes=30,
        stale_after_minutes=11520,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query=FRESHNESS_SQL,
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="discover_x_threads",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(720, offset_minutes=502),),
        schedule_grace_minutes=30,
        systemd_timer="pwc-cron-discover-x-threads.timer",
        systemd_service="pwc-cron-discover-x-threads.service",
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="X Thread Discovery",
        category="daily",
        schedule="22 8,20 * * * (twice daily)",
        script_path="backend/scripts/discover_x_threads.py",
        log_name="discover_x_threads",
        process_patterns=("backend.scripts.discover_x_threads",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/discover_x_threads.lock"
        ),
        expected_runtime_minutes=5,
        stale_after_minutes=1500,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(last_scanned_at) AS last_write,
                   count(*) FILTER (WHERE linked_at IS NOT NULL) AS linked_papers
            FROM paper_x_thread_scans
        """,
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="post_trending_paper_to_x",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(240, offset_minutes=13),),
        schedule_grace_minutes=30,
        systemd_timer="pwc-cron-post-trending-paper-to-x.timer",
        systemd_service="pwc-cron-post-trending-paper-to-x.service",
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="Post Trending Paper to X",
        category="hourly",
        schedule="13 */4 * * * (every four hours)",
        script_path="backend/scripts/post_trending_paper_to_x.py",
        log_name="post_trending_paper_to_x",
        process_patterns=("backend.scripts.post_trending_paper_to_x",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "post_trending_paper_to_x.lock"
        ),
        expected_runtime_minutes=2,
        # A run with nothing left to post writes no row, so allow a quiet day.
        stale_after_minutes=1440,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(posted_at) AS last_write,
                   count(*) FILTER (
                     WHERE posted_at > now() - interval '24 hours'
                   ) AS recent_writes
            FROM paper_x_posts
        """,
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="post_x_insight",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.daily(9, 43), SchedulePolicy.daily(17, 43)),
        schedule_grace_minutes=30,
        systemd_timer="pwc-cron-post-x-insight.timer",
        systemd_service="pwc-cron-post-x-insight.service",
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="Post Insight to X",
        category="daily",
        schedule="43 9,17 * * * (twice daily)",
        script_path="backend/scripts/post_x_insight.py",
        log_name="post_x_insight",
        process_patterns=("backend.scripts.post_x_insight",),
        lock_file=("/var/lib/paperswithcode/production/cron-locks/post_x_insight.lock"),
        expected_runtime_minutes=3,
        # A run with nothing new to say writes no row, so allow quiet days.
        stale_after_minutes=4320,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(posted_at) AS last_write,
                   count(*) FILTER (
                     WHERE posted_at > now() - interval '72 hours'
                   ) AS recent_writes
            FROM x_insight_posts
        """,
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="link_abstract_mentions",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=51),),
        schedule_grace_minutes=30,
        systemd_timer="pwc-cron-link-abstract-mentions.timer",
        systemd_service="pwc-cron-link-abstract-mentions.service",
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="Link Abstract Mentions",
        category="hourly",
        schedule="51 * * * * (hourly)",
        script_path="backend/scripts/link_abstract_mentions.py",
        log_name="link_abstract_mentions",
        process_patterns=("backend.scripts.link_abstract_mentions",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/link_abstract_mentions.lock"
        ),
        expected_runtime_minutes=10,
        stale_after_minutes=180,
        critical=False,
        # Hours without new or edited abstracts write nothing.
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(created_at) AS last_write,
                   count(*) FILTER (WHERE created_at > now() - interval '3 hours')
                       AS recent_writes
            FROM paper_abstract_mentions
        """,
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="judge_research_topics",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=54),),
        schedule_grace_minutes=30,
        systemd_timer="pwc-cron-judge-research-topics.timer",
        systemd_service="pwc-cron-judge-research-topics.service",
        systemd_extra_units=(),
        output_evaluator="research_topics",
        display_name="Judge Research Topics",
        category="hourly",
        schedule="54 * * * * (hourly)",
        script_path="backend/scripts/judge_research_topics.py",
        log_name="judge_research_topics",
        process_patterns=("backend.scripts.judge_research_topics",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/judge_research_topics.lock"
        ),
        expected_runtime_minutes=15,
        stale_after_minutes=180,
        critical=False,
        # Hours without new papers or followed topics judge nothing.
        healthy_no_work_allowed=True,
        db_freshness_query="""
            WITH followed AS (
              SELECT DISTINCT s.topic_id FROM research_subscriptions s
              JOIN research_topics t ON t.id = s.topic_id
              WHERE t.backfill_status = 'done'
            ), recent AS (
              SELECT id, created_at FROM papers
              WHERE is_latest_version
                AND date_published BETWEEN current_date - 90 AND current_date
            )
            SELECT (SELECT max(judged_at) FROM research_topic_verdicts) AS last_write,
                   (SELECT count(*) FROM research_topic_verdicts
                    WHERE judged_at > now() - interval '3 hours') AS recent_writes,
                   (SELECT extract(epoch FROM now() - min(r.created_at)) / 60
                    FROM recent r CROSS JOIN followed f
                    WHERE NOT EXISTS (
                      SELECT 1 FROM research_topic_verdicts v
                      WHERE v.topic_id = f.topic_id AND v.paper_id = r.id
                    )) AS oldest_unjudged_age_minutes,
                   (SELECT extract(epoch FROM now() - min(t.created_at)) / 60
                    FROM research_topics t
                    WHERE t.backfill_status IN ('pending', 'running')
                      AND t.id IN (SELECT topic_id FROM research_subscriptions))
                       AS oldest_pending_backfill_minutes,
                   (SELECT count(*) FROM research_topics t
                    WHERE t.backfill_status = 'failed'
                      AND t.id IN (SELECT topic_id FROM research_subscriptions))
                       AS failed_backfills
        """,
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="backfill_research_topics",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(1),),
        schedule_grace_minutes=3,
        systemd_timer="pwc-cron-backfill-research-topics.timer",
        systemd_service="pwc-cron-backfill-research-topics.service",
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="Backfill Research Topics",
        category="systemd",
        schedule="every minute (systemd)",
        script_path="backend/scripts/judge_research_topics.py",
        log_name="backfill_research_topics",
        process_patterns=("backend.scripts.judge_research_topics --backfill",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "backfill_research_topics.lock"
        ),
        expected_runtime_minutes=30,
        stale_after_minutes=60,
        critical=False,
        # Minutes without a new topic claim nothing.
        healthy_no_work_allowed=True,
        db_freshness_query=None,
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="rescan_abstract_mentions",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.daily(3, 21),),
        schedule_grace_minutes=60,
        systemd_timer="pwc-cron-rescan-abstract-mentions.timer",
        systemd_service="pwc-cron-rescan-abstract-mentions.service",
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="Rescan Abstract Mentions",
        category="daily",
        schedule="21 3 * * * (daily)",
        script_path="backend/scripts/link_abstract_mentions.py",
        log_name="rescan_abstract_mentions",
        process_patterns=("backend.scripts.link_abstract_mentions --rescan",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "rescan_abstract_mentions.lock"
        ),
        expected_runtime_minutes=60,
        stale_after_minutes=1560,
        critical=False,
        # A night without catalog changes rewrites nothing.
        healthy_no_work_allowed=True,
        db_freshness_query=None,
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="warm_paper_suggested_questions",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=33),),
        schedule_grace_minutes=30,
        systemd_timer="pwc-cron-warm-paper-suggested-questions.timer",
        systemd_service="pwc-cron-warm-paper-suggested-questions.service",
        systemd_extra_units=(),
        output_evaluator="suggested_questions",
        display_name="Warm Paper Suggested Questions",
        category="hourly",
        schedule="33 * * * * (hourly)",
        script_path="backend/scripts/warm_paper_suggested_questions.py",
        log_name="warm_paper_suggested_questions",
        process_patterns=("backend.scripts.warm_paper_suggested_questions",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "warm_paper_suggested_questions.lock"
        ),
        expected_runtime_minutes=15,
        stale_after_minutes=180,
        critical=False,
        healthy_no_work_allowed=True,
        # A run with every visible paper covered writes no row, so the
        # evaluator judges the home-feed cohort's coverage instead of writes.
        db_freshness_query="""
            WITH home_feed AS (
                SELECT id
                FROM papers
                WHERE is_latest_version = TRUE
                  AND date_published >= CURRENT_DATE - 6
                ORDER BY trending_score DESC NULLS LAST, id
                LIMIT 90
            )
            SELECT (SELECT max(created_at) FROM paper_suggested_questions)
                       AS last_write,
                   (SELECT count(*) FROM paper_suggested_questions
                    WHERE created_at > now() - interval '3 hours')
                       AS recent_writes,
                   count(*) AS visible_papers,
                   count(*) FILTER (
                     WHERE NOT EXISTS (
                       SELECT 1 FROM paper_suggested_questions AS questions
                       WHERE questions.paper_id = home_feed.id
                     )
                   ) AS visible_missing
            FROM home_feed
        """,
        workflow_freshness_required=False,
    ),
    CronJobDefinition(
        id="export_enrichment_dashboard",
        output_evaluator="enrichment_snapshot",
        work_metrics_provider="enrichment_snapshot",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.daily(3, 10),),
        schedule_grace_minutes=60,
        systemd_timer="pwc-cron-export-enrichment-dashboard.timer",
        systemd_service="pwc-cron-export-enrichment-dashboard.service",
        systemd_extra_units=(),
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.daily(2, 20),),
        schedule_grace_minutes=60,
        systemd_timer="pwc-cron-sync-hf-organizations.timer",
        systemd_service="pwc-cron-sync-hf-organizations.service",
        systemd_extra_units=(),
        output_evaluator="organization_sync",
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
        id="sync_hf_author_profiles",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.daily(2, 50),),
        schedule_grace_minutes=60,
        systemd_timer="pwc-cron-sync-hf-author-profiles.timer",
        systemd_service="pwc-cron-sync-hf-author-profiles.service",
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="Sync HF Author Profiles",
        category="daily",
        schedule="50 2 * * * (daily)",
        script_path="daily/sync_hf_author_profiles.py",
        log_name="sync_hf_author_profiles",
        process_patterns=("scripts.daily.sync_hf_author_profiles",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/sync_hf_author_profiles.lock"
        ),
        expected_runtime_minutes=5,
        stale_after_minutes=1800,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT max(updated_at) AS last_write,
                   count(*) FILTER (
                     WHERE updated_at > now() - interval '30 hours'
                   ) AS recent_writes,
                   count(*) AS linked_authors
            FROM authors
            WHERE hf_username IS NOT NULL
        """,
        workflow_file="cron-sync-hf-author-profiles.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="link_openalex_organizations",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.daily(3, 20),),
        schedule_grace_minutes=60,
        systemd_timer="pwc-cron-link-openalex-organizations.timer",
        systemd_service="pwc-cron-link-openalex-organizations.service",
        systemd_extra_units=(),
        output_evaluator="generic",
        display_name="Link OpenAlex Organizations",
        category="daily",
        schedule="20 3 * * * (daily)",
        script_path="daily/link_openalex_organizations.py",
        log_name="link_openalex_organizations",
        process_patterns=("scripts.daily.link_openalex_organizations",),
        lock_file=(
            "/var/lib/paperswithcode/production/cron-locks/"
            "link_openalex_organizations.lock"
        ),
        expected_runtime_minutes=5,
        stale_after_minutes=1800,
        critical=False,
        healthy_no_work_allowed=True,
        db_freshness_query="""
            SELECT count(*) AS openalex_links,
                   count(DISTINCT po.paper_id) FILTER (
                     WHERE p.date_published >= CURRENT_DATE - 60
                   ) AS recent_linked_papers
            FROM paper_organizations po
            JOIN papers p ON p.id = po.paper_id
            WHERE po.source = 'openalex'
        """,
        workflow_file="cron-link-openalex-organizations.yml",
        workflow_jobs=("run",),
    ),
    CronJobDefinition(
        id="calculate_organization_trending_scores",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.daily(3, 40),),
        schedule_grace_minutes=60,
        systemd_timer="pwc-cron-calculate-organization-trending-scores.timer",
        systemd_service="pwc-cron-calculate-organization-trending-scores.service",
        systemd_extra_units=(),
        output_evaluator="organization_trending",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=15),),
        schedule_grace_minutes=20,
        systemd_timer="pwc-cron-refresh-paper-embeddings.timer",
        systemd_service="pwc-cron-refresh-paper-embeddings.service",
        systemd_extra_units=(),
        output_evaluator="paper_embeddings",
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
        scheduler="systemd",
        schedule_policies=(
            SchedulePolicy.fixed(180),
            SchedulePolicy.daily(4, 15),
            SchedulePolicy.daily(4, 30),
            SchedulePolicy.daily(4, 45),
        ),
        schedule_grace_minutes=60,
        systemd_timer="pwc-cron-preload-thumbnails-visible.timer",
        systemd_service="pwc-cron-preload-thumbnails-visible.service",
        systemd_extra_units=(
            (
                "pwc-cron-preload-thumbnails-task-top.timer",
                "pwc-cron-preload-thumbnails-task-top.service",
            ),
            (
                "pwc-cron-preload-thumbnails-method-top.timer",
                "pwc-cron-preload-thumbnails-method-top.service",
            ),
            (
                "pwc-cron-preload-thumbnails-recent.timer",
                "pwc-cron-preload-thumbnails-recent.service",
            ),
            (
                "pwc-cron-preload-thumbnails-external.timer",
                "pwc-cron-preload-thumbnails-external.service",
            ),
        ),
        output_evaluator="thumbnail_preload",
        # Each lane has its own launcher lock; a skip means a lane overran its
        # own next slot, which is still missed work.
        lock_skip_misses_work=True,
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.daily(5, 0),),
        schedule_grace_minutes=60,
        systemd_timer="pwc-cron-mirror-thumbnails-to-disk.timer",
        systemd_service="pwc-cron-mirror-thumbnails-to-disk.service",
        systemd_extra_units=(),
        output_evaluator="thumbnail_mirror",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.weekly(6, 4, 0),),
        schedule_grace_minutes=180,
        systemd_timer="pwc-cron-link-methods-by-references.timer",
        systemd_service="pwc-cron-link-methods-by-references.service",
        systemd_extra_units=(),
        output_evaluator="weekly_linker",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.daily(1, 10),),
        schedule_grace_minutes=60,
        systemd_timer="pwc-cron-backfill-method-keywords.timer",
        systemd_service="pwc-cron-backfill-method-keywords.service",
        systemd_extra_units=(),
        output_evaluator="backfill",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60, offset_minutes=15),),
        schedule_grace_minutes=60,
        systemd_timer="pwc-cron-backfill-method-references.timer",
        systemd_service="pwc-cron-backfill-method-references.service",
        systemd_extra_units=(),
        output_evaluator="backfill",
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
            SELECT count(*) AS total_partitions,
                   count(*) FILTER (WHERE status != 'complete') AS incomplete_partitions,
                   count(*) FILTER (
                       WHERE eligible_papers != processed_papers + unresolvable_papers
                   ) AS unaccounted_partitions,
                   max(updated_at) AS last_write,
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.weekly(6, 5, 0),),
        schedule_grace_minutes=180,
        systemd_timer="pwc-cron-link-papers-by-task-keywords.timer",
        systemd_service="pwc-cron-link-papers-by-task-keywords.service",
        systemd_extra_units=(),
        output_evaluator="weekly_linker",
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
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(15),),
        schedule_grace_minutes=10,
        systemd_timer="autonomous-cron-health.timer",
        systemd_service="autonomous-cron-health.service",
        systemd_extra_units=(),
        output_evaluator="autonomous_cron_operator",
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
        work_metrics_provider="autonomous_cron",
    ),
    CronJobDefinition(
        id="autonomous_cron_audit",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.daily(2, 20),),
        schedule_grace_minutes=45,
        systemd_timer="autonomous-cron-audit.timer",
        systemd_service="autonomous-cron-audit.service",
        systemd_extra_units=(),
        output_evaluator="autonomous_cron_operator",
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
        work_metrics_provider="autonomous_cron",
    ),
    CronJobDefinition(
        id="review_submissions",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(60),),
        schedule_grace_minutes=20,
        systemd_timer="submission-review.timer",
        systemd_service="submission-review.service",
        systemd_extra_units=(),
        output_evaluator="submission_review",
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
        work_metrics_provider="submission_review",
        enablement_settings=(
            "autonomous_submission_enabled",
            "autonomous_submission_jobs_enabled",
        ),
    ),
    CronJobDefinition(
        id="monitor_chat_operational_alerts",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(1),),
        schedule_grace_minutes=3,
        systemd_timer="pwc-chat-alert-monitor.timer",
        systemd_service="pwc-chat-alert-monitor.service",
        systemd_extra_units=(),
        output_evaluator="chat_alert_monitor",
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
        work_metrics_provider="chat_monitor",
    ),
    CronJobDefinition(
        id="run_chat_synthetic_probe",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(1),),
        schedule_grace_minutes=3,
        systemd_timer="pwc-cron-run-chat-synthetic-probe.timer",
        systemd_service="pwc-cron-run-chat-synthetic-probe.service",
        systemd_extra_units=(),
        output_evaluator="chat_alert_monitor",
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
        work_metrics_provider="chat_synthetic",
    ),
    CronJobDefinition(
        id="process_curation_thumbnails",
        scheduler="systemd",
        schedule_policies=(SchedulePolicy.fixed(1),),
        schedule_grace_minutes=3,
        systemd_timer="pwc-curation-thumbnails.timer",
        systemd_service="pwc-curation-thumbnails.service",
        systemd_extra_units=(),
        output_evaluator="curation_thumbnails",
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
                   count(*) FILTER (
                     WHERE thumbnail_status = 'failed'
                       AND thumbnail_finished_at > now() - interval '24 hours'
                   ) AS failed,
                   COALESCE(EXTRACT(EPOCH FROM (
                     now() - min(thumbnail_requested_at)
                       FILTER (WHERE thumbnail_status = 'queued')
                   )) / 60, 0)::bigint AS oldest_wait_minutes
            FROM paper_curation_jobs
            WHERE thumbnail_status IS NOT NULL
        """,
    ),
)


validate_cron_jobs(CRON_JOBS)


def get_cron_job(job_id: str) -> Optional[CronJobDefinition]:
    for job in CRON_JOBS:
        if job.id == job_id:
            return job
    return None


def list_cron_jobs() -> Sequence[CronJobDefinition]:
    return CRON_JOBS
