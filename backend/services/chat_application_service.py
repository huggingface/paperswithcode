"""Application-owned preparation, admission, billing, and turn startup."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, replace
from typing import AsyncIterator, Literal

from backend.config import Settings
from backend.database.connection import db_manager
from backend.models.chat import ChatRequest
from backend.services.chat_admission_billing import authorize_openrouter
from backend.services.chat_admission_service import (
    PreparedAdmission,
    admit_prepared_turn,
)
from backend.services.chat_detached_runtime import (
    detached_chat_runtime,
    replay_detached_frames,
)
from backend.services.chat_durable_qualification_evidence import (
    QualificationEvidenceUnavailable,
    record_qualification_event_safely,
)
from backend.services.chat_live_stream_service import live_chat_stream_registry
from backend.services.chat_paper_context_service import (
    ChatPaperContextService,
    PreparedPaperTurn,
)
from backend.services.chat_sandbox_spend_access import (
    assert_chat_sandbox_spend_available,
)
from backend.services.chat_sandbox_spend_service import ChatComputeDisabled
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
)
from backend.services.chat_stream_service import ChatStreamFrame, ChatStreamOrchestrator
from backend.services.chat_turn_event_repository import JournalFrame
from backend.services.chat_web_search_service import web_search_available
from backend.services.deployment_lifecycle import deployment_lifecycle

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatTurnOutcome:
    kind: Literal["execute", "replay", "attach"]
    frames: AsyncIterator[ChatStreamFrame | JournalFrame]


class ChatApplicationError(Exception):
    def __init__(
        self,
        status_code: int,
        detail: str | dict,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail
        self.headers = headers

    @classmethod
    def from_service(cls, error: ChatServiceError, headers=None):
        return cls(
            error.status_code,
            {"code": error.code, "message": str(error), **error.details},
            headers,
        )


def _prepare_paper_turn(
    settings: Settings,
    owner_id: str,
    body: ChatRequest,
) -> PreparedPaperTurn:
    with db_manager.session_local() as db:
        return ChatPaperContextService(db, settings).prepare_turn(
            owner_id=owner_id,
            display_message=body.message,
            mentions=body.paper_mentions,
            session_id=body.session_id,
            replace_message_id=body.replace_message_id,
            primary_route_id=body.primary_paper_route_id,
            viewer_context=body.viewer_context,
            paper_selection=body.paper_selection,
        )


async def _release_durable_admission() -> None:
    """The database lease is released by turn finalization, not this callback."""


async def _never_disconnected() -> bool:
    """A durable turn outlives any one browser transport."""

    return False


class ChatApplicationService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def start_turn(
        self,
        *,
        body: ChatRequest,
        owner: ChatOwner,
        user_role: str | None,
        inference_credential_present: bool,
        qualification_scope=None,
        after_sequence: int = 0,
    ) -> ChatTurnOutcome:
        settings = self.settings
        search_is_available = self._check_available(body, user_role)
        request_id = str(uuid.uuid4())
        prepared = await self._prepare(body, owner, request_id)
        try:
            prepared_admission = await asyncio.to_thread(
                admit_prepared_turn,
                settings=settings,
                owner=owner,
                body=body,
                prepared=prepared,
                request_id=request_id,
                search_is_available=search_is_available,
                inference_credential_present=inference_credential_present,
                qualification_scope=qualification_scope,
            )
        except QualificationEvidenceUnavailable as exc:
            raise ChatApplicationError(
                409, {"code": "qualification_scope_unavailable"}
            ) from exc
        owner = await self._authorize(owner, prepared_admission)
        return await self._start(
            prepared_admission, prepared, owner, request_id, after_sequence
        )

    def _check_available(self, body: ChatRequest, user_role: str | None) -> bool:
        settings = self.settings
        if not settings.chat_enabled:
            raise ChatApplicationError(status_code=503, detail="Chat is not configured")
        if (
            body.paper_selection is not None
            and not settings.paper_reader_selection_enabled
        ):
            raise ChatApplicationError(
                status_code=409,
                detail={
                    "code": "paper_selection_disabled",
                    "message": "Paper selection is currently disabled. Remove it before sending.",
                },
            )
        if body.primary_paper_route_id is not None or body.paper_selection is not None:
            if not settings.paper_reader_chat_enabled:
                raise ChatApplicationError(
                    status_code=404,
                    detail={
                        "code": "paper_reader_chat_disabled",
                        "message": "Paper reader chat is not enabled.",
                    },
                )
            if settings.environment == "staging" and user_role != "admin":
                raise ChatApplicationError(
                    status_code=403,
                    detail={
                        "code": "staging_access_required",
                        "message": "Paper reader chat on staging is limited to the reviewer account.",
                    },
                )
        if (
            not settings.chat_public_admission_enabled
            or not settings.chat_sandbox_admission_enabled
        ):
            raise ChatApplicationError(
                status_code=503,
                detail={
                    "code": "chat_temporarily_disabled",
                    "message": "Chat is temporarily disabled. Your message was not sent.",
                },
            )
        if (
            settings.chat_default_backend == "modal_cli"
            and settings.chat_sandbox_spend_enforcement_enabled
        ):
            try:
                assert_chat_sandbox_spend_available(
                    settings,
                    session_factory=db_manager.session_local,
                )
            except ChatComputeDisabled as error:
                raise ChatApplicationError(
                    status_code=503,
                    detail={"code": error.code, "message": str(error)},
                ) from error
        search_is_available = web_search_available(settings)
        if body.web_search_enabled and not search_is_available:
            raise ChatApplicationError(
                status_code=503,
                detail={
                    "code": "web_search_unavailable",
                    "message": "Web search is temporarily unavailable. Turn Search off and retry.",
                },
            )
        if not deployment_lifecycle.status().accepting_chat_turns:
            raise ChatApplicationError(
                status_code=503,
                detail="A deployment is activating; retry this turn shortly",
                headers={"Retry-After": "3"},
            )
        return search_is_available

    async def _prepare(
        self, body: ChatRequest, owner: ChatOwner, request_id: str
    ) -> PreparedPaperTurn:
        settings = self.settings
        prepared = PreparedPaperTurn(body.message, body.message, [], 0, 0, 0)
        existing_prompt: str | None = None
        if body.session_id is not None:
            with db_manager.session_local() as replay_db:
                existing_prompt = ChatSessionService(
                    replay_db, settings
                ).existing_effective_prompt(
                    owner, body.session_id, body.client_message_id
                )
        if existing_prompt is not None:
            prepared = PreparedPaperTurn(body.message, existing_prompt, [], 0, 0, 0)
        else:
            started = time.perf_counter()
            try:
                prepared = await asyncio.wait_for(
                    asyncio.to_thread(
                        _prepare_paper_turn, settings, owner.hf_user_id, body
                    ),
                    timeout=settings.chat_paper_context_timeout_seconds,
                )
            except TimeoutError as exc:
                logger.info(
                    "chat paper context outcome=timeout elapsed_ms=%s",
                    round((time.perf_counter() - started) * 1000),
                )
                raise ChatApplicationError(
                    status_code=503,
                    detail={
                        "code": "paper_context_unavailable",
                        "message": "Attached paper context could not be prepared. Please retry.",
                    },
                    headers={"Retry-After": "2"},
                ) from exc
            except ChatServiceError as exc:
                logger.info(
                    "chat paper context outcome=%s elapsed_ms=%s",
                    exc.code,
                    round((time.perf_counter() - started) * 1000),
                )
                raise ChatApplicationError.from_service(
                    exc, {"Retry-After": "2"} if exc.status_code == 503 else None
                ) from exc
            logger.info(
                "chat paper context prepared request_id=%s papers=%s occurrences=%s bytes=%s truncated=%s elapsed_ms=%s",
                request_id,
                prepared.distinct_papers,
                len(prepared.mentions),
                prepared.included_bytes,
                prepared.truncated_papers,
                round((time.perf_counter() - started) * 1000),
            )
        return prepared

    async def _authorize(
        self, owner: ChatOwner, prepared_admission: PreparedAdmission
    ) -> ChatOwner:
        settings = self.settings
        admission = prepared_admission.admission
        transport = prepared_admission.transport
        if (
            prepared_admission.qualified
            and not admission.replay_assistant
            and not getattr(admission, "attach_only", False)
        ):
            await asyncio.to_thread(
                record_qualification_event_safely,
                turn_id=admission.turn_id,
                chat_session_id=admission.session_id,
                event_type="admitted_no_queue",
            )
        if (
            transport == "openrouter"
            and not admission.replay_assistant
            and not getattr(admission, "attach_only", False)
        ):
            try:
                with db_manager.session_local() as db:
                    openrouter = await authorize_openrouter(
                        settings,
                        db,
                        owner.hf_user_id,
                    )
            except ChatServiceError as exc:
                with db_manager.session_local() as db:
                    ChatSessionService(db, settings).fail_turn(
                        owner, admission, exc.code
                    )
                    db.commit()
                raise
            owner = replace(
                owner,
                openrouter_mode=openrouter.mode,
                openrouter_token=openrouter.token,
                openrouter_credential_revision=openrouter.credential_revision,
            )
        return owner

    async def _start(
        self,
        prepared_admission: PreparedAdmission,
        prepared: PreparedPaperTurn,
        owner: ChatOwner,
        request_id: str,
        after_sequence: int,
    ) -> ChatTurnOutcome:
        settings = self.settings
        admission = prepared_admission.admission
        if getattr(admission, "attach_only", False):
            return ChatTurnOutcome(
                "attach",
                replay_detached_frames(
                    detached_chat_runtime().coordinator,
                    admission,
                    request_id=request_id,
                    after_sequence=after_sequence,
                ),
            )
        orchestrator = ChatStreamOrchestrator(
            settings=settings,
            owner=owner,
            admission=admission,
            prompt=prepared.effective_prompt,
            display_message=prepared.title_prompt or prepared.display_message,
            request_id=request_id,
            title_token=prepared_admission.title_token,
            is_disconnected=_never_disconnected,
            release_admission=_release_durable_admission,
            scope_messages=prepared_admission.scope_messages,
        )
        if (
            settings.chat_durable_turn_dispatch_enabled
            and admission.replay_assistant is None
        ):
            claim = await orchestrator.claim_durable_turn()
            stream = await detached_chat_runtime(settings).start(
                admission=admission,
                owner_id=owner.hf_user_id,
                claim=claim,
                orchestrator=orchestrator,
            )
            return ChatTurnOutcome("execute", stream.subscribe(after_sequence))
        stream = live_chat_stream_registry().start(
            session_id=admission.session_id,
            turn_id=admission.turn_id,
            owner_id=owner.hf_user_id,
            source=orchestrator.events(),
        )
        kind = "replay" if admission.replay_assistant is not None else "execute"
        return ChatTurnOutcome(kind, stream.subscribe())
