from types import SimpleNamespace

from backend.config import Settings
from backend.scripts.manage_chat_sandbox_circuit import (
    reviewed_policy_transition_allowed,
)


def _settings() -> Settings:
    return Settings(
        environment="production",
        chat_sandbox_warning_microusd=75_000_000,
        chat_sandbox_application_cap_microusd=100_000_000,
        chat_sandbox_environment_cap_microusd=125_000_000,
        chat_sandbox_workspace_cap_microusd=250_000_000,
        chat_sandbox_budget_attestation=(
            "modal-workspace-paperswithcode-250-production-125-v1"
        ),
    )


def _state(**changes):
    values = {
        "trip_reason": "accounting_integrity",
        "warning_microusd": 75_000_000,
        "application_cap_microusd": 100_000_000,
        "environment_cap_microusd": 0,
        "workspace_cap_microusd": 250_000_000,
        "policy_attestation": (
            "modal-workspace-paperswithcode-250-production-starter-v1"
        ),
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_reviewed_policy_transition_accepts_exact_same_cap_change():
    assert reviewed_policy_transition_allowed(_state(), _settings())


def test_reviewed_policy_transition_rejects_unrelated_cap_change():
    assert not reviewed_policy_transition_allowed(
        _state(application_cap_microusd=90_000_000),
        _settings(),
    )


def test_reviewed_policy_transition_requires_integrity_trip():
    assert not reviewed_policy_transition_allowed(
        _state(trip_reason="application_cap"),
        _settings(),
    )
