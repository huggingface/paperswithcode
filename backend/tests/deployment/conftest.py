"""Isolate deployment tests: stub the live OpenRouter guardrail, restore env,
and keep slot control requests away from the host's live backend sockets."""

from __future__ import annotations

import os
import subprocess

import pytest

import deploy.cli as deploy_cli
from backend.services import openrouter_budget_service as deploy_openrouter


@pytest.fixture(autouse=True)
def _avoid_live_openrouter_guardrail(monkeypatch: pytest.MonkeyPatch):
    environment = os.environ.copy()
    monkeypatch.setattr(
        deploy_openrouter, "validate_openrouter_guardrail", lambda _settings: None
    )
    yield
    os.environ.clear()
    os.environ.update(environment)


@pytest.fixture(autouse=True)
def _keep_tests_off_live_host(tmp_path, monkeypatch: pytest.MonkeyPatch):
    real_run = subprocess.run

    def refuse_host_mutation(command, *args, **kwargs):
        if (
            isinstance(command, (list, tuple))
            and len(command) > 1
            and command[0] == "systemctl"
            and command[1] not in {"show", "is-active", "is-enabled"}
        ):
            raise AssertionError(f"test reached host systemd: {command}")
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", refuse_host_mutation)
    monkeypatch.setattr(
        deploy_cli,
        "_slot_socket",
        lambda environment, slot: tmp_path / f"{environment}-{slot}.sock",
    )
