"""Sandbox resource probes and qualification evidence."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.config import Settings
from backend.scripts import qualify_chat_sandbox, qualify_chat_soak
from backend.scripts.qualify_chat_sandbox import (
    QualificationRunner,
    Sample,
    merge_release_settings,
    summarize,
)


def test_resource_probe_treats_ephemeral_disk_as_provider_managed(monkeypatch):
    settings = type(
        "Settings",
        (),
        {"chat_sandbox_pids_max": 64, "chat_sandbox_memory_mib": 2048},
    )()
    runner = QualificationRunner(settings, starts=1, parallel=1, snapshot_samples=0)
    probes: list[str] = []

    async def record(name, *_command, **_options):
        probes.append(name)

    monkeypatch.setattr(runner, "_resource_probe", record)

    assert asyncio.run(runner.run_resource_probes()) == {
        "pids": "enforced",
        "disk": "provider_managed_ephemeral",
        "memory": "enforced",
    }
    assert probes == ["pids", "memory"]


def test_qualification_retains_samples_when_resource_probe_fails(monkeypatch):
    runner = QualificationRunner(
        SimpleNamespace(), starts=1, parallel=1, snapshot_samples=0
    )

    async def sample(_index):
        return Sample(1, 2, 3, None, None)

    async def fail_resources():
        raise RuntimeError("content must not be emitted")

    monkeypatch.setattr(runner, "_sample", sample)
    monkeypatch.setattr(runner, "run_resource_probes", fail_resources)

    samples, resources = asyncio.run(runner.run(resource_probes=True))

    assert samples == [Sample(1, 2, 3, None, None)]
    assert resources == {"status": "failed", "error_code": "RuntimeError"}


def test_qualification_merges_complete_release_runtime_identity():
    environment = Settings(
        _env_file=None,
        release_id="protected-stale",
        chat_modal_image_version="im-stale",
        chat_worker_contract_version="3",
        chat_pi_version="",
        chat_pi_node_version="",
    )
    release = environment.model_copy(
        update={
            "release_id": "exact-release",
            "chat_modal_image_version": "im-exact",
            "chat_worker_contract_version": "80",
            "chat_default_agent_harness": "pi",
            "chat_pi_version": "0.84.1",
            "chat_pi_node_version": "22.19.0",
            "chat_pi_runtime_enabled": True,
        }
    )

    merged = merge_release_settings(environment, release)

    assert merged.release_id == "exact-release"
    assert merged.chat_modal_image_version == "im-exact"
    assert merged.chat_worker_contract_version == "80"
    assert merged.chat_default_agent_harness == "pi"
    assert merged.chat_pi_version == "0.84.1"
    assert merged.chat_pi_node_version == "22.19.0"
    assert merged.chat_pi_runtime_enabled is True


def test_pi_prewarm_qualification_creates_the_actual_blank_profile(monkeypatch):
    settings = SimpleNamespace(release_id="release-a")
    runner = QualificationRunner(
        settings,
        starts=1,
        parallel=1,
        snapshot_samples=0,
        pi_prewarm=True,
    )
    captured = {}

    async def create(configured, **options):
        captured.update(settings=configured, **options)
        return object()

    monkeypatch.setattr(qualify_chat_sandbox, "create_isolated_sandbox", create)

    asyncio.run(runner._create("one"))

    assert captured["settings"] is settings
    assert captured["tags"]["pool"] == "blank"
    assert captured["tags"]["release"] == "release-a"


@pytest.mark.parametrize(
    "provider_error",
    [
        qualify_chat_sandbox.NotFoundError("gone"),
        qualify_chat_sandbox.ConflictError("shutting down"),
    ],
)
def test_resource_probe_accepts_provider_kill_as_expected_limit(
    monkeypatch, provider_error
):
    settings = type(
        "Settings",
        (),
        {"chat_sandbox_pids_max": 64, "chat_sandbox_memory_mib": 2048},
    )()
    runner = QualificationRunner(settings, starts=1, parallel=1, snapshot_samples=0)
    terminated = False

    class Sandbox:
        class Terminate:
            async def aio(self, **_options):
                nonlocal terminated
                terminated = True
                raise qualify_chat_sandbox.NotFoundError("gone")

        terminate = Terminate()

    async def create(_name):
        return Sandbox()

    async def provider_killed(*_args, **_options):
        raise provider_error

    monkeypatch.setattr(runner, "_create", create)
    monkeypatch.setattr(qualify_chat_sandbox, "_exec", provider_killed)

    asyncio.run(
        runner._resource_probe(
            "memory",
            "python",
            "-c",
            "raise SystemExit(1)",
            expect_success=False,
            timeout=30,
        )
    )
    assert terminated


def test_forced_failure_probe_does_not_record_user_cancellation():
    assert qualify_chat_soak._requests_user_cancel("clean")
    assert not qualify_chat_soak._requests_user_cancel("forced")


def test_qualification_summary_uses_nearest_rank_p95():
    samples = [
        Sample(
            cold_start_ms=value,
            exec_ms=value * 2,
            termination_ms=value * 3,
            snapshot_ms=value if value <= 3 else None,
            restore_ms=value + 1 if value <= 3 else None,
        )
        for value in range(1, 21)
    ]
    result = summarize(samples)
    assert result["cold_start_ms"] == {
        "count": 20,
        "min": 1,
        "p50": 10,
        "p95": 19,
        "max": 20,
    }
    assert result["snapshot_ms"]["count"] == 3
