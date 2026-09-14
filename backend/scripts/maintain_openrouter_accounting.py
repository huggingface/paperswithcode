"""Bounded chat-provider reconciliation and retention maintenance."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.services.chat_openai_usage_reconciler import ChatOpenAIUsageReconciler
from backend.services.openrouter_byok_service import OpenRouterBYOKService
from backend.services.openrouter_user_budget_service import OpenRouterUserBudgetService

logger = logging.getLogger(__name__)


async def run(
    batch_size: int, *, rotate_credentials: bool = False
) -> dict[str, object]:
    settings = get_settings()
    with db_manager.session_local() as db:
        service = OpenRouterUserBudgetService(db, settings)
        reconciliation = await service.reconcile_unknown(batch_size=batch_size)
        cleanup = service.cleanup_retention(batch_size=batch_size)
        rotated_credentials = (
            OpenRouterBYOKService(db, settings).rotate_to_active_key(batch_size)
            if rotate_credentials
            else 0
        )
        direct_openai = (
            ChatOpenAIUsageReconciler(db, settings).run_once(batch_size=batch_size)
            if settings.chat_openai_direct_enabled
            else None
        )
        db.commit()
    return {
        "reconciliation": reconciliation,
        "cleanup": cleanup,
        "rotated_credentials": rotated_credentials,
        "direct_openai_reconciliation": (
            {
                "stale_dispatches_marked_unknown": (
                    direct_openai.stale_dispatches_marked_unknown
                ),
                "unknown_calls_settled_at_ceiling": (
                    direct_openai.unknown_calls_settled_at_ceiling
                ),
                "turn_reservations_reconciled": (
                    direct_openai.turn_reservations_reconciled
                ),
            }
            if direct_openai is not None
            else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--rotate-credentials",
        action="store_true",
        help="explicitly re-encrypt older BYOK rows with the configured active key",
    )
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 500:
        parser.error("--batch-size must be between 1 and 500")
    try:
        result = asyncio.run(
            run(args.batch_size, rotate_credentials=args.rotate_credentials)
        )
    except Exception as error:
        logger.exception(
            "openrouter accounting maintenance failed error=%s",
            type(error).__name__,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
