"""Bounded, content-free durable bridge probe for staging load tests."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.loadtests.chat_core import Metric
from backend.models.database import ChatSession, ChatTurnJob
from backend.scripts.qualify_chat_durable_dispatch import (
    CONFIRMATION as QUALIFICATION_CONFIRMATION,
)
from backend.scripts.qualify_chat_durable_dispatch import (
    QualificationRefused,
    SchemaAudit,
    validate_operator_context,
    validate_schema_audit,
)
from backend.services.chat_turn_admission_coordinator import (
    ChatTurnAdmissionCoordinator,
)
from backend.services.chat_turn_job_repository import ChatTurnJobRepository


@dataclass(frozen=True, slots=True)
class BridgeProbeResult:
    metrics: tuple[Metric, ...]
    failure_code: str | None

    @property
    def success(self) -> bool:
        return self.failure_code is None and all(
            metric.success for metric in self.metrics
        )


class OverlapGate(Protocol):
    def wait(self, participant: str) -> bool: ...


class TwoPartyOverlapGate:
    """One-shot, bounded rendezvous for two distinct process-local probes."""

    _TIMEOUT_SECONDS = 5.0

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._participants: set[str] = set()
        self._released_participants: frozenset[str] | None = None
        self._broken = False

    def wait(self, participant: str) -> bool:
        deadline = time.monotonic() + self._TIMEOUT_SECONDS
        with self._condition:
            if (
                self._broken
                or participant in self._participants
                or self._released_participants is not None
            ):
                return False
            self._participants.add(participant)
            if len(self._participants) == 2:
                self._released_participants = frozenset(self._participants)
                self._condition.notify_all()
                return True
            while self._released_participants is None and not self._broken:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._broken = True
                    self._condition.notify_all()
                    return False
                self._condition.wait(remaining)
            return (
                self._released_participants is not None
                and participant in self._released_participants
            )


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def run_durable_bridge_probe(
    *,
    session_factory: Callable[[], Session],
    settings: Settings,
    release_id: str,
    worker_contract_version: str,
    schema_audit: SchemaAudit,
    opaque_identity: str,
    overlap_gate: OverlapGate | None = None,
) -> BridgeProbeResult:
    """Exercise one uniquely owned durable turn and remove only its exact rows."""

    started = time.perf_counter()
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    request_id = f"loadtest-{uuid.uuid4().hex}"
    stage_success = {
        name: False for name in ("admission", "ownership", "overlap", "terminal")
    }
    stage_elapsed = {name: 0 for name in stage_success}
    cleanup_success = True
    failure_code: str | None = None
    touched_database = False

    try:
        if not opaque_identity.startswith("loadtest-") or len(opaque_identity) > 255:
            raise QualificationRefused("synthetic identity contract mismatch")
        validate_operator_context(
            confirmation=QUALIFICATION_CONFIRMATION,
            environment=settings,
            release_id=release_id,
            worker_contract_version=worker_contract_version,
        )
        validate_schema_audit(schema_audit)
        if settings.chat_max_concurrency != 2:
            raise QualificationRefused("bridge probe requires exact capacity")

        with session_factory() as db:
            repository = ChatTurnJobRepository(
                advisory_locker=(
                    (lambda *_args: None)
                    if db.bind is not None and db.bind.dialect.name == "sqlite"
                    else None
                )
            )
            coordinator = ChatTurnAdmissionCoordinator(
                db, settings, repository=repository
            )
            decision_now = datetime.now(UTC)
            repository.lock_admission_authority(db, hf_user_id=opaque_identity)
            expired = repository.load_expired_claims(
                db,
                now=decision_now,
                hf_user_id=opaque_identity,
                limit=1,
            )
            if expired:
                raise QualificationRefused(
                    "expired durable claim awaits normal reconciliation"
                )
            db.add(
                ChatSession(
                    id=session_id,
                    hf_user_id=opaque_identity,
                    hf_username=opaque_identity,
                    selected_model="qualification",
                )
            )
            touched_database = True
            db.flush()
            preflight = coordinator.preflight(
                hf_user_id=opaque_identity,
                request_id=request_id,
                requested_session_id=session_id,
                now=decision_now,
            )
            coordinator.admit(
                preflight,
                turn_id=turn_id,
                chat_session_id=session_id,
                hf_user_id=opaque_identity,
                revision=1,
                dispatch_route="durable-bridge-probe",
                app_release_id=release_id,
                worker_contract_version=worker_contract_version,
                now=datetime.now(UTC),
            )
            db.commit()
            stage_success["admission"] = True
            stage_elapsed["admission"] = _elapsed_ms(started)

            claimed_at = datetime.now(UTC)
            claim = repository.claim(
                db,
                turn_id=turn_id,
                worker_id=f"loadtest-{uuid.uuid4().hex}",
                worker_generation=1,
                now=claimed_at,
                lease_seconds=30,
            )
            repository.transition(
                db,
                claim=claim,
                state="running",
                now=claimed_at + timedelta(milliseconds=1),
            )
            db.commit()
            stage_success["ownership"] = True
            stage_elapsed["ownership"] = _elapsed_ms(started)

            if overlap_gate is None or not overlap_gate.wait(opaque_identity):
                failure_code = "bridge_overlap_failed"
            else:
                stage_success["overlap"] = True
                stage_elapsed["overlap"] = _elapsed_ms(started)

            if stage_success["overlap"]:
                repository.write_terminal(
                    db,
                    claim=claim,
                    state="completed",
                    now=claimed_at + timedelta(milliseconds=2),
                )
                db.commit()
                terminal = db.get(ChatTurnJob, turn_id)
                if terminal is None or terminal.state != "completed":
                    raise RuntimeError("terminal verification failed")
                stage_success["terminal"] = True
                stage_elapsed["terminal"] = _elapsed_ms(started)
    except QualificationRefused:
        failure_code = "bridge_refused"
    except SQLAlchemyError:
        failure_code = "database_failure"
    except (RuntimeError, ValueError):
        failure_code = "bridge_failure"
    finally:
        if touched_database:
            try:
                with session_factory() as cleanup_db:
                    cleanup_db.execute(
                        delete(ChatTurnJob).where(ChatTurnJob.turn_id == turn_id)
                    )
                    cleanup_db.execute(
                        delete(ChatSession).where(ChatSession.id == session_id)
                    )
                    cleanup_db.commit()
                    cleanup_success = (
                        cleanup_db.scalar(
                            select(ChatTurnJob.turn_id).where(
                                ChatTurnJob.turn_id == turn_id
                            )
                        )
                        is None
                        and cleanup_db.scalar(
                            select(ChatSession.id).where(ChatSession.id == session_id)
                        )
                        is None
                    )
            except SQLAlchemyError:
                cleanup_success = False
        if not cleanup_success:
            failure_code = "cleanup_failure"

    elapsed = _elapsed_ms(started)
    metrics = tuple(
        Metric(f"bridge.{name}", stage_elapsed[name] or elapsed, stage_success[name])
        for name in ("admission", "ownership", "overlap", "terminal")
    ) + (Metric("bridge.cleanup", elapsed, cleanup_success),)
    return BridgeProbeResult(metrics=metrics, failure_code=failure_code)
