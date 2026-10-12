from unittest.mock import Mock

import pytest

from backend.config import Settings
from backend.services.chat_durable_lifecycle_observer import (
    DurableLifecycleObserver,
)
from backend.services.chat_operational_alert_service import runtime_failure_counts


def test_observer_emits_only_bounded_content_free_labels(caplog):
    observation = Mock()
    client = Mock()
    client.start_observation.return_value = observation
    observer = DurableLifecycleObserver(Settings(environment="staging"), client=client)

    with caplog.at_level("INFO"):
        observer("typed_failure", "execution_lost", 1)

    assert (
        "chat durable lifecycle event=typed_failure code=execution_lost value=1"
        in caplog.text
    )
    client.start_observation.assert_called_once_with(
        name="durable-chat-lifecycle",
        as_type="span",
        metadata={"event": "typed_failure", "code": "execution_lost", "value": 1},
    )
    observation.end.assert_called_once_with()
    assert runtime_failure_counts(caplog.messages) == {}


def test_observer_sends_bounded_latency_signal_to_langfuse():
    observation = Mock()
    client = Mock()
    client.start_observation.return_value = observation
    observer = DurableLifecycleObserver(Settings(environment="staging"), client=client)

    observer("ttft_ms", None, 12_000)

    client.start_observation.assert_called_once_with(
        name="durable-chat-lifecycle",
        as_type="span",
        metadata={"event": "ttft_ms", "code": "none", "value": 12_000},
    )
    observation.end.assert_called_once_with()


@pytest.mark.parametrize(
    ("event", "code", "value"),
    [
        ("turn_id", None, 1),
        ("typed_failure", "user-controlled-value", 1),
        ("journal_bytes", None, -1),
        ("journal_bytes", None, 16 * 1024 * 1024 + 1),
        ("journal_bytes", None, True),
    ],
)
def test_observer_rejects_high_cardinality_or_unbounded_values(event, code, value):
    observer = DurableLifecycleObserver(Settings(environment="staging"), client=Mock())

    with pytest.raises(ValueError, match="observation is invalid"):
        observer(event, code, value)
