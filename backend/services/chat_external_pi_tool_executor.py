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
    ExternalExecutorWorkspace,
)
from backend.services.chat_sandbox_executor import (
    ExecutorContext,
    ExecutorExecutionLost,
    ExecutorExecutionResult,
    ExecutorOperationError,
    ExecutorTransportError,
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

type WorkspaceSettlement = Literal["release", "invalidate"]
type LifecycleObserver = Callable[[str, str | None, int], None]
type QualificationEvidenceRecorder = Callable[..., bool]


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
        self.active_context: ExecutorContext | None = None

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
        tool_call_id = str(request.get("tool_call_id") or "")
        context: ExecutorContext | None = None
        workspace: ExternalExecutorWorkspace | None = None
        settlement: WorkspaceSettlement = "invalidate"
        primary_exception_active = False
        try:
            workspace = await self._workspace_manager().acquire(
                session_id=self.admission.session_id,
                turn_claim=self._durable_turn_claim(),
            )
            context = await self._ensure_executor(workspace, tool_call_id, operation_id)
            if operation == "exec":
                result = await self.executor.exec_resumable(
                    context,
                    command=str(request["command"]),
                    timeout_ms=int(request["timeout_ms"]),
                )
                self._record_executor_start(operation_id, operation_kind="bash")
                if result.recovered:
                    self.observe("executor_recovery", "succeeded", 1)
                terminal = dict(result.terminal)
                settlement = "release"
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
            result = await self.executor.read_file(
                context,
                path=str(request["path"]),
                offset=int(request["offset"]),
                max_bytes=int(request["max_bytes"]),
            )
            self._record_executor_start(operation_id, operation_kind="read")
            settlement = "release"
            return {
                **base,
                "ok": True,
                "data_base64": base64.b64encode(result.data).decode("ascii"),
                "eof": result.eof,
            }
        except ExecutorExecutionLost:
            primary_exception_active = True
            if context is not None:
                settlement = (
                    "release" if await self.cancel_executor(context) else "invalidate"
                )
            raise
        except asyncio.CancelledError:
            primary_exception_active = True
            if context is not None:
                settlement = (
                    "release" if await self.cancel_executor(context) else "invalidate"
                )
            raise
        except ExecutorOperationError as error:
            if context is not None:
                settlement = "release"
            return {**base, "ok": False, "error": error.code}
        except (ExecutorTransportError, ProtocolError, SandboxError) as error:
            return {**base, "ok": False, "error": getattr(error, "code", "tool_failed")}
        finally:
            self.active_context = None
            if workspace is not None:
                await self._settle(
                    workspace,
                    settlement=settlement,
                    primary_exception_active=primary_exception_active,
                    stale_boundary=stale_boundary,
                )

    async def _ensure_executor(
        self,
        workspace: ExternalExecutorWorkspace,
        tool_call_id: str,
        operation_id: str,
    ) -> ExecutorContext:
        context = ExecutorContext(
            sandbox=workspace.sandbox,
            workspace_id=str(self.admission.session_id),
            workspace_generation=workspace.workspace_generation,
            session_id=str(self.admission.session_id),
            turn_id=str(self.admission.turn_id),
            execution_id=operation_id,
            tool_call_id=tool_call_id,
            worker_generation=workspace.worker_generation,
            capability=self.capability.token,
        )
        await self.executor.ensure_workspace(context)
        self.active_context = context
        return context

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

    async def cancel_executor(self, context: ExecutorContext) -> bool:
        try:
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
        workspace: ExternalExecutorWorkspace,
        *,
        settlement: WorkspaceSettlement,
        primary_exception_active: bool,
        stale_boundary: QualificationStaleFenceBoundary,
    ) -> None:
        manager = self._workspace_manager()
        if settlement == "release":
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
