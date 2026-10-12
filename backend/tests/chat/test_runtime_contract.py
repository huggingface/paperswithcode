from __future__ import annotations

from dataclasses import replace

import pytest

from backend.services.chat_runtime_contract import (
    DURABLE_EXTERNAL_PI_RUNTIME_CONTRACT,
    EXTERNAL_PI_WORKER_CONTRACT,
    ExternalAdmissionContract,
    require_external_admission_contract,
)


def _ready_contract() -> ExternalAdmissionContract:
    return ExternalAdmissionContract(
        durable_dispatch=True,
        event_journal_schema=True,
        external_supervisor=True,
        ready_worker_registry=True,
        remote_workspace_tools=True,
        lazy_workspace=True,
        sandbox_executor=True,
        remote_bash=True,
        remote_read=True,
        worker_contract_version=EXTERNAL_PI_WORKER_CONTRACT,
        runtime_contract_version=DURABLE_EXTERNAL_PI_RUNTIME_CONTRACT,
    )


def test_durable_external_admission_accepts_only_the_complete_contract() -> None:
    require_external_admission_contract(_ready_contract())


@pytest.mark.parametrize(
    "field",
    [
        "durable_dispatch",
        "event_journal_schema",
        "external_supervisor",
        "ready_worker_registry",
        "remote_workspace_tools",
        "lazy_workspace",
        "sandbox_executor",
        "remote_bash",
        "remote_read",
    ],
)
def test_durable_external_admission_refuses_each_missing_readiness_gate(field) -> None:
    with pytest.raises(ValueError, match="external admission contract is incomplete"):
        require_external_admission_contract(
            replace(_ready_contract(), **{field: False})
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("worker_contract_version", "external-pi-v0"),
        ("runtime_contract_version", "durable-external-pi-v0"),
    ],
)
def test_durable_external_admission_refuses_stale_contract_versions(
    field, value
) -> None:
    with pytest.raises(ValueError, match="contract version is incompatible"):
        require_external_admission_contract(
            replace(_ready_contract(), **{field: value})
        )
