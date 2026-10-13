"""Launch and collect off-box conference deadline sweeps.

A scheduled run on the VPS does two bounded things and exits:

1. **collect**: for every sweep still ``running``, inspect its Hugging Face Job;
   once terminal, read the per-series results from the Job logs, validate each
   change set, and apply the accepted parts with the guarded writer in
   ``conference_deadline_service``;
2. **launch**: pick the series to research (priority order), snapshot their
   current rows into a manifest, and start one Job that researches them
   sequentially with ``conference_deadline_agent``.

The Claude Agent SDK never runs on the VPS, and the Job never sees database
credentials: it only receives the manifest and an Anthropic API key.
"""

from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from huggingface_hub import HfApi
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import ConferenceDeadlineSweep
from backend.services import conference_deadline_agent as agent
from backend.services.catalog_errors import CatalogError
from backend.services.conference_deadline_service import (
    DeadlineValidationError,
    aware_utc,
    SeriesChangeSet,
    apply_series_change_set,
    load_deadline_series,
    select_sweep_series,
    series_manifest,
)

logger = logging.getLogger(__name__)

Mode = Literal["weekly", "daily", "manual"]

ACTIVE_STAGES = {"RUNNING", "UPDATING", "SCHEDULING", "PENDING", "STARTING"}
TERMINAL_STAGES = {"COMPLETED", "CANCELED", "ERROR", "DELETED"}
RETRIEVAL_AGENTS = {"weekly": 3, "daily": 1, "manual": 3}
SECONDS_PER_SERIES = {"weekly": 900, "daily": 600, "manual": 900}
WORKER_PATH = Path(agent.__file__)


class SweepConfigurationError(RuntimeError):
    """Required credentials for the off-box sweep are missing."""


@dataclass(frozen=True)
class JobCredentials:
    namespace: str
    token: str
    anthropic_api_key: str


def job_credentials(settings: Settings) -> JobCredentials:
    namespace = (
        settings.conference_deadlines_hf_namespace or settings.codex_jobs_namespace
    )
    token = settings.conference_deadlines_hf_token or settings.codex_jobs_token
    missing = [
        name
        for name, value in (
            (
                "PWC_CONFERENCE_DEADLINES_HF_NAMESPACE (or PWC_CODEX_JOBS_NAMESPACE)",
                namespace,
            ),
            ("PWC_CONFERENCE_DEADLINES_HF_TOKEN (or PWC_CODEX_JOBS_TOKEN)", token),
            (
                "PWC_CONFERENCE_DEADLINES_ANTHROPIC_API_KEY",
                settings.conference_deadlines_anthropic_api_key,
            ),
        )
        if not value
    ]
    if missing:
        raise SweepConfigurationError("missing " + ", ".join(missing))
    return JobCredentials(
        namespace, token, settings.conference_deadlines_anthropic_api_key
    )


def job_command(sdk_version: str) -> list[str]:
    """Install the SDK, then run the shipped worker as a non-root user.

    Claude Code refuses ``bypassPermissions`` as root; the worker only has the
    WebSearch/WebFetch tools anyway.
    """
    write_worker = (
        "import base64,gzip,os;"
        "open('/home/agent/worker.py','wb').write(gzip.decompress("
        "base64.b64decode(os.environ['PWC_DEADLINE_AGENT_SOURCE'])))"
    )
    script = " && ".join(
        [
            "set -euo pipefail",
            "pip install --quiet --no-cache-dir "
            + shlex.quote(f"claude-agent-sdk=={sdk_version}"),
            "useradd -m agent",
            "python -c " + shlex.quote(write_worker),
            "chown agent /home/agent/worker.py",
            "exec su agent -c 'cd /home/agent && python -u worker.py'",
        ]
    )
    return ["bash", "-c", script]


def job_timeout_seconds(mode: Mode, count: int) -> int:
    return 1800 + SECONDS_PER_SERIES[mode] * count


class ConferenceDeadlineSweeps:
    def __init__(self, db: Session, settings: Settings, api: Any = None):
        self.db = db
        self.settings = settings
        self._api = api

    def api(self, credentials: JobCredentials) -> Any:
        if self._api is None:
            self._api = HfApi(token=credentials.token)
        return self._api

    # --- launch -------------------------------------------------------------

    def running(self) -> list[ConferenceDeadlineSweep]:
        return (
            self.db.query(ConferenceDeadlineSweep)
            .filter(ConferenceDeadlineSweep.status.in_(("launching", "running")))
            .order_by(ConferenceDeadlineSweep.id)
            .all()
        )

    def plan(
        self,
        mode: Mode,
        *,
        now: datetime,
        limit: Optional[int] = None,
        only: Optional[list[str]] = None,
    ) -> list[dict]:
        series = load_deadline_series(self.db, only=set(only) if only else None)
        if only:
            missing = set(only) - {s.series for s in series}
            if missing:
                raise DeadlineValidationError(
                    "unknown conference series: " + ", ".join(sorted(missing))
                )
            chosen = series
        else:
            default_limit = (
                self.settings.conference_deadlines_daily_limit
                if mode == "daily"
                else self.settings.conference_deadlines_weekly_limit
            )
            chosen = select_sweep_series(
                series,
                mode="daily" if mode == "daily" else "weekly",
                now=now,
                limit=limit or default_limit,
            )
        return [series_manifest(item, now.date()) for item in chosen]

    def launch(
        self,
        mode: Mode,
        manifests: list[dict],
        *,
        now: datetime,
    ) -> ConferenceDeadlineSweep:
        credentials = job_credentials(self.settings)
        sweep = ConferenceDeadlineSweep(
            mode=mode,
            status="launching",
            series=[m["series"] for m in manifests],
            launched_at=now,
        )
        self.db.add(sweep)
        self.db.commit()
        payload = {
            "sweep_id": sweep.id,
            "num_retrieval_agents": RETRIEVAL_AGENTS[mode],
            "series": manifests,
        }
        try:
            remote = self.api(credentials).run_job(
                image=self.settings.conference_deadlines_job_image,
                command=job_command(self.settings.conference_deadlines_sdk_version),
                env={
                    "PWC_DEADLINE_AGENT_SOURCE": agent.encode_payload_bytes(
                        WORKER_PATH.read_bytes()
                    ),
                    "PWC_DEADLINE_MANIFEST": agent.encode_payload(payload),
                    "PWC_DEADLINE_RETRIEVAL_MODEL": self.settings.conference_deadlines_retrieval_model,
                    "PWC_DEADLINE_AGGREGATION_MODEL": self.settings.conference_deadlines_aggregation_model,
                },
                secrets={"ANTHROPIC_API_KEY": credentials.anthropic_api_key},
                flavor=self.settings.conference_deadlines_job_flavor,
                timeout=job_timeout_seconds(mode, len(manifests)),
                labels={
                    "product": "paperswithcode",
                    "workflow": "conference-deadlines",
                    "sweep_id": str(sweep.id),
                    "mode": mode,
                },
                namespace=credentials.namespace,
            )
        except Exception as exc:  # Record why the Job never started, then re-raise.
            sweep.status = "failed"
            sweep.error = f"launch failed: {type(exc).__name__}: {exc}"[:2000]
            sweep.finished_at = datetime.now(timezone.utc)
            self.db.commit()
            raise
        sweep.hf_job_id = str(remote.id)
        sweep.status = "running"
        self.db.commit()
        return sweep

    # --- collect ------------------------------------------------------------

    def collect(self, *, now: datetime, dry_run: bool = False) -> list[dict]:
        reports = []
        for sweep in self.running():
            report = self.collect_one(sweep, now=now, dry_run=dry_run)
            if report is not None:
                reports.append(report)
        return reports

    def collect_one(
        self, sweep: ConferenceDeadlineSweep, *, now: datetime, dry_run: bool = False
    ) -> Optional[dict]:
        if sweep.hf_job_id is None:
            # Crashed between the ledger insert and run_job returning.
            if now - aware_utc(sweep.launched_at) > timedelta(hours=1):
                sweep.status = "failed"
                sweep.error = "no Hugging Face Job was recorded for this sweep"
                sweep.finished_at = now
                self.db.commit()
            return None
        credentials = job_credentials(self.settings)
        api = self.api(credentials)
        info = api.inspect_job(job_id=sweep.hf_job_id, namespace=credentials.namespace)
        stage = str(getattr(getattr(info, "status", None), "stage", "") or "")
        if stage not in TERMINAL_STAGES:
            deadline = aware_utc(sweep.launched_at) + timedelta(
                seconds=job_timeout_seconds(sweep.mode, len(sweep.series)) + 3600
            )
            if now > deadline:
                sweep.status = "failed"
                sweep.error = f"Job still {stage or 'unknown'} past its timeout"
                sweep.finished_at = now
                self.db.commit()
            return None
        lines = list(
            api.fetch_job_logs(
                job_id=sweep.hf_job_id, namespace=credentials.namespace, follow=True
            )
        )
        return self.apply_results(
            sweep,
            agent.decode_result_lines(lines),
            stage=stage,
            completed=any(agent.DONE_MARKER in line for line in lines),
            now=now,
            dry_run=dry_run,
        )

    def apply_results(
        self,
        sweep: ConferenceDeadlineSweep,
        results: list[dict],
        *,
        stage: str,
        completed: bool,
        now: datetime,
        dry_run: bool = False,
    ) -> dict:
        """Validate and apply each series' change set; partial sweeps still apply."""
        per_series = []
        applied = 0
        cost = 0.0
        for result in results:
            series = result.get("series")
            entry: dict[str, Any] = {
                "series": series,
                "status": result.get("status"),
                "cost_usd": result.get("total_cost_usd"),
                "reasoning": (result.get("reasoning") or "")[:2000],
            }
            cost += float(result.get("total_cost_usd") or 0)
            if result.get("error"):
                entry["error"] = str(result["error"])[:500]
            if result.get("status") == "proposed" and series in sweep.series:
                try:
                    change_set = SeriesChangeSet.model_validate(result["change_set"])
                    plans = apply_series_change_set(
                        self.db,
                        series,
                        change_set,
                        now=now,
                        dry_run=dry_run,
                        request_id=f"conference-deadline-sweep:{sweep.id}:{series}",
                    )
                except (ValidationError, DeadlineValidationError, CatalogError) as exc:
                    self.db.rollback()
                    entry["status"] = "invalid"
                    entry["error"] = str(exc)[:1000]
                else:
                    entry["editions"] = [p.to_dict() for p in plans]
                    changed = sum(len(p.changes) for p in plans)
                    entry["changes"] = changed
                    applied += 0 if dry_run else changed
            per_series.append(entry)
            logger.info("conference_deadline_sweep_result %s", entry)

        missing = sorted(set(sweep.series) - {r.get("series") for r in results})
        summary = {
            "stage": stage,
            "completed": completed,
            "missing_series": missing,
            "series": per_series,
        }
        if dry_run:
            return {"sweep_id": sweep.id, "dry_run": True, **summary}
        sweep.results = summary
        sweep.changes_applied = applied
        sweep.cost_usd = round(cost, 4)
        sweep.finished_at = now
        if stage == "COMPLETED" and completed and not missing:
            sweep.status = "applied"
        else:
            sweep.status = "failed"
            sweep.error = (
                f"Job ended {stage}; {len(missing)} of {len(sweep.series)} "
                "conferences returned no result"
            )
        self.db.commit()
        return {
            "sweep_id": sweep.id,
            "status": sweep.status,
            "changes_applied": applied,
            **summary,
        }


def run_scheduled_sweep(
    db: Session,
    settings: Settings,
    mode: Literal["weekly", "daily"],
    *,
    now: Optional[datetime] = None,
    api: Any = None,
) -> dict:
    """CRON entrypoint: collect finished sweeps, then launch one if none is running.

    The daily pass also skips its launch when any sweep started in the last
    20 hours (twice-daily timers collect a weekly sweep on the same day).
    """
    now = now or datetime.now(timezone.utc)
    sweeps = ConferenceDeadlineSweeps(db, settings, api)
    collected = sweeps.collect(now=now)
    report: dict[str, Any] = {"mode": mode, "collected": collected, "launched": None}
    if sweeps.running():
        report["skipped"] = "a sweep is still running"
        return report
    if mode == "daily":
        recent = (
            db.query(ConferenceDeadlineSweep.id)
            .filter(ConferenceDeadlineSweep.launched_at > now - timedelta(hours=20))
            .first()
        )
        if recent is not None:
            report["skipped"] = "a sweep was launched in the last 20 hours"
            return report
    manifests = sweeps.plan(mode, now=now)
    if not manifests:
        report["skipped"] = "no conference needs research"
        return report
    sweep = sweeps.launch(mode, manifests, now=now)
    report["launched"] = {
        "sweep_id": sweep.id,
        "hf_job_id": sweep.hf_job_id,
        "series": sweep.series,
        "url": f"https://huggingface.co/jobs/{job_credentials(settings).namespace}/{sweep.hf_job_id}",
    }
    return report
