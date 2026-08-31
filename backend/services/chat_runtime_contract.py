"""Pure immutable-runtime and dedicated-gateway contract checks."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

GATEWAY_PATH = "/api/internal/chat-gateway"
PUBLIC_STAGING_HOST = "staging.paperswithcode.co"
EXTERNAL_PI_WORKER_CONTRACT = "external-pi-v1"
DURABLE_EXTERNAL_PI_RUNTIME_CONTRACT = "durable-external-pi-v1"


@dataclass(frozen=True, slots=True)
class ExternalAdmissionContract:
    durable_dispatch: bool
    event_journal_schema: bool
    external_supervisor: bool
    ready_worker_registry: bool
    remote_workspace_tools: bool
    lazy_workspace: bool
    sandbox_executor: bool
    remote_bash: bool
    remote_read: bool
    worker_contract_version: str
    runtime_contract_version: str


def require_external_admission_contract(contract: ExternalAdmissionContract) -> None:
    readiness = (
        contract.durable_dispatch,
        contract.event_journal_schema,
        contract.external_supervisor,
        contract.ready_worker_registry,
        contract.remote_workspace_tools,
        contract.lazy_workspace,
        contract.sandbox_executor,
        contract.remote_bash,
        contract.remote_read,
    )
    if not all(readiness):
        raise ValueError("external admission contract is incomplete")
    if (
        contract.worker_contract_version != EXTERNAL_PI_WORKER_CONTRACT
        or contract.runtime_contract_version != DURABLE_EXTERNAL_PI_RUNTIME_CONTRACT
    ):
        raise ValueError("external admission contract version is incompatible")


def require_immutable_image_id(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("im-"):
        raise ValueError("chat runtime requires an immutable Modal image ID")
    return value


def dedicated_gateway_hostname(value: str) -> str:
    gateway = urlsplit(value)
    if (
        gateway.scheme != "https"
        or not gateway.hostname
        or gateway.hostname == PUBLIC_STAGING_HOST
        or gateway.path.rstrip("/") != GATEWAY_PATH
        or gateway.query
        or gateway.fragment
    ):
        raise ValueError("chat gateway must use its dedicated HTTPS origin and path")
    return gateway.hostname
