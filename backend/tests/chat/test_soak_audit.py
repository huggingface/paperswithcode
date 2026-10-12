import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from backend.scripts import audit_chat_soak
from backend.scripts.audit_chat_soak import (
    _journal_counts,
    _parse_time,
    _status,
    render_report,
)


def test_parse_time_requires_an_explicit_timezone():
    assert _parse_time("2026-07-31T12:00:00Z") == datetime(2026, 7, 31, 12, tzinfo=UTC)

    try:
        _parse_time("2026-07-31T12:00:00")
    except ValueError as error:
        assert "timezone" in str(error)
    else:
        raise AssertionError("timezone-free start was accepted")


def test_render_report_serializes_dates_as_iso_8601():
    rendered = json.loads(
        render_report(
            {
                "observed_at": datetime(2026, 8, 4, 7, 16, tzinfo=UTC),
                "billing_cycle": date(2026, 8, 1),
            }
        )
    )

    assert rendered == {
        "observed_at": "2026-08-04T07:16:00+00:00",
        "billing_cycle": "2026-08-01",
    }


def test_status_fails_health_before_elapsed_or_sample_gates():
    now = datetime(2026, 7, 31, 12, tzinfo=UTC)
    finish = now + timedelta(days=1)

    assert (
        _status(
            now=now,
            finish=finish,
            sample_gates={"samples": False},
            health_gates={"healthy": False},
        )
        == "failed"
    )
    assert (
        _status(
            now=now,
            finish=finish,
            sample_gates={"samples": False},
            health_gates={"healthy": True},
        )
        == "soaking"
    )


def test_status_requires_samples_after_the_full_window():
    now = datetime(2026, 8, 7, 12, tzinfo=UTC)
    finish = now - timedelta(seconds=1)

    assert (
        _status(
            now=now,
            finish=finish,
            sample_gates={"samples": False},
            health_gates={"healthy": True},
        )
        == "insufficient_samples"
    )
    assert (
        _status(
            now=now,
            finish=finish,
            sample_gates={"samples": True},
            health_gates={"healthy": True},
        )
        == "telemetry_ready"
    )


def test_journal_counts_ignore_only_qualification_forced_failure_sessions(
    monkeypatch,
):
    expected_session_id = "b20b2118-6d2d-4b72-942b-ff30972da2d6"
    unexpected_session_id = "ee31e680-cf77-401a-82f4-8a2d68841b80"
    monkeypatch.setattr(
        audit_chat_soak.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=(
                "chat research producer failed "
                f"session_id={expected_session_id} error=ConnectionClosedError\n"
                "chat research producer failed "
                f"session_id={unexpected_session_id} error=ConnectionClosedError\n"
                f"chat cleanup failed session_id={expected_session_id}\n"
            )
        ),
    )

    counts = _journal_counts(
        datetime(2026, 8, 4, 10, 32, tzinfo=UTC),
        expected_failure_session_ids={expected_session_id},
    )

    assert counts["research_producer_failure"] == 1
    assert counts["turn_cleanup_failure"] == 1


def test_journal_counts_report_content_free_execution_recovery_aggregates(monkeypatch):
    monkeypatch.setattr(
        audit_chat_soak.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=(
                "chat execution recovery request_id=a turn_id=b rounds=6/6 "
                "denied_rounds=1 calls=9/12 denied_calls=2 tooling_closed=answer_now "
                "limit_reached=True finalizer_attempted=True finalizer_outcome=success "
                "finalization_latency_ms=1200\n"
                "chat execution recovery request_id=c turn_id=d rounds=6/6 "
                "denied_rounds=0 calls=8/12 denied_calls=0 tooling_closed=None "
                "limit_reached=True finalizer_attempted=True finalizer_outcome=success "
                "finalization_latency_ms=800\n"
                "chat provider usage request_id=a turn_id=b phase=finalization "
                "provider_requests=1 tokens=400\n"
            )
        ),
    )

    counts = _journal_counts(datetime(2026, 8, 4, 10, 32, tzinfo=UTC))

    assert counts["execution_limits_raw"] == 2
    assert counts["execution_limits_recovered"] == 2
    assert counts["repeated_denials_after_closure"] == 1
    assert counts["finalization_latency_ms"] == {
        "count": 2,
        "mean": 1000,
        "p95": 1200,
    }
    assert counts["finalization_provider_usage"] == {
        "provider_requests": 1,
        "tokens": 400,
    }
