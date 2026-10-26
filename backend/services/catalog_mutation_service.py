"""Atomic audit, idempotency, concurrency, history, and rollback primitives."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.services.catalog_errors import (
    CatalogConflictError,
    CatalogValidationError,
)
from backend.models.database import (
    CatalogAuditReadProgress,
    CatalogMutationEvent,
    CatalogMutationIdempotency,
)

# Deferred trigger in add_single_benchmark_board_guard.sql.
SINGLE_BOARD_CONSTRAINT = "evaluations_single_benchmark_board"


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def encode_cursor(event: CatalogMutationEvent) -> str:
    value = f"{event.created_at.isoformat()}|{event.id}".encode()
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def decode_cursor(value: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()
        created, event_id = raw.rsplit("|", 1)
        return datetime.fromisoformat(created), uuid.UUID(event_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise CatalogValidationError("Invalid audit cursor") from exc


class CatalogMutationService:
    def __init__(self, db: Session):
        self.db = db

    def mutate(
        self,
        *,
        actor: dict,
        operation: str,
        entity_type: str,
        entity_id: str,
        request_payload: Any,
        idempotency_key: str | None,
        expected_version: str | None,
        snapshot: Callable[[], Any],
        apply: Callable[[], Any],
        request_id: str,
        version_snapshot: Callable[[], Any] | None = None,
        rollback_of_event_id: uuid.UUID | None = None,
    ) -> tuple[Any, CatalogMutationEvent, bool]:
        from backend.services.paper_edit_access import PaperEditAccess
        from backend.models.database import Evaluation

        paper_id = None
        if entity_type.startswith("paper_"):
            paper_id = int(entity_id)
        elif entity_type == "evaluation":
            if entity_id.startswith("paper:"):
                paper_id = int(entity_id.split(":", 1)[1])
            else:
                row = self.db.get(Evaluation, int(entity_id))
                paper_id = int(row.paper_id) if row else None
        access = PaperEditAccess(self.db)
        if paper_id is not None:
            access.check_write(
                actor, paper_id, entity_type, operation, request_payload, limits=False
            )
        elif actor.get("source") == "paper_token":
            from backend.services.catalog_errors import CatalogPermissionError

            raise CatalogPermissionError(
                "Paper authorization cannot mutate this resource"
            )
        before = json_safe(snapshot())
        current_version = canonical_hash(
            json_safe(version_snapshot()) if version_snapshot else before
        )
        is_contributor = actor["role"] == "contributor"
        if is_contributor and not idempotency_key:
            raise CatalogValidationError("Idempotency-Key is required")
        if is_contributor and not expected_version:
            raise CatalogValidationError("If-Match is required")

        request_hash = canonical_hash(
            {
                "operation": operation,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "payload": request_payload,
                "expected_version": expected_version,
            }
        )
        if idempotency_key:
            existing = self.db.get(
                CatalogMutationIdempotency,
                (actor["hf_subject"], idempotency_key),
            )
            if existing:
                if existing.request_hash != request_hash:
                    raise CatalogConflictError(
                        "Idempotency key was already used for another request"
                    )
                event = self.db.get(CatalogMutationEvent, existing.event_id)
                return existing.result_snapshot, event, True
        if expected_version and expected_version.strip('"') != current_version:
            raise CatalogConflictError(
                {"code": "stale_catalog_version", "current_version": current_version}
            )

        if paper_id is not None:
            access.check_write(actor, paper_id, entity_type, operation, request_payload)
        try:
            apply()
            self.db.flush()
            after = json_safe(snapshot())
            # A long-running batch may cross an expiry or UTC quota boundary.
            # Recheck before recording and committing its publication.
            if paper_id is not None:
                access.check_write(
                    actor, paper_id, entity_type, operation, request_payload
                )
            event = CatalogMutationEvent(
                actor_hf_subject=actor["hf_subject"],
                actor_username=actor.get("username"),
                actor_role=actor["role"],
                operation=operation,
                entity_type=entity_type,
                entity_id=entity_id,
                paper_id=paper_id,
                before_snapshot=before,
                after_snapshot=after,
                request_id=request_id,
                source_environment=get_settings().environment,
                release_id=get_settings().release_id,
                rollback_of_event_id=rollback_of_event_id,
                created_at=datetime.now(timezone.utc),
            )
            self.db.add(event)
            self.db.flush()
            if idempotency_key:
                self.db.add(
                    CatalogMutationIdempotency(
                        actor_hf_subject=actor["hf_subject"],
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        result_snapshot=after,
                        event_id=event.id,
                    )
                )
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            diag = getattr(error.orig, "diag", None)
            if getattr(diag, "constraint_name", None) == SINGLE_BOARD_CONSTRAINT:
                raise CatalogValidationError(diag.message_primary) from None
            if idempotency_key:
                winner = self.db.get(
                    CatalogMutationIdempotency,
                    (actor["hf_subject"], idempotency_key),
                )
                if winner and winner.request_hash == request_hash:
                    winner_event = self.db.get(CatalogMutationEvent, winner.event_id)
                    return winner.result_snapshot, winner_event, True
            raise
        except Exception:
            self.db.rollback()
            raise
        return after, event, False

    def list_events(
        self, *, actor_subject: str | None, cursor: str | None, limit: int
    ) -> dict:
        query = self.db.query(CatalogMutationEvent)
        if actor_subject:
            query = query.filter(CatalogMutationEvent.actor_hf_subject == actor_subject)
        if cursor:
            created, event_id = decode_cursor(cursor)
            query = query.filter(
                or_(
                    CatalogMutationEvent.created_at < created,
                    and_(
                        CatalogMutationEvent.created_at == created,
                        CatalogMutationEvent.id < event_id,
                    ),
                )
            )
        rows = (
            query.order_by(
                CatalogMutationEvent.created_at.desc(),
                CatalogMutationEvent.id.desc(),
            )
            .limit(limit + 1)
            .all()
        )
        page = rows[:limit]
        return {
            "events": [self.serialize_event(row) for row in page],
            "next_cursor": (
                encode_cursor(page[-1]) if len(rows) > limit and page else None
            ),
        }

    @staticmethod
    def serialize_event(event: CatalogMutationEvent) -> dict:
        return {
            "id": str(event.id),
            "actor_username": event.actor_username,
            "actor_role": event.actor_role,
            "operation": event.operation,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "before": event.before_snapshot,
            "after": event.after_snapshot,
            "created_at": event.created_at,
            "rollback_of_event_id": (
                str(event.rollback_of_event_id) if event.rollback_of_event_id else None
            ),
        }

    def unread_count(self, admin_subject: str) -> int:
        progress = self.db.get(CatalogAuditReadProgress, admin_subject)
        query = self.db.query(CatalogMutationEvent).filter(
            CatalogMutationEvent.actor_role == "contributor"
        )
        if progress:
            query = query.filter(
                CatalogMutationEvent.created_at > progress.read_through_created_at
            )
        return query.count()

    def acknowledge(self, admin_subject: str) -> None:
        now = datetime.now(timezone.utc)
        progress = self.db.get(CatalogAuditReadProgress, admin_subject)
        if progress:
            progress.read_through_created_at = now
        else:
            self.db.add(
                CatalogAuditReadProgress(
                    admin_hf_subject=admin_subject,
                    read_through_created_at=now,
                )
            )
        self.db.commit()
