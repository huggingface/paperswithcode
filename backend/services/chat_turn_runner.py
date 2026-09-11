"""Typed execution boundary for local and sandbox chat turns."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from threading import Lock
from typing import Protocol

from backend.config import Settings
from backend.database.connection import db_manager
from backend.services.chat_agent_service import stream_agent_events
from backend.services.chat_capability_service import (
    ChatCapabilityService,
    IssuedCapability,
)
from backend.services.chat_external_pi_turn_runner import ExternalPiChatTurnRunner
from backend.services.chat_latency_service import ChatLatencyService
from backend.services.chat_durable_lifecycle_observer import (
    durable_lifecycle_observer,
)
from backend.services.chat_durable_qualification_evidence import (
    ChatDurableQualificationEvidenceService,
)
from backend.services.chat_sandbox_service import SandboxSessionManager
from backend.services.chat_session_service import ChatOwner, TurnAdmission
from backend.services.chat_web_search_service import opaque_owner
from backend.services.postgres_sdk_session_store import PostgresSDKSessionStore


class ChatTurnRunner(Protocol):
    sdk_directory: str

    def events(self) -> AsyncIterator[dict]: ...

    async def cancel(self) -> None: ...

    async def close(self) -> None: ...


def _uses_external_pi(
    settings: Settings,
    admission: TurnAdmission,
    *,
    qualification_authorized: bool = False,
) -> bool:
    return bool(
        (settings.chat_external_pi_admission_enabled or qualification_authorized)
        and admission.agent_harness == "pi"
        and admission.execution_backend == "modal_cli"
    )


class LocalChatTurnRunner:
    def __init__(
        self,
        *,
        settings: Settings,
        admission: TurnAdmission,
        prompt: str,
        resume_id: uuid.UUID | None,
        store: PostgresSDKSessionStore,
        owner: ChatOwner,
    ):
        self.settings = settings
        self.admission = admission
        self.prompt = prompt
        self.resume_id = resume_id
        self.store = store
        self.owner = owner
        self.sdk_directory = settings.chat_agent_cwd

    async def events(self) -> AsyncIterator[dict]:
        yield {"type": "workspace_ready"}
        provider = self.settings.chat_route_providers[self.admission.model_route]
        if provider == "openrouter":
            raise RuntimeError(
                "OpenRouter calls require the private gateway accounting boundary"
            )
        else:
            provider_token = self.owner.hf_inference_token or ""
            provider_base_url = "https://router.huggingface.co"
        if not provider_token:
            raise RuntimeError(f"{provider} chat credentials are not configured")
        async for event in stream_agent_events(
            self.prompt,
            self.settings,
            provider_token=provider_token,
            provider_base_url=provider_base_url,
            model_route=self.admission.model_route,
            session_store=self.store,
            resume=str(self.resume_id) if self.resume_id else None,
            web_search_enabled=self.admission.web_search_enabled,
            reader_mode=self.admission.reader_mode,
            reasoning_effort=self.admission.reasoning_effort,
            owner_hash=opaque_owner(self.owner.hf_user_id),
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
        hf_username: str,
        manager: SandboxSessionManager | None = None,
    ):
        self.manager = manager or shared_sandbox_manager(settings)
        self.admission = admission
        self.prompt = prompt
        self.request_id = request_id
        self.resume_id = resume_id
        self.capability = capability
        self.hf_username = hf_username
        self.capability_id: uuid.UUID | None = capability.capability_id

    def events(self) -> AsyncIterator[dict]:
        return self.manager.run_turn(
            chat_session_id=self.admission.session_id,
            turn_id=self.admission.turn_id,
            request_id=self.request_id,
            prompt=self.prompt,
            model=self.admission.model_route,
            provider_protocol=self.manager.settings.chat_route_protocols[
                self.admission.model_route
            ],
            provider_model=self.manager.settings.chat_route_provider_models[
                self.admission.model_route
            ],
            resume=str(self.resume_id) if self.resume_id else None,
            capability=self.capability,
            agent_harness=self.admission.agent_harness,
            web_search_enabled=self.admission.web_search_enabled,
            reader_mode=self.admission.reader_mode,
            poster_mode=self.admission.poster_mode,
            paper_artifacts_enabled=self.admission.paper_artifacts_enabled,
            paper_descriptor=self.admission.paper_descriptor,
            reasoning_effort=self.admission.reasoning_effort,
            fetchable_urls=list(self.admission.fetchable_urls),
            hf_username=self.hf_username,
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


_manager_lock = Lock()
_manager_settings: Settings | None = None
_manager: SandboxSessionManager | None = None


def _provider_mode_for_route(
    settings: Settings, owner: ChatOwner, model_route: str
) -> str:
    provider = settings.chat_route_providers[model_route]
    if provider == "openrouter":
        return owner.openrouter_mode
    if provider == "openai":
        return "openai_funded"
    return "huggingface"


def shared_sandbox_manager(settings: Settings) -> SandboxSessionManager:
    """Keep persistent control attachments alive across HTTP turn runners."""

    global _manager, _manager_settings
    with _manager_lock:
        if _manager is None or _manager_settings is not settings:
            from backend.services.deployment_lifecycle import deployment_lifecycle

            _manager = SandboxSessionManager(
                settings,
                pool_maintenance_owner=deployment_lifecycle.owns_active_slot,
            )
            _manager_settings = settings
        return _manager


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
            owner=owner,
        )
    if admission.execution_backend != "modal_cli":
        raise ValueError(
            f"Unsupported chat execution backend: {admission.execution_backend}"
        )
    with db_manager.session_local() as db:
        provider = settings.chat_route_providers[admission.model_route]
        provider_mode = _provider_mode_for_route(settings, owner, admission.model_route)
        if provider == "openrouter" and provider_mode not in {
            "openrouter_funded",
            "openrouter_byok",
        }:
            raise ValueError("OpenRouter turn has no typed credential admission")
        qualification_authorized = (
            False
            if settings.chat_external_pi_admission_enabled
            else ChatDurableQualificationEvidenceService(db).external_pi_authorized(
                turn_id=admission.turn_id,
                chat_session_id=admission.session_id,
                settings=settings,
            )
        )
        uses_external_pi = _uses_external_pi(
            settings,
            admission,
            qualification_authorized=qualification_authorized,
        )
        # WebFetch is intentionally dormant for both harnesses during the
        # controlled Pi comparison. The trusted gateway route remains intact.
        scopes = {"model", "catalog", "session_store"}
        if admission.web_search_enabled:
            scopes.add("web_search")
        if settings.chat_hf_catalog_enabled:
            scopes.add("hf_catalog")
        if admission.poster_mode:
            scopes.add("artifact")
        if admission.paper_artifacts_enabled:
            scopes.add("paper")
        if uses_external_pi:
            scopes.add("external_turn")
            # Admission recorded the Modal sandbox shape because routing is only
            # resolved here. Correct it before the turn is billed for compute it
            # never uses.
            ChatLatencyService(db).mark_external_pi(request_id)
        capability = ChatCapabilityService(db).issue(
            chat_session_id=admission.session_id,
            turn_id=admission.turn_id,
            owner_id=owner.hf_user_id,
            provider_token=(
                owner.hf_inference_token
                if provider == "huggingface"
                else (
                    owner.openrouter_token
                    if provider_mode == "openrouter_byok"
                    else None
                )
            ),
            provider_bill_to=(
                owner.hf_inference_bill_to if provider == "huggingface" else None
            ),
            settings=settings,
            provider_mode=provider_mode,
            provider_credential_revision=owner.openrouter_credential_revision,
            reasoning_effort=admission.reasoning_effort,
            model=admission.model_route,
            scopes=scopes,
            sdk_session_id=resume_id,
            agent_harness=admission.agent_harness,
            lifetime_seconds=round(
                (
                    settings.chat_posterly_timeout_seconds
                    if admission.poster_mode
                    else settings.chat_agent_timeout_seconds
                )
                + 60
            ),
        )
        db.commit()
    runner_type = ExternalPiChatTurnRunner if uses_external_pi else ModalChatTurnRunner
    runner_kwargs = dict(
        settings=settings,
        admission=admission,
        prompt=prompt,
        request_id=request_id,
        resume_id=resume_id,
        capability=capability,
        hf_username=owner.hf_username,
    )
    if runner_type is ExternalPiChatTurnRunner:
        runner_kwargs["observe"] = durable_lifecycle_observer(settings)
    return runner_type(**runner_kwargs)
