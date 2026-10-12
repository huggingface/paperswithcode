"""Isolate deployment tests: stub the live OpenRouter guardrail, restore env."""

from __future__ import annotations

import os

import pytest

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
