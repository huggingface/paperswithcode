"""Durable Stop workflow across database and sandbox control boundaries."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy.orm import Session
from websockets.exceptions import WebSocketException

from backend.chat_sandbox_worker.executor_protocol import ProtocolError
from backend.config import Settings
from backend.services.chat_sandbox_executor import ExecutorTransportError
from backend.services.chat_sandbox_lease_lifecycle_coordinator import (
    SandboxCleanupUnverified,
)
from backend.services.chat_sandbox_provider import SandboxError
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_sandbox_worker_transport import WorkerCancelStatus
from backend.services.chat_session_service import (
    CancelTurnRequest,
    ChatOwner,
    ChatSessionService,
)
from backend.services.chat_turn_cancel_control import CancelControlResult

logger = logging.getLogger(__name__)


class ChatTurnCancellationCoordinator:
    """Commit durable cancellation before signalling current runner control."""

    def __init__(
        self,
        db: Session,
        settings: Settings,
        manager: SandboxSessionManager,
        *,
        external_cancel: Callable[[CancelTurnRequest], Awaitable[CancelControlResult]]
        | None = None,
        observe: Callable[[str, str | None, int], None] | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.manager = manager
        self.external_cancel = external_cancel
        self.observe = observe or (lambda _event, _code, _value: None)
        self.sessions = ChatSessionService(db, settings)

    async def cancel(self, owner: ChatOwner, session_id: uuid.UUID) -> None:
        request = self.sessions.request_cancel(owner, session_id)
        self.db.commit()
        if request is None:
            return
        self.observe("turn_state", "cancelling", 1)
        if self.external_cancel is not None:
            control = CancelControlResult.MISSING
            try:
                control = await self.external_cancel(request)
            except (
                ExecutorTransportError,
                OSError,
                ProtocolError,
                SandboxError,
                TimeoutError,
                WebSocketException,
            ) as error:
                logger.warning(
                    "durable external cancel control unavailable error=%s",
                    type(error).__name__,
                )
            if control is not CancelControlResult.REQUESTED:
                self.sessions.interrupt_cancel_without_control(owner, request)
                self.db.commit()
                self.observe("typed_failure", "cancel_control_missing", 1)
            return
        status: WorkerCancelStatus | None = None
        try:
            status = await self.manager.cancel_status(session_id, request.turn_id)
        except (SandboxError, SandboxCleanupUnverified):
            logger.exception(
                "Durable chat cancel delivery failed",
                extra={"chat_session_id": str(session_id)},
            )
        if status in {WorkerCancelStatus.COMPLETED, WorkerCancelStatus.PENDING}:
            return
        try:
            await self.manager.terminate(
                session_id, failure_code="cancel_control_missing"
            )
        except (SandboxError, SandboxCleanupUnverified):
            logger.exception(
                "Durable chat cancel termination failed",
                extra={"chat_session_id": str(session_id)},
            )
        self.sessions.interrupt_cancel_without_control(owner, request)
        self.db.commit()
