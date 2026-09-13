"""Fenced external-Pi tool execution inside retained executor workspaces."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal

from backend.chat_sandbox_worker.executor_protocol import ProtocolError
from backend.config import Settings
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_external_executor_workspace import (
    ChatExternalExecutorWorkspaceManager,
    ExternalExecutorTurnBinding,
    ExternalExecutorWorkspace,
    MIN_EXECUTOR_CLAIM_SECONDS,
)
from backend.services.chat_sandbox_executor import (
    ExecutorContext,
    ExecutorExecutionLost,
    ExecutorExecutionResult,
    ExecutorOperationError,
    ExecutorTransportError,
    PersistentExecutorChannel,
    SandboxExecutorClient,
)
from backend.services.chat_sandbox_provider import (
    ModalSandboxProviderAdapter,
    SandboxError,
)
from backend.services.chat_session_service import TurnAdmission
from backend.services.chat_turn_job_repository import TurnLeaseClaim
from backend.services.chat_qualification_stale_boundary import (
    QualificationStaleFenceBoundary,
)

type LifecycleObserver = Callable[[str, str | None, int], None]
type QualificationEvidenceRecorder = Callable[..., bool]
type ChannelFactory = Callable[
    [ExternalExecutorWorkspace, TurnLeaseClaim, int],
    Awaitable[PersistentExecutorChannel],
]


class _LegacyExecutorChannel:
    """Compatibility adapter until persistent admission selects the new route."""

    def __init__(self, executor: Any, sandbox: object) -> None:
        self.executor = executor
        self.sandbox = sandbox

    async def health(self) -> str:
        return await self.executor.health(self.sandbox)

    async def ensure_workspace(self, context: ExecutorContext) -> None:
        await self.executor.ensure_workspace(context)

    async def exec_resumable(self, context: ExecutorContext, **kwargs: Any):
        return await self.executor.exec_resumable(context, **kwargs)

    async def read_file(self, context: ExecutorContext, **kwargs: Any):
        return await self.executor.read_file(context, **kwargs)

    async def cancel(self, context: ExecutorContext) -> bool:
        result = await self.executor.cancel_execution(context)
        return isinstance(result, ExecutorExecutionResult) and is_safe_cancel_terminal(
            result.terminal
        )


def is_safe_cancel_terminal(terminal: object) -> bool:
    if not isinstance(terminal, Mapping) or set(terminal) != {
        "status",
        "exit_code",
        "error",
    }:
        return False
    status = terminal["status"]
    exit_code = terminal["exit_code"]
    if terminal["error"] is not None or status not in {"completed", "cancelled"}:
        return False
    if exit_code is not None and (
        not isinstance(exit_code, int)
        or isinstance(exit_code, bool)
        or not -(2**31) <= exit_code < 2**31
    ):
        return False
    return status == "cancelled" or exit_code is not None


class ExternalPiToolWorkspaceExecutor:
    """Execute one correlated tool operation and settle its workspace fence."""

    def __init__(
        self,
        *,
        settings: Settings,
        admission: TurnAdmission,
        capability: IssuedCapability,
        provider: Any | None,
        executor: SandboxExecutorClient | Any | None,
        workspace_manager: ChatExternalExecutorWorkspaceManager | Any | None,
        transition: Callable[[str], Awaitable[None]],
        observe: LifecycleObserver,
        record_evidence: QualificationEvidenceRecorder | None = None,
        channel_factory: ChannelFactory | None = None,
    ) -> None:
        self.settings = settings
        self.admission = admission
        self.capability = capability
        self.provider = provider or ModalSandboxProviderAdapter(settings)
        self.executor = executor or SandboxExecutorClient(self.provider)
        self.workspace_manager = workspace_manager
        self.transition = transition
        self.observe = observe
        self.record_evidence = record_evidence or (lambda **_kwargs: False)
        self.channel_factory = channel_factory
        self.active_context: ExecutorContext | None = None
        self._binding: ExternalExecutorTurnBinding | None = None
        self._binding_lock = asyncio.Lock()
        self._operation_limit = asyncio.Semaphore(4)
        self._hold_binding = False

    def begin_turn(self) -> None:
        """Keep the lazy binding until the runner's outermost cleanup boundary."""

        self._hold_binding = True

    async def settle_turn(self) -> None:
        """Settle and close the cached turn binding exactly once."""

        async with self._binding_lock:
            binding = self._binding
            self._hold_binding = False
            if binding is None or binding.settled:
                return
            boundary = QualificationStaleFenceBoundary(
                turn_id=self.admission.turn_id,
                chat_session_id=self.admission.session_id,
                recorder=self.record_evidence,
            )
            await self._settle(
                binding=binding,
                primary_exception_active=False,
                stale_boundary=boundary,
            )
            binding.settled = True
            self._binding = None

    async def tool_result(self, request: dict[str, object]) -> dict[str, object]:
        operation_id = str(request.get("operation_id") or "")
        tool_call_id = str(request.get("tool_call_id") or "")
        if not operation_id or not tool_call_id:
            raise ValueError("invalid_tool_identity")
        operation = request.get("operation")
        if operation not in {"exec", "read"}:
            raise ValueError("unsupported_tool_operation")
        await self.transition("waiting_tool")
        self.observe("turn_state", "waiting_tool", 1)
        stale_boundary = QualificationStaleFenceBoundary(
            turn_id=self.admission.turn_id,
            chat_session_id=self.admission.session_id,
            recorder=self.record_evidence,
        )
        result = await stale_boundary.call(
            self._execute(
                request,
                operation_id=operation_id,
                operation=operation,
                stale_boundary=stale_boundary,
            )
        )
        await self.transition("running")
        self.observe("turn_state", "running", 1)
        return result

    async def _execute(
        self,
        request: dict[str, object],
        *,
        operation_id: str,
        operation: str,
        stale_boundary: QualificationStaleFenceBoundary,
    ) -> dict[str, object]:
        base: dict[str, object] = {
            "type": "tool_result",
            "operation_id": operation_id,
        }
        context: ExecutorContext | None = None
        binding: ExternalExecutorTurnBinding | None = None
        primary_exception_active = False
        try:
            binding = await self._turn_binding(operation_id)
            context = self._context(binding.workspace, operation_id)
            self.active_context = context
            async with self._operation_limit:
                if operation == "exec":
                    result = await binding.channel.exec_resumable(
                        context,
                        command=str(request["command"]),
                        timeout_ms=int(request["timeout_ms"]),
                    )
                    self._record_executor_start(operation_id, operation_kind="bash")
                    if result.recovered:
                        self.observe("executor_recovery", "succeeded", 1)
                    terminal = dict(result.terminal)
                    return {
                        **base,
                        "ok": terminal.get("status") == "completed",
                        "outputs": list(result.outputs),
                        "terminal": terminal,
                        **(
                            {"error": str(terminal["error"])}
                            if terminal.get("error")
                            else {}
                        ),
                    }
                result = await binding.channel.read_file(
                    context,
                    path=str(request["path"]),
                    offset=int(request["offset"]),
                    max_bytes=int(request["max_bytes"]),
                )
                self._record_executor_start(operation_id, operation_kind="read")
                return {
                    **base,
                    "ok": True,
                    "data_base64": base64.b64encode(result.data).decode("ascii"),
                    "eof": result.eof,
                }
        except ExecutorExecutionLost:
            primary_exception_active = True
            if context is not None and binding is not None:
                if not await self.cancel_executor(context, channel=binding.channel):
                    binding.settlement = "invalidate"
            raise
        except asyncio.CancelledError:
            primary_exception_active = True
            if context is not None and binding is not None:
                if not await self.cancel_executor(context, channel=binding.channel):
                    binding.settlement = "invalidate"
            raise
        except ExecutorOperationError as error:
            return {**base, "ok": False, "error": error.code}
        except (ExecutorTransportError, ProtocolError, SandboxError) as error:
            if binding is not None:
                binding.settlement = "invalidate"
            return {**base, "ok": False, "error": getattr(error, "code", "tool_failed")}
        finally:
            self.active_context = None
            if binding is not None and not self._hold_binding:
                await self._settle_direct(
                    binding,
                    primary_exception_active=primary_exception_active,
                    stale_boundary=stale_boundary,
                )

    async def _turn_binding(
        self,
        operation_id: str,
    ) -> ExternalExecutorTurnBinding:
        async with self._binding_lock:
            if self._binding is not None:
                return self._binding
            manager = self._workspace_manager()
            turn_claim = self._durable_turn_claim()
            acquire_for_binding = getattr(manager, "acquire_for_binding", None)
            if acquire_for_binding is None:
                workspace = await manager.acquire(
                    session_id=self.admission.session_id,
                    turn_claim=turn_claim,
                )
            else:
                workspace = await acquire_for_binding(
                    session_id=self.admission.session_id,
                    turn_claim=turn_claim,
                )
            try:
                channel = (
                    await self.channel_factory(
                        workspace,
                        turn_claim,
                        MIN_EXECUTOR_CLAIM_SECONDS,
                    )
                    if self.channel_factory is not None
                    else _LegacyExecutorChannel(self.executor, workspace.sandbox)
                )
                if acquire_for_binding is not None and await channel.health() != "ok":
                    raise SandboxError(
                        "sandbox_worker_failed",
                        "Secure workspace executor is unavailable",
                    )
                context = self._context(workspace, operation_id)
                await channel.ensure_workspace(context)
            except asyncio.CancelledError:
                await self._invalidate(workspace, primary_exception_active=True)
                raise
            except Exception:
                await self._invalidate(workspace, primary_exception_active=True)
                raise
            binding = ExternalExecutorTurnBinding(
                workspace=workspace,
                channel=channel,
                settlement="release",
            )
            self._binding = binding
            return binding

    async def _ensure_executor(
        self,
        workspace: ExternalExecutorWorkspace,
        _tool_call_id: str,
        operation_id: str,
    ) -> ExecutorContext:
        """Compatibility seam for callers that perform a one-off legacy bind."""

        turn_claim = self._durable_turn_claim()
        context = ExecutorContext(
            sandbox=workspace.sandbox,
            workspace_id=str(self.admission.session_id),
            workspace_generation=workspace.workspace_generation,
            session_id=str(self.admission.session_id),
            turn_id=str(self.admission.turn_id),
            execution_id=operation_id,
            tool_call_id=operation_id,
            worker_generation=workspace.worker_generation,
            capability=self.capability.token,
            turn_worker_id=turn_claim.worker_id,
            turn_worker_generation=str(turn_claim.worker_generation),
            turn_lease_generation=str(turn_claim.lease_generation),
        )
        await self.executor.ensure_workspace(context)
        self.active_context = context
        return context

    def _context(
        self, workspace: ExternalExecutorWorkspace, operation_id: str
    ) -> ExecutorContext:
        turn_claim = self._durable_turn_claim()
        return ExecutorContext(
            sandbox=workspace.sandbox,
            workspace_id=str(self.admission.session_id),
            workspace_generation=workspace.workspace_generation,
            session_id=str(self.admission.session_id),
            turn_id=str(self.admission.turn_id),
            execution_id=operation_id,
            # Provider tool-call IDs are untrusted and can contain characters
            # outside the executor protocol. The harness-issued operation ID is
            # already unique, replay-stable, and bound to the provider call.
            tool_call_id=operation_id,
            worker_generation=workspace.worker_generation,
            capability=self.capability.token,
            turn_worker_id=turn_claim.worker_id,
            turn_worker_generation=str(turn_claim.worker_generation),
            turn_lease_generation=str(turn_claim.lease_generation),
        )

    def _record_executor_start(
        self, operation_id: str, *, operation_kind: Literal["read", "bash"]
    ) -> None:
        self.record_evidence(
            turn_id=self.admission.turn_id,
            chat_session_id=self.admission.session_id,
            event_type="executor_started",
            operation_id=operation_id,
            operation_kind=operation_kind,
        )

    async def cancel_executor(
        self,
        context: ExecutorContext,
        *,
        channel: PersistentExecutorChannel | None = None,
    ) -> bool:
        try:
            if channel is not None:
                return await channel.cancel(context)
            result = await self.executor.cancel_execution(context)
        except (
            ExecutorTransportError,
            ProtocolError,
            SandboxError,
            OSError,
            TimeoutError,
        ):
            return False
        if not isinstance(result, ExecutorExecutionResult):
            return False
        return is_safe_cancel_terminal(result.terminal)

    async def _settle(
        self,
        *,
        binding: ExternalExecutorTurnBinding,
        primary_exception_active: bool,
        stale_boundary: QualificationStaleFenceBoundary,
    ) -> None:
        manager = self._workspace_manager()
        workspace = binding.workspace
        close = getattr(binding.channel, "aclose", None)
        if close is not None:
            try:
                await close()
            except asyncio.CancelledError:
                binding.settlement = "invalidate"
                await self._invalidate(workspace, primary_exception_active=True)
                if not primary_exception_active:
                    raise
                return
            except Exception:
                binding.settlement = "invalidate"
        if binding.settlement == "release":
            try:
                released = await manager.release(workspace)
                if not released:
                    stale_boundary.reject()
                return
            except asyncio.CancelledError:
                await self._invalidate(
                    workspace,
                    primary_exception_active=primary_exception_active,
                )
                if not primary_exception_active:
                    raise
                return
            except Exception:
                # Cleanup is best-effort after the operation result is fixed. A
                # workspace-manager defect must not turn a successful tool call
                # into a duplicate-prone retry; invalidation below still fences
                # the workspace from reuse.
                pass
        await self._invalidate(
            workspace,
            primary_exception_active=primary_exception_active,
        )

    async def _settle_direct(
        self,
        binding: ExternalExecutorTurnBinding,
        *,
        primary_exception_active: bool,
        stale_boundary: QualificationStaleFenceBoundary,
    ) -> None:
        async with self._binding_lock:
            if binding.settled:
                return
            try:
                await self._settle(
                    binding=binding,
                    primary_exception_active=primary_exception_active,
                    stale_boundary=stale_boundary,
                )
            except asyncio.CancelledError:
                if not primary_exception_active:
                    raise
            binding.settled = True
            if self._binding is binding:
                self._binding = None

    async def _invalidate(
        self,
        workspace: ExternalExecutorWorkspace,
        *,
        primary_exception_active: bool,
    ) -> None:
        try:
            await self._workspace_manager().invalidate(workspace)
        except asyncio.CancelledError:
            if not primary_exception_active:
                raise
        except Exception:
            # Invalidation is the final cleanup boundary. Preserve the primary
            # tool/cancellation outcome even when a provider implementation has
            # an unexpected cleanup defect.
            return

    def _workspace_manager(self) -> ChatExternalExecutorWorkspaceManager:
        manager = self.workspace_manager
        if manager is None:
            manager = ChatExternalExecutorWorkspaceManager.from_settings(
                self.settings,
                provider=self.provider,
                executor=self.executor,
            )
            self.workspace_manager = manager
        return manager

    def _durable_turn_claim(self) -> TurnLeaseClaim:
        claim = self.admission.durable_claim
        if claim is None or claim.turn_id != self.admission.turn_id:
            raise RuntimeError("External Pi tool use requires the durable turn claim")
        return claim
