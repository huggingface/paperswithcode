"""Compatibility façade for durable chat sandbox components."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Callable
from typing import cast

import modal
from google.protobuf.empty_pb2 import Empty
from modal.client import _Client
from modal_proto import api_pb2
from sqlalchemy.orm import Session
from websockets.asyncio.client import connect as websocket_connect

from backend.chat_sandbox_worker.contract import MODAL_APP_NAME
from backend.config import Settings
from backend.database.connection import db_manager
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_sandbox_acquisition_coordinator import (
    ChatSandboxAcquisitionCoordinator,
    LegacyEnsureReadyResult,
    legacy_ensure_ready_result,
)
from backend.services.chat_sandbox_capacity_repository import (
    ChatSandboxCapacityRepository,
)
from backend.services.chat_sandbox_lease_eviction_coordinator import (
    ChatSandboxLeaseEvictionCoordinator,
)
from backend.services.chat_sandbox_lease_lifecycle_coordinator import (
    ChatSandboxLeaseLifecycleCoordinator,
)
from backend.services.chat_sandbox_lease_lifecycle_coordinator import (
    SandboxCleanupUnverified as SandboxCleanupUnverified,  # noqa: PLC0414
)
from backend.services.chat_sandbox_lease_maintenance_coordinator import (
    ChatSandboxLeaseMaintenanceCoordinator,
)
from backend.services.chat_sandbox_pool_coordinator import (
    ChatSandboxPoolCoordinator,
    PoolMaintenanceResult,
    lock_pool_maintenance,
)
from backend.services.chat_sandbox_pool_repository import ChatSandboxPoolRepository
from backend.services.chat_sandbox_provider import (
    ModalSandboxProviderAdapter,
    SandboxError,
    SandboxProvider,
)
from backend.services.chat_sandbox_provider import (
    resolve_modal_image as _resolve_modal_image,
)
from backend.services.chat_sandbox_provider import (
    sandbox_environment as _sandbox_environment,
)
from backend.services.chat_sandbox_spend_alert_dispatcher import (
    ChatSandboxSpendAlertDispatcher,
)
from backend.services.chat_sandbox_spend_cap_coordinator import (
    ChatSandboxSpendCapCoordinator,
    SpendCapPublicResult,
)
from backend.services.chat_sandbox_spend_reconciler import (
    ChatSandboxSpendReconciler,
    PoolBudgetStatus,
    ProviderReconciliationOutcome,
)
from backend.services.chat_sandbox_spend_reporter import (
    ModalProviderSpendReporter,
    ProviderSpendReporter,
)
from backend.services.chat_sandbox_state_repository import ChatSandboxStateRepository
from backend.services.chat_sandbox_state_repository import (
    WorkerClaim as WorkerClaim,  # noqa: PLC0414
)
from backend.services.chat_sandbox_turn_coordinator import (
    ChatSandboxTurnCoordinator,
    ChatSandboxTurnRequest,
)
from backend.services.chat_sandbox_worker_transport import (
    ChatSandboxWorkerTransport,
    WorkerCancelStatus,
)
from backend.services.chat_sandbox_worker_transport import (
    RunningWorker as RunningWorker,  # noqa: PLC0414
)


async def resolve_modal_image(image_reference: str):
    """Compatibility export for qualification scripts and existing tests."""

    return await _resolve_modal_image(image_reference)


def sandbox_environment(settings: Settings) -> dict[str, str]:
    """Compatibility export for the provider worker environment."""

    return _sandbox_environment(settings)


async def _connect_provider_websocket(*args, **kwargs):
    """Resolve the legacy monkeypatch seam when the connection is opened."""

    return await websocket_connect(*args, **kwargs)


async def create_isolated_sandbox(
    settings: Settings,
    *,
    name: str,
    tags: dict[str, str],
    worker_generation: str | None = None,
):
    """Compatibility export backed by the provider adapter."""

    provider = ModalSandboxProviderAdapter(
        settings,
        image_resolver=resolve_modal_image,
        websocket_connector=_connect_provider_websocket,
    )
    return await provider.create(
        name=name,
        tags=tags,
        worker_generation=worker_generation,
    )


class WorkspaceSnapshotProvider:
    """Directory-only snapshots; never capture processes or the full filesystem."""

    supported = True

    def __init__(self, *, ttl_days: int = 30):
        self.ttl_seconds = ttl_days * 24 * 60 * 60

    async def save(self, sandbox, _chat_session_id: uuid.UUID) -> str:
        image = await sandbox.snapshot_directory.aio(
            "/workspace",
            timeout=55,
            ttl=self.ttl_seconds,
        )
        await image.hydrate.aio()
        return image.object_id

    async def restore(self, sandbox, snapshot_id: str) -> None:
        image = modal.Image.from_id(snapshot_id)
        await sandbox.mount_image.aio("/workspace", image)

    async def delete(self, _snapshot_id: str) -> None:
        # Modal Image currently has no early-delete API. Dropping the durable
        # reference revokes application access; provider TTL performs deletion.
        return


class SandboxSessionManager:
    MAINTENANCE_CONCURRENCY = 8

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: Callable[[], Session] | None = None,
        snapshot_provider: WorkspaceSnapshotProvider | None = None,
        sandbox_provider: SandboxProvider | None = None,
        state_repository: ChatSandboxStateRepository | None = None,
        capacity_repository: ChatSandboxCapacityRepository | None = None,
        pool_repository: ChatSandboxPoolRepository | None = None,
        pool_maintenance_owner: Callable[[], bool] | None = None,
        lease_eviction_coordinator: ChatSandboxLeaseEvictionCoordinator | None = None,
        lease_lifecycle_coordinator: ChatSandboxLeaseLifecycleCoordinator | None = None,
        lease_maintenance_coordinator: (
            ChatSandboxLeaseMaintenanceCoordinator | None
        ) = None,
        spend_alert_dispatcher: ChatSandboxSpendAlertDispatcher | None = None,
        spend_reporter: ProviderSpendReporter | None = None,
        spend_reconciler: ChatSandboxSpendReconciler | None = None,
    ):
        self.settings = settings
        self.session_factory = session_factory or db_manager.session_local
        if pool_repository is not None and pool_repository.settings is not settings:
            raise ValueError("Pool repository settings must be shared")
        if spend_alert_dispatcher is not None:
            if spend_alert_dispatcher.settings is not settings:
                raise ValueError("Spend alert dispatcher settings must be shared")
            if spend_alert_dispatcher.session_factory is not self.session_factory:
                raise ValueError("Spend alert dispatcher sessions must be shared")
        if spend_reporter is not None and spend_reporter.settings is not settings:
            raise ValueError("Spend reporter settings must be shared")
        if spend_reconciler is not None:
            if spend_reconciler.settings is not settings:
                raise ValueError("Spend reconciler settings must be shared")
            if spend_reconciler.session_factory is not self.session_factory:
                raise ValueError("Spend reconciler sessions must be shared")
            if (
                spend_reporter is not None
                and spend_reconciler.reporter is not spend_reporter
            ):
                raise ValueError("Spend reconciler reporter must be shared")
            if (
                pool_repository is not None
                and spend_reconciler.pool_repository is not pool_repository
            ):
                raise ValueError("Spend reconciler pool repository must be shared")
            spend_reporter = spend_reconciler.reporter
            pool_repository = spend_reconciler.pool_repository
        self._sandbox_provider = sandbox_provider
        self._sandbox_state = state_repository
        self._sandbox_capacity = capacity_repository
        self._sandbox_pool = pool_repository
        self._sandbox_pool_coordinator = None
        self._sandbox_lease_eviction = lease_eviction_coordinator
        self._sandbox_lease_lifecycle = lease_lifecycle_coordinator
        self._sandbox_lease_maintenance = lease_maintenance_coordinator
        self._sandbox_spend_alerts = spend_alert_dispatcher
        self._sandbox_spend_reporter = spend_reporter
        self._sandbox_spend_reconciler = spend_reconciler
        self._sandbox_spend_cap = None
        self._sandbox_acquisition = None
        self._sandbox_turn = None
        self.pool_maintenance_owner = pool_maintenance_owner or (lambda: True)
        self.snapshots = snapshot_provider or WorkspaceSnapshotProvider(
            ttl_days=settings.chat_workspace_snapshot_inactivity_days
        )
        self._worker_transport_state = ChatSandboxWorkerTransport(
            self._provider_adapter()
        )
        if settings.chat_workspace_snapshots_enabled and not self.snapshots.supported:
            raise SandboxError(
                "snapshot_unsupported",
                "Configured workspace snapshots require a Directory Snapshot provider",
            )

    def _provider_adapter(self) -> SandboxProvider:
        provider = getattr(self, "_sandbox_provider", None)
        if provider is not None:
            return provider
        provider = ModalSandboxProviderAdapter(
            self.settings,
            image_resolver=resolve_modal_image,
            websocket_connector=_connect_provider_websocket,
        )
        self._sandbox_provider = provider
        return provider

    def _worker_transport(self) -> ChatSandboxWorkerTransport:
        transport = getattr(self, "_worker_transport_state", None)
        if transport is None:
            transport = ChatSandboxWorkerTransport(self._provider_adapter())
            self._worker_transport_state = transport
        return transport

    def _state_repository(self) -> ChatSandboxStateRepository:
        repository = getattr(self, "_sandbox_state", None)
        if repository is None:
            repository = ChatSandboxStateRepository(self.settings)
            self._sandbox_state = repository
        return repository

    def _capacity_repository(self) -> ChatSandboxCapacityRepository:
        repository = getattr(self, "_sandbox_capacity", None)
        if repository is None:
            state_repository = self._state_repository()
            repository = ChatSandboxCapacityRepository(
                self.settings,
                state_repository,
            )
            self._sandbox_capacity = repository
        return repository

    def _pool_repository(self) -> ChatSandboxPoolRepository:
        repository = getattr(self, "_sandbox_pool", None)
        if repository is None:
            repository = ChatSandboxPoolRepository(
                self.settings,
                capacity_locker=self._capacity_repository().capacity_locker,
            )
            self._sandbox_pool = repository
        return repository

    def _lease_eviction_coordinator(self) -> ChatSandboxLeaseEvictionCoordinator:
        coordinator = getattr(self, "_sandbox_lease_eviction", None)
        if coordinator is None:
            transport = self._worker_transport()
            coordinator = ChatSandboxLeaseEvictionCoordinator(
                self.settings,
                session_factory=self.session_factory,
                repository=self._state_repository(),
                provider=cast(SandboxProvider, transport.provider),
                transport=transport,
                snapshots=self.snapshots,
                capacity_locker=self._capacity_repository().capacity_locker,
            )
            self._sandbox_lease_eviction = coordinator
        return coordinator

    def _pool_coordinator(self) -> ChatSandboxPoolCoordinator:
        coordinator = getattr(self, "_sandbox_pool_coordinator", None)
        if coordinator is None:
            transport = self._worker_transport()
            coordinator = ChatSandboxPoolCoordinator(
                self.settings,
                session_factory=self.session_factory,
                repository=self._pool_repository(),
                provider=cast(SandboxProvider, transport.provider),
                transport=transport,
                maintenance_owner=self.pool_maintenance_owner,
                maintenance_locker=lock_pool_maintenance,
                lease_eviction=self._lease_eviction_coordinator(),
            )
            self._sandbox_pool_coordinator = coordinator
        return coordinator

    def _lease_lifecycle_coordinator(self) -> ChatSandboxLeaseLifecycleCoordinator:
        coordinator = getattr(self, "_sandbox_lease_lifecycle", None)
        if coordinator is None:
            transport = self._worker_transport()
            coordinator = ChatSandboxLeaseLifecycleCoordinator(
                self.settings,
                session_factory=self.session_factory,
                repository=self._state_repository(),
                provider=cast(SandboxProvider, transport.provider),
                transport=transport,
                snapshots=self.snapshots,
                idle_eviction=self._lease_eviction_coordinator(),
                capacity_locker=self._capacity_repository().capacity_locker,
                termination_concurrency=self.MAINTENANCE_CONCURRENCY,
            )
            self._sandbox_lease_lifecycle = coordinator
        return coordinator

    def _lease_maintenance_coordinator(
        self,
    ) -> ChatSandboxLeaseMaintenanceCoordinator:
        coordinator = getattr(self, "_sandbox_lease_maintenance", None)
        if coordinator is None:
            transport = self._worker_transport()
            lifecycle = self._lease_lifecycle_coordinator()
            coordinator = ChatSandboxLeaseMaintenanceCoordinator(
                self.settings,
                session_factory=self.session_factory,
                repository=self._state_repository(),
                provider=cast(SandboxProvider, transport.provider),
                lifecycle=lifecycle,
                snapshots=self.snapshots,
                capacity_locker=lifecycle.capacity_locker,
                qualification_cleanup=self._cleanup_qualification_evidence,
            )
            self._sandbox_lease_maintenance = coordinator
        return coordinator

    def _cleanup_qualification_evidence(self) -> int:
        from backend.services.chat_durable_qualification_evidence import (
            ChatDurableQualificationEvidenceService,
        )

        with self.session_factory() as db, db.begin():
            return ChatDurableQualificationEvidenceService(db).cleanup_expired()

    def _spend_alert_dispatcher(self) -> ChatSandboxSpendAlertDispatcher:
        dispatcher = getattr(self, "_sandbox_spend_alerts", None)
        if dispatcher is None:
            dispatcher = ChatSandboxSpendAlertDispatcher(
                self.settings,
                session_factory=self.session_factory,
            )
            self._sandbox_spend_alerts = dispatcher
        return dispatcher

    def _spend_reporter(self) -> ProviderSpendReporter:
        reporter = getattr(self, "_sandbox_spend_reporter", None)
        if reporter is None:
            reporter = ModalProviderSpendReporter(self.settings)
            self._sandbox_spend_reporter = reporter
        return reporter

    def _spend_reconciler(self) -> ChatSandboxSpendReconciler:
        reconciler = getattr(self, "_sandbox_spend_reconciler", None)
        if reconciler is None:
            reconciler = ChatSandboxSpendReconciler(
                self.settings,
                session_factory=self.session_factory,
                reporter=self._spend_reporter(),
                pool_repository=self._pool_repository(),
            )
            self._sandbox_spend_reconciler = reconciler
        return reconciler

    def _spend_cap_coordinator(self) -> ChatSandboxSpendCapCoordinator:
        coordinator = getattr(self, "_sandbox_spend_cap", None)
        if coordinator is None:
            transport = self._worker_transport()
            coordinator = ChatSandboxSpendCapCoordinator(
                self.settings,
                session_factory=self.session_factory,
                lifecycle=self._lease_lifecycle_coordinator(),
                pool=self._pool_coordinator(),
                transport=transport,
                provider=cast(SandboxProvider, transport.provider),
                termination_concurrency=self.MAINTENANCE_CONCURRENCY,
            )
            self._sandbox_spend_cap = coordinator
        return coordinator

    def _acquisition_coordinator(self) -> ChatSandboxAcquisitionCoordinator:
        coordinator = getattr(self, "_sandbox_acquisition", None)
        if coordinator is None:
            transport = self._worker_transport()
            coordinator = ChatSandboxAcquisitionCoordinator(
                self.settings,
                session_factory=self.session_factory,
                state_repository=self._state_repository(),
                capacity_repository=self._capacity_repository(),
                pool=self._pool_coordinator(),
                provider=cast(SandboxProvider, transport.provider),
                transport=transport,
                snapshots=self.snapshots,
                lease_maintenance=self._lease_maintenance_coordinator(),
            )
            self._sandbox_acquisition = coordinator
        return coordinator

    def _turn_coordinator(self) -> ChatSandboxTurnCoordinator:
        coordinator = getattr(self, "_sandbox_turn", None)
        if coordinator is None:
            coordinator = ChatSandboxTurnCoordinator(
                self.settings,
                session_factory=self.session_factory,
                state_repository=self._state_repository(),
                acquisition=self._acquisition_coordinator(),
                transport=self._worker_transport(),
                lifecycle=self._lease_lifecycle_coordinator(),
                maintenance=self._lease_maintenance_coordinator(),
            )
            self._sandbox_turn = coordinator
        return coordinator

    def pool_budget_status(self) -> PoolBudgetStatus:
        return self._spend_reconciler().pool_budget_status()

    async def claim_blank(
        self, chat_session_id: uuid.UUID
    ) -> tuple[object, int] | None:
        return await self._pool_coordinator().claim_blank(chat_session_id)

    async def replenish_pool(self) -> int:
        return await self._pool_coordinator().replenish_pool()

    async def reconcile_pool_orphans(self) -> int:
        return await self._pool_coordinator().reconcile_pool_orphans()

    async def maintain_pool(self) -> dict[str, int]:
        result: PoolMaintenanceResult = await self._pool_coordinator().maintain_pool()
        return {
            "drained": result.drained,
            "lost": result.lost,
            "orphaned": result.orphaned,
            "abandoned": result.abandoned,
            "cleaned": result.cleaned,
            "replenished": result.replenished,
        }

    @property
    def ready_timeout_seconds(self) -> float:
        if getattr(self.settings, "chat_persistent_worker_enabled", False):
            return getattr(
                self.settings,
                "chat_worker_ready_timeout_seconds",
                self.settings.chat_sandbox_ready_timeout_seconds,
            )
        return self.settings.chat_sandbox_ready_timeout_seconds

    @property
    def blank_pool_enabled(self) -> bool:
        return bool(
            getattr(self.settings, "chat_blank_pool_enabled", False)
            and getattr(self.settings, "chat_sandbox_admission_enabled", True)
        )

    async def validate_image_reference(self) -> None:
        if self.settings.chat_sandbox_spend_enforcement_enabled:
            actual_environment = os.environ.get("MODAL_ENVIRONMENT", "")
            if actual_environment != self.settings.chat_sandbox_modal_environment:
                raise SandboxError(
                    "sandbox_identity_unverified",
                    "The sandbox provider Environment does not match deployment policy",
                )
            client = await _Client.from_env()
            try:
                token = await client.stub.TokenInfoGet(api_pb2.TokenInfoGetRequest())
                if self.settings.chat_sandbox_provider_mode == "starter_workspace":
                    if (
                        token.WhichOneof("identity") != "user_identity"
                        or token.workspace_name
                        != self.settings.chat_sandbox_modal_workspace
                        or token.user_identity.username
                        != self.settings.chat_sandbox_modal_owner_username
                    ):
                        raise SandboxError(
                            "sandbox_identity_unverified",
                            "The configured personal Workspace identity does not match deployment policy",
                        )
                elif (
                    token.WhichOneof("identity") != "service_user_identity"
                    or token.workspace_name
                    != self.settings.chat_sandbox_modal_workspace
                ):
                    raise SandboxError(
                        "sandbox_identity_unverified",
                        "A restricted Environment service identity is required",
                    )
                else:
                    environments = await client.stub.EnvironmentList(Empty())
                    visible_environments = {
                        item.name: item.environment_id for item in environments.items
                    }
                    if set(visible_environments) != {
                        self.settings.chat_sandbox_modal_environment
                    }:
                        raise SandboxError(
                            "sandbox_identity_unverified",
                            "The service identity must see only the chat Environment",
                        )
                    budget = await client.stub.EnvironmentGetBudget(
                        api_pb2.EnvironmentGetBudgetRequest(
                            environment_id=visible_environments[
                                self.settings.chat_sandbox_modal_environment
                            ]
                        )
                    )
                    configured_budget_microusd = (
                        round(budget.cycle_budget_dollars * 1_000_000)
                        if budget.HasField("cycle_budget_dollars")
                        else None
                    )
                    if (
                        configured_budget_microusd
                        != self.settings.chat_sandbox_environment_cap_microusd
                    ):
                        raise SandboxError(
                            "sandbox_budget_unverified",
                            "The provider Environment budget does not match deployment policy",
                        )
            finally:
                await client._close()
        try:
            await modal.App.lookup.aio(MODAL_APP_NAME, create_if_missing=False)
            await resolve_modal_image(self.settings.chat_modal_image_version)
        except Exception as error:
            raise SandboxError(
                "sandbox_image_unresolved",
                "The pinned sandbox image could not be resolved",
            ) from error

    async def ensure_ready(
        self,
        chat_session_id: uuid.UUID,
        *,
        allow_pool: bool = False,
        pool_miss: bool = False,
        pool_lookup_ms: int | None = None,
        budget_prechecked: bool = False,
    ) -> LegacyEnsureReadyResult:
        return legacy_ensure_ready_result(
            await self._acquisition_coordinator().acquire(
                chat_session_id,
                allow_pool=allow_pool,
                pool_miss=pool_miss,
                pool_lookup_ms=pool_lookup_ms,
                budget_prechecked=budget_prechecked,
            )
        )

    async def run_turn(
        self,
        *,
        chat_session_id: uuid.UUID,
        turn_id: uuid.UUID,
        request_id: str,
        prompt: str,
        model: str,
        provider_protocol: str = "anthropic-messages",
        provider_model: str | None = None,
        resume: str | None,
        capability: IssuedCapability,
        agent_harness: str = "claude",
        web_search_enabled: bool = False,
        reader_mode: bool = False,
        poster_mode: bool = False,
        paper_artifacts_enabled: bool = False,
        paper_descriptor: dict[str, object] | None = None,
        reasoning_effort: str = "high",
        fetchable_urls: list[str] | None = None,
        hf_username: str = "unknown",
    ) -> AsyncIterator[dict]:
        request = ChatSandboxTurnRequest(
            chat_session_id=chat_session_id,
            turn_id=turn_id,
            request_id=request_id,
            prompt=prompt,
            model=model,
            provider_protocol=provider_protocol,
            provider_model=provider_model,
            resume=resume,
            capability_token=capability.token,
            agent_harness=agent_harness,
            web_search_enabled=web_search_enabled,
            reader_mode=reader_mode,
            poster_mode=poster_mode,
            paper_artifacts_enabled=paper_artifacts_enabled,
            paper_descriptor=paper_descriptor,
            reasoning_effort=reasoning_effort,
            fetchable_urls=tuple(fetchable_urls or ()),
            hf_username=hf_username,
        )
        async for event in self._turn_coordinator().run(request):
            yield event

    async def cancel(self, chat_session_id: uuid.UUID, turn_id: uuid.UUID) -> bool:
        outcome = await self.cancel_status(chat_session_id, turn_id)
        return outcome is not WorkerCancelStatus.NOT_FOUND

    async def cancel_status(
        self, chat_session_id: uuid.UUID, turn_id: uuid.UUID
    ) -> WorkerCancelStatus:
        """Expose exact cancel delivery while preserving the legacy bool façade."""
        outcome = await self._turn_coordinator().cancel(chat_session_id, turn_id)
        return outcome

    async def terminate(
        self, chat_session_id: uuid.UUID, *, failure_code: str | None = None
    ) -> None:
        await self._lease_lifecycle_coordinator().terminate(
            chat_session_id,
            failure_code=failure_code,
        )

    async def cleanup_deleted(
        self, sandbox_id: str | None, snapshot_id: str | None
    ) -> None:
        await self._lease_lifecycle_coordinator().cleanup_deleted(
            sandbox_id,
            snapshot_id,
        )

    async def reap_idle(self) -> int:
        return await self._lease_maintenance_coordinator().reap_idle()

    async def snapshot_and_terminate(self, chat_session_id: uuid.UUID) -> bool:
        outcome = await self._lease_eviction_coordinator().evict_idle(chat_session_id)
        return outcome.acquired

    async def enforce_warm_cap(self) -> int:
        return await self._lease_maintenance_coordinator().enforce_warm_cap()

    async def enforce_spend_cap(self) -> SpendCapPublicResult:
        result = await self._spend_cap_coordinator().enforce()
        return {
            "state": result.state,
            "terminated": result.terminated,
            "uncertain": result.uncertain,
        }

    async def deliver_spend_alerts(self) -> int:
        return await self._spend_alert_dispatcher().deliver_pending()

    async def reconcile_spend_provider(self) -> bool:
        outcome = await self._spend_reconciler().reconcile_provider()
        return outcome is ProviderReconciliationOutcome.RECONCILED

    async def reconcile(self) -> int:
        """Converge expired creations and provider-lost sandbox leases."""
        return await self._lease_maintenance_coordinator().reconcile()

    async def expire_inactive_snapshots(self) -> int:
        return await self._lease_maintenance_coordinator().expire_inactive_snapshots()
