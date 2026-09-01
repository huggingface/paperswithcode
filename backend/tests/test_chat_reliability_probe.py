from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import uuid

import pytest

from backend.config import Settings
from backend.services.autonomous_cron_probe import FindingState
from backend.services.chat_reliability_probe import (
    ChatAggregateSnapshot,
    classify_chat_aggregates,
    probe_chat_aggregates,
)
from backend.services.chat_operational_alert_service import (
    reliability_alert_classifications,
)
from backend.services.chat_tracing_service import (
    IncidentTraceContentQuery,
    SafeChatTurnObservation,
    SafeProviderObservation,
    authorize_incident_trace_content_access,
    fetch_chat_turn_observations,
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
        ttft_ms=(500, 700, 900, 12_000, 14_000),
        completion_ms=(2_000, 3_000, 4_000, 5_000, 200_000),
        stream_interruptions=2,
        persistence_failures=1,
        capacity_failures=3,
        collection_complete=True,
        window_start=NOW - timedelta(minutes=15),
        window_end=NOW,
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
    }
    assert degraded["auth_errors"].evidence["incident_signature"] == (
        "chat:authentication:auth_error"
    )
    serialized = repr([item.as_dict() for item in findings]).lower()
    assert "prompt" not in serialized
    assert "answer" not in serialized
    assert "session_id" not in serialized
    assert "trace_id" not in serialized


def test_probe_combines_safe_langfuse_observations_and_operational_counts(monkeypatch):
    monkeypatch.setattr(
        "backend.services.chat_reliability_probe.fetch_provider_request_observations",
        lambda _settings, _start, _end: SimpleNamespace(
            complete=True,
            observations=(
                SafeProviderObservation("success", 300, 1000),
                SafeProviderObservation("provider_error", None, 2000),
            ),
        ),
    )
    monkeypatch.setattr(
        "backend.services.chat_reliability_probe.fetch_chat_turn_observations",
        lambda _settings, _start, _end: SimpleNamespace(
            complete=True,
            observations=(
                SafeChatTurnObservation("success", 300, 1000),
                SafeChatTurnObservation("interrupted", 400, 2000),
            ),
        ),
    )

    findings = probe_chat_aggregates(
        timedelta(minutes=15),
        settings=Settings(environment="production"),
        now=NOW,
        operational_counts={
            "stream_persistence_failure": 1,
            "capacity_saturation": 2,
        },
    )

    by_contract = {item.contract: item for item in findings}
    assert by_contract["provider_errors"].state == FindingState.DEGRADED
    assert by_contract["persistence"].evidence["failure_count"] == 1
    assert by_contract["capacity"].evidence["failure_count"] == 2


def test_probe_counts_predispatch_turn_provider_auth_and_billing_failures(monkeypatch):
    monkeypatch.setattr(
        "backend.services.chat_reliability_probe.fetch_provider_request_observations",
        lambda _settings, _start, _end: SimpleNamespace(
            complete=True,
            observations=(SafeProviderObservation("success", 300, 1000),),
        ),
    )
    monkeypatch.setattr(
        "backend.services.chat_reliability_probe.fetch_chat_turn_observations",
        lambda _settings, _start, _end: SimpleNamespace(
            complete=True,
            observations=(
                SafeChatTurnObservation("provider_error", None, 100),
                SafeChatTurnObservation("auth_error", None, 200),
                SafeChatTurnObservation("billing_error", None, 300),
            ),
        ),
    )

    findings = probe_chat_aggregates(
        timedelta(minutes=15),
        settings=Settings(environment="production"),
        now=NOW,
    )

    by_contract = {item.contract: item for item in findings}
    assert by_contract["provider_errors"].state == FindingState.DEGRADED
    assert by_contract["provider_errors"].evidence["failure_count"] == 1
    assert by_contract["auth_errors"].state == FindingState.DEGRADED
    assert by_contract["auth_errors"].evidence["failure_count"] == 1
    assert by_contract["billing_errors"].state == FindingState.DEGRADED
    assert by_contract["billing_errors"].evidence["failure_count"] == 1


def test_unavailable_or_truncated_aggregate_source_is_unknown(monkeypatch):
    monkeypatch.setattr(
        "backend.services.chat_reliability_probe.fetch_provider_request_observations",
        lambda _settings, _start, _end: None,
    )
    monkeypatch.setattr(
        "backend.services.chat_reliability_probe.fetch_chat_turn_observations",
        lambda _settings, _start, _end: None,
    )

    findings = probe_chat_aggregates(
        timedelta(minutes=15),
        settings=Settings(environment="production"),
        now=NOW,
    )

    assert findings
    assert all(item.state == FindingState.UNKNOWN for item in findings)


def test_alert_projection_contains_only_contract_and_stable_signature():
    findings = classify_chat_aggregates(
        ChatAggregateSnapshot(
            total_requests=1,
            successful_requests=0,
            provider_errors=1,
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


def test_trace_content_access_requires_finding_no_telemetry_and_durable_audit():
    finding = next(
        item
        for item in classify_chat_aggregates(
            ChatAggregateSnapshot(
                total_requests=1,
                successful_requests=0,
                provider_errors=1,
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
    audit_records = []

    with pytest.raises(PermissionError, match="telemetry retention"):
        authorize_incident_trace_content_access(
            finding=finding,
            actor="operator:alice",
            run_id=uuid.uuid4(),
            query=query,
            telemetry_retention_disabled=False,
            durable_audit=lambda record: audit_records.append(record) or True,
            now=NOW,
        )
    assert audit_records == []

    permit = authorize_incident_trace_content_access(
        finding=finding,
        actor="operator:alice",
        run_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        query=query,
        telemetry_retention_disabled=True,
        durable_audit=lambda record: audit_records.append(record) or True,
        now=NOW,
    )

    assert permit.incident_signature == "chat:provider:provider_error"
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
    assert "content" not in repr(audit_records).lower()


def test_trace_content_access_rejects_failed_durable_audit():
    snapshot = ChatAggregateSnapshot(
        total_requests=1,
        successful_requests=0,
        provider_errors=1,
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

    with pytest.raises(PermissionError, match="durable audit"):
        authorize_incident_trace_content_access(
            finding=finding,
            actor="operator:alice",
            run_id=uuid.uuid4(),
            query=IncidentTraceContentQuery(
                trace_id="b" * 32,
                window_start=NOW - timedelta(minutes=5),
                window_end=NOW,
            ),
            telemetry_retention_disabled=True,
            durable_audit=lambda _record: False,
            now=NOW,
        )
