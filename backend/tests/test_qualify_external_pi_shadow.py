from __future__ import annotations

import asyncio

from backend.scripts.qualify_external_pi_shadow import (
    ExternalWorkCounters,
    QualificationIdentity,
    run_qualification,
    synthetic_native_cases,
)


class _Harness:
    def __init__(self):
        self.active = 0
        self.maximum_active = 0
        self.concurrent_ids: set[str] = set()

    async def compare(self, case_name, request):
        if case_name.startswith("isolated_session_"):
            self.concurrent_ids.add(str(request.agent_session_id))
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
        projection = {
            "current_leaf_id": request.current_leaf_id,
            "entry_count": len(request.transcript_entries),
            "prompt_sha256": request.prompt_sha256,
            "tool_names_sha256": request.tool_names_sha256,
            "transcript_sha256": request.transcript_sha256,
        }
        return projection

    async def capacity_rejected_without_queue(self):
        return True

    async def restart_after_lease_expiry(self):
        return (4, 5)

    async def stale_generation_fenced(self):
        return True

    async def drain_and_recover(self):
        return True

    async def observed_counters(self):
        return ExternalWorkCounters(shadow_requests=20), True


def test_qualification_covers_native_trees_concurrency_and_lifecycle_content_free():
    harness = _Harness()
    report = asyncio.run(
        run_qualification(
            QualificationIdentity("release-a", "worker-a", 6),
            harness,
            qualification_nonce="n" * 32,
        )
    )

    assert report.passed is True
    assert [case.name for case in report.cases] == [
        "linear_history",
        "branching_history",
        "tool_history",
        "eight_isolated_sessions",
        "capacity_no_queue",
        "restart_after_lease_expiry",
        "stale_generation_fencing",
        "drain_recovery",
        "zero_external_work",
    ]
    assert all(case.passed and case.failure_code is None for case in report.cases)
    assert harness.maximum_active == 8
    assert len(harness.concurrent_ids) == 8
    assert report.worker_generation == 6
    assert set(report.model_dump()) == {
        "release_id",
        "worker_id",
        "worker_generation",
        "qualification_nonce",
        "qualified_at_unix_ms",
        "passed",
        "case_count",
        "duration_ms",
        "external_work_counts",
        "cases",
    }
    serialized = report.model_dump_json()
    assert "prompt" not in serialized
    assert "transcript" not in serialized
    assert "tool_result" not in serialized


def test_qualification_fails_closed_with_typed_code_when_external_work_occurs():
    harness = _Harness()

    async def observed():
        return ExternalWorkCounters(shadow_requests=1, provider_calls=1), True

    harness.observed_counters = observed
    report = asyncio.run(
        run_qualification(
            QualificationIdentity("release-a", "worker-a", 6),
            harness,
            qualification_nonce="n" * 32,
        )
    )

    assert report.passed is False
    assert report.cases[-1].failure_code == "external_work_detected"
    assert report.external_work_counts.provider_calls == 1


def test_tool_history_case_contains_native_tool_call_and_result_messages():
    entries = synthetic_native_cases()["tool_history"].transcript_entries

    assert entries[2]["message"]["content"][0]["type"] == "toolCall"
    assert entries[3]["message"]["role"] == "toolResult"
    assert entries[3]["message"]["toolCallId"] == "qualification-call"
