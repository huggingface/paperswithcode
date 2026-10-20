"""Atomic chat admission, title reservation, and guardrail history."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select

from backend.config import Settings
from backend.database.connection import db_manager
from backend.models.chat import ChatRequest
from backend.models.database import ChatMessageRecord
from backend.services.chat_durable_qualification_evidence import (
    ChatDurableQualificationEvidenceService,
)
from backend.services.chat_latency_service import ChatLatencyService
from backend.services.chat_paper_context_service import PreparedPaperTurn
from backend.services.chat_scope_guardrail_service import (
    ScopeMessage,
    build_scope_context,
)
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    TurnAdmission,
)


@dataclass(frozen=True)
class PreparedAdmission:
    admission: TurnAdmission
    transport: str
    title_token: uuid.UUID | None
    scope_messages: list[ScopeMessage]
    qualified: bool


def admit_prepared_turn(
    *,
    settings: Settings,
    owner: ChatOwner,
    body: ChatRequest,
    prepared: PreparedPaperTurn,
    request_id: str,
    search_is_available: bool,
    inference_credential_present: bool,
    qualification_scope: tuple[uuid.UUID, Literal["no_tool", "read", "bash"]] | None,
) -> PreparedAdmission:
    scope_messages = [ScopeMessage(role="user", content=body.message)]
    with db_manager.session_local() as db:
        try:
            qualification_context = (
                ChatDurableQualificationEvidenceService(db).require_active_context(
                    qualification_scope[0],
                    workload=qualification_scope[1],
                    settings=settings,
                )
                if qualification_scope is not None
                else None
            )
            service = ChatSessionService(db, settings)
            admission = service.begin_turn(
                owner,
                session_id=body.session_id,
                client_message_id=body.client_message_id,
                text=prepared.display_message,
                effective_prompt=prepared.effective_prompt,
                paper_mentions=prepared.mentions,
                primary_paper_id=prepared.primary_paper_id,
                primary_paper_context=prepared.primary_paper_context,
                viewer_context=prepared.viewer_context,
                paper_selection=prepared.paper_selection,
                initial_model=body.initial_model,
                replace_message_id=body.replace_message_id,
                prior_revision=body.prior_revision,
                retry_message_id=body.retry_message_id,
                web_search_enabled=body.web_search_enabled,
                reasoning_effort=body.reasoning_effort,
                update_web_search_preference=search_is_available,
                qualification=qualification_context,
            )
            transport = settings.chat_route_providers[admission.model_route]
            if (
                not getattr(admission, "attach_only", False)
                and transport == "huggingface"
                and settings.chat_route_funding_modes.get(admission.model_route)
                != "hf_org_funded"
                and not inference_credential_present
            ):
                raise ChatServiceError(
                    "hf_inference_billing_required",
                    402,
                    "Your Hugging Face Inference Providers authorization is "
                    "missing or expired. Re-sign in with Hugging Face to continue.",
                )
            title_token = (
                service.begin_title(
                    owner,
                    admission.session_id,
                    revision=admission.prompt_revision,
                )
                if admission.title_should_generate and not admission.replay_assistant
                else None
            )
            if not admission.replay_assistant and not getattr(
                admission, "attach_only", False
            ):
                latency = ChatLatencyService(db)
                latency.admit(
                    turn_id=admission.turn_id,
                    session_id=admission.session_id,
                    request_id=request_id,
                    settings=settings,
                    model_route=admission.model_route,
                    execution_backend=admission.execution_backend,
                    is_new_chat=body.session_id is None,
                    agent_harness=admission.agent_harness,
                )
                if qualification_context is not None and not latency.mark_qualification(
                    request_id,
                    scope_id=qualification_context.scope_id,
                    run_id=qualification_context.run_id,
                    profile=qualification_context.profile,
                    workload=qualification_scope[1],
                    scenario="reliability",
                ):
                    raise RuntimeError("qualification scope persistence failed")
                if settings.chat_scope_guardrail_enabled:
                    current_user = db.get(ChatMessageRecord, admission.user_message_id)
                    cutoff = (
                        admission.replacement_target_sequence
                        if admission.replacement_target_sequence is not None
                        else getattr(current_user, "sequence", 0)
                    )
                    prior_rows = list(
                        db.execute(
                            select(ChatMessageRecord)
                            .where(
                                ChatMessageRecord.session_id == admission.session_id,
                                ChatMessageRecord.sequence < cutoff,
                                ChatMessageRecord.role.in_(("user", "assistant")),
                                ChatMessageRecord.status == "complete",
                            )
                            .order_by(ChatMessageRecord.sequence.desc())
                            .limit(settings.chat_scope_guardrail_max_prior_messages)
                        ).scalars()
                    )
                    selected_paper = None
                    primary = prepared.primary_paper_context
                    if isinstance(primary, dict):
                        selected_paper = {
                            "title": primary.get("title"),
                            "route_id": primary.get("route_id"),
                        }
                    scope_messages = build_scope_context(
                        [
                            ScopeMessage(role=row.role, content=row.content)
                            for row in reversed(prior_rows)
                        ],
                        prepared.display_message,
                        max_prior_messages=(
                            settings.chat_scope_guardrail_max_prior_messages
                        ),
                        max_chars=settings.chat_scope_guardrail_max_context_chars,
                        selected_paper=selected_paper,
                    )
            db.commit()
        except ChatServiceError as exc:
            if exc.commit_changes:
                db.commit()
            else:
                db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
    return PreparedAdmission(
        admission=admission,
        transport=transport,
        title_token=title_token,
        scope_messages=scope_messages,
        qualified=qualification_context is not None,
    )
