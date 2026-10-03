"""Provider billing authorization for admitted chat turns."""

from __future__ import annotations

import logging
import uuid
from contextlib import nullcontext
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.services.chat_session_service import ChatServiceError
from backend.services.openrouter_budget_service import (
    OpenRouterBudgetExceeded,
    OpenRouterBudgetUnavailable,
    require_openrouter_budget,
)
from backend.services.openrouter_byok_service import OpenRouterBYOKService
from backend.services.openrouter_user_budget_service import (
    PUBLIC_SUPPORT_URL,
    OpenRouterUserBudgetService,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenRouterAdmission:
    mode: str
    token: str | None = None
    credential_revision: uuid.UUID | None = None


OPENROUTER_UNAVAILABLE_MESSAGE = (
    "OpenRouter is currently unavailable. However, you can still bring your own "
    "key in Settings."
)


def _selected_byok(db: Session, settings: Settings, owner_id: str):
    """Isolate credential faults so a healthy funded ledger can still admit."""

    nested = db.begin_nested() if hasattr(db, "begin_nested") else nullcontext()
    try:
        with nested:
            return OpenRouterBYOKService(db, settings).selected(owner_id)
    except Exception as error:
        logger.error(
            "openrouter credential selection unavailable error=%s",
            type(error).__name__,
        )
        return None


async def authorize_openrouter(
    settings: Settings,
    db: Session | None = None,
    owner_id: str | None = None,
) -> OpenRouterAdmission:
    if not settings.chat_openrouter_server_funded_enabled:
        if db is not None and owner_id is not None:
            byok = _selected_byok(db, settings, owner_id)
            if byok:
                return OpenRouterAdmission("openrouter_byok", byok.token, byok.revision)
        raise ChatServiceError(
            "openrouter_unavailable",
            503,
            OPENROUTER_UNAVAILABLE_MESSAGE,
            details={
                "byok_settings_available": True,
                "support_url": PUBLIC_SUPPORT_URL,
            },
        )
    if db is not None and owner_id is not None:
        try:
            funded_available = OpenRouterUserBudgetService(db, settings).can_fund_call(
                owner_id
            )
        except Exception as error:
            logger.error(
                "openrouter user budget database failure error=%s",
                type(error).__name__,
            )
            raise ChatServiceError(
                "openrouter_unavailable",
                503,
                OPENROUTER_UNAVAILABLE_MESSAGE,
                details={
                    "byok_settings_available": True,
                    "support_url": PUBLIC_SUPPORT_URL,
                },
            ) from None
        byok = _selected_byok(db, settings, owner_id)
        if not funded_available:
            if byok:
                return OpenRouterAdmission("openrouter_byok", byok.token, byok.revision)
            status = OpenRouterUserBudgetService(db, settings).status_percentage(
                owner_id
            )
            raise ChatServiceError(
                "openrouter_monthly_budget_exhausted",
                429,
                "The remaining shared Papers With Code OpenRouter allowance is not enough for another model call.",
                details={
                    "used_percent": status.used_percent,
                    "remaining_percent": status.remaining_percent,
                    "resets_at": status.resets_at.isoformat().replace("+00:00", "Z"),
                },
            )
    try:
        await require_openrouter_budget(settings)
    except OpenRouterBudgetExceeded:
        if db is not None and owner_id is not None:
            byok = _selected_byok(db, settings, owner_id)
            if byok:
                return OpenRouterAdmission("openrouter_byok", byok.token, byok.revision)
        raise ChatServiceError(
            "openrouter_unavailable",
            503,
            OPENROUTER_UNAVAILABLE_MESSAGE,
            details={
                "byok_settings_available": True,
                "support_url": PUBLIC_SUPPORT_URL,
            },
        ) from None
    except OpenRouterBudgetUnavailable:
        if db is not None and owner_id is not None:
            byok = _selected_byok(db, settings, owner_id)
            if byok:
                return OpenRouterAdmission("openrouter_byok", byok.token, byok.revision)
        raise ChatServiceError(
            "openrouter_unavailable",
            503,
            OPENROUTER_UNAVAILABLE_MESSAGE,
            details={
                "byok_settings_available": True,
                "support_url": PUBLIC_SUPPORT_URL,
            },
        ) from None
    return OpenRouterAdmission("openrouter_funded")
