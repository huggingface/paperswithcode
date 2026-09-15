from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from backend.loadtests.persistent_executor_cold import (
    COLD_ALLOCATION_MICROUSD,
    COLD_RESERVATION_MICROUSD,
    COMBINED_CEILING_MICROUSD,
    PRIOR_ALLOCATION_MICROUSD,
    ColdJournal,
    ColdObservation,
    cold_gate_impossible,
    cold_stage_result,
    collect_cold_observation,
    read_observations,
)
from backend.services.chat_sandbox_provider import SandboxLaunchMode


class Fixture:
    def __init__(self, tmp_path):
        self.journal = ColdJournal(
            tmp_path / "run", source_sha="a" * 40, image_id="im-test"
        )
        self.settings = SimpleNamespace(
            environment="staging",
            chat_sandbox_modal_environment="pwc-chat-staging",
            chat_modal_image_version="im-test",
            chat_sandbox_cpu=0.5,
            chat_sandbox_cpu_limit=1,
            chat_sandbox_memory_mib=512,
            chat_sandbox_memory_limit_mib=2048,
        )
        self.events = []
        self.now = 0
        self.exit_code = 0
        self.poll_result = 137
        self.fail_at = None
        self.workspace_ids = []

    def event(self, name):
        self.events.append(name)
        if name == self.fail_at:
            raise RuntimeError("sensitive error must not be persisted")

    def reserve(self, generation):
        self.event("reserve")
        return generation

    def created(self, reservation, sandbox):
        self.event("created")

    def terminated(self, sandbox):
        self.event("settled")

    async def prepare_launch(self, generation):
        self.event("launch")
        self.now += 1
        return "launch-bundle"

    async def create(self, **kwargs):
        self.event("create")
        assert kwargs["tags"]["qualification_profile"] == "persistent-cold"
        assert kwargs["launch_mode"] is SandboxLaunchMode.EXECUTOR
        assert kwargs["executor_launch"] == "launch-bundle"
        self.now += 2
        return SimpleNamespace(object_id="sb-" + kwargs["worker_generation"])

    async def attach_channel(self, workspace, claim, lifetime):
        self.event("attach")
        assert lifetime == 240
        self.now += 3
        return self

    async def ensure_workspace(self, context):
        self.event("workspace")
        self.workspace_ids.append(context.workspace_id)
        self.now += 4

    async def exec_resumable(self, context, **kwargs):
        self.event("pwd")
        assert kwargs == {"command": "pwd", "timeout_ms": 1000}
        self.now += 5
        return SimpleNamespace(terminal={"exit_code": self.exit_code})

    async def aclose(self):
        self.event("close")

    async def terminate(self, sandbox_id, box):
        self.event("terminate")
        return True

    async def poll(self, box):
        self.event("poll")
        return self.poll_result

    def verify(self, sandbox_id):
        self.event("verify")

    async def collect(self, index=0, profile="cold_first_pwd"):
        return await collect_cold_observation(
            observation=self.journal.admit(profile, index),
            journal=self.journal,
            runtime=self,
            provider=self,
            spend=self,
            verify_sandbox=self.verify,
            clock=lambda: self.now,
        )


def test_budget_is_additional_cold_only_and_keeps_prior_allocation():
    assert PRIOR_ALLOCATION_MICROUSD == 16_250_000
    assert COLD_ALLOCATION_MICROUSD == 25_000_000
    assert COMBINED_CEILING_MICROUSD == 41_250_000
    assert COLD_RESERVATION_MICROUSD == 24_284_240
    assert COLD_RESERVATION_MICROUSD <= COLD_ALLOCATION_MICROUSD


def test_actual_channel_path_includes_all_startup_stages(tmp_path):
    fixture = Fixture(tmp_path)
    row = asyncio.run(fixture.collect())
    assert row.elapsed_ms == 15_000
    assert row.completed and row.terminal_confirmed and row.error is None
    assert fixture.events == [
        "reserve",
        "launch",
        "create",
        "created",
        "verify",
        "attach",
        "workspace",
        "pwd",
        "close",
        "terminate",
        "poll",
        "settled",
    ]
    assert read_observations(fixture.journal.directory) == [row]


@pytest.mark.parametrize(
    "stage",
    ["reserve", "launch", "create", "created", "verify", "attach", "workspace", "pwd"],
)
def test_failure_is_durable_and_never_retried(tmp_path, stage):
    fixture = Fixture(tmp_path)
    fixture.fail_at = stage
    row = asyncio.run(fixture.collect())
    assert row.error == "RuntimeError"
    assert row.elapsed_ms is None
    assert read_observations(fixture.journal.directory) == [row]
    assert (
        "sensitive"
        not in (fixture.journal.directory / "cold_first_pwd-0000.json").read_text()
    )
    if stage in {"created", "verify", "attach", "workspace", "pwd"}:
        assert row.terminal_confirmed
        assert fixture.events.count("terminate") == 1
    else:
        assert not row.terminal_confirmed
        assert "settled" not in fixture.events
    with pytest.raises(ValueError, match="retried"):
        asyncio.run(fixture.collect())


def test_termination_ack_without_terminal_poll_retains_reservation(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.poll_result = None
    row = asyncio.run(fixture.collect())
    assert row.cleanup_error == "sandbox:RuntimeError"
    assert not row.terminal_confirmed
    assert "settled" not in fixture.events


def test_channel_cleanup_failure_does_not_skip_provider_cleanup(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.fail_at = "close"
    row = asyncio.run(fixture.collect())
    assert row.terminal_confirmed
    assert row.cleanup_error == "channel:RuntimeError"


def test_nonzero_pwd_is_failed_evidence(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.exit_code = 1
    row = asyncio.run(fixture.collect())
    assert row.error and row.elapsed_ms is None and row.terminal_confirmed


def test_cancellation_cleans_up_and_preserves_incomplete_observation(tmp_path):
    fixture = Fixture(tmp_path)

    async def cancel_during_attach(*args):
        raise asyncio.CancelledError()

    fixture.attach_channel = cancel_during_attach
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(fixture.collect())
    (row,) = read_observations(fixture.journal.directory)
    assert not row.completed
    assert row.terminal_confirmed
    assert row.elapsed_ms is None


def test_interrupted_run_cannot_be_reopened_or_reclassified(tmp_path):
    fixture = Fixture(tmp_path)
    row = fixture.journal.admit("cold_first_pwd", 0)
    assert read_observations(fixture.journal.directory) == [row]
    assert not cold_stage_result([row])["latency_gates_passed"]
    with pytest.raises(FileExistsError):
        ColdJournal(fixture.journal.directory, source_sha="b" * 40, image_id="im-other")
    for profile, index in [
        ("warm_ack", 0),
        ("cold_first_pwd", 1000),
        ("cold_32_way", 32),
        ("cold_32_way", -1),
    ]:
        with pytest.raises(ValueError):
            fixture.journal.admit(profile, index)


def test_collector_has_no_hidden_serialization_of_burst(tmp_path):
    fixture = Fixture(tmp_path)

    async def run():
        started = 0
        all_started = asyncio.Event()
        create = fixture.create

        async def create_together(**kwargs):
            nonlocal started
            started += 1
            if started == 32:
                all_started.set()
            await asyncio.wait_for(all_started.wait(), 2)
            return await create(**kwargs)

        fixture.create = create_together
        rows = await asyncio.gather(
            *(fixture.collect(i, "cold_32_way") for i in range(32))
        )
        assert all(row.terminal_confirmed and row.error is None for row in rows)
        assert len(set(fixture.workspace_ids)) == 32

    asyncio.run(run())


def complete_rows():
    return [
        ColdObservation(
            profile,
            i,
            f"{profile}-{i}",
            sandbox_id=f"sb-{profile}-{i}",
            elapsed_ms=elapsed,
            terminal_confirmed=True,
            completed=True,
        )
        for profile, count, elapsed in [
            ("cold_first_pwd", 1000, 5000),
            ("cold_32_way", 32, 8000),
        ]
        for i in range(count)
    ]


def test_thresholds_are_inclusive_and_never_qualify_full_release():
    rows = complete_rows()
    result = cold_stage_result(rows)
    assert result["latency_gates_passed"]
    assert not result["full_release_qualified"]
    assert not cold_stage_result(rows[:-1])["latency_gates_passed"]
    assert not cold_stage_result(rows + [rows[0]])["latency_gates_passed"]
    rows[-1] = replace(rows[-1], elapsed_ms=8000.001)
    assert not cold_stage_result(rows)["latency_gates_passed"]


def test_mathematically_impossible_tails_include_missing_and_failed_samples():
    rows = complete_rows()[:1000]
    for i in range(50):
        rows[i] = replace(rows[i], elapsed_ms=5000.001)
    assert not cold_gate_impossible(rows)
    rows[50] = replace(rows[50], elapsed_ms=5000.001)
    assert cold_gate_impossible(rows)
    rows = complete_rows()[:1000]
    for i in range(10):
        rows[i] = replace(rows[i], elapsed_ms=None, error="TimeoutError")
    assert not cold_gate_impossible(rows)
    rows[10] = replace(rows[10], elapsed_ms=None, error="TimeoutError")
    assert cold_gate_impossible(rows)


def test_same_admitted_observation_cannot_launch_twice(tmp_path):
    fixture = Fixture(tmp_path)
    observation = fixture.journal.admit("cold_first_pwd", 0)

    async def collect():
        return await collect_cold_observation(
            observation=observation,
            journal=fixture.journal,
            runtime=fixture,
            provider=fixture,
            spend=fixture,
            verify_sandbox=fixture.verify,
        )

    asyncio.run(collect())
    before = list(fixture.events)
    with pytest.raises(ValueError, match="exactly once"):
        asyncio.run(collect())
    assert fixture.events == before


@pytest.mark.parametrize("elapsed", [-1, float("nan"), float("inf")])
def test_invalid_latency_cannot_pass(elapsed):
    with pytest.raises(ValueError):
        replace(complete_rows()[0], elapsed_ms=elapsed)


def test_sandbox_reuse_cannot_pass():
    rows = complete_rows()
    rows[1] = replace(rows[1], sandbox_id=rows[0].sandbox_id)
    assert not cold_stage_result(rows)["latency_gates_passed"]


def test_coordinator_preflights_whole_burst_and_preserves_all_samples(
    tmp_path, monkeypatch
):
    import backend.loadtests.persistent_executor_cold as module

    fixture = Fixture(tmp_path)
    widths = []

    async def preflight(width):
        widths.append(width)

    async def simulated_observation(*, observation, journal, **kwargs):
        journal.begin(observation)
        row = replace(
            observation,
            sandbox_id="sb-" + observation.worker_generation,
            elapsed_ms=100,
            completed=True,
            terminal_confirmed=True,
        )
        journal.save(row)
        return row

    monkeypatch.setattr(module, "collect_cold_observation", simulated_observation)
    result = asyncio.run(
        module.collect_cold_stage(
            journal=fixture.journal,
            runtime=fixture,
            provider=fixture,
            spend=fixture,
            verify_sandbox=fixture.verify,
            preflight=preflight,
        )
    )
    assert widths == [4] * 250 + [32]
    assert len(read_observations(fixture.journal.directory)) == 1032
    assert result["latency_gates_passed"]
    assert not result["cold_stage_qualified"]


def test_preflight_rejection_launches_nothing(tmp_path):
    from backend.loadtests.persistent_executor_cold import collect_cold_stage

    fixture = Fixture(tmp_path)

    async def reject(width):
        raise RuntimeError("capacity refused")

    with pytest.raises(RuntimeError, match="capacity refused"):
        asyncio.run(
            collect_cold_stage(
                journal=fixture.journal,
                runtime=fixture,
                provider=fixture,
                spend=fixture,
                verify_sandbox=fixture.verify,
                preflight=reject,
            )
        )
    assert fixture.events == []
    assert read_observations(fixture.journal.directory) == []


def test_cleanup_failure_stops_all_new_admission(tmp_path):
    from backend.loadtests.persistent_executor_cold import collect_cold_stage

    fixture = Fixture(tmp_path)
    fixture.poll_result = None

    async def preflight(width):
        assert width == 4

    result = asyncio.run(
        collect_cold_stage(
            journal=fixture.journal,
            runtime=fixture,
            provider=fixture,
            spend=fixture,
            verify_sandbox=fixture.verify,
            preflight=preflight,
        )
    )
    assert len(read_observations(fixture.journal.directory)) == 4
    assert not result["latency_gates_passed"]
    assert fixture.events.count("create") == 4
    assert fixture.events.count("terminate") == 4


def test_resource_shape_mismatch_refuses_before_reserving(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.settings.chat_sandbox_cpu_limit = 2
    with pytest.raises(ValueError, match="frozen cold shape"):
        asyncio.run(fixture.collect())
    assert fixture.events == []


def test_journal_failure_after_create_still_attempts_cleanup(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)
    save = fixture.journal.save

    def fail_after_create(row):
        if row.sandbox_id is not None:
            raise OSError("disk failure")
        save(row)

    monkeypatch.setattr(fixture.journal, "save", fail_after_create)
    with pytest.raises(OSError):
        asyncio.run(fixture.collect())
    assert fixture.events.count("terminate") == 1
    (persisted,) = read_observations(fixture.journal.directory)
    assert persisted.reservation_id is not None
    assert not persisted.completed


def test_sandbox_reuse_between_profiles_cannot_pass():
    rows = complete_rows()
    rows[-1] = replace(rows[-1], sandbox_id=rows[0].sandbox_id)
    assert not cold_stage_result(rows)["latency_gates_passed"]
