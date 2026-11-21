"""Resume a bounded number of durable staging LaTeX compiler jobs."""

from __future__ import annotations

import argparse
import json

from backend.config import Settings, get_settings
from backend.database.connection import get_database_session
from backend.services.latex_paper_service import LatexPaperService

CONFIRMATION = "RECONCILE_STAGING_LATEX_COMPILER_JOBS"


def validate_settings(settings: Settings, *, cleanup_only: bool = False) -> None:
    if settings.environment != "staging":
        raise ValueError("LaTeX compiler reconciliation requires staging")
    if not cleanup_only and not settings.chat_latex_compiler_jobs_enabled:
        raise ValueError("LaTeX compiler kill switch is enabled")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--cleanup-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"Pass --confirm {CONFIRMATION}")
    if not 1 <= args.limit <= 100:
        raise SystemExit("--limit must be between 1 and 100")
    settings = get_settings()
    try:
        validate_settings(settings, cleanup_only=args.cleanup_only)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    session_generator = get_database_session()
    db = next(session_generator)
    try:
        service = LatexPaperService(db, settings)
        reconciled = (
            0
            if args.cleanup_only
            else service.reconcile_pending_compiles(limit=args.limit)
        )
        if args.cleanup_only:
            service.reconcile_storage_cleanup(limit=args.limit)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        session_generator.close()
    print(json.dumps({"reconciled": reconciled}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
