"""Transaction-rolled-back durable fencing probe for staging external Pi."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.services.chat_external_worker_registry import (
    ChatExternalWorkerRepository,
    ExternalWorkerClaim,
    StaleWorkerClaim,
)


def prove_stale_generation_fenced(
    db: Session,
    repository: ChatExternalWorkerRepository,
    *,
    worker_id: str,
    release_id: str,
    stale_generation: int,
    current_generation: int,
) -> bool:
    row = repository.load(db, worker_id)
    if (
        row is None
        or row.release_id != release_id
        or row.generation != current_generation
        or row.state != "ready"
        or stale_generation >= current_generation
    ):
        raise RuntimeError("durable external Pi worker identity is invalid")
    stale = ExternalWorkerClaim(
        worker_id,
        row.instance_id,
        stale_generation,
        row.release_id,
        row.contract_version,
    )
    try:
        repository.heartbeat(
            db,
            claim=stale,
            active_sessions=0,
            now=datetime.now(UTC),
            lease_seconds=30,
        )
    except StaleWorkerClaim:
        return True
    raise RuntimeError("stale external Pi generation was accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True)
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--stale-generation", type=int, required=True)
    parser.add_argument("--current-generation", type=int, required=True)
    args = parser.parse_args()
    settings = get_settings()
    if args.environment != "staging" or settings.environment != "staging":
        raise RuntimeError("durable external Pi fencing probe is staging-only")
    repository = ChatExternalWorkerRepository(environment="staging")
    with db_manager.session_local() as db:
        try:
            fenced = prove_stale_generation_fenced(
                db,
                repository,
                worker_id=args.worker_id,
                release_id=args.release_id,
                stale_generation=args.stale_generation,
                current_generation=args.current_generation,
            )
        finally:
            db.rollback()
    print(json.dumps({"stale_fenced": fenced}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
