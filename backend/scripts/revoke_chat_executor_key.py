#!/usr/bin/env python3
"""Root-only exact-ID executor key revocation and security hold."""

from __future__ import annotations

import argparse
import os
import uuid
from collections.abc import Callable, Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import ChatExecutorRegistration
from backend.services.chat_executor_registry import ChatExecutorRegistry
from backend.services.chat_executor_transport_circuit import ExecutorTransportCircuit

REASON_CLASSES = ("credential_exposure", "credential_loss", "operator_security_hold")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument(
        "--environment", required=True, choices=("staging", "production")
    )
    value.add_argument("--cell", required=True)
    value.add_argument("--key-id", required=True)
    value.add_argument("--reason-class", required=True, choices=REASON_CLASSES)
    value.add_argument("--actor", required=True)
    value.add_argument("--request-id", required=True, type=uuid.UUID)
    value.add_argument("--confirm", required=True)
    return value


def run(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], Session] | None = None,
    effective_uid: int | None = None,
) -> int:
    args = parser().parse_args(argv)
    if (os.geteuid() if effective_uid is None else effective_uid) != 0:
        raise PermissionError("Executor key revocation requires root")
    if args.confirm != f"REVOKE {args.key_id}":
        raise ValueError("Executor key revocation confirmation does not match key ID")
    session_factory = session_factory or db_manager.session_local
    repository = ChatExecutorRegistry()
    with session_factory() as db, db.begin():
        affected = int(
            db.scalar(
                select(func.count())
                .select_from(ChatExecutorRegistration)
                .where(
                    ChatExecutorRegistration.cell_id == args.cell,
                    or_(
                        ChatExecutorRegistration.authorization_key_id == args.key_id,
                        ChatExecutorRegistration.public_key_id == args.key_id,
                    ),
                )
            )
            or 0
        )
        print(
            f"cell={args.cell} key_id={args.key_id} "
            f"reason_class={args.reason_class} affected_registrations={affected}"
        )
        row = repository.revoke_key(
            db,
            request_id=args.request_id,
            cell_id=args.cell,
            key_id=args.key_id,
            actor=args.actor,
            reason_class=args.reason_class,
        )
        circuit = ExecutorTransportCircuit(environment=args.environment)
        circuit.initialize(db, now=repository._database_now(db))
        circuit.security_hold(
            db, reason=args.reason_class, now=repository._database_now(db)
        )
        print(
            f"applied request_id={row.request_id} previous_epoch={row.previous_epoch} "
            f"new_epoch={row.new_epoch}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
