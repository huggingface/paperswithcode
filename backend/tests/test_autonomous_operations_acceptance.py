from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.models.database import (
    AutonomousControlEvent,
    AutonomousOperatorState,
    ChatReliabilityBaseline,
)
from backend.services.autonomous_acceptance_service import (
    AcceptanceNotReady,
    AutonomousAcceptanceService,
)
from backend.services.autonomous_capabilities import CAPABILITY_MANIFESTS
from backend.services.autonomous_operations_repository import (
    AutonomousOperationsRepository,
    Operator,
)


NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    AutonomousOperatorState.__table__.create(engine)
    AutonomousControlEvent.__table__.create(engine)
    ChatReliabilityBaseline.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add_all(
            [
                AutonomousOperatorState(
                    operator="global",
                    enabled=False,
                    manual_mode=False,
                    revision=1,
                    updated_by="system:migration",
                    updated_at=NOW,
                ),
                *(
                    AutonomousOperatorState(
                        operator=operator.value,
                        enabled=False,
                        manual_mode=False,
                        revision=1,
                        updated_by="system:migration",
                        updated_at=NOW,
                    )
                    for operator in Operator
                ),
            ]
        )
        session.commit()
        yield session


def record(
    service: AutonomousAcceptanceService,
    db: Session,
    operator: Operator,
    gate: str,
    index: int,
    *,
    at: datetime = NOW,
) -> None:
    service.record_evidence(
        db,
        operator=operator,
        gate_code=gate,
        evidence_digest=f"{index:064x}",
        actor="admin:owner",
        occurred_at=at,
    )


def test_submission_enablement_requires_all_drills_and_seven_distinct_shadow_days(db):
    service = AutonomousAcceptanceService()
    for index, gate in enumerate(
        (
            "oldest_first",
            "max_batch",
            "human_only_deferral",
            "external_no_enrichment",
            "callback_idempotency",
        ),
        start=1,
    ):
        record(service, db, Operator.SUBMISSIONS, gate, index)
    for day in range(6):
        record(
            service,
            db,
            Operator.SUBMISSIONS,
            "shadow_comparison",
            100 + day,
            at=NOW - timedelta(days=day),
        )

    readiness = service.readiness(db, Operator.SUBMISSIONS)
    assert readiness.ready is False
    assert readiness.shadow_days == 6
    with pytest.raises(AcceptanceNotReady):
        service.set_operator_enabled(
            db,
            operator=Operator.SUBMISSIONS,
            enabled=True,
            expected_revision=1,
            actor="admin:owner",
            now=NOW,
        )

    record(
        service,
        db,
        Operator.SUBMISSIONS,
        "shadow_comparison",
        106,
        at=NOW - timedelta(days=6),
    )
    assert service.readiness(db, Operator.SUBMISSIONS).ready is True
    state = service.set_operator_enabled(
        db,
        operator=Operator.SUBMISSIONS,
        enabled=True,
        expected_revision=1,
        actor="admin:owner",
        now=NOW,
    )
    assert state.enabled[Operator.SUBMISSIONS] is True


def test_cron_enablement_requires_every_recovery_and_rollback_drill(db):
    service = AutonomousAcceptanceService()
    gates = (
        "shadow_diagnosis",
        "missed_schedule",
        "stale_log",
        "stale_durable_data",
        "safe_retry",
        "rejected_schema_change",
        "source_repair",
        "failed_production_verification",
        "rollback",
    )
    for index, gate in enumerate(gates, start=1):
        record(service, db, Operator.CRON_HEALTH, gate, index)

    assert service.readiness(db, Operator.CRON_HEALTH).ready is True
    service.set_operator_enabled(
        db,
        operator=Operator.CRON_HEALTH,
        enabled=True,
        expected_revision=1,
        actor="admin:owner",
        now=NOW,
    )
    assert db.get(AutonomousOperatorState, "cron_health").enabled is True


def test_curation_enablement_requires_every_dispatch_and_callback_drill(db):
    service = AutonomousAcceptanceService()
    gates = (
        "dispatcher_preflight",
        "capability_isolation",
        "callback_idempotency",
        "paused_callback_apply",
    )

    for index, gate in enumerate(gates[:-1], start=1):
        record(service, db, Operator.CURATION, gate, index)

    readiness = service.readiness(db, Operator.CURATION)
    assert readiness.ready is False
    assert readiness.missing_gates == ("paused_callback_apply",)
    with pytest.raises(AcceptanceNotReady):
        service.set_operator_enabled(
            db,
            operator=Operator.CURATION,
            enabled=True,
            expected_revision=1,
            actor="admin:owner",
            now=NOW,
        )

    record(service, db, Operator.CURATION, gates[-1], len(gates))
    assert service.readiness(db, Operator.CURATION).ready is True
    service.set_operator_enabled(
        db,
        operator=Operator.CURATION,
        enabled=True,
        expected_revision=1,
        actor="admin:owner",
        now=NOW,
    )
    assert db.get(AutonomousOperatorState, "curation").enabled is True


def test_global_manual_mode_still_blocks_mutation_after_acceptance(db):
    repository = AutonomousOperationsRepository()
    service = AutonomousAcceptanceService(repository)
    for index, gate in enumerate(
        (
            "shadow_diagnosis",
            "missed_schedule",
            "stale_log",
            "stale_durable_data",
            "safe_retry",
            "rejected_schema_change",
            "source_repair",
            "failed_production_verification",
            "rollback",
        ),
        start=1,
    ):
        record(service, db, Operator.CRON_HEALTH, gate, index)
    state = service.set_operator_enabled(
        db,
        operator=Operator.CRON_HEALTH,
        enabled=True,
        expected_revision=1,
        actor="admin:owner",
        now=NOW,
    )
    repository.set_manual_mode(
        db,
        enabled=True,
        expected_revision=state.revision,
        actor="admin:owner",
        now=NOW,
    )

    from backend.services.autonomous_operations_repository import (
        ManualModeEnabled,
        RunContext,
    )
    import uuid

    with pytest.raises(ManualModeEnabled):
        repository.assert_mutation_allowed(
            db,
            RunContext(uuid.uuid4(), Operator.CRON_HEALTH, False, "acceptance-test"),
        )
    assert db.get(AutonomousOperatorState, "cron_health").enabled is True


def test_no_capability_manifest_can_create_or_mutate_taxonomy():
    prohibited = {
        "create_task",
        "create_method",
        "create_benchmark",
        "create_dataset",
        "create_metric",
        "create_conference",
        "mutate_task",
        "mutate_method",
        "mutate_benchmark",
        "mutate_dataset",
        "mutate_metric",
        "mutate_conference",
    }
    declared = {
        capability.value
        for capabilities in CAPABILITY_MANIFESTS.values()
        for capability in capabilities
    }
    assert prohibited.isdisjoint(declared)


def test_rollout_units_are_packaged_but_not_implicitly_enabled():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for timer in (
        root / "deploy/autonomous/submission-review.timer",
        root / "deploy/autonomous/autonomous-cron-health.timer",
        root / "deploy/autonomous/autonomous-cron-audit.timer",
    ):
        text = timer.read_text(encoding="utf-8")
        assert "WantedBy=timers.target" in text
    installer = (root / "deploy/install_host_layout.py").read_text(encoding="utf-8")
    assert 'systemctl", "enable' not in installer
    assert 'systemctl", "start' not in installer


def test_chat_acceptance_stays_locked_without_recorded_scalable_baseline(db):
    service = AutonomousAcceptanceService()

    readiness = service.readiness(db, Operator.CHAT_RELIABILITY)

    assert readiness.ready is False
    assert "scalable_chat_baseline_reconciliation_pending" in readiness.missing_gates
    with pytest.raises(ValueError, match="qualified scalable-chat baseline"):
        record(
            service,
            db,
            Operator.CHAT_RELIABILITY,
            "qualified_baseline",
            1,
        )
    with pytest.raises(AcceptanceNotReady):
        service.set_operator_enabled(
            db,
            operator=Operator.CHAT_RELIABILITY,
            enabled=True,
            expected_revision=1,
            actor="admin:owner",
            now=NOW,
        )


def test_chat_acceptance_uses_recorded_exact_qualified_baseline(db):
    repository = AutonomousOperationsRepository()
    service = AutonomousAcceptanceService(repository)
    repository.qualify_chat_baseline(
        db,
        sha="0a5e6338caece3c71ffc1c2e8cac507e86d13e8b",
        actor="admin:owner",
        expected_revision=0,
        now=NOW,
    )

    for index, gate in enumerate(
        (
            "qualified_baseline",
            "qualified_fallback",
            "atomic_provider_manifest",
            "billing_auth_failover",
            "threshold_failover",
            "fallback_restoration",
            "broken_stream",
            "persistence_reopen",
            "independent_review_rejection",
            "staging_canary_failure",
            "production_rollback",
            "privacy_redaction",
            "retry_exhaustion",
            "daily_review_cycle",
            "synthetic_cycle",
        ),
        start=1,
    ):
        record(service, db, Operator.CHAT_RELIABILITY, gate, index)

    readiness = service.readiness(db, Operator.CHAT_RELIABILITY)
    assert readiness.ready is True
    assert "qualified_baseline" in readiness.passed_gates
