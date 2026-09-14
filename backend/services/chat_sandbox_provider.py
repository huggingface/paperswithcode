"""Provider-only operations for Modal chat sandboxes."""

from __future__ import annotations

import asyncio
import base64
import re
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import modal
from modal.exception import NotFoundError
from modal.stream_type import StreamType
from websockets.asyncio.client import connect as websocket_connect

from backend.chat_sandbox_worker.contract import (
    CHAT_SANDBOX_REGION,
    CONTROL_PORT,
    MODAL_APP_NAME,
    PROVIDER_OUTPUT_TOKEN_LIMIT,
)
from backend.chat_sandbox_worker.executor_daemon import EXECUTOR_SOCKET
from backend.chat_sandbox_worker.executor_protocol import PROTOCOL as EXECUTOR_PROTOCOL
from backend.chat_sandbox_worker.mcp_app_registry import (
    egress_policy_digest,
    sandbox_outbound_domains,
)
from backend.config import Settings
from backend.services.chat_executor_timing import executor_stage

ImageResolver = Callable[[str], Awaitable[object]]
WebSocketConnector = Callable[..., Awaitable[object]]


FAILURE_STAGES = frozenset(
    {
        "claim_worker",
        "control_open",
        "queue_registration",
        "dispatch_write",
        "agent_stream",
        "broker_clear",
        "worker_done_send",
        "unknown",
    }
)
ATTEMPT_KINDS = frozenset({"pool", "reused", "direct"})
_FAILURE_CLASS = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")


class SandboxLaunchMode(StrEnum):
    LEGACY = "legacy"
    EXECUTOR = "executor"
    LEGACY_EXECUTOR = "legacy_executor"


EXECUTOR_RENDEZVOUS_URLS = {
    "production": "wss://chat-executor.paperswithcode.co",
    "staging": "wss://chat-executor-staging.paperswithcode.co",
}
MAX_EXECUTOR_ADMISSION_BYTES = 2_048


@dataclass(frozen=True, slots=True)
class ExecutorLaunchBundle:
    """One daemon-only, short-lived registration capability."""

    admission: bytes
    shard_generation: int
    authorization_keys_json: str

    def rendezvous_url(self, environment: str) -> str:
        base = EXECUTOR_RENDEZVOUS_URLS.get(environment)
        if base is None or self.shard_generation <= 0:
            raise SandboxError(
                "sandbox_executor_generation_invalid",
                "Sandbox executor generation is invalid",
            )
        return f"{base}/v1/generations/{self.shard_generation}/environment"

    def encoded_admission(self) -> str:
        if not self.admission or len(self.admission) > MAX_EXECUTOR_ADMISSION_BYTES:
            raise SandboxError(
                "sandbox_executor_admission_invalid",
                "Sandbox executor admission is invalid",
            )
        return base64.urlsafe_b64encode(self.admission).decode("ascii")

    def authorization_keys(self) -> str:
        if (
            not self.authorization_keys_json
            or len(self.authorization_keys_json.encode()) > 4_096
        ):
            raise SandboxError(
                "sandbox_executor_authorization_keys_invalid",
                "Sandbox executor authorization keys are invalid",
            )
        return self.authorization_keys_json


def sanitized_failure_stage(value: object) -> str:
    return value if isinstance(value, str) and value in FAILURE_STAGES else "unknown"


def sanitized_failure_class(value: object) -> str:
    return (
        value
        if isinstance(value, str) and _FAILURE_CLASS.fullmatch(value)
        else "UnknownError"
    )


class SandboxError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        uncertain: bool = False,
        failure_stage: str | None = None,
        failure_class: str | None = None,
        attempt_kind: str | None = None,
        sandbox_id: str | None = None,
        failure_monotonic: float | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.uncertain = uncertain
        self.failure_stage = (
            sanitized_failure_stage(failure_stage)
            if failure_stage is not None
            else None
        )
        self.failure_class = (
            sanitized_failure_class(failure_class)
            if failure_class is not None
            else None
        )
        self.attempt_kind = attempt_kind if attempt_kind in ATTEMPT_KINDS else None
        self.sandbox_id = sandbox_id if isinstance(sandbox_id, str) else None
        self.failure_monotonic = failure_monotonic


class SandboxProvider(Protocol):
    async def create(
        self,
        *,
        name: str,
        tags: dict[str, str],
        worker_generation: str | None = None,
        launch_mode: SandboxLaunchMode = SandboxLaunchMode.LEGACY,
        executor_launch: ExecutorLaunchBundle | None = None,
    ) -> object: ...

    async def resolve(self, sandbox_id: str) -> object: ...

    async def poll(self, sandbox: object) -> object | None: ...

    async def health(
        self,
        sandbox: object,
        *,
        persistent: bool,
        worker_generation: str | None,
        launch_mode: SandboxLaunchMode = SandboxLaunchMode.LEGACY,
    ) -> bool: ...

    async def terminate(
        self, sandbox_id: str, sandbox: object | None = None
    ) -> bool: ...

    async def open_persistent_connection(
        self, sandbox: object, worker_generation: str
    ) -> object: ...

    async def open_turn_process(
        self, sandbox: object, *, timeout_seconds: int
    ) -> object: ...

    async def open_executor_relay(
        self, sandbox: object, *, timeout_seconds: int
    ) -> object: ...

    def iter_sandboxes(self, *, tags: dict[str, str]) -> AsyncIterator[object]: ...

    async def get_tags(self, sandbox: object) -> dict[str, str]: ...


async def resolve_modal_image(image_reference: str) -> object:
    if image_reference.startswith("im-"):
        return modal.Image.from_id(image_reference)
    return modal.Image.from_name(image_reference)


def sandbox_environment(
    settings: Settings, *, pi_prewarm: bool = False
) -> dict[str, str]:
    return {
        "PWC_CHAT_GATEWAY_URL": settings.chat_gateway_url,
        "PWC_CHAT_PREFLIGHT_MODEL": settings.chat_deepseek_v4_flash_route,
        "PWC_CHAT_SHOW_REASONING": str(settings.chat_show_reasoning).lower(),
        "PWC_CHAT_MAX_TURNS": str(settings.chat_max_turns),
        "PWC_CHAT_MAX_TOOL_CALLS": str(settings.chat_max_tool_calls),
        "PWC_CHAT_MAX_DIRECT_SEARCH_CALLS": str(settings.chat_max_direct_search_calls),
        "PWC_CHAT_MAX_WEB_SEARCH_CALLS": str(settings.chat_web_search_max_calls),
        "PWC_CHAT_TOOL_RESULT_MAX_BYTES": str(settings.chat_tool_result_max_bytes),
        "PWC_CHAT_TURN_TOOL_OUTPUT_MAX_BYTES": str(
            settings.chat_turn_tool_output_max_bytes
        ),
        "PWC_CHAT_POSTERLY_TOOL_RESULT_MAX_BYTES": str(
            settings.chat_posterly_tool_result_max_bytes
        ),
        "PWC_CHAT_POSTERLY_TURN_TOOL_OUTPUT_MAX_BYTES": str(
            settings.chat_posterly_turn_tool_output_max_bytes
        ),
        "PWC_CHAT_LATEX_PAPER_TIMEOUT_SECONDS": str(
            settings.chat_latex_paper_timeout_seconds
        ),
        "PWC_CHAT_LATEX_PAPER_MAX_TOOL_ROUNDS": str(
            settings.chat_latex_paper_max_tool_rounds
        ),
        "PWC_CHAT_LATEX_PAPER_MAX_TOOL_CALLS": str(
            settings.chat_latex_paper_max_tool_calls
        ),
        "PWC_CHAT_LATEX_PAPER_MAX_DIRECT_SEARCH_CALLS": str(
            settings.chat_latex_paper_max_direct_search_calls
        ),
        "PWC_CHAT_BASH_TIMEOUT_SECONDS": str(settings.chat_bash_timeout_seconds),
        "PWC_CHAT_AGENT_TIMEOUT_SECONDS": str(settings.chat_agent_timeout_seconds),
        "PWC_CHAT_SANDBOX_PIDS_MAX": str(settings.chat_sandbox_pids_max),
        "PWC_CHAT_MAX_OUTPUT_TOKENS": str(PROVIDER_OUTPUT_TOKEN_LIMIT),
        "PWC_CHAT_PI_PREWARM_ENABLED": str(
            settings.chat_pi_prewarm_enabled and pi_prewarm
        ).lower(),
        "PWC_CHAT_PI_PREWARM_MODEL": settings.chat_route_provider_models.get(
            settings.chat_effective_pi_prewarm_model,
            settings.chat_effective_pi_prewarm_model,
        ),
        "PWC_CHAT_PI_PREWARM_PROTOCOL": settings.chat_route_protocols.get(
            settings.chat_effective_pi_prewarm_model, "anthropic-messages"
        ),
        "PWC_CHAT_PI_PREWARM_REASONING_EFFORT": (
            settings.chat_pi_prewarm_reasoning_effort
        ),
        "PWC_CHAT_PI_PROVIDER_ADAPTER_CONTRACT": (
            settings.chat_pi_provider_adapter_contract
        ),
        "PWC_CHAT_EXCALIDRAW_ENABLED": str(settings.chat_excalidraw_enabled).lower(),
        "PWC_CHAT_MCP_APPS_HOST_ENABLED": str(
            settings.chat_mcp_apps_host_enabled
        ).lower(),
        "PWC_CHAT_EGRESS_POLICY_DIGEST": egress_policy_digest(settings),
    }


class ModalSandboxProviderAdapter:
    """Stateless Modal sandbox operations with no persistence side effects."""

    def __init__(
        self,
        settings: Settings,
        *,
        image_resolver: ImageResolver = resolve_modal_image,
        websocket_connector: WebSocketConnector = websocket_connect,
    ):
        self.settings = settings
        self.image_resolver = image_resolver
        self.websocket_connector = websocket_connector

    async def create(
        self,
        *,
        name: str,
        tags: dict[str, str],
        worker_generation: str | None = None,
        launch_mode: SandboxLaunchMode = SandboxLaunchMode.LEGACY,
        executor_launch: ExecutorLaunchBundle | None = None,
    ) -> object:
        if not isinstance(launch_mode, SandboxLaunchMode):
            raise SandboxError(
                "sandbox_launch_mode_invalid", "Sandbox launch mode is invalid"
            )
        remote_executor = launch_mode is SandboxLaunchMode.EXECUTOR
        executor_enabled = launch_mode in {
            SandboxLaunchMode.EXECUTOR,
            SandboxLaunchMode.LEGACY_EXECUTOR,
        }
        if executor_enabled and not self.settings.chat_sandbox_executor_enabled:
            raise SandboxError(
                "sandbox_executor_disabled", "Sandbox executor launch is disabled"
            )
        if (
            executor_enabled
            and self.settings.chat_sandbox_executor_contract_version
            != EXECUTOR_PROTOCOL
        ):
            raise SandboxError(
                "sandbox_executor_contract_invalid",
                "Sandbox executor contract is invalid",
            )
        if remote_executor and executor_launch is None:
            raise SandboxError(
                "sandbox_executor_admission_missing",
                "Sandbox executor admission is unavailable",
            )
        rendezvous_url = (
            executor_launch.rendezvous_url(self.settings.environment)
            if remote_executor and executor_launch is not None
            else None
        )
        try:
            outbound_domains = sandbox_outbound_domains(self.settings)
        except ValueError as error:
            raise SandboxError(
                "gateway_unavailable", "The research gateway is not configured"
            ) from error
        with executor_stage("provider_lookup", worker_generation or "legacy"):
            app, image = await asyncio.gather(
                modal.App.lookup.aio(MODAL_APP_NAME, create_if_missing=False),
                self.image_resolver(self.settings.chat_modal_image_version),
            )
        persistent_enabled = bool(
            getattr(self.settings, "chat_persistent_worker_enabled", False)
        )
        qualification_profile = tags.get("qualification_profile")
        if qualification_profile == "32-functional-turns":
            from backend.services.durable_external_qualification_contract import (
                DURABLE_QUALIFICATION_SANDBOX_LIFETIME_SECONDS,
            )

            sandbox_lifetime_seconds = DURABLE_QUALIFICATION_SANDBOX_LIFETIME_SECONDS
        else:
            sandbox_lifetime_seconds = (
                self.settings.chat_persistent_sandbox_lifetime_seconds
                if persistent_enabled
                else 3600
            )
        worker_generation = worker_generation or secrets.token_hex(16)
        command = (
            (
                "/usr/local/bin/pwc-executor-environment",
                "--connect",
                rendezvous_url,
                "--admission-env",
                "PWC_CHAT_EXECUTOR_ADMISSION",
                "--authorization-env",
                "PWC_CHAT_EXECUTOR_AUTHORIZATION_KEYS",
            )
            if remote_executor
            else ("python", "-m", "backend.chat_sandbox_worker.executor_daemon")
            if executor_enabled
            else (
                ("python", "-m", "backend.chat_sandbox_worker.control_daemon")
                if persistent_enabled
                else ("sleep", "infinity")
            )
        )
        cpu_limit = (
            getattr(self.settings, "chat_sandbox_cpu_limit", None)
            or self.settings.chat_sandbox_cpu
        )
        memory_limit = (
            getattr(self.settings, "chat_sandbox_memory_limit_mib", None)
            or self.settings.chat_sandbox_memory_mib
        )
        if cpu_limit < self.settings.chat_sandbox_cpu:
            raise SandboxError("sandbox_resource_invalid", "CPU limit is below request")
        if memory_limit < self.settings.chat_sandbox_memory_mib:
            raise SandboxError(
                "sandbox_resource_invalid", "Memory limit is below request"
            )
        with executor_stage("provider_create", worker_generation):
            sandbox = await modal.Sandbox.create.aio(
                *command,
                app=app,
                image=image,
                env={
                    **sandbox_environment(
                        self.settings,
                        pi_prewarm=tags.get("pool") == "blank",
                    ),
                    "PWC_CHAT_WORKER_GENERATION": worker_generation,
                    **(
                        {
                            "PWC_CHAT_EXECUTOR_CONTRACT_VERSION": (
                                self.settings.chat_sandbox_executor_contract_version
                            ),
                        }
                        if executor_enabled
                        else {}
                    ),
                    **(
                        {
                            "PWC_CHAT_EXECUTOR_ADMISSION": (
                                executor_launch.encoded_admission()
                            ),
                            "PWC_CHAT_EXECUTOR_AUTHORIZATION_KEYS": (
                                executor_launch.authorization_keys()
                            ),
                        }
                        if remote_executor
                        else {}
                    ),
                },
                name=name,
                tags=tags,
                region=CHAT_SANDBOX_REGION,
                timeout=sandbox_lifetime_seconds,
                idle_timeout=(
                    sandbox_lifetime_seconds
                    if qualification_profile == "32-functional-turns"
                    else (
                        self.settings.chat_persistent_sandbox_lifetime_seconds
                        if persistent_enabled
                        else max(60, self.settings.chat_sandbox_warm_seconds)
                    )
                ),
                workdir="/workspace",
                cpu=(self.settings.chat_sandbox_cpu, cpu_limit),
                memory=(self.settings.chat_sandbox_memory_mib, memory_limit),
                outbound_domain_allowlist=[
                    *outbound_domains,
                    *(
                        ["chat-executor.paperswithcode.co"]
                        if remote_executor and self.settings.environment == "production"
                        else ["chat-executor-staging.paperswithcode.co"]
                        if remote_executor
                        else []
                    ),
                ],
                inbound_cidr_allowlist=(
                    None if persistent_enabled and not executor_enabled else []
                ),
                encrypted_ports=[],
                unencrypted_ports=[],
                include_oidc_identity_token=False,
                readiness_probe=modal.sandbox.Probe.with_exec(
                    *(
                        (
                            "python",
                            "-m",
                            "backend.chat_sandbox_worker.relay",
                            "--ping",
                            worker_generation,
                        )
                        if persistent_enabled and not executor_enabled
                        else (
                            (
                                "test",
                                "-S",
                                "/run/pwc-chat-executor/executor.sock",
                            )
                            if executor_enabled
                            else ("test", "-x", "/usr/local/bin/pwc")
                        )
                    )
                ),
            )
        if remote_executor:
            # Only authenticated durable registration establishes executor
            # readiness. Modal exec probes are intentionally not part of the
            # warm path and cannot establish remote identity.
            return sandbox
        if not persistent_enabled and not executor_enabled:
            return sandbox
        deadline = time.monotonic() + self.settings.chat_worker_ready_timeout_seconds
        while time.monotonic() < deadline:
            try:
                if await self.health(
                    sandbox,
                    persistent=True,
                    worker_generation=worker_generation,
                    launch_mode=launch_mode,
                ):
                    return sandbox
            except Exception:
                pass
            if await self.poll(sandbox) is not None:
                break
            await asyncio.sleep(0.05)
        await sandbox.terminate.aio(
            wait=self.settings.chat_sandbox_spend_enforcement_enabled
        )
        raise SandboxError(
            "sandbox_worker_not_ready", "Persistent worker readiness timed out"
        )

    async def resolve(self, sandbox_id: str) -> object:
        return await modal.Sandbox.from_id.aio(sandbox_id)

    async def poll(self, sandbox: object) -> object | None:
        return await sandbox.poll.aio()

    async def health(
        self,
        sandbox: object,
        *,
        persistent: bool,
        worker_generation: str | None,
        launch_mode: SandboxLaunchMode = SandboxLaunchMode.LEGACY,
    ) -> bool:
        if launch_mode in {
            SandboxLaunchMode.EXECUTOR,
            SandboxLaunchMode.LEGACY_EXECUTOR,
        }:
            command = ("test", "-S", str(EXECUTOR_SOCKET))
        elif persistent:
            if not worker_generation:
                raise ValueError("Persistent sandbox health requires a generation")
            command = (
                "python",
                "-m",
                "backend.chat_sandbox_worker.relay",
                "--ping",
                worker_generation,
            )
        else:
            command = ("test", "-x", "/usr/local/bin/pwc")
        probe = await sandbox.exec.aio(*command, timeout=5)
        await probe.wait.aio()
        return probe.returncode == 0

    async def terminate(self, sandbox_id: str, sandbox: object | None = None) -> bool:
        try:
            target = sandbox or await self.resolve(sandbox_id)
            if getattr(self.settings, "chat_sandbox_spend_enforcement_enabled", False):
                async with asyncio.timeout(
                    getattr(
                        self.settings,
                        "chat_sandbox_termination_grace_seconds",
                        30,
                    )
                ):
                    await target.terminate.aio(wait=True)
            else:
                await target.terminate.aio(wait=False)
            return True
        except NotFoundError:
            return True
        except Exception:
            return False

    async def open_persistent_connection(
        self, sandbox: object, worker_generation: str
    ) -> object:
        credentials = await sandbox.create_connect_token.aio(
            user_metadata={"worker_generation": worker_generation},
            port=CONTROL_PORT,
        )
        websocket_url = credentials.url.replace("https://", "wss://", 1)
        return await self.websocket_connector(
            websocket_url,
            additional_headers={"Authorization": f"Bearer {credentials.token}"},
            compression=None,
            proxy=None,
            open_timeout=5,
            ping_interval=20,
            ping_timeout=20,
            max_size=1024 * 1024,
        )

    async def open_turn_process(
        self, sandbox: object, *, timeout_seconds: int
    ) -> object:
        return await sandbox.exec.aio(
            "python",
            "-m",
            "backend.chat_sandbox_worker.supervisor",
            stdout=StreamType.PIPE,
            stderr=StreamType.PIPE,
            timeout=timeout_seconds,
            workdir="/workspace",
            text=False,
        )

    async def open_executor_relay(
        self, sandbox: object, *, timeout_seconds: int
    ) -> object:
        return await sandbox.exec.aio(
            "python",
            "-m",
            "backend.chat_sandbox_worker.executor_relay",
            stdout=StreamType.PIPE,
            stderr=StreamType.DEVNULL,
            timeout=timeout_seconds,
            workdir="/workspace",
            env={"PYTHONPATH": "/opt/pwc"},
            text=False,
        )

    async def iter_sandboxes(self, *, tags: dict[str, str]) -> AsyncIterator[object]:
        async for sandbox in modal.Sandbox.list.aio(tags=tags):
            yield sandbox

    async def get_tags(self, sandbox: object) -> dict[str, str]:
        return await sandbox.get_tags.aio()
