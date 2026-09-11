from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.models.database import (
    AutonomousAction,
    AutonomousAlertDelivery,
    AutonomousControlEvent,
    AutonomousExecutionIntent,
    AutonomousOperatorState,
    AutonomousRepairLease,
    AutonomousRun,
)
from backend.services.autonomous_alert_service import (
    AlertDeliveryError,
    AutonomousAlert,
    AutonomousAlertService,
)
from backend.services.autonomous_digest_service import (
    AutonomousBudgetService,
    AutonomousDigestService,
    BudgetLimits,
)
from backend.services.autonomous_operations_repository import Operator


NOW = datetime(2026, 8, 28, 12, tzinfo=UTC)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    for table in (
        AutonomousOperatorState,
        AutonomousExecutionIntent,
        AutonomousRun,
        AutonomousAction,
        AutonomousControlEvent,
        AutonomousRepairLease,
        AutonomousAlertDelivery,
    ):
        table.__table__.create(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    session.add_all(
        [
            AutonomousOperatorState(
                operator="global",
                enabled=False,
                manual_mode=False,
                revision=1,
                updated_by="system:test",
                updated_at=NOW,
            ),
            *(
                AutonomousOperatorState(
                    operator=operator.value,
                    enabled=True,
                    manual_mode=False,
                    revision=1,
                    updated_by="system:test",
                    updated_at=NOW,
                )
                for operator in Operator
            ),
        ]
    )
    session.commit()
    return session


def alert(event_kind: str = "operator_failure") -> AutonomousAlert:
    return AutonomousAlert(
        event_kind=event_kind,
        operator=Operator.CRON_HEALTH,
        resource_key="calculate_trending_scores",
        environment="production",
        release_id="a" * 12 + "-production",
        occurred_at=NOW,
        runbook_url="https://paperswithcode.co/docs/autonomous#cron",
    )


def test_urgent_alert_uses_acknowledged_primary_and_persists_content_free_receipt(db):
    calls = []
    service = AutonomousAlertService(
        primary_url="https://slack.test/primary",
        fallback_url="https://alerts.test/fallback",
        sender=lambda url, payload: calls.append((url, payload)) or 200,
    )

    receipt = service.send_autonomous_alert(db, alert())

    assert receipt.severity == "high"
    assert receipt.delivered_route == "primary"
    assert [call[0] for call in calls] == ["https://slack.test/primary"]
    assert "calculate_trending_scores" not in calls[0][1]["text"]
    row = db.get(AutonomousAlertDelivery, receipt.id)
    assert row.resource_digest != "calculate_trending_scores"
    assert not hasattr(row, "payload")


def test_curation_alert_persists_operator_receipt(db):
    service = AutonomousAlertService(
        primary_url="https://slack.test/primary",
        fallback_url="https://alerts.test/fallback",
        sender=lambda _url, _payload: 200,
    )
    curation_alert = AutonomousAlert(
        event_kind="operator_failure",
        operator=Operator.CURATION,
        resource_key="trending-model-candidate",
        environment="production",
        release_id="a" * 12 + "-production",
        occurred_at=NOW,
        runbook_url="https://paperswithcode.co/docs/autonomous#curation",
    )

    receipt = service.send_autonomous_alert(db, curation_alert)

    assert db.get(AutonomousAlertDelivery, receipt.id).operator == "curation"


def test_unacknowledged_primary_uses_distinct_fallback_and_deduplicates(db):
    calls = []

    def sender(url, _payload):
        calls.append(url)
        return 503 if "slack" in url else 202

    service = AutonomousAlertService(
        primary_url="https://slack.test/primary",
        fallback_url="https://alerts.test/fallback",
        sender=sender,
    )

    first = service.send_autonomous_alert(db, alert("rollback"))
    repeated = service.send_autonomous_alert(db, alert("rollback"))

    assert first.delivered_route == "fallback"
    assert repeated.id == first.id
    assert calls == ["https://slack.test/primary", "https://alerts.test/fallback"]

    with pytest.raises(IntegrityError, match="append-only"):
        db.execute(
            update(AutonomousAlertDelivery)
            .where(AutonomousAlertDelivery.id == first.id)
            .values(delivered_route="none")
        )
    db.rollback()


def test_urgent_alert_fails_if_neither_route_acknowledges(db):
    service = AutonomousAlertService(
        primary_url="https://slack.test/primary",
        fallback_url="https://alerts.test/fallback",
        sender=lambda _url, _payload: 500,
    )

    with pytest.raises(AlertDeliveryError):
        service.send_autonomous_alert(db, alert("both_provider_outage"))
    receipt = db.query(AutonomousAlertDelivery).one()
    assert receipt.delivered_route == "none"
    assert receipt.primary_state == "failed"
    assert receipt.fallback_state == "failed"
    with pytest.raises(AlertDeliveryError):
        service.send_autonomous_alert(db, alert("both_provider_outage"))


def test_alert_contract_rejects_unbounded_or_secret_bearing_fields():
    with pytest.raises(ValueError):
        AutonomousAlert(
            event_kind="operator_failure",
            operator=Operator.CRON_HEALTH,
            resource_key="sk-secret-value",
            environment="production",
            release_id="release",
            occurred_at=NOW,
            runbook_url="https://paperswithcode.co/runbook",
        )
    with pytest.raises(ValueError, match="HTTPS"):
        AutonomousAlertService(
            primary_url="http://alerts.test/insecure",
            fallback_url="https://alerts.test/fallback",
        )


def add_run(
    db,
    *,
    operator: Operator,
    cost: str,
    tokens: int,
    created_at: datetime,
    status: str = "completed",
):
    run = AutonomousRun(
        id=uuid.uuid4(),
        operator=operator.value,
        dry_run=False,
        manifest_revision="test-v1",
        status=status,
        input_tokens=tokens // 2,
        output_tokens=tokens - tokens // 2,
        cost_usd=Decimal(cost),
        result_digest="b" * 64,
        exit_classification=status,
        capability_requests=[],
        evidence_digests=[],
        pricing_revision="test",
        pricing_policy_digest="c" * 64,
        created_at=created_at,
    )
    db.add(run)
    db.flush()
    return run


def test_daily_digest_is_aggregate_content_free_and_mobile_sized(db):
    run = add_run(
        db,
        operator=Operator.SUBMISSIONS,
        cost="1.25",
        tokens=1200,
        created_at=NOW,
    )
    db.add(
        AutonomousAction(
            id=uuid.uuid4(),
            run_id=run.id,
            operator=run.operator,
            capability="apply_submission_decision",
            reason_code="approved",
            resource_kind="pending_edit",
            resource_identifier="private-row-id",
            before_digest="d" * 64,
            after_digest="e" * 64,
            created_at=NOW,
        )
    )
    db.commit()

    digest = AutonomousDigestService(
        pending_human_counter=lambda _db: 7
    ).build_daily_digest(db, date(2026, 8, 28))

    assert digest["cost_usd"] == "1.250000000"
    assert digest["pending_human_only"] == 7
    assert digest["runs_by_status"] == {"completed": 1}
    assert digest["actions_by_reason"] == {"approved": 1}
    assert "private-row-id" not in digest["text"]
    assert len(digest["text"]) < 1800


def test_daily_digest_uses_distinct_mobile_route_and_rejects_unbounded_fields(db):
    digest = AutonomousDigestService(
        pending_human_counter=lambda _db: 0,
        now=lambda: NOW,
    ).build_daily_digest(db, date(2026, 8, 28))
    calls = []
    service = AutonomousAlertService(
        primary_url="https://slack.test/primary",
        fallback_url="https://alerts.test/fallback",
        digest_url="https://codex-mobile.test/digest",
        sender=lambda url, payload: calls.append((url, payload)) or 204,
    )

    receipt = service.send_daily_digest(db, alert("daily_digest"), digest)

    assert receipt.delivered_route == "primary"
    assert calls == [("https://codex-mobile.test/digest", {"text": digest["text"]})]
    invalid = dict(digest)
    invalid["disabled_operators"] = ["submission-content"]
    with pytest.raises(ValueError, match="aggregates"):
        service.send_daily_digest(
            db,
            AutonomousAlert(
                event_kind="daily_digest",
                operator=Operator.CRON_HEALTH,
                resource_key="different_digest",
                environment="production",
                release_id="release",
                occurred_at=NOW,
                runbook_url="https://paperswithcode.co/runbook",
            ),
            invalid,
        )


def test_unacknowledged_mobile_digest_emits_urgent_delivery_alert(db):
    digest = AutonomousDigestService(
        pending_human_counter=lambda _db: 0,
        now=lambda: NOW,
    ).build_daily_digest(db, date(2026, 8, 28))
    calls = []

    def sender(url, _payload):
        calls.append(url)
        return 503 if "codex-mobile" in url else 200

    service = AutonomousAlertService(
        primary_url="https://slack.test/primary",
        fallback_url="https://alerts.test/fallback",
        digest_url="https://codex-mobile.test/digest",
        sender=sender,
    )

    receipt = service.send_daily_digest(db, alert("daily_digest"), digest)

    assert receipt.delivered_route == "none"
    assert calls == [
        "https://codex-mobile.test/digest",
        "https://slack.test/primary",
    ]
    assert {row.event_kind for row in db.query(AutonomousAlertDelivery)} == {
        "daily_digest",
        "operator_failure",
    }


def test_budget_exhaustion_disables_only_mutation_and_is_idempotent(db):
    add_run(
        db,
        operator=Operator.CRON_HEALTH,
        cost="4.50",
        tokens=9000,
        created_at=NOW - timedelta(minutes=5),
    )
    db.commit()
    service = AutonomousBudgetService(
        limits=BudgetLimits(
            per_run_cost_usd=Decimal("2"),
            per_run_tokens=5000,
            daily_cost_usd=Decimal("5"),
            daily_tokens=10000,
            monthly_cost_usd=Decimal("50"),
            monthly_tokens=100000,
        ),
        now=lambda: NOW,
    )

    first = service.enforce_before_run(
        db,
        operator=Operator.CRON_HEALTH,
        requested_cost_usd=Decimal("1"),
        requested_tokens=1000,
    )
    second = service.enforce_before_run(
        db,
        operator=Operator.CRON_HEALTH,
        requested_cost_usd=Decimal("1"),
        requested_tokens=1000,
    )

    assert first.allowed is False
    assert first.reason_code == "daily_cost_limit"
    assert second.transitioned is False
    assert db.get(AutonomousOperatorState, "cron_health").enabled is False
    assert db.get(AutonomousOperatorState, "global").manual_mode is False
    assert db.get(AutonomousOperatorState, "submissions").enabled is True


def test_budget_exhaustion_keeps_content_free_alert_callback_active(db):
    alerts = []
    service = AutonomousBudgetService(
        limits=BudgetLimits(
            per_run_cost_usd=Decimal("1"),
            per_run_tokens=1000,
            daily_cost_usd=Decimal("2"),
            daily_tokens=2000,
            monthly_cost_usd=Decimal("3"),
            monthly_tokens=3000,
        ),
        now=lambda: NOW,
        on_exhausted=lambda _db, operator, reason, at: alerts.append(
            (operator, reason, at)
        ),
    )

    decision = service.enforce_before_run(
        db,
        operator=Operator.SUBMISSIONS,
        requested_cost_usd=Decimal("1.50"),
        requested_tokens=500,
    )

    assert decision.reason_code == "per_run_cost_limit"
    assert alerts == [(Operator.SUBMISSIONS, "per_run_cost_limit", NOW)]


def test_budget_limits_load_all_six_environment_ceilings():
    limits = BudgetLimits.from_environ(
        {
            "PWC_AUTONOMOUS_PER_RUN_COST_USD": "1",
            "PWC_AUTONOMOUS_PER_RUN_TOKENS": "2",
            "PWC_AUTONOMOUS_DAILY_COST_USD": "3",
            "PWC_AUTONOMOUS_DAILY_TOKENS": "4",
            "PWC_AUTONOMOUS_MONTHLY_COST_USD": "5",
            "PWC_AUTONOMOUS_MONTHLY_TOKENS": "6",
        }
    )

    assert limits == BudgetLimits(Decimal("1"), 2, Decimal("3"), 4, Decimal("5"), 6)


def test_cumulative_budget_is_shared_and_reserves_unfinished_intents(db):
    add_run(
        db,
        operator=Operator.SUBMISSIONS,
        cost="3.00",
        tokens=3000,
        created_at=NOW - timedelta(minutes=10),
    )
    db.add(
        AutonomousExecutionIntent(
            run_id=uuid.uuid4(),
            operator=Operator.CHAT_RELIABILITY.value,
            dry_run=False,
            manifest_revision="chat-review-v1",
            request_digest="a" * 64,
            evidence_digests=[],
            model_alias="diagnosis",
            budget_usd=Decimal("1.50"),
            pricing_policy_digest="b" * 64,
            created_at=NOW - timedelta(minutes=5),
        )
    )
    db.commit()
    service = AutonomousBudgetService(
        limits=BudgetLimits(
            per_run_cost_usd=Decimal("2"),
            per_run_tokens=5000,
            daily_cost_usd=Decimal("5"),
            daily_tokens=10000,
            monthly_cost_usd=Decimal("50"),
            monthly_tokens=100000,
        ),
        now=lambda: NOW,
    )

    decision = service.enforce_before_run(
        db,
        operator=Operator.CRON_HEALTH,
        requested_cost_usd=Decimal("1"),
        requested_tokens=1000,
    )

    assert decision.allowed is False
    assert decision.reason_code == "daily_cost_limit"
    assert decision.daily_cost_usd == Decimal("4.50")
    assert decision.daily_tokens == 8000
    assert db.get(AutonomousOperatorState, "cron_health").enabled is False
    assert db.get(AutonomousOperatorState, "submissions").enabled is True
    assert db.get(AutonomousOperatorState, "chat_reliability").enabled is True
