"""Transaction-scoped state transitions for the blank sandbox pool."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Mapping, Protocol

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.chat_sandbox_worker.mcp_app_registry import (
    EMPTY_EGRESS_POLICY_DIGEST,
    egress_policy_digest,
)
from backend.models.database import (
    ChatSandboxComputeInterval,
    ChatSandboxLease,
    ChatSandboxPool,
)

MODAL_CPU_USD_PER_CORE_SECOND = 0.00003942
MODAL_MEMORY_USD_PER_GIB_SECOND = 0.00000672


class CapacityLocker(Protocol):
    def __call__(self, db: Session, *, wait: bool = True) -> bool: ...


IntervalReserver = Callable[[str], uuid.UUID | None]
AvailabilityAssertion = Callable[[], None]


class LeaseLoader(Protocol):
    def __call__(
        self,
        db: Session,
        chat_session_id: uuid.UUID,
        *,
        lock: bool,
    ) -> ChatSandboxLease | None: ...


@dataclass(frozen=True)
class PoolCompatibility:
    image_version: str
    worker_contract_version: str
    cpu_request: float
    cpu_limit: float
    memory_request_mib: int
    memory_limit_mib: int
    agent_harness: str = "generic"
    agent_harness_version: str = "generic"
    model_profile: str = "generic"
    reasoning_profile: str = "generic"
    prompt_digest: str = "generic"
    provider_adapter_contract: str = "generic"
    egress_policy_digest: str = EMPTY_EGRESS_POLICY_DIGEST


@dataclass(frozen=True)
class BlankPoolCandidate:
    pool_id: uuid.UUID
    sandbox_id: str | None
    worker_generation: str
    claim_generation: int
    token_hash: str | None


@dataclass(frozen=True)
class BlankPoolClaim:
    pool_id: uuid.UUID
    sandbox_id: str
    worker_generation: str
    claim_generation: int
    token_hash: str


@dataclass(frozen=True)
class PoolStartReservation:
    pool_id: uuid.UUID
    worker_generation: str
    token_hash: str
    compatibility: PoolCompatibility
    app_release_id: str
    claim_generation: int
    interval_id: uuid.UUID | None


@dataclass(frozen=True)
class PoolEvictionRequired:
    chat_session_id: uuid.UUID


class PoolReservationUnavailable(StrEnum):
    CAPACITY_LOCKED = "capacity_locked"
    TARGET_SATISFIED = "target_satisfied"


class PoolLandingOutcome(StrEnum):
    LANDED = "landed"
    OWNERSHIP_CHANGED = "ownership_changed"


class PoolLandingDurability(StrEnum):
    BLANK_READY = "blank_ready"
    OWNERSHIP_MOVED = "ownership_moved"
    NOT_DURABLE = "not_durable"


@dataclass(frozen=True)
class PoolTerminationClaim:
    pool_id: uuid.UUID
    sandbox_id: str | None
    token_hash: str
    failure_code: str | None


class PoolTerminationFinishOutcome(StrEnum):
    FINISHED = "finished"
    OWNERSHIP_CHANGED = "ownership_changed"


@dataclass(frozen=True)
class PoolHealthCandidate:
    pool_id: uuid.UUID
    sandbox_id: str
    worker_generation: str
    claim_generation: int
    token_hash: str | None


@dataclass(frozen=True)
class PoolHealthCheckClaim:
    pool_id: uuid.UUID
    sandbox_id: str
    worker_generation: str
    claim_generation: int
    claim_token_hash: str | None
    health_token: str


class PoolHealthCheckFinishOutcome(StrEnum):
    HEALTHY = "healthy"
    DEAD = "dead"
    OWNERSHIP_CHANGED = "ownership_changed"


@dataclass(frozen=True)
class PoolHealthCheckFinish:
    outcome: PoolHealthCheckFinishOutcome
    termination_claim: PoolTerminationClaim | None = None


@dataclass(frozen=True)
class PoolMaintenancePlan:
    termination_claims: tuple[PoolTerminationClaim, ...]
    health_candidates: tuple[PoolHealthCandidate, ...]


class ProviderPoolDisposition(StrEnum):
    PROTECTED_ACTIVE = "protected_active"
    PROTECTED_FRESH_START = "protected_fresh_start"
    ORPHAN = "orphan"
    OUT_OF_SCOPE = "out_of_scope"
    INSPECTION_UNAVAILABLE = "inspection_unavailable"


@dataclass(frozen=True)
class ProviderPoolInspection:
    disposition: ProviderPoolDisposition
    interval_id: uuid.UUID | None = None
    termination_claim: PoolTerminationClaim | None = None


PoolReservationOutcome = (
    PoolStartReservation | PoolEvictionRequired | PoolReservationUnavailable
)


class ChatSandboxPoolRepository:
    """Mutate pool rows inside caller-owned transactions and lock scopes."""

    def __init__(
        self,
        settings: Settings,
        *,
        capacity_locker: CapacityLocker,
        lease_loader: LeaseLoader | None = None,
        token_factory: Callable[[], str] | None = None,
        worker_generation_factory: Callable[[], str] | None = None,
        pool_id_factory: Callable[[], uuid.UUID] | None = None,
    ):
        self.settings = settings
        self.capacity_locker = capacity_locker
        self.lease_loader = lease_loader or self._load_lease
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(24))
        self.worker_generation_factory = worker_generation_factory or (
            lambda: secrets.token_hex(16)
        )
        self.pool_id_factory = pool_id_factory or uuid.uuid4

    def compatibility(self) -> PoolCompatibility:
        pi_prewarm = self.settings.chat_pi_prewarm_enabled
        return PoolCompatibility(
            image_version=self.settings.chat_modal_image_version,
            worker_contract_version=self.settings.chat_worker_contract_version,
            cpu_request=self.settings.chat_sandbox_cpu,
            cpu_limit=(
                self.settings.chat_sandbox_cpu_limit or self.settings.chat_sandbox_cpu
            ),
            memory_request_mib=self.settings.chat_sandbox_memory_mib,
            memory_limit_mib=(
                self.settings.chat_sandbox_memory_limit_mib
                or self.settings.chat_sandbox_memory_mib
            ),
            agent_harness="pi" if pi_prewarm else "generic",
            agent_harness_version=(
                self.settings.chat_pi_version if pi_prewarm else "generic"
            ),
            model_profile=(
                self.settings.chat_effective_pi_prewarm_model
                if pi_prewarm
                else "generic"
            ),
            reasoning_profile=(
                self.settings.chat_pi_prewarm_reasoning_effort
                if pi_prewarm
                else "generic"
            ),
            prompt_digest=(
                self.settings.chat_system_prompt_sha256 if pi_prewarm else "generic"
            ),
            provider_adapter_contract=(
                self.settings.chat_pi_provider_adapter_contract
                if pi_prewarm
                else "generic"
            ),
            egress_policy_digest=egress_policy_digest(self.settings),
        )

    def acquire_capacity_lock(self, db: Session, *, wait: bool = True) -> bool:
        """Acquire the shared pool/lease/spend lock in the caller transaction."""

        return self.capacity_locker(db, wait=wait)

    def list_claim_candidates(
        self,
        db: Session,
        compatibility: PoolCompatibility,
        *,
        minimum_expires_at: datetime,
        limit: int,
    ) -> tuple[BlankPoolCandidate, ...]:
        rows = db.execute(
            select(
                ChatSandboxPool.id,
                ChatSandboxPool.modal_sandbox_id,
                ChatSandboxPool.worker_generation,
                ChatSandboxPool.claim_generation,
                ChatSandboxPool.claim_token_hash,
            )
            .where(
                ChatSandboxPool.state == "blank_ready",
                ChatSandboxPool.health_check_token_hash.is_(None),
                *self._compatibility_conditions(compatibility),
                ChatSandboxPool.expires_at > minimum_expires_at,
            )
            .order_by(ChatSandboxPool.ready_at)
            .limit(limit)
        ).all()
        return tuple(
            BlankPoolCandidate(
                pool_id=pool_id,
                sandbox_id=sandbox_id,
                worker_generation=worker_generation,
                claim_generation=claim_generation,
                token_hash=token_hash,
            )
            for (
                pool_id,
                sandbox_id,
                worker_generation,
                claim_generation,
                token_hash,
            ) in rows
        )

    def claim_blank(
        self,
        db: Session,
        candidate: BlankPoolCandidate,
        chat_session_id: uuid.UUID,
        compatibility: PoolCompatibility,
        *,
        minimum_expires_at: datetime,
        now: datetime,
        availability_assertion: AvailabilityAssertion | None = None,
    ) -> BlankPoolClaim | None:
        if not self.capacity_locker(db):
            return None
        if availability_assertion is not None:
            availability_assertion()
        existing_lease = self.lease_loader(db, chat_session_id, lock=True)
        if existing_lease is not None or candidate.sandbox_id is None:
            return None
        token_condition = (
            ChatSandboxPool.claim_token_hash.is_(None)
            if candidate.token_hash is None
            else ChatSandboxPool.claim_token_hash == candidate.token_hash
        )
        row = db.execute(
            select(ChatSandboxPool)
            .where(
                ChatSandboxPool.id == candidate.pool_id,
                ChatSandboxPool.state == "blank_ready",
                ChatSandboxPool.health_check_token_hash.is_(None),
                ChatSandboxPool.modal_sandbox_id == candidate.sandbox_id,
                ChatSandboxPool.worker_generation == candidate.worker_generation,
                ChatSandboxPool.claim_generation == candidate.claim_generation,
                token_condition,
                *self._compatibility_conditions(compatibility),
                ChatSandboxPool.expires_at > minimum_expires_at,
            )
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if row is None:
            return None
        token_hash = self._token_hash(self.token_factory())
        row.state = "claimed"
        row.claim_generation += 1
        row.claim_token_hash = token_hash
        row.claimed_at = now
        row.last_health_checked_at = now
        row.updated_at = now
        self.finalize_cost(row, now)
        db.add(
            ChatSandboxLease(
                chat_session_id=chat_session_id,
                modal_sandbox_id=candidate.sandbox_id,
                app_release_id=self.settings.release_id,
                image_version=compatibility.image_version,
                worker_contract_version=compatibility.worker_contract_version,
                egress_policy_digest=compatibility.egress_policy_digest,
                worker_generation=row.worker_generation,
                state="ready",
                last_activity_at=now,
                workspace_dirty=False,
                created_at=now,
                updated_at=now,
            )
        )
        return BlankPoolClaim(
            pool_id=row.id,
            sandbox_id=candidate.sandbox_id,
            worker_generation=row.worker_generation,
            claim_generation=row.claim_generation,
            token_hash=token_hash,
        )

    def reserve_starting_blank(
        self,
        db: Session,
        *,
        now: datetime,
        interval_reserver: IntervalReserver | None = None,
    ) -> PoolReservationOutcome:
        """Reserve one row; the optional spend action runs before the row is added."""

        if not self.capacity_locker(db, wait=False):
            return PoolReservationUnavailable.CAPACITY_LOCKED
        live_pool = (
            db.scalar(
                select(func.count())
                .select_from(ChatSandboxPool)
                .where(
                    ChatSandboxPool.state.in_(["starting", "blank_ready", "draining"])
                )
            )
            or 0
        )
        if (
            live_pool >= self.settings.chat_blank_pool_min
            or live_pool >= self.settings.chat_blank_pool_max
        ):
            return PoolReservationUnavailable.TARGET_SATISFIED
        live_assigned = (
            db.scalar(
                select(func.count())
                .select_from(ChatSandboxLease)
                .where(
                    ChatSandboxLease.state.in_(
                        ["starting", "ready", "busy", "idle", "terminating"]
                    )
                )
            )
            or 0
        )
        if live_pool + live_assigned >= self.settings.chat_sandbox_total_live_cap:
            session_id = db.execute(
                select(ChatSandboxLease.chat_session_id)
                .where(ChatSandboxLease.state == "idle")
                .order_by(ChatSandboxLease.last_activity_at)
                .limit(1)
            ).scalar_one_or_none()
            if session_id is None:
                return PoolReservationUnavailable.TARGET_SATISFIED
            return PoolEvictionRequired(session_id)

        compatibility = self.compatibility()
        worker_generation = self.worker_generation_factory()
        interval_id = (
            interval_reserver(worker_generation)
            if interval_reserver is not None
            else None
        )
        reservation = PoolStartReservation(
            pool_id=self.pool_id_factory(),
            worker_generation=worker_generation,
            token_hash=self._token_hash(self.token_factory()),
            compatibility=compatibility,
            app_release_id=self.settings.release_id,
            claim_generation=0,
            interval_id=interval_id,
        )
        db.add(
            ChatSandboxPool(
                id=reservation.pool_id,
                state="starting",
                image_version=compatibility.image_version,
                worker_contract_version=compatibility.worker_contract_version,
                agent_harness=compatibility.agent_harness,
                agent_harness_version=compatibility.agent_harness_version,
                model_profile=compatibility.model_profile,
                reasoning_profile=compatibility.reasoning_profile,
                prompt_digest=compatibility.prompt_digest,
                provider_adapter_contract=compatibility.provider_adapter_contract,
                egress_policy_digest=compatibility.egress_policy_digest,
                worker_generation=reservation.worker_generation,
                app_release_id=reservation.app_release_id,
                claim_generation=reservation.claim_generation,
                claim_token_hash=reservation.token_hash,
                created_at=now,
                expires_at=now
                + timedelta(
                    seconds=self.settings.chat_persistent_sandbox_lifetime_seconds
                ),
                updated_at=now,
                cpu_request=compatibility.cpu_request,
                cpu_limit=compatibility.cpu_limit,
                memory_request_mib=compatibility.memory_request_mib,
                memory_limit_mib=compatibility.memory_limit_mib,
                billing_month=self.billing_month(now),
            )
        )
        return reservation

    def land_provider_creation(
        self,
        db: Session,
        reservation: PoolStartReservation,
        sandbox_id: str,
        *,
        now: datetime,
        provider_create_ms: int | None = None,
        backend_control_connect_ms: int | None = None,
        broker_ready_ms: int | None = None,
        control_ready_ms: int | None = None,
        agent_spawn_ms: int | None = None,
        agent_startup_ready_ms: int | None = None,
    ) -> PoolLandingOutcome:
        if not self.capacity_locker(db):
            return PoolLandingOutcome.OWNERSHIP_CHANGED
        row = db.execute(
            select(ChatSandboxPool)
            .where(ChatSandboxPool.id == reservation.pool_id)
            .with_for_update()
        ).scalar_one_or_none()
        compatibility = reservation.compatibility
        if (
            row is None
            or row.state != "starting"
            or row.modal_sandbox_id is not None
            or row.claim_token_hash != reservation.token_hash
            or row.claim_generation != reservation.claim_generation
            or row.worker_generation != reservation.worker_generation
            or row.image_version != compatibility.image_version
            or row.worker_contract_version != compatibility.worker_contract_version
            or row.agent_harness != compatibility.agent_harness
            or row.agent_harness_version != compatibility.agent_harness_version
            or row.model_profile != compatibility.model_profile
            or row.reasoning_profile != compatibility.reasoning_profile
            or row.prompt_digest != compatibility.prompt_digest
            or row.provider_adapter_contract != compatibility.provider_adapter_contract
            or row.egress_policy_digest != compatibility.egress_policy_digest
            or row.app_release_id != reservation.app_release_id
            or row.cpu_request != compatibility.cpu_request
            or row.cpu_limit != compatibility.cpu_limit
            or row.memory_request_mib != compatibility.memory_request_mib
            or row.memory_limit_mib != compatibility.memory_limit_mib
        ):
            return PoolLandingOutcome.OWNERSHIP_CHANGED
        row.modal_sandbox_id = sandbox_id
        row.state = "blank_ready"
        row.ready_at = now
        row.last_health_checked_at = now
        row.updated_at = now
        row.provider_create_ms = provider_create_ms
        row.backend_control_connect_ms = backend_control_connect_ms
        row.broker_ready_ms = broker_ready_ms
        row.control_ready_ms = control_ready_ms
        row.agent_spawn_ms = agent_spawn_ms
        row.agent_startup_ready_ms = agent_startup_ready_ms
        self.finalize_cost(row, now)
        return PoolLandingOutcome.LANDED

    def provider_landing_durability(
        self,
        db: Session,
        reservation: PoolStartReservation,
        sandbox_id: str,
    ) -> PoolLandingDurability:
        """Classify an exact provider landing after an ambiguous database result."""

        row = db.get(ChatSandboxPool, reservation.pool_id)
        compatibility = reservation.compatibility
        if (
            row is None
            or row.modal_sandbox_id != sandbox_id
            or row.worker_generation != reservation.worker_generation
            or row.image_version != compatibility.image_version
            or row.worker_contract_version != compatibility.worker_contract_version
            or row.agent_harness != compatibility.agent_harness
            or row.agent_harness_version != compatibility.agent_harness_version
            or row.model_profile != compatibility.model_profile
            or row.reasoning_profile != compatibility.reasoning_profile
            or row.prompt_digest != compatibility.prompt_digest
            or row.provider_adapter_contract != compatibility.provider_adapter_contract
            or row.egress_policy_digest != compatibility.egress_policy_digest
            or row.app_release_id != reservation.app_release_id
            or row.cpu_request != compatibility.cpu_request
            or row.cpu_limit != compatibility.cpu_limit
            or row.memory_request_mib != compatibility.memory_request_mib
            or row.memory_limit_mib != compatibility.memory_limit_mib
        ):
            return PoolLandingDurability.NOT_DURABLE
        if row.state == "blank_ready":
            return PoolLandingDurability.BLANK_READY
        return PoolLandingDurability.OWNERSHIP_MOVED

    def claim_start_termination(
        self,
        db: Session,
        reservation: PoolStartReservation,
        expected_sandbox_id: str | None,
        *,
        failure_code: str,
        now: datetime,
    ) -> PoolTerminationClaim | None:
        """Fence cleanup to the exact starting reservation that created a provider."""

        if not self.capacity_locker(db):
            return None
        row = db.execute(
            select(ChatSandboxPool)
            .where(ChatSandboxPool.id == reservation.pool_id)
            .with_for_update()
        ).scalar_one_or_none()
        compatibility = reservation.compatibility
        if (
            row is None
            or row.state != "starting"
            or row.modal_sandbox_id != expected_sandbox_id
            or row.claim_token_hash != reservation.token_hash
            or row.claim_generation != reservation.claim_generation
            or row.worker_generation != reservation.worker_generation
            or row.image_version != compatibility.image_version
            or row.worker_contract_version != compatibility.worker_contract_version
            or row.agent_harness != compatibility.agent_harness
            or row.agent_harness_version != compatibility.agent_harness_version
            or row.model_profile != compatibility.model_profile
            or row.reasoning_profile != compatibility.reasoning_profile
            or row.prompt_digest != compatibility.prompt_digest
            or row.provider_adapter_contract != compatibility.provider_adapter_contract
            or row.egress_policy_digest != compatibility.egress_policy_digest
            or row.app_release_id != reservation.app_release_id
            or row.cpu_request != compatibility.cpu_request
            or row.cpu_limit != compatibility.cpu_limit
            or row.memory_request_mib != compatibility.memory_request_mib
            or row.memory_limit_mib != compatibility.memory_limit_mib
        ):
            return None
        token_hash = self._token_hash(self.token_factory())
        row.state = "draining"
        row.claim_token_hash = token_hash
        row.failure_code = self._termination_failure(
            row.failure_code,
            failure_code,
        )
        row.updated_at = now
        return PoolTerminationClaim(
            pool_id=row.id,
            sandbox_id=row.modal_sandbox_id,
            token_hash=token_hash,
            failure_code=row.failure_code,
        )

    def claim_termination(
        self,
        db: Session,
        pool_id: uuid.UUID,
        expected_sandbox_id: str | None,
        *,
        failure_code: str | None,
        now: datetime,
        stale_draining_before: datetime,
        capacity_locked: bool = False,
        allow_settled_claimed: bool = False,
    ) -> PoolTerminationClaim | None:
        if not capacity_locked and not self.capacity_locker(db):
            return None
        claimable_state = ChatSandboxPool.state.in_(
            ["starting", "blank_ready", "draining"]
        )
        if allow_settled_claimed:
            claimable_state = or_(
                claimable_state,
                self._settled_claimed_condition(),
            )
        row = db.execute(
            select(ChatSandboxPool)
            .where(ChatSandboxPool.id == pool_id, claimable_state)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None or row.health_check_token_hash is not None:
            return None
        if (
            expected_sandbox_id is not None
            and row.modal_sandbox_id != expected_sandbox_id
        ):
            return None
        if row.state == "draining" and self._as_utc(row.updated_at) > self._as_utc(
            stale_draining_before
        ):
            return None
        effective_failure = self._termination_failure(row.failure_code, failure_code)
        token_hash = self._token_hash(self.token_factory())
        row.state = "draining"
        row.claim_token_hash = token_hash
        row.failure_code = effective_failure
        row.updated_at = now
        return PoolTerminationClaim(
            pool_id=row.id,
            sandbox_id=row.modal_sandbox_id,
            token_hash=token_hash,
            failure_code=effective_failure,
        )

    @staticmethod
    def _settled_claimed_condition():
        active_lease = (
            select(ChatSandboxLease.chat_session_id)
            .where(
                ChatSandboxLease.modal_sandbox_id == ChatSandboxPool.modal_sandbox_id,
                ChatSandboxLease.state.in_(
                    ["starting", "ready", "busy", "idle", "terminating"]
                ),
            )
            .exists()
        )
        open_interval = (
            select(ChatSandboxComputeInterval.id)
            .where(
                ChatSandboxComputeInterval.modal_sandbox_id
                == ChatSandboxPool.modal_sandbox_id,
                ChatSandboxComputeInterval.terminal_at.is_(None),
            )
            .exists()
        )
        return and_(
            ChatSandboxPool.state == "claimed",
            ~active_lease,
            ~open_interval,
        )

    def finish_termination(
        self,
        db: Session,
        claim: PoolTerminationClaim,
        *,
        confirmed: bool,
        now: datetime,
    ) -> PoolTerminationFinishOutcome:
        if not self.capacity_locker(db):
            return PoolTerminationFinishOutcome.OWNERSHIP_CHANGED
        row = db.execute(
            select(ChatSandboxPool)
            .where(ChatSandboxPool.id == claim.pool_id)
            .with_for_update()
        ).scalar_one_or_none()
        if (
            row is None
            or row.state != "draining"
            or row.claim_token_hash != claim.token_hash
            or row.modal_sandbox_id != claim.sandbox_id
        ):
            return PoolTerminationFinishOutcome.OWNERSHIP_CHANGED
        failure_code = claim.failure_code
        if claim.sandbox_id is not None and not confirmed:
            failure_code = "termination_uncertain"
        self.finalize_cost(row, now)
        row.state = "failed" if failure_code else "terminated"
        row.failure_code = failure_code
        row.terminated_at = now
        row.updated_at = now
        return PoolTerminationFinishOutcome.FINISHED

    def plan_maintenance(
        self,
        db: Session,
        *,
        now: datetime,
        enabled: bool,
        budget_blocked: bool,
        starting_expired_before: datetime,
        rotation_before: datetime,
        stale_draining_before: datetime,
        termination_limit: int,
        scan_limit: int,
        capacity_locked: bool = False,
    ) -> PoolMaintenancePlan:
        """Claim bounded pool drains and return exact rows needing health I/O."""

        if not capacity_locked and not self.capacity_locker(db):
            return PoolMaintenancePlan((), ())
        compatibility = self.compatibility()
        rows = tuple(
            db.execute(
                select(ChatSandboxPool)
                .where(
                    or_(
                        ChatSandboxPool.state.in_(
                            ["starting", "blank_ready", "draining"]
                        ),
                        self._settled_claimed_condition(),
                    )
                )
                .order_by(ChatSandboxPool.updated_at, ChatSandboxPool.id)
                .limit(scan_limit)
                .with_for_update()
            ).scalars()
        )
        claims: list[PoolTerminationClaim] = []
        health_candidates: list[PoolHealthCandidate] = []
        for row in rows:
            incompatible = (
                row.app_release_id != self.settings.release_id
                or row.image_version != compatibility.image_version
                or row.worker_contract_version != compatibility.worker_contract_version
                or row.agent_harness != compatibility.agent_harness
                or row.agent_harness_version != compatibility.agent_harness_version
                or row.model_profile != compatibility.model_profile
                or row.reasoning_profile != compatibility.reasoning_profile
                or row.prompt_digest != compatibility.prompt_digest
                or row.provider_adapter_contract
                != compatibility.provider_adapter_contract
                or row.egress_policy_digest != compatibility.egress_policy_digest
                or row.cpu_request != compatibility.cpu_request
                or row.cpu_limit != compatibility.cpu_limit
                or row.memory_request_mib != compatibility.memory_request_mib
                or row.memory_limit_mib != compatibility.memory_limit_mib
            )
            creation_expired = row.state == "starting" and self._as_utc(
                row.updated_at
            ) <= self._as_utc(starting_expired_before)
            failure_code = (
                "sandbox_start_failed"
                if creation_expired
                else (
                    "sandbox_lost"
                    if row.state == "blank_ready" and row.modal_sandbox_id is None
                    else None
                )
            )
            should_drain = (
                row.state == "draining"
                or row.state == "claimed"
                or not enabled
                or incompatible
                or self._as_utc(row.expires_at) <= self._as_utc(rotation_before)
                or row.billing_month != self.billing_month(now)
                or budget_blocked
                or creation_expired
                or (row.state == "blank_ready" and row.modal_sandbox_id is None)
            )
            if row.health_check_token_hash is not None:
                continue
            if should_drain:
                if len(claims) >= termination_limit:
                    continue
                claim = self.claim_termination(
                    db,
                    row.id,
                    row.modal_sandbox_id,
                    failure_code=failure_code,
                    now=now,
                    stale_draining_before=stale_draining_before,
                    capacity_locked=True,
                    allow_settled_claimed=True,
                )
                if claim is not None:
                    claims.append(claim)
            elif row.state == "blank_ready" and row.modal_sandbox_id:
                health_candidates.append(
                    PoolHealthCandidate(
                        pool_id=row.id,
                        sandbox_id=row.modal_sandbox_id,
                        worker_generation=row.worker_generation,
                        claim_generation=row.claim_generation,
                        token_hash=row.claim_token_hash,
                    )
                )
        return PoolMaintenancePlan(tuple(claims), tuple(health_candidates))

    def claim_health_check(
        self,
        db: Session,
        candidate: PoolHealthCandidate,
        *,
        now: datetime,
    ) -> PoolHealthCheckClaim | None:
        """Take expiring, exact ownership before any provider health I/O."""

        if not self.capacity_locker(db):
            return None
        token_condition = (
            ChatSandboxPool.claim_token_hash.is_(None)
            if candidate.token_hash is None
            else ChatSandboxPool.claim_token_hash == candidate.token_hash
        )
        row = db.execute(
            select(ChatSandboxPool)
            .where(
                ChatSandboxPool.id == candidate.pool_id,
                ChatSandboxPool.state == "blank_ready",
                ChatSandboxPool.modal_sandbox_id == candidate.sandbox_id,
                ChatSandboxPool.worker_generation == candidate.worker_generation,
                ChatSandboxPool.claim_generation == candidate.claim_generation,
                token_condition,
                ChatSandboxPool.health_check_token_hash.is_(None),
                *self._compatibility_conditions(self.compatibility()),
            )
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if row is None:
            return None
        health_token = self.token_factory()
        row.health_check_token_hash = self._token_hash(health_token)
        row.health_check_started_at = now
        row.updated_at = now
        return PoolHealthCheckClaim(
            pool_id=row.id,
            sandbox_id=candidate.sandbox_id,
            worker_generation=row.worker_generation,
            claim_generation=row.claim_generation,
            claim_token_hash=row.claim_token_hash,
            health_token=health_token,
        )

    def health_check_owned(
        self,
        db: Session,
        claim: PoolHealthCheckClaim,
    ) -> bool:
        """Prove the exact health owner immediately before provider I/O."""

        return bool(
            db.execute(
                select(ChatSandboxPool.id).where(
                    *self._health_claim_conditions(claim),
                )
            ).scalar_one_or_none()
        )

    def finish_health_check(
        self,
        db: Session,
        claim: PoolHealthCheckClaim,
        *,
        healthy: bool,
        now: datetime,
    ) -> PoolHealthCheckFinish:
        """Settle only the exact health owner; never mutate a successor."""

        if not self.capacity_locker(db):
            return PoolHealthCheckFinish(PoolHealthCheckFinishOutcome.OWNERSHIP_CHANGED)
        row = db.execute(
            select(ChatSandboxPool)
            .where(*self._health_claim_conditions(claim))
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            return PoolHealthCheckFinish(PoolHealthCheckFinishOutcome.OWNERSHIP_CHANGED)
        row.health_check_token_hash = None
        row.health_check_started_at = None
        row.updated_at = now
        if healthy:
            row.last_health_checked_at = now
            self.finalize_cost(row, now)
            return PoolHealthCheckFinish(PoolHealthCheckFinishOutcome.HEALTHY)

        termination_token_hash = self._token_hash(self.token_factory())
        row.state = "draining"
        row.claim_token_hash = termination_token_hash
        row.failure_code = self._termination_failure(row.failure_code, "sandbox_lost")
        termination_claim = PoolTerminationClaim(
            pool_id=row.id,
            sandbox_id=row.modal_sandbox_id,
            token_hash=termination_token_hash,
            failure_code=row.failure_code,
        )
        return PoolHealthCheckFinish(
            PoolHealthCheckFinishOutcome.DEAD,
            termination_claim,
        )

    def reclaim_stale_health_checks(
        self,
        db: Session,
        *,
        cutoff: datetime,
        now: datetime,
        limit: int,
        capacity_locked: bool = False,
    ) -> tuple[PoolTerminationClaim, ...]:
        """Fence timed-out probes into verified cleanup exactly once."""

        if not capacity_locked and not self.capacity_locker(db):
            return ()
        rows = tuple(
            db.execute(
                select(ChatSandboxPool)
                .where(
                    ChatSandboxPool.state == "blank_ready",
                    ChatSandboxPool.health_check_token_hash.is_not(None),
                    ChatSandboxPool.health_check_started_at <= cutoff,
                )
                .order_by(ChatSandboxPool.health_check_started_at, ChatSandboxPool.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).scalars()
        )
        claims: list[PoolTerminationClaim] = []
        for row in rows:
            termination_token_hash = self._token_hash(self.token_factory())
            row.state = "draining"
            row.claim_token_hash = termination_token_hash
            row.health_check_token_hash = None
            row.health_check_started_at = None
            row.failure_code = self._termination_failure(
                row.failure_code,
                "health_check_timeout",
            )
            row.updated_at = now
            claims.append(
                PoolTerminationClaim(
                    pool_id=row.id,
                    sandbox_id=row.modal_sandbox_id,
                    token_hash=termination_token_hash,
                    failure_code=row.failure_code,
                )
            )
        return tuple(claims)

    def cleanup_terminal(
        self,
        db: Session,
        *,
        updated_before: datetime,
        limit: int,
    ) -> int:
        terminal_ids = tuple(
            db.execute(
                select(ChatSandboxPool.id)
                .where(
                    ChatSandboxPool.state.in_(["claimed", "terminated", "failed"]),
                    ChatSandboxPool.updated_at < updated_before,
                )
                .order_by(ChatSandboxPool.updated_at, ChatSandboxPool.id)
                .limit(limit)
            ).scalars()
        )
        if not terminal_ids:
            return 0
        return (
            db.execute(
                delete(ChatSandboxPool).where(
                    ChatSandboxPool.id.in_(terminal_ids),
                    ChatSandboxPool.state.in_(["claimed", "terminated", "failed"]),
                    ChatSandboxPool.updated_at < updated_before,
                )
            ).rowcount
            or 0
        )

    def classify_and_claim_provider_sandbox(
        self,
        db: Session,
        sandbox_id: str,
        tags: Mapping[str, str],
        *,
        environment: str,
        fresh_start_after: datetime,
        stale_draining_before: datetime,
        now: datetime,
        capacity_locked: bool = False,
    ) -> ProviderPoolInspection:
        """Classify one provider and claim an exact stale start or drain."""

        if tags.get("environment") != environment:
            return ProviderPoolInspection(ProviderPoolDisposition.OUT_OF_SCOPE)
        if not capacity_locked and not self.capacity_locker(db):
            return ProviderPoolInspection(
                ProviderPoolDisposition.INSPECTION_UNAVAILABLE
            )
        active_pool = db.execute(
            select(ChatSandboxPool.id)
            .where(
                ChatSandboxPool.modal_sandbox_id == sandbox_id,
                ChatSandboxPool.state.in_(["blank_ready", "draining"]),
            )
            .limit(1)
        ).scalar_one_or_none()
        if active_pool is not None:
            return ProviderPoolInspection(ProviderPoolDisposition.PROTECTED_ACTIVE)
        active_lease = db.execute(
            select(ChatSandboxLease.chat_session_id)
            .where(
                ChatSandboxLease.modal_sandbox_id == sandbox_id,
                ChatSandboxLease.state.in_(
                    ["starting", "ready", "busy", "idle", "terminating"]
                ),
            )
            .limit(1)
        ).scalar_one_or_none()
        if active_lease is not None:
            return ProviderPoolInspection(ProviderPoolDisposition.PROTECTED_ACTIVE)

        try:
            pool_id = uuid.UUID(str(tags["pool_id"]))
        except (KeyError, TypeError, ValueError):
            return ProviderPoolInspection(ProviderPoolDisposition.ORPHAN)
        pool = db.execute(
            select(ChatSandboxPool)
            .where(ChatSandboxPool.id == pool_id)
            .with_for_update()
        ).scalar_one_or_none()
        exact_identity = bool(
            pool is not None
            and tags.get("service") == "pwc-chat"
            and tags.get("pool") == "blank"
            and tags.get("release") == pool.app_release_id
            and tags.get("image") == pool.image_version
            and tags.get("contract") == pool.worker_contract_version
            and tags.get("egress") == pool.egress_policy_digest
        )
        if (
            exact_identity
            and pool is not None
            and pool.state == "starting"
            and pool.modal_sandbox_id in {None, sandbox_id}
            and self._as_utc(pool.updated_at) > self._as_utc(fresh_start_after)
        ):
            return ProviderPoolInspection(ProviderPoolDisposition.PROTECTED_FRESH_START)
        if (
            exact_identity
            and pool is not None
            and pool.state == "draining"
            and pool.modal_sandbox_id is None
            and self._as_utc(pool.updated_at) > self._as_utc(stale_draining_before)
        ):
            return ProviderPoolInspection(ProviderPoolDisposition.PROTECTED_ACTIVE)
        if not exact_identity or pool is None:
            return ProviderPoolInspection(ProviderPoolDisposition.ORPHAN)
        termination_claim = None
        if pool.state in {"starting", "draining"} and pool.modal_sandbox_id in {
            None,
            sandbox_id,
        }:
            requested_failure = (
                "sandbox_start_failed" if pool.state == "starting" else None
            )
            token_hash = self._token_hash(self.token_factory())
            pool.modal_sandbox_id = sandbox_id
            pool.state = "draining"
            pool.claim_token_hash = token_hash
            pool.failure_code = self._termination_failure(
                pool.failure_code,
                requested_failure,
            )
            pool.updated_at = now
            termination_claim = PoolTerminationClaim(
                pool_id=pool.id,
                sandbox_id=sandbox_id,
                token_hash=token_hash,
                failure_code=pool.failure_code,
            )
        if not getattr(
            self.settings,
            "chat_sandbox_spend_enforcement_enabled",
            False,
        ):
            return ProviderPoolInspection(
                ProviderPoolDisposition.ORPHAN,
                termination_claim=termination_claim,
            )
        interval = db.execute(
            select(
                ChatSandboxComputeInterval.id,
                ChatSandboxComputeInterval.modal_sandbox_id,
            )
            .where(
                ChatSandboxComputeInterval.environment == environment,
                ChatSandboxComputeInterval.origin == "blank_pool",
                ChatSandboxComputeInterval.worker_generation == pool.worker_generation,
                or_(
                    ChatSandboxComputeInterval.modal_sandbox_id.is_(None),
                    ChatSandboxComputeInterval.modal_sandbox_id == sandbox_id,
                ),
            )
            .order_by(ChatSandboxComputeInterval.reserved_at.desc())
            .limit(1)
            .with_for_update()
        ).one_or_none()
        return ProviderPoolInspection(
            ProviderPoolDisposition.ORPHAN,
            interval_id=(
                interval.id
                if interval is not None and interval.modal_sandbox_id is None
                else None
            ),
            termination_claim=termination_claim,
        )

    @staticmethod
    def billing_month(now: datetime) -> date:
        return now.date().replace(day=1)

    @staticmethod
    def finalize_cost(row: ChatSandboxPool, now: datetime) -> tuple[int, float]:
        created_at = ChatSandboxPoolRepository._as_utc(row.created_at)
        expires_at = ChatSandboxPoolRepository._as_utc(row.expires_at)
        end = min(now, expires_at)
        seconds = max(0, round((end - created_at).total_seconds()))
        cost = seconds * (
            float(row.cpu_request) * MODAL_CPU_USD_PER_CORE_SECOND
            + (float(row.memory_request_mib) / 1024 * MODAL_MEMORY_USD_PER_GIB_SECOND)
        )
        row.blank_billable_seconds = seconds
        row.estimated_blank_cost_usd = cost
        return seconds, cost

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def _termination_failure(existing: str | None, requested: str | None) -> str | None:
        return existing if existing is not None else requested

    @staticmethod
    def _compatibility_conditions(compatibility: PoolCompatibility) -> tuple:
        return (
            ChatSandboxPool.image_version == compatibility.image_version,
            ChatSandboxPool.worker_contract_version
            == compatibility.worker_contract_version,
            ChatSandboxPool.agent_harness == compatibility.agent_harness,
            ChatSandboxPool.agent_harness_version
            == compatibility.agent_harness_version,
            ChatSandboxPool.model_profile == compatibility.model_profile,
            ChatSandboxPool.reasoning_profile == compatibility.reasoning_profile,
            ChatSandboxPool.prompt_digest == compatibility.prompt_digest,
            ChatSandboxPool.provider_adapter_contract
            == compatibility.provider_adapter_contract,
            ChatSandboxPool.egress_policy_digest == compatibility.egress_policy_digest,
            ChatSandboxPool.cpu_request == compatibility.cpu_request,
            ChatSandboxPool.cpu_limit == compatibility.cpu_limit,
            ChatSandboxPool.memory_request_mib == compatibility.memory_request_mib,
            ChatSandboxPool.memory_limit_mib == compatibility.memory_limit_mib,
        )

    @classmethod
    def _health_claim_conditions(cls, claim: PoolHealthCheckClaim) -> tuple:
        claim_token_condition = (
            ChatSandboxPool.claim_token_hash.is_(None)
            if claim.claim_token_hash is None
            else ChatSandboxPool.claim_token_hash == claim.claim_token_hash
        )
        return (
            ChatSandboxPool.id == claim.pool_id,
            ChatSandboxPool.state == "blank_ready",
            ChatSandboxPool.modal_sandbox_id == claim.sandbox_id,
            ChatSandboxPool.worker_generation == claim.worker_generation,
            ChatSandboxPool.claim_generation == claim.claim_generation,
            claim_token_condition,
            ChatSandboxPool.health_check_token_hash
            == cls._token_hash(claim.health_token),
        )

    @staticmethod
    def _load_lease(
        db: Session,
        chat_session_id: uuid.UUID,
        *,
        lock: bool,
    ) -> ChatSandboxLease | None:
        query = select(ChatSandboxLease).where(
            ChatSandboxLease.chat_session_id == chat_session_id
        )
        if lock:
            query = query.with_for_update()
        return db.execute(query).scalar_one_or_none()
