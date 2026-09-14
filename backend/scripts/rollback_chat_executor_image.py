#!/usr/bin/env python3
"""Root-only, audited executor creation-manifest rollback."""

from __future__ import annotations

import argparse
import os
import uuid
from collections.abc import Callable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    ChatExecutorCell,
    ChatExecutorManifest,
    ChatExecutorRegistration,
)
from backend.services.chat_executor_registry import ChatExecutorRegistry

REASON_CLASSES = ("image_regression", "qualification_failure", "compatibility_failure")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--cell", required=True)
    value.add_argument("--target-digest", required=True)
    value.add_argument("--reason-class", required=True, choices=REASON_CLASSES)
    value.add_argument("--qualification-evidence-ref", required=True)
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
        raise PermissionError("Executor image rollback requires root")
    if args.confirm != f"ROLLBACK {args.target_digest}":
        raise ValueError("Executor image rollback confirmation does not match target")
    session_factory = session_factory or db_manager.session_local
    repository = ChatExecutorRegistry()
    with session_factory() as db, db.begin():
        cell = db.get(ChatExecutorCell, args.cell)
        target = db.get(ChatExecutorManifest, args.target_digest)
        if cell is None or target is None or cell.selected_manifest_digest is None:
            raise ValueError("Executor rollback preview is unavailable")
        cohorts = dict(
            db.execute(
                select(ChatExecutorRegistration.state, func.count())
                .where(ChatExecutorRegistration.cell_id == args.cell)
                .group_by(ChatExecutorRegistration.state)
            ).all()
        )
        print(
            f"cell={args.cell} source={cell.selected_manifest_digest} "
            f"target={target.digest} cohorts={cohorts}"
        )
        audit = repository.rollback_manifest(
            db,
            request_id=args.request_id,
            cell_id=args.cell,
            target_digest=args.target_digest,
            actor=args.actor,
            reason_class=args.reason_class,
            qualification_evidence_ref=args.qualification_evidence_ref,
        )
        print(f"applied request_id={audit.request_id} epoch={audit.epoch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
