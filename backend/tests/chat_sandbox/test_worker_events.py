"""Worker output budget, paper receipts, and public event contracts."""

from __future__ import annotations


from backend.chat_sandbox_worker import (
    agent,
)
from backend.chat_sandbox_worker.protocol import (
    WorkerEventValidator,
    paper_events_from_output,
)


def test_worker_expands_output_budget_only_for_poster_mode():
    settings = agent.WorkerSettings()

    ordinary = agent.WorkerToolHooks(settings)
    poster = agent.WorkerToolHooks(settings, poster_mode=True)

    assert ordinary.budget.maximum_result_bytes == 24 * 1024
    assert ordinary.budget.maximum_turn_output_bytes == 96 * 1024
    assert poster.budget.maximum_result_bytes == 192 * 1024
    assert poster.budget.maximum_turn_output_bytes == 1024 * 1024


def test_paper_receipt_is_bounded_and_emits_a_typed_event():
    event = paper_events_from_output(
        '@@PWC_PAPER@@{"operation":"create","activated":true,"paper":{"artifact_id":"paper-1","title":"Draft"}}'
    )
    assert event == [
        {
            "type": "paper_artifact",
            "operation": "create",
            "activated": True,
            "paper": {"artifact_id": "paper-1", "title": "Draft"},
            "descriptor": {"artifact_id": "paper-1", "title": "Draft"},
        }
    ]
    validator = WorkerEventValidator()
    validator.accept(event[0])


def test_paper_draft_receipt_is_a_typed_event():
    event = paper_events_from_output(
        '@@PWC_PAPER@@{"operation":"draft","activated":false,"paper":{"artifact_id":"paper-1","title":"Draft"}}'
    )

    assert event is not None
    validator = WorkerEventValidator()
    validator.accept(event[0])
    assert event[0]["operation"] == "draft"


def test_worker_keeps_large_tool_evidence_out_of_public_events():
    event = agent._public_tool_result_event(
        {
            "type": "tool_result",
            "id": "large",
            "status": "success",
            "took_ms": 1,
            "content": [{"type": "text", "text": "x" * (64 * 1024)}],
            "metadata": {"output_truncated": False},
        }
    )

    assert len(event["content"][0]["text"].encode()) <= 24 * 1024
    assert event["content"][0]["truncated"] is True
    assert event["metadata"]["output_truncated"] is True
