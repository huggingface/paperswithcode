"""Run one deterministic CRON snapshot and at most one bounded repair."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.services.autonomous_alert_service import (
    AutonomousAlert,
    AutonomousAlertService,
)
from backend.services.autonomous_capabilities import (
    Capability,
    ResourceKind,
    ResourceRef,
)
from backend.services.autonomous_cron_operator import (
    AutonomousCronOperator,
    CronCandidateEditor,
    CronCandidateReviewer,
    CronCodexDiagnoser,
    CronSourceRepairPipeline,
    PwcCronRetrier,
    RepairResult,
    _finding_digest,
    build_cron_repair_contracts,
    build_cron_source_repair_targets,
)
from backend.services.autonomous_cron_probe import FindingState, HealthFinding
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    Operator,
    RunContext,
)
from backend.services.autonomous_policy import AutonomousPolicy
from backend.services.autonomous_digest_service import AutonomousDigestService
from backend.services.autonomous_release_service import AutonomousReleaseService
from backend.services.autonomous_source_repair import AutonomousSourceRepairService
from backend.services.cron_dashboard_snapshot_service import (
    CronDashboardSnapshotService,
)


HEALTH_FILE = "autonomous-cron-operator-health.json"


def _deliver_daily_digest(db, digest: dict[str, object]) -> None:
    settings = get_settings()
    service = AutonomousAlertService(
        primary_url=settings.autonomous_alert_slack_webhook_url,
        fallback_url=settings.autonomous_alert_fallback_webhook_url,
        digest_url=settings.autonomous_digest_webhook_url,
    )
    receipt = service.send_daily_digest(
        db,
        AutonomousAlert(
            event_kind="daily_digest",
            operator=Operator.CRON_HEALTH,
            resource_key=f"daily_digest_{digest['day']}",
            environment=settings.environment,
            release_id=settings.release_id or "unknown",
            occurred_at=datetime.now(UTC),
            runbook_url=(
                settings.autonomous_alert_runbook_url
                or "https://paperswithcode.co/docs/autonomous-operations"
            ),
        ),
        digest,
    )
    print(
        "AUTONOMOUS_DAILY_DIGEST "
        + json.dumps(
            {"delivery_id": str(receipt.id), "route": receipt.delivered_route},
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _finding(value: dict) -> HealthFinding:
    return HealthFinding(
        job_name=value["job_name"],
        plane=value["plane"],
        contract=value["contract"],
        state=FindingState(value["state"]),
        summary=value["summary"],
        evidence=value["evidence"],
        observed_at=value["observed_at"],
        operator_url=value["operator_url"],
        run_url=value["run_url"],
    )


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.new-{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    os.replace(temporary, path)


def _smoke(environment: str, _sha: str) -> bool:
    base = (
        "https://paperswithcode.co"
        if environment == "production"
        else "https://staging.paperswithcode.co"
    )
    try:
        for route in ("/health", "/", "/tasks", "/api/v1/papers/?page=1"):
            with urlopen(f"{base}{route}", timeout=15) as response:
                if not 200 <= response.status < 400:
                    return False
    except (OSError, URLError):
        return False
    return True


def _next_job(findings: tuple[HealthFinding, ...]) -> tuple[HealthFinding, ...]:
    candidates = sorted(
        {finding.job_name for finding in findings},
        key=lambda job: (
            not any(
                finding.job_name == job and finding.state is FindingState.DEGRADED
                for finding in findings
            ),
            job,
        ),
    )
    if not candidates:
        return ()
    selected = candidates[0]
    return tuple(finding for finding in findings if finding.job_name == selected)


def run(mode: str, *, health_file: Path) -> int:
    if mode not in {"strict", "daily"}:
        raise ValueError("Unknown autonomous CRON health mode")
    started = datetime.now(UTC)
    snapshot_service = CronDashboardSnapshotService()
    payload = snapshot_service.build_autonomous_snapshot(daily=mode == "daily")
    findings = tuple(_finding(value) for value in payload["findings"])
    selected = _next_job(
        tuple(
            finding for finding in findings if finding.state is not FindingState.HEALTHY
        )
    )
    if not selected:
        daily_digest = None
        if mode == "daily":
            with db_manager.session_local() as db:
                daily_digest = AutonomousDigestService().build_daily_digest(
                    db, datetime.now(UTC).date()
                )
                _deliver_daily_digest(db, daily_digest)
        _atomic_json(
            health_file,
            {
                "status": "healthy",
                "mode": mode,
                "started_at": started.isoformat(),
                "completed_at": datetime.now(UTC).isoformat(),
                "job": None,
                "reason_code": "healthy",
                **({"daily_digest": daily_digest} if daily_digest is not None else {}),
            },
        )
        return 0

    run_id = uuid.uuid4()
    context = RunContext(
        run_id,
        Operator.CRON_HEALTH,
        False,
        f"cron-operator-v1:{mode}",
    )
    contracts = build_cron_repair_contracts()
    daily_digest = None
    with db_manager.session_local() as db:
        repository = AutonomousOperationsRepository()
        policy = AutonomousPolicy(repository)
        retrier = PwcCronRetrier(context.run_id)

        def probe(job_name: str) -> tuple[HealthFinding, ...]:
            refreshed = snapshot_service.build_autonomous_snapshot(
                daily=mode == "daily"
            )
            return tuple(
                _finding(value)
                for value in refreshed["findings"]
                if value["job_name"] == job_name
            )

        settings = get_settings()
        alert_service = AutonomousAlertService(
            primary_url=settings.autonomous_alert_slack_webhook_url,
            fallback_url=settings.autonomous_alert_fallback_webhook_url,
            digest_url=settings.autonomous_digest_webhook_url,
        )

        def alert(event: dict[str, object]) -> None:
            reason = str(event.get("reason_code", "operator_failure"))
            event_kind = (
                "rollback"
                if "rollback" in reason or reason == "production_verification_failed"
                else "budget_threshold"
                if "budget" in reason
                else "operator_failure"
            )
            receipt = alert_service.send_autonomous_alert(
                db,
                AutonomousAlert(
                    event_kind=event_kind,
                    operator=Operator.CRON_HEALTH,
                    resource_key=str(event.get("job") or "cron_health"),
                    environment=settings.environment,
                    release_id=settings.release_id or "unknown",
                    occurred_at=datetime.now(UTC),
                    runbook_url=(
                        settings.autonomous_alert_runbook_url
                        or "https://paperswithcode.co/docs/autonomous-operations"
                    ),
                ),
            )
            print(
                "AUTONOMOUS_CRON_ALERT "
                + json.dumps(
                    {
                        "delivery_id": str(receipt.id),
                        "event_kind": receipt.event_kind,
                        "route": receipt.delivered_route,
                        "severity": receipt.severity,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )

        def repair(
            repair_context,
            job_name,
            contract,
            repair_findings,
        ) -> RepairResult:
            source = AutonomousSourceRepairService(
                repository=repository,
                source_repository=Path("/srv/paperswithcode/repository.git"),
                candidates_root=Path("/var/lib/paperswithcode/autonomous-candidates"),
                repair_targets=build_cron_source_repair_targets(contracts),
            )
            release = AutonomousReleaseService(
                repository=repository,
                smoke_verifier=_smoke,
            )
            reviewer = CronCandidateReviewer(
                db=db,
                context=repair_context,
                job_name=job_name,
            )

            def recovered(name: str) -> bool:
                decision = policy.authorize(
                    db,
                    repair_context,
                    Capability.RETRY_DECLARED_CRON,
                    ResourceRef(ResourceKind.DECLARED_CRON, name, True),
                )
                if not decision.allowed:
                    return False
                before_digest = _finding_digest(tuple(repair_findings))
                repository.append_action(
                    db,
                    context=repair_context,
                    capability=Capability.RETRY_DECLARED_CRON.value,
                    reason_code="retry_authorized",
                    resource_kind=ResourceKind.DECLARED_CRON.value,
                    resource_identifier=name,
                    before_digest=before_digest,
                    after_digest=before_digest,
                    now=datetime.now(UTC),
                )
                db.commit()
                return retrier(name) == 0 and all(
                    item.state is FindingState.HEALTHY for item in probe(name)
                )

            return CronSourceRepairPipeline(
                db=db,
                source_service=source,
                release_service=release,
                policy=policy,
                editor=CronCandidateEditor(db=db),
                reviewer=reviewer,
                recovery_verifier=recovered,
            )(repair_context, job_name, contract, repair_findings)

        outcome = AutonomousCronOperator(
            db=db,
            repository=repository,
            policy=policy,
            diagnose=CronCodexDiagnoser(db=db),
            retry=retrier,
            probe=probe,
            source_repair=repair,
            alert=alert,
            contracts=contracts,
        ).handle_cron_findings(context, selected)
        if mode == "daily":
            daily_digest = AutonomousDigestService().build_daily_digest(
                db, datetime.now(UTC).date()
            )
            _deliver_daily_digest(db, daily_digest)

    monitoring_only = outcome.reason_code in {
        "manual_mode",
        "operator_disabled",
        "dry_run",
    }
    recorded_status = "monitoring_only" if monitoring_only else outcome.status
    _atomic_json(
        health_file,
        {
            "status": recorded_status,
            "mode": mode,
            "started_at": started.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "job": outcome.job_name,
            "reason_code": outcome.reason_code,
            "before_digest": outcome.before_digest,
            "after_digest": outcome.after_digest,
            "published_sha": outcome.published_sha,
            "rollback_performed": outcome.rollback_performed,
            "run_id": str(run_id),
            **({"daily_digest": daily_digest} if daily_digest is not None else {}),
        },
    )
    return (
        0
        if recorded_status
        in {"monitoring_only", "noop", "runtime_recovered", "source_repaired"}
        else 1
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("strict", "daily"), required=True)
    parser.add_argument("--health-file", type=Path)
    args = parser.parse_args()
    health_file = (
        args.health_file
        or Path(
            os.environ.get(
                "PWC_CRON_LOG_DIR",
                "/var/lib/paperswithcode/production/cron-logs",
            )
        )
        / HEALTH_FILE
    )
    try:
        return run(args.mode, health_file=health_file)
    except Exception as error:
        _atomic_json(
            health_file,
            {
                "status": "failed",
                "mode": args.mode,
                "completed_at": datetime.now(UTC).isoformat(),
                "error_class": type(error).__name__[:128],
            },
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
