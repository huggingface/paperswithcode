import pytest

from backend.chat_sandbox_worker.protocol import ProtocolError, WorkerEventValidator
from backend.services.chat_turn_event_service import from_legacy_event


def test_compaction_frames_roundtrip_without_becoming_terminal():
    validator = WorkerEventValidator()
    frames = [
        {"type": "compaction_status", "state": "started"},
        {"type": "_compaction_telemetry", "outcome": "success", "chunk_count": 3},
        {"type": "compaction_status", "state": "finished"},
        {"type": "answer_delta", "text": "Recovered answer"},
        {"type": "done", "finish_reason": "success", "followups": []},
        {"type": "worker_done", "status": "complete"},
    ]
    for frame in frames:
        validator.accept(frame)
        assert from_legacy_event(frame).to_legacy() == frame
    assert validator.terminal


def test_compaction_status_rejects_unknown_states_and_post_terminal_updates():
    validator = WorkerEventValidator()
    with pytest.raises(ProtocolError, match="Invalid compaction"):
        validator.accept({"type": "compaction_status", "state": "invalid"})
    validator.accept({"type": "error", "code": "context_too_large", "message": "Retry"})
    with pytest.raises(ProtocolError, match="followed a terminal"):
        validator.accept({"type": "compaction_status", "state": "finished"})
