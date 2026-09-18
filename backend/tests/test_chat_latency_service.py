from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import (
    Base,
    ChatMessageRecord,
    ChatSession,
    ChatTurnJob,
    ChatTurnLatency,
)
from backend.services.chat_latency_service import ChatLatencyService


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def _settings():
    return SimpleNamespace(
        release_id="release-test",
        chat_modal_image_version="im-test",
        chat_worker_contract_version="worker-v2",
        chat_pwc_cli_version="0.2.0",
        chat_system_prompt_sha256="a" * 64,
        chat_sandbox_cpu=0.125,
        chat_sandbox_memory_mib=512,
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            ChatSession.__table__,
            ChatMessageRecord.__table__,
            ChatTurnLatency.__table__,
            ChatTurnJob.__table__,
        ],
    )
    with Session(engine) as session:
        yield session


def _session(db: Session, owner_id: str = "owner-1") -> uuid.UUID:
    session_id = uuid.uuid4()
    db.add(
        ChatSession(
            id=session_id,
            hf_user_id=owner_id,
            hf_username="owner",
            selected_model="model",
            execution_backend="modal_cli",
        )
    )
    db.flush()
    return session_id


def _admit(
    db: Session,
    *,
    session_id: uuid.UUID,
    request_id: uuid.UUID | None = None,
    turn_id: uuid.UUID | None = None,
    is_new_chat: bool = True,
) -> ChatTurnLatency:
    return ChatLatencyService(db).admit(
        turn_id=turn_id or uuid.uuid4(),
        session_id=session_id,
        request_id=str(request_id or uuid.uuid4()),
        settings=_settings(),
        model_route="provider/model:route",
        execution_backend="modal_cli",
        is_new_chat=is_new_chat,
    )


def _user_message(
    db: Session,
    *,
    session_id: uuid.UUID,
    turn_id: uuid.UUID,
    status: str = "generating",
) -> ChatMessageRecord:
    message = ChatMessageRecord(
        id=uuid.uuid4(),
        session_id=session_id,
        turn_id=turn_id,
        sequence=1,
        role="user",
        content="content intentionally omitted from telemetry",
        status=status,
    )
    db.add(message)
    db.flush()
    return message


def test_admit_stores_only_required_opaque_identifiers_and_versions(db):
    session_id = _session(db)
    turn_id = uuid.uuid4()
    request_id = uuid.uuid4()

    row = _admit(
        db,
        session_id=session_id,
        turn_id=turn_id,
        request_id=request_id,
        is_new_chat=False,
    )

    assert row.turn_id == turn_id
    assert row.request_id == request_id
    assert row.chat_session_id == session_id
    assert row.traffic_class == "followup"
    assert row.acquisition_outcome == "pending"
    assert row.model_route == "provider/model:route"
    assert row.app_release_id == "release-test"
    assert row.sandbox_image_version == "im-test"
    assert row.worker_contract_version == "worker-v2"
    assert row.pwc_cli_version == "0.2.0"
    assert row.system_prompt_sha256 == "a" * 64
    assert float(row.sandbox_cpu_request) == 0.125
    assert row.sandbox_memory_request_mib == 512
    columns = set(ChatTurnLatency.__table__.columns.keys())
    assert not columns & {
        "prompt",
        "user_id",
        "owner_id",
        "capability",
        "command",
        "tool_output",
        "provider_token",
        "transcript",
    }


def test_record_phase_and_finalize_are_first_write_only(db):
    session_id = _session(db)
    request_id = uuid.uuid4()
    row = _admit(db, session_id=session_id, request_id=request_id)
    service = ChatLatencyService(db)

    assert service.record_phase(
        str(request_id),
        "pool_lookup_completed",
        17,
        acquisition_outcome="pool_hit",
    )
    assert not service.record_phase(
        str(request_id),
        "pool_lookup_completed",
        99,
        acquisition_outcome="pool_miss",
    )
    assert service.finalize(str(request_id), "complete", 321)
    assert not service.finalize(str(request_id), "error", 400)
    db.refresh(row)

    assert row.pool_lookup_completed_ms == 17
    assert row.acquisition_outcome == "pool_hit"
    assert row.terminal_status == "complete"
    assert row.total_ms == 321
    assert float(row.estimated_active_cost_usd) > 0
    assert row.completed_at is not None
    assert not service.record_phase(str(request_id), "first_worker_delta", 200)


def test_failed_pool_assignment_moves_out_of_hit_cohort(db):
    session_id = _session(db)
    request_id = uuid.uuid4()
    row = _admit(db, session_id=session_id, request_id=request_id)
    service = ChatLatencyService(db)
    assert service.record_phase(
        str(request_id),
        "pool_lookup_completed",
        17,
        acquisition_outcome="pool_hit",
    )

    assert service.record_pool_assignment_fallback(str(request_id))
    assert not service.record_pool_assignment_fallback(str(request_id))
    db.refresh(row)

    assert row.acquisition_outcome == "pool_miss"
    assert row.pool_miss_reason == "unhealthy_blank"


def test_warm_fallback_diagnostics_are_bounded_and_content_free(db):
    session_id = _session(db)
    request_id = uuid.uuid4()
    row = _admit(db, session_id=session_id, request_id=request_id)
    service = ChatLatencyService(db)

    assert service.record_phase(
        str(request_id),
        "assignment_fallback",
        41,
        failure_stage="dispatch_write",
        failure_class="BrokenPipeError",
        attempt_kind="pool",
    )
    db.refresh(row)
    assert row.retry_overhead_ms == 41
    assert row.failure_stage == "dispatch_write"
    assert row.failure_class == "BrokenPipeError"
    assert row.attempt_kind == "pool"
    assert not {
        "prompt",
        "capability",
        "assignment_token",
        "transcript",
        "user_content",
    } & set(ChatTurnLatency.__table__.columns.keys())

    with pytest.raises(ValueError, match="Incomplete warm assignment diagnostics"):
        service.record_phase(
            str(uuid.uuid4()),
            "assignment_fallback",
            1,
            failure_stage="agent_stream",
        )


def test_ttft_semantics_and_pool_cohorts_are_content_free(db):
    session_id = _session(db)
    request_id = uuid.uuid4()
    row = _admit(db, session_id=session_id, request_id=request_id)
    service = ChatLatencyService(db)

    assert service.record_phase(
        str(request_id),
        "first_semantic_event",
        123,
        first_semantic_event_class="reasoning",
    )
    assert service.record_phase(
        str(request_id),
        "sandbox_acquisition_ms",
        20,
        acquisition_outcome="pool_miss",
        pool_miss_reason="incompatible_profile",
    )
    assert service.update_browser(
        "owner-1",
        str(request_id),
        SimpleNamespace(
            submission_to_stream_start_ms=None,
            submission_to_first_visible_delta_ms=150,
            submission_to_first_reasoning_delta_ms=175,
            submission_to_first_tool_call_ms=300,
            submission_to_first_answer_delta_ms=450,
            terminal_classification=None,
        ),
    )
    db.refresh(row)

    assert row.first_semantic_event_ms == 123
    assert row.first_semantic_event_class == "reasoning"
    assert row.pool_miss_reason == "incompatible_profile"
    assert row.browser_first_reasoning_delta_ms == 175
    assert row.browser_first_tool_call_ms == 300
    assert row.browser_first_answer_delta_ms == 450


def test_mark_qualification_is_explicit_validated_and_first_write_only(db):
    session_id = _session(db)
    request_id = uuid.uuid4()
    row = _admit(db, session_id=session_id, request_id=request_id)
    service = ChatLatencyService(db)
    scope_id = uuid.uuid4()

    assert service.mark_qualification(
        str(request_id),
        scope_id=scope_id,
        run_id="run-123",
        profile="32-functional-turns",
        scenario="forced_failure",
        workload="read",
    )
    assert not service.mark_qualification(
        str(request_id),
        scope_id=uuid.uuid4(),
        run_id="run-456",
        profile="100-immediate-admission",
        scenario="reliability",
        workload="no_tool",
    )
    with pytest.raises(ValueError, match="Unsupported qualification scenario"):
        service.mark_qualification(
            str(uuid.uuid4()),
            scope_id=scope_id,
            run_id="run-123",
            profile="32-functional-turns",
            scenario="unknown",
            workload="read",
        )
    db.refresh(row)

    assert row.qualification_run_id == "run-123"
    assert row.qualification_scope_id == scope_id
    assert row.qualification_profile == "32-functional-turns"
    assert row.qualification_scenario == "forced_failure"
    assert row.qualification_workload == "read"


def test_reconcile_stale_turns_repairs_expired_projection_and_latency(db):
    now = datetime(2026, 7, 31, 12, tzinfo=UTC)
    session_id = _session(db)
    turn_id = uuid.uuid4()
    row = _admit(db, session_id=session_id, turn_id=turn_id)
    message = _user_message(db, session_id=session_id, turn_id=turn_id)
    session = db.get(ChatSession, session_id)
    session.active_turn_id = turn_id
    session.active_turn_expires_at = now - timedelta(seconds=1)
    row.admitted_at = now - timedelta(minutes=4)
    db.flush()

    reconciled = ChatLatencyService(db).reconcile_stale_turns(now=now)
    db.refresh(row)
    db.refresh(message)
    db.refresh(session)

    assert reconciled == {"complete": 0, "error": 0, "interrupted": 1}
    assert row.terminal_status == "interrupted"
    assert row.total_ms == 239_000
    assert row.completed_at.replace(tzinfo=UTC) == now - timedelta(seconds=1)
    assert float(row.estimated_active_cost_usd) > 0
    assert message.status == "interrupted"
    assert message.error_code == "lease_expired"
    assert session.active_turn_id is None
    assert session.active_turn_expires_at is None


@pytest.mark.parametrize(
    ("message_status", "expected"),
    [("complete", "complete"), ("error", "error"), ("interrupted", "interrupted")],
)
def test_reconcile_stale_turns_follows_persisted_terminal_projection(
    db, message_status, expected
):
    now = datetime(2026, 7, 31, 12, tzinfo=UTC)
    session_id = _session(db)
    turn_id = uuid.uuid4()
    row = _admit(db, session_id=session_id, turn_id=turn_id)
    _user_message(
        db,
        session_id=session_id,
        turn_id=turn_id,
        status=message_status,
    )
    row.admitted_at = now - timedelta(minutes=1)
    session = db.get(ChatSession, session_id)
    session.updated_at = now - timedelta(minutes=1)
    db.flush()

    reconciled = ChatLatencyService(db).reconcile_stale_turns(now=now)
    db.refresh(row)

    assert reconciled[expected] == 1
    assert row.terminal_status == expected


def test_reconcile_stale_turns_allows_stream_finalizer_grace(db):
    now = datetime(2026, 7, 31, 12, tzinfo=UTC)
    session_id = _session(db)
    turn_id = uuid.uuid4()
    row = _admit(db, session_id=session_id, turn_id=turn_id)
    _user_message(db, session_id=session_id, turn_id=turn_id, status="complete")
    session = db.get(ChatSession, session_id)
    session.updated_at = now - timedelta(seconds=5)
    db.flush()

    reconciled = ChatLatencyService(db).reconcile_stale_turns(now=now)
    db.refresh(row)

    assert reconciled == {"complete": 0, "error": 0, "interrupted": 0}
    assert row.terminal_status == "running"


def test_reconcile_stale_turns_leaves_an_unexpired_active_turn_running(db):
    now = datetime(2026, 7, 31, 12, tzinfo=UTC)
    session_id = _session(db)
    turn_id = uuid.uuid4()
    row = _admit(db, session_id=session_id, turn_id=turn_id)
    _user_message(db, session_id=session_id, turn_id=turn_id)
    session = db.get(ChatSession, session_id)
    session.active_turn_id = turn_id
    session.active_turn_expires_at = now + timedelta(minutes=1)
    db.flush()

    reconciled = ChatLatencyService(db).reconcile_stale_turns(now=now)
    db.refresh(row)

    assert reconciled == {"complete": 0, "error": 0, "interrupted": 0}
    assert row.terminal_status == "running"


@pytest.mark.parametrize("lease_seconds", [-1, 60])
def test_telemetry_cleanup_leaves_durable_expiry_to_admission(db, lease_seconds):
    from backend.services.chat_turn_admission_coordinator import (
        ChatTurnAdmissionCoordinator,
    )
    from backend.services.chat_turn_job_repository import ChatTurnJobRepository

    now = datetime.now(UTC)
    session_id = _session(db)
    row = _admit(db, session_id=session_id)
    message = _user_message(db, session_id=session_id, turn_id=row.turn_id)
    session = db.get(ChatSession, session_id)
    session.active_turn_id = row.turn_id
    session.active_turn_expires_at = now - timedelta(seconds=30)
    job = ChatTurnJob(
        turn_id=row.turn_id,
        chat_session_id=session_id,
        hf_user_id="owner-1",
        request_id=str(row.request_id),
        revision=1,
        dispatch_class="interactive",
        dispatch_route="legacy-claude",
        state="running",
        worker_id="worker-a",
        worker_generation=1,
        lease_generation=1,
        app_release_id="test",
        worker_contract_version="test",
        admitted_at=now - timedelta(minutes=2),
        lease_expires_at=now + timedelta(seconds=lease_seconds),
    )
    db.add(job)
    db.expire_on_commit = False
    db.commit()

    assert ChatLatencyService(db).reconcile_stale_turns(now=now) == {
        "complete": 0,
        "error": 0,
        "interrupted": 0,
    }
    assert message.status == "generating"
    assert session.active_turn_id == row.turn_id
    assert job.state == "running"

    coordinator = ChatTurnAdmissionCoordinator(
        db,
        SimpleNamespace(chat_max_concurrency=32),
        repository=ChatTurnJobRepository(advisory_locker=lambda *_args: None),
        observe=lambda *_args: None,
    )
    coordinator.preflight(
        hf_user_id="other-owner",
        request_id="new-request",
        requested_session_id=None,
        now=now,
    )
    db.flush()
    assert job.state == ("interrupted" if lease_seconds < 0 else "running")
    assert message.status == ("interrupted" if lease_seconds < 0 else "generating")

    if lease_seconds < 0:
        # Both projections roll back together if the admitting transaction fails.
        db.rollback()
        assert db.get(ChatTurnJob, row.turn_id).state == "running"
        assert db.get(ChatMessageRecord, message.id).status == "generating"
        coordinator.preflight(
            hf_user_id="other-owner",
            request_id="retry-request",
            requested_session_id=None,
            now=now,
        )
        db.commit()
        assert ChatLatencyService(db).reconcile_stale_turns(
            now=now + timedelta(minutes=1)
        ) == {"complete": 0, "error": 0, "interrupted": 1}
        assert row.terminal_status == "interrupted"


def test_gateway_can_record_by_turn_and_derive_admission_delta(db):
    session_id = _session(db)
    row = _admit(db, session_id=session_id)
    row.admitted_at = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    db.flush()
    service = ChatLatencyService(db)

    assert service.record_gateway_received(
        row.turn_id,
        datetime(2026, 7, 29, 12, 0, 1, 250_000, tzinfo=UTC),
    )
    assert service.record_phase_for_turn(row.turn_id, "upstream_response_headers", 800)
    db.refresh(row)

    assert row.provider_gateway_received_ms == 1_250
    assert row.upstream_response_headers_ms == 800


def test_browser_update_validates_owner_and_never_overwrites_a_timing_class(db):
    session_id = _session(db)
    request_id = uuid.uuid4()
    row = _admit(db, session_id=session_id, request_id=request_id)
    service = ChatLatencyService(db)

    first = SimpleNamespace(
        submission_to_stream_start_ms=40.6,
        submission_to_first_visible_delta_ms=None,
        terminal_classification=None,
    )
    second = SimpleNamespace(
        submission_to_stream_start_ms=900,
        submission_to_first_visible_delta_ms=1_200,
        terminal_classification="complete",
    )
    assert not service.update_browser("another-owner", str(request_id), first)
    assert service.update_browser("owner-1", str(request_id), first)
    assert service.update_browser("owner-1", str(request_id), second)
    assert service.update_browser("owner-1", str(request_id), second)
    db.refresh(row)

    assert row.browser_stream_start_ms == 41
    assert row.browser_first_visible_delta_ms == 1_200
    assert row.browser_terminal_classification == "complete"


def test_cleanup_deletes_only_one_bounded_thirty_day_batch(db):
    session_id = _session(db)
    service = ChatLatencyService(db)
    now = datetime(2026, 7, 29, tzinfo=UTC)
    old = [_admit(db, session_id=session_id, request_id=uuid.uuid4()) for _ in range(3)]
    recent = _admit(db, session_id=session_id, request_id=uuid.uuid4())
    for index, row in enumerate(old):
        row.admitted_at = now - timedelta(days=31, seconds=index)
    recent.admitted_at = now - timedelta(days=29)
    db.flush()

    assert service.cleanup(batch_size=2, now=now) == 2
    assert service.cleanup(batch_size=2, now=now) == 1
    assert service.cleanup(batch_size=2, now=now) == 0
    assert (
        db.scalar(
            select(ChatTurnLatency).where(ChatTurnLatency.turn_id == recent.turn_id)
        )
        is recent
    )


def test_active_spend_status_is_zero_without_costed_turns(db):
    status = ChatLatencyService(db).active_spend_status(
        now=datetime(2026, 7, 30, 12, tzinfo=UTC)
    )

    assert status == {
        "month_to_date_cost_usd": 0.0,
        "completed_turns": 0,
        "cost_per_completed_turn_usd": 0.0,
        "projected_monthly_cost_usd": 0.0,
        "trailing_seven_day_cost_usd": 0.0,
        "trailing_daily_average_usd": 0.0,
        "trailing_30_day_projection_usd": 0.0,
        "alert_threshold_usd": 50.0,
        "should_alert": False,
    }


def test_active_spend_status_amortizes_all_compute_over_completed_turns(db):
    session_id = _session(db)
    completed = _admit(db, session_id=session_id)
    failed = _admit(db, session_id=session_id)
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    for row, status, cost in (
        (completed, "complete", 0.7),
        (failed, "error", 0.3),
    ):
        row.terminal_status = status
        row.estimated_active_cost_usd = cost
        row.completed_at = now - timedelta(days=7)
    db.flush()

    status = ChatLatencyService(db).active_spend_status(now=now)

    assert status["month_to_date_cost_usd"] == pytest.approx(1)
    assert status["completed_turns"] == 1
    assert status["cost_per_completed_turn_usd"] == pytest.approx(1)
    assert status["projected_monthly_cost_usd"] == pytest.approx(31 / 7)
    assert status["trailing_30_day_projection_usd"] == pytest.approx(30 / 7)
    assert status["alert_threshold_usd"] == 50
    assert status["should_alert"] is False


def test_active_spend_status_alerts_on_current_run_rate_above_dynamic_threshold(db):
    session_id = _session(db)
    row = _admit(db, session_id=session_id)
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    row.terminal_status = "complete"
    row.estimated_active_cost_usd = 100
    row.completed_at = now - timedelta(days=1)
    db.flush()

    status = ChatLatencyService(db).active_spend_status(now=now)

    assert status["projected_monthly_cost_usd"] == pytest.approx(3_100)
    assert status["trailing_30_day_projection_usd"] == pytest.approx(3_000 / 7)
    assert status["alert_threshold_usd"] == pytest.approx(6_000 / 7)
    assert status["should_alert"] is True


def test_active_spend_status_requires_timezone_aware_now(db):
    with pytest.raises(ValueError, match="timezone-aware"):
        ChatLatencyService(db).active_spend_status(now=datetime(2026, 7, 30))


def test_latency_migration_is_environment_scoped_and_least_privilege():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "add_chat_turn_latency.sql"
    ).read_text()

    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "OWNER TO pwc_staging_owner" in migration
    assert "TO pwc_staging;" in migration
    assert "FROM paperswithcode_user;" in migration
    assert "OWNER TO paperswithcode_user" in migration
    assert "FROM pwc_staging;" in migration


def test_qualification_metadata_migration_is_environment_scoped_and_least_privilege():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "add_chat_qualification_metadata.sql"
    ).read_text()

    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "OWNER TO pwc_staging_owner" in migration
    assert "TO pwc_staging;" in migration
    assert "FROM paperswithcode_user;" in migration
    assert "OWNER TO paperswithcode_user" in migration
    assert "FROM pwc_staging;" in migration
    assert "qualification_run_id" in migration
    assert "qualification_scenario" in migration


def test_external_pi_turns_are_not_billed_for_an_unused_sandbox(db):
    # Routing to the external fleet is resolved after admission, so the row
    # starts out carrying the Modal sandbox shape. Left uncorrected, finalize
    # bills the requested CPU and memory for the whole turn even though no
    # sandbox was ever created, and that figure feeds the Modal spend circuits.
    session_id = _session(db)
    request_id = uuid.uuid4()
    row = _admit(db, session_id=session_id, request_id=request_id)
    service = ChatLatencyService(db)

    assert float(row.sandbox_cpu_request) == 0.125
    assert service.mark_external_pi(str(request_id))
    db.refresh(row)

    assert row.execution_backend == "external_pi"
    assert row.sandbox_cpu_request is None
    assert row.sandbox_memory_request_mib is None

    assert service.finalize(str(request_id), "complete", 30_000)
    db.refresh(row)
    assert row.estimated_active_cost_usd is None


def test_marking_external_pi_is_idempotent_and_leaves_modal_turns_billed(db):
    session_id = _session(db)
    request_id = uuid.uuid4()
    _admit(db, session_id=session_id, request_id=request_id)
    service = ChatLatencyService(db)

    assert service.mark_external_pi(str(request_id))
    # A second call must not re-mark a row that is already external.
    assert not service.mark_external_pi(str(request_id))

    other_request = uuid.uuid4()
    other = _admit(db, session_id=session_id, request_id=other_request)
    assert service.record_phase(
        str(other_request),
        "pool_lookup_completed",
        12,
        acquisition_outcome="pool_hit",
    )
    assert service.finalize(str(other_request), "complete", 30_000)
    db.refresh(other)

    assert other.execution_backend == "modal_cli"
    assert float(other.estimated_active_cost_usd) > 0

    with pytest.raises(ValueError, match="request_id must be a UUID"):
        service.mark_external_pi("not-a-uuid")


def test_external_pi_backend_migration_is_environment_scoped():
    migration = (
        Path(__file__).parents[1]
        / "database"
        / "migrations"
        / "allow_external_pi_latency_backend.sql"
    ).read_text()

    assert "current_schema() NOT IN ('staging', 'public')" in migration
    # The deployed constraint is the auto-named inline CHECK from
    # add_chat_turn_latency.sql, not the ORM's explicit name. Dropping only the
    # ORM name is a silent no-op that leaves the two-value check enforced.
    assert (
        "DROP CONSTRAINT IF EXISTS chat_turn_latency_execution_backend_check"
        in migration
    )
    assert "DROP CONSTRAINT IF EXISTS chat_turn_latency_backend_check" in migration
    assert "ADD CONSTRAINT chat_turn_latency_backend_check" in migration
    assert "'external_pi'" in migration


def test_finalize_records_turn_failure_attribution_once(db):
    session_id = _session(db)
    request_id = uuid.uuid4()
    row = _admit(db, session_id=session_id, request_id=request_id)
    service = ChatLatencyService(db)

    with pytest.raises(ValueError, match="requires an error status"):
        service.finalize(
            str(request_id), "complete", 10, failure_class="provider_error"
        )
    assert service.finalize(
        str(request_id),
        "error",
        4200,
        failure_stage="awaiting_first_event",
        failure_class="external_worker_lost",
    )
    db.refresh(row)

    assert row.terminal_status == "error"
    assert row.failure_stage == "awaiting_first_event"
    assert row.failure_class == "external_worker_lost"


def test_finalize_keeps_warm_assignment_diagnostics_and_sanitizes_labels(db):
    session_id = _session(db)
    request_id = uuid.uuid4()
    row = _admit(db, session_id=session_id, request_id=request_id)
    service = ChatLatencyService(db)
    service.record_phase(
        str(request_id),
        "assignment_fallback",
        50,
        failure_stage="dispatch_write",
        failure_class="BrokenPipeError",
        attempt_kind="pool",
    )

    assert service.finalize(
        str(request_id),
        "error",
        900,
        failure_stage="not a stage",
        failure_class="bad class; DROP TABLE",
    )
    db.refresh(row)

    # Earlier warm-assignment diagnostics win; finalize never overwrites them.
    assert row.failure_stage == "dispatch_write"
    assert row.failure_class == "BrokenPipeError"

    other = uuid.uuid4()
    other_row = _admit(db, session_id=session_id, request_id=other)
    service.finalize(
        str(other), "error", 900, failure_stage="not a stage", failure_class="bad;"
    )
    db.refresh(other_row)
    assert (other_row.failure_stage, other_row.failure_class) == (
        "unknown",
        "UnknownError",
    )
