from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    Base,
    ChatMessageRecord,
    ChatSession,
    ChatTurnLatency,
)
from backend.services.autonomous_cron_probe import FindingState
from backend.services.chat_reliability_service import (
    ChatAggregateSnapshot,
    classify_chat_aggregates,
    probe_chat_aggregates,
)
from backend.services.chat_operational_alert_service import (
    reliability_alert_classifications,
)
from backend.services.chat_tracing_service import (
    IncidentTraceContentPermit,
    IncidentTraceContentQuery,
    SafeChatTurnObservation,
    SafeProviderObservation,
    authorize_incident_trace_content_access,
    fetch_chat_turn_observations,
    fetch_incident_trace_content,
    fetch_provider_request_observations,
)


NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)


def test_langfuse_query_requests_no_input_output_or_metadata(monkeypatch):
    calls = []
    page = SimpleNamespace(
        data=[
            SimpleNamespace(
                level="DEFAULT",
                status_message=None,
                end_time=NOW,
                latency=2.5,
                time_to_first_token=0.4,
            )
        ],
        meta=SimpleNamespace(cursor=None),
    )
    observations = SimpleNamespace(
        get_many=lambda **kwargs: calls.append(kwargs) or page
    )
    client = SimpleNamespace(api=SimpleNamespace(observations=observations))
    monkeypatch.setattr(
        "backend.services.chat_tracing_service.configured_chat_client",
        lambda _settings: client,
    )

    result = fetch_provider_request_observations(
        Settings(environment="production"), NOW - timedelta(minutes=15), NOW
    )

    assert result is not None
    assert result.complete is True
    assert result.observations == (
        SafeProviderObservation(outcome="success", ttft_ms=400, duration_ms=2500),
    )
    assert calls[0]["fields"] == "core,basic,time,metrics"
    assert "io" not in calls[0]["fields"]
    assert "metadata" not in calls[0]["fields"]
    assert calls[0]["name"] == "provider-request"


def test_turn_query_classifies_interruption_without_fetching_io(monkeypatch):
    calls = []
    page = SimpleNamespace(
        data=[
            SimpleNamespace(
                level="WARNING",
                status_message="interrupted",
                end_time=NOW,
                latency=12.0,
                time_to_first_token=1.2,
            )
        ],
        meta=SimpleNamespace(cursor=None),
    )
    observations = SimpleNamespace(
        get_many=lambda **kwargs: calls.append(kwargs) or page
    )
    client = SimpleNamespace(api=SimpleNamespace(observations=observations))
    monkeypatch.setattr(
        "backend.services.chat_tracing_service.configured_chat_client",
        lambda _settings: client,
    )

    result = fetch_chat_turn_observations(
        Settings(environment="production"), NOW - timedelta(minutes=15), NOW
    )

    assert result is not None
    assert result.observations == (
        SafeChatTurnObservation("interrupted", 1200, 12_000),
    )
    assert calls[0]["fields"] == "core,basic,time,metrics"
    assert calls[0]["name"] == "generate-research-response"


def test_turn_query_classifies_predispatch_auth_and_billing_errors(monkeypatch):
    page = SimpleNamespace(
        data=[
            SimpleNamespace(
                level="ERROR",
                status_message="provider_unauthorized",
                end_time=NOW,
                latency=0.2,
                time_to_first_token=None,
            ),
            SimpleNamespace(
                level="ERROR",
                status_message="openrouter_monthly_budget_exhausted",
                end_time=NOW,
                latency=0.3,
                time_to_first_token=None,
            ),
        ],
        meta=SimpleNamespace(cursor=None),
    )
    client = SimpleNamespace(
        api=SimpleNamespace(
            observations=SimpleNamespace(get_many=lambda **_kwargs: page)
        )
    )
    monkeypatch.setattr(
        "backend.services.chat_tracing_service.configured_chat_client",
        lambda _settings: client,
    )

    result = fetch_chat_turn_observations(
        Settings(environment="production"), NOW - timedelta(minutes=15), NOW
    )

    assert result is not None
    assert [item.outcome for item in result.observations] == [
        "auth_error",
        "billing_error",
    ]


def test_turn_query_classifies_actual_predispatch_provider_failures(monkeypatch):
    page = SimpleNamespace(
        data=[
            SimpleNamespace(
                level="ERROR",
                status_message=code,
                end_time=NOW,
                latency=0.2,
                time_to_first_token=None,
            )
            for code in ("openai_unavailable", "openrouter_unavailable")
        ],
        meta=SimpleNamespace(cursor=None),
    )
    client = SimpleNamespace(
        api=SimpleNamespace(
            observations=SimpleNamespace(get_many=lambda **_kwargs: page)
        )
    )
    monkeypatch.setattr(
        "backend.services.chat_tracing_service.configured_chat_client",
        lambda _settings: client,
    )

    result = fetch_chat_turn_observations(
        Settings(environment="production"), NOW - timedelta(minutes=15), NOW
    )

    assert result is not None
    assert [item.outcome for item in result.observations] == [
        "provider_error",
        "provider_error",
    ]


def test_aggregate_classification_is_deterministic_and_content_free():
    snapshot = ChatAggregateSnapshot(
        total_requests=10,
        successful_requests=6,
        provider_errors=2,
        auth_errors=1,
        billing_errors=1,
        ttft_ms=(500, 16_000, 17_000, 18_000, 19_000),
        completion_ms=(2_000, 3_000, 4_000, 5_000, 200_000),
        stream_interruptions=2,
        persistence_failures=1,
        capacity_failures=3,
        collection_complete=True,
        window_start=NOW - timedelta(minutes=15),
        window_end=NOW,
        provider_failovers=1,
    )

    findings = classify_chat_aggregates(snapshot)
    degraded = {
        item.contract: item for item in findings if item.state == FindingState.DEGRADED
    }

    assert set(degraded) == {
        "success_rate",
        "provider_errors",
        "auth_errors",
        "billing_errors",
        "time_to_first_token",
        "completion_latency",
        "stream_integrity",
        "persistence",
        "capacity",
        "provider_failover",
    }
    assert degraded["auth_errors"].evidence["incident_signature"] == (
        "chat:authentication:auth_error"
    )
    serialized = repr([item.as_dict() for item in findings]).lower()
    assert "prompt" not in serialized
    assert "answer" not in serialized
    assert "session_id" not in serialized
    assert "trace_id" not in serialized


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            ChatSession.__table__,
            ChatMessageRecord.__table__,
            ChatTurnLatency.__table__,
        ],
    )
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX idx_chat_messages_current_revision"))
    with Session(engine) as session:
        yield session


TERMINAL_FOR_STATUS = {
    "complete": "complete",
    "error": "error",
    "interrupted": "interrupted",
}


def _turn(
    db,
    *,
    status="complete",
    error_code=None,
    terminal_status=None,
    completed_at=NOW - timedelta(minutes=5),
    ttft_ms=1_000,
    total_ms=10_000,
    user_route="gpt-5.6-luna@openai",
    answer_route=None,
    qualification_run_id=None,
):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    db.add(
        ChatSession(
            id=session_id,
            hf_user_id="owner",
            hf_username="owner",
            selected_model="model",
            execution_backend="modal_cli",
        )
    )
    db.flush()
    db.add(
        ChatTurnLatency(
            turn_id=turn_id,
            request_id=uuid.uuid4(),
            chat_session_id=session_id,
            traffic_class="new_chat",
            execution_backend="modal_cli",
            model_route=user_route,
            app_release_id="release",
            admitted_at=(completed_at or NOW) - timedelta(minutes=1),
            completed_at=completed_at,
            terminal_status=terminal_status or TERMINAL_FOR_STATUS.get(status, "error"),
            first_semantic_event_ms=ttft_ms,
            total_ms=total_ms,
            qualification_run_id=qualification_run_id,
        )
    )
    db.add(
        ChatMessageRecord(
            id=uuid.uuid4(),
            session_id=session_id,
            turn_id=turn_id,
            sequence=1,
            role="user",
            content="omitted",
            status=status,
            error_code=error_code,
            model_route=user_route,
        )
    )
    if answer_route is not None:
        db.add(
            ChatMessageRecord(
                id=uuid.uuid4(),
                session_id=session_id,
                turn_id=turn_id,
                sequence=2,
                role="assistant",
                content="omitted",
                status="complete",
                model_route=answer_route,
            )
        )
    db.flush()


def _probe(db, **overrides):
    settings = Settings(
        environment="production",
        chat_sponsored_deepseek_route="deepseek-route",
        **overrides,
    )
    findings = probe_chat_aggregates(
        timedelta(minutes=15), settings=settings, db=db, now=NOW
    )
    return {item.contract: item for item in findings}


def test_probe_reads_terminal_turn_outcomes_from_the_database(db):
    for _ in range(6):
        _turn(db)
    _turn(db, status="error", error_code="provider_error")
    _turn(db, status="superseded", error_code="openai_unavailable")
    _turn(db, status="error", error_code="gateway_unavailable")
    _turn(db, status="error", error_code="hf_inference_billing_exhausted")
    _turn(db, status="interrupted", error_code="external_worker_lost")

    by_contract = _probe(db)

    assert by_contract["success_rate"].state == FindingState.DEGRADED
    assert by_contract["success_rate"].evidence["failed_requests"] == 5
    assert by_contract["provider_errors"].evidence["failure_count"] == 2
    assert by_contract["provider_errors"].state == FindingState.DEGRADED
    assert by_contract["billing_errors"].state == FindingState.DEGRADED
    assert by_contract["stream_integrity"].state == FindingState.DEGRADED
    assert by_contract["provider_failover"].state == FindingState.HEALTHY


def test_probe_ignores_user_stops_limits_qualification_and_other_windows(db):
    _turn(db)
    _turn(db, status="interrupted", error_code="cancelled")
    _turn(db, status="superseded", error_code="cancel_control_missing")
    _turn(db, status="error", error_code="context_too_large")
    _turn(db, status="error", error_code="openai_user_concurrency_limited")
    _turn(db, status="interrupted", terminal_status="stopped", error_code="cancelled")
    _turn(db, status="generating", terminal_status="running", completed_at=None)
    _turn(db, status="error", error_code="provider_error", qualification_run_id="q")
    _turn(
        db,
        status="error",
        error_code="provider_error",
        completed_at=NOW - timedelta(minutes=20),
    )

    by_contract = _probe(db)

    assert by_contract["success_rate"].evidence["total_requests"] == 1
    assert by_contract["success_rate"].state == FindingState.HEALTHY
    assert by_contract["provider_errors"].evidence["failure_count"] == 0


def test_edited_prompts_keep_their_recorded_outcome(db):
    _turn(db, status="superseded", terminal_status="complete")
    _turn(db, status="superseded", terminal_status="complete")
    _turn(db, status="superseded", error_code="provider_error")

    finding = _probe(db)["success_rate"]

    assert finding.evidence["total_requests"] == 3
    assert finding.evidence["failed_requests"] == 1


def test_turns_count_in_the_window_where_they_finish(db):
    _turn(
        db,
        status="error",
        error_code="provider_error",
        completed_at=NOW - timedelta(minutes=2),
    )
    latency = db.query(ChatTurnLatency).one()
    latency.admitted_at = NOW - timedelta(minutes=40)
    db.flush()

    assert _probe(db)["provider_errors"].evidence["failure_count"] == 1


def test_isolated_failures_do_not_alert(db):
    for _ in range(3):
        _turn(db)
    _turn(db, status="error", error_code="provider_error")
    _turn(db, status="error", error_code="gateway_unavailable")

    findings = _probe(db).values()

    assert reliability_alert_classifications(tuple(findings)) == {}


def test_probe_alerts_on_luna_turns_answered_by_the_failover_route(db):
    _turn(db, answer_route="deepseek-route")
    _turn(db, answer_route="gpt-5.6-luna@openai")
    _turn(db, user_route="deepseek-route", answer_route="deepseek-route")

    by_contract = _probe(db)

    assert by_contract["provider_failover"].state == FindingState.DEGRADED
    assert by_contract["provider_failover"].evidence["failover_count"] == 1
    assert by_contract["success_rate"].state == FindingState.HEALTHY


def test_latency_needs_enough_samples_and_uses_the_median(db):
    for ttft in (500, 600, 20_000, 21_000):
        _turn(db, ttft_ms=ttft)
    assert _probe(db)["time_to_first_token"].state == FindingState.UNKNOWN

    _turn(db, ttft_ms=22_000)
    finding = _probe(db)["time_to_first_token"]
    assert finding.state == FindingState.DEGRADED
    assert finding.evidence["p50_ms"] == 20_000


def test_probe_adds_operational_counts_to_database_outcomes(db):
    _turn(db)
    _turn(db, status="error", error_code="transcript_mirror_error")
    settings = Settings(environment="production")

    findings = probe_chat_aggregates(
        timedelta(minutes=15),
        settings=settings,
        db=db,
        now=NOW,
        operational_counts={
            "stream_persistence_failure": 1,
            "capacity_saturation": 2,
        },
    )

    by_contract = {item.contract: item for item in findings}
    assert by_contract["persistence"].evidence["failure_count"] == 2
    assert by_contract["capacity"].evidence["failure_count"] == 2


def test_database_failure_makes_the_aggregate_source_unknown():
    class BrokenSession:
        def execute(self, *_args, **_kwargs):
            raise OperationalError("select", {}, Exception("down"))

        def rollback(self):
            pass

    findings = probe_chat_aggregates(
        timedelta(minutes=15),
        settings=Settings(environment="production"),
        db=BrokenSession(),
        now=NOW,
    )

    assert findings
    assert all(item.state == FindingState.UNKNOWN for item in findings)


def test_alert_projection_contains_only_contract_and_stable_signature():
    findings = classify_chat_aggregates(
        ChatAggregateSnapshot(
            total_requests=3,
            successful_requests=0,
            provider_errors=2,
            auth_errors=0,
            billing_errors=0,
            ttft_ms=(),
            completion_ms=(),
            stream_interruptions=0,
            persistence_failures=0,
            capacity_failures=0,
            collection_complete=True,
            window_start=NOW - timedelta(minutes=15),
            window_end=NOW,
        )
    )

    projected = reliability_alert_classifications(findings)

    assert projected == {
        "provider_errors|chat:provider:provider_error": 1,
        "success_rate|chat:request_path:success_rate_low": 1,
    }
    assert "trace" not in repr(projected).lower()


def test_trace_content_access_requires_finding_no_telemetry_and_durable_audit(
    monkeypatch, tmp_path
):
    finding = next(
        item
        for item in classify_chat_aggregates(
            ChatAggregateSnapshot(
                total_requests=1,
                successful_requests=0,
                provider_errors=2,
                auth_errors=0,
                billing_errors=0,
                ttft_ms=(),
                completion_ms=(),
                stream_interruptions=0,
                persistence_failures=0,
                capacity_failures=0,
                collection_complete=True,
                window_start=NOW - timedelta(minutes=15),
                window_end=NOW,
            )
        )
        if item.contract == "provider_errors"
    )
    query = IncidentTraceContentQuery(
        trace_id="a" * 32,
        window_start=NOW - timedelta(minutes=5),
        window_end=NOW,
    )
    audit_path = tmp_path / "chat-incident-trace-access-audit.jsonl"
    monkeypatch.setattr(
        "backend.services.chat_tracing_service.get_settings",
        lambda: Settings(environment="production", cron_log_dir=str(tmp_path)),
    )

    with pytest.raises(PermissionError, match="telemetry retention"):
        authorize_incident_trace_content_access(
            finding=finding,
            actor="operator:alice",
            run_id=uuid.uuid4(),
            query=query,
            now=NOW,
        )
    assert not audit_path.exists()

    monkeypatch.setattr(
        "backend.services.chat_tracing_service.get_settings",
        lambda: Settings(
            environment="production",
            cron_log_dir=str(tmp_path),
            chat_langfuse_trace_content_access_enabled=True,
        ),
    )

    permit = authorize_incident_trace_content_access(
        finding=finding,
        actor="operator:alice",
        run_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        query=query,
        now=NOW,
    )

    assert permit.incident_signature == "chat:provider:provider_error"
    audit_records = [
        json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()
    ]
    assert audit_records == [
        {
            "actor": "operator:alice",
            "accessed_at": NOW.isoformat(),
            "incident_signature": "chat:provider:provider_error",
            "query": {
                "trace_id": "a" * 32,
                "window_start": (NOW - timedelta(minutes=5)).isoformat(),
                "window_end": NOW.isoformat(),
            },
            "run_id": "11111111-1111-1111-1111-111111111111",
        }
    ]
    assert audit_path.stat().st_mode & 0o777 == 0o600
    assert "content" not in repr(audit_records).lower()


def test_trace_content_access_rejects_failed_durable_audit(monkeypatch, tmp_path):
    snapshot = ChatAggregateSnapshot(
        total_requests=1,
        successful_requests=0,
        provider_errors=2,
        auth_errors=0,
        billing_errors=0,
        ttft_ms=(),
        completion_ms=(),
        stream_interruptions=0,
        persistence_failures=0,
        capacity_failures=0,
        collection_complete=True,
        window_start=NOW - timedelta(minutes=15),
        window_end=NOW,
    )
    finding = classify_chat_aggregates(snapshot)[1]

    monkeypatch.setattr(
        "backend.services.chat_tracing_service.get_settings",
        lambda: Settings(
            environment="production",
            cron_log_dir=str(tmp_path),
            chat_langfuse_trace_content_access_enabled=True,
        ),
    )

    def fail_audit(_settings, _record):
        raise OSError("disk full")

    monkeypatch.setattr(
        "backend.services.chat_tracing_service.append_incident_trace_access_audit",
        fail_audit,
    )

    with pytest.raises(OSError, match="disk full"):
        authorize_incident_trace_content_access(
            finding=finding,
            actor="operator:alice",
            run_id=uuid.uuid4(),
            query=IncidentTraceContentQuery(
                trace_id="b" * 32,
                window_start=NOW - timedelta(minutes=5),
                window_end=NOW,
            ),
            now=NOW,
        )


def test_authorized_incident_trace_content_fetch_is_bounded_to_permit(
    monkeypatch, tmp_path
):
    finding = next(
        item
        for item in classify_chat_aggregates(
            ChatAggregateSnapshot(
                total_requests=1,
                successful_requests=0,
                provider_errors=2,
                auth_errors=0,
                billing_errors=0,
                ttft_ms=(),
                completion_ms=(),
                stream_interruptions=0,
                persistence_failures=0,
                capacity_failures=0,
                collection_complete=True,
                window_start=NOW - timedelta(minutes=15),
                window_end=NOW,
            )
        )
        if item.contract == "provider_errors"
    )
    query = IncidentTraceContentQuery(
        trace_id="d" * 32,
        window_start=NOW - timedelta(minutes=10),
        window_end=NOW,
    )
    settings = Settings(
        environment="production",
        cron_log_dir=str(tmp_path),
        chat_langfuse_trace_content_access_enabled=True,
    )
    monkeypatch.setattr(
        "backend.services.chat_tracing_service.get_settings", lambda: settings
    )
    permit = authorize_incident_trace_content_access(
        finding=finding,
        actor="operator:chat-reliability",
        run_id=uuid.uuid4(),
        query=query,
        now=NOW,
    )
    trace = SimpleNamespace(
        id=query.trace_id,
        timestamp=NOW - timedelta(minutes=5),
        environment="production",
        input={"role": "user", "content": "private"},
        output="private response",
        observations=[],
    )
    calls = []
    client = SimpleNamespace(
        api=SimpleNamespace(
            trace=SimpleNamespace(
                get=lambda trace_id, **kwargs: calls.append((trace_id, kwargs)) or trace
            )
        )
    )
    monkeypatch.setattr(
        "backend.services.chat_tracing_service.configured_chat_client",
        lambda _settings: client,
    )

    result = fetch_incident_trace_content(
        permit,
        now=NOW,
    )

    assert result is trace
    assert calls == [(query.trace_id, {"fields": "core,io,observations"})]

    with pytest.raises(PermissionError, match="single-use"):
        fetch_incident_trace_content(
            permit,
            now=NOW,
        )


def test_incident_trace_content_permit_cannot_be_constructed_directly():
    query = IncidentTraceContentQuery(
        trace_id="e" * 32,
        window_start=NOW - timedelta(minutes=5),
        window_end=NOW,
    )

    with pytest.raises(PermissionError, match="authorization helper"):
        IncidentTraceContentPermit(
            "chat:provider:provider_error",
            query,
            NOW,
            "forged-nonce",
        )
