"""Daily token pauses expire without unpausing operator/security stops."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.services import codex_add_evals_service as service


@pytest.mark.parametrize(
    "condition,days,enabled,threshold,tokens,cleared",
    [
        ("daily_token_guardrail", 1, True, 100, 0, True),
        ("daily_token_guardrail", 1, True, 100, 100, True),
        ("daily_token_guardrail", 0, True, 100, 0, False),
        ("daily_token_guardrail", 1, False, 100, 0, False),
        ("daily_token_guardrail", 1, True, None, 0, False),
        ("daily_token_guardrail", 1, True, 100, 101, False),
        ("operator", 1, True, 100, 0, False),
        ("trace_failure", 1, True, 100, 101, False),
    ],
)
def test_daily_pause_recovery(
    monkeypatch, condition, days, enabled, threshold, tokens, cleared
):
    now = datetime(2026, 10, 9, 0, 1, tzinfo=UTC)
    monkeypatch.setattr(service, "_now", lambda: now)
    monkeypatch.setattr(
        service.CodexPaperJobService,
        "_scheduled_usage_snapshot",
        staticmethod(
            lambda *_: {
                "pause_threshold_tokens": threshold,
                "current_day_tokens": tokens,
            }
        ),
    )
    state = SimpleNamespace(
        first_enabled_at=now - timedelta(days=30),
        dispatch_enabled=enabled,
        pause_condition=condition,
        paused_at=now - timedelta(days=days),
        pause_reason="original reason",
    )
    db = Mock()
    allowed = service.CodexPaperJobService._scheduled_usage_allowed(db, state)
    assert (state.paused_at is None) == cleared
    assert allowed == (threshold is None or tokens <= threshold)
    if cleared:
        assert state.pause_condition is None
        assert state.pause_reason is None
        db.commit.assert_called_once()
    elif condition != "daily_token_guardrail":
        assert state.pause_condition == condition
        assert state.pause_reason == "original reason"
        db.commit.assert_not_called()
