"""Typed execution boundary for local and sandbox chat turns."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Protocol

from backend.config import Settings
from backend.database.connection import db_manager
from backend.services.chat_agent_service import stream_agent_events
from backend.services.chat_capability_service import (
    ChatCapabilityService,
    IssuedCapability,
)
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_session_service import ChatOwner, TurnAdmission
from backend.services.postgres_sdk_session_store import PostgresSDKSessionStore


class ChatTurnRunner(Protocol):
    sdk_directory: str

    def events(self) -> AsyncIterator[dict]: ...

    async def cancel(self) -> None: ...

    async def close(self) -> None: ...


class LocalChatTurnRunner:
    def __init__(
        self,
        *,
        settings: Settings,
        admission: TurnAdmission,
        prompt: str,
        resume_id: uuid.UUID | None,
        store: PostgresSDKSessionStore,
    ):
        self.settings = settings
        self.admission = admission
        self.prompt = prompt
        self.resume_id = resume_id
        self.store = store
        self.sdk_directory = settings.chat_agent_cwd

    async def events(self) -> AsyncIterator[dict]:
        async for event in stream_agent_events(
            self.prompt,
            self.settings,
            model_route=self.admission.model_route,
            session_store=self.store,
            resume=str(self.resume_id) if self.resume_id else None,
        ):
            yield event
            if event.get("type") in {"done", "error"}:
                return

    async def cancel(self) -> None:
        return

    async def close(self) -> None:
        return


class ModalChatTurnRunner:
    sdk_directory = "/workspace"

    def __init__(
        self,
        *,
        settings: Settings,
        admission: TurnAdmission,
        prompt: str,
        request_id: str,
        resume_id: uuid.UUID | None,
        capability: IssuedCapability,
    ):
        self.manager = SandboxSessionManager(settings)
        self.admission = admission
        self.prompt = prompt
        self.request_id = request_id
        self.resume_id = resume_id
        self.capability = capability
        self.capability_id: uuid.UUID | None = capability.capability_id

    def events(self) -> AsyncIterator[dict]:
        return self.manager.run_turn(
            chat_session_id=self.admission.session_id,
            turn_id=self.admission.turn_id,
            request_id=self.request_id,
            prompt=self.prompt,
            model=self.admission.model_route,
            resume=str(self.resume_id) if self.resume_id else None,
            capability=self.capability,
        )

    def _revoke(self) -> None:
        if self.capability_id is None:
            return
        with db_manager.session_local() as db:
            ChatCapabilityService(db).revoke(self.capability_id)
            db.commit()
        self.capability_id = None

    async def cancel(self) -> None:
        self._revoke()
        await self.manager.cancel(self.admission.session_id, self.admission.turn_id)

    async def close(self) -> None:
        self._revoke()


def create_chat_turn_runner(
    *,
    settings: Settings,
    owner: ChatOwner,
    admission: TurnAdmission,
    prompt: str,
    request_id: str,
    resume_id: uuid.UUID | None,
    store: PostgresSDKSessionStore,
) -> ChatTurnRunner:
    if admission.execution_backend == "local_mcp":
        return LocalChatTurnRunner(
            settings=settings,
            admission=admission,
            prompt=prompt,
            resume_id=resume_id,
            store=store,
        )
    if admission.execution_backend != "modal_cli":
        raise ValueError(
            f"Unsupported chat execution backend: {admission.execution_backend}"
        )
    with db_manager.session_local() as db:
        capability = ChatCapabilityService(db).issue(
            chat_session_id=admission.session_id,
            turn_id=admission.turn_id,
            owner_id=owner.hf_user_id,
            model=admission.model_route,
            scopes={"model", "catalog", "session_store"},
            sdk_session_id=resume_id,
            lifetime_seconds=round(settings.chat_agent_timeout_seconds + 60),
        )
        db.commit()
    return ModalChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt=prompt,
        request_id=request_id,
        resume_id=resume_id,
        capability=capability,
    )
