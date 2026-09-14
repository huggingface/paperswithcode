"""Bounded asynchronous reconciliation for direct OpenAI provider calls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.services.chat_openai_budget_service import ChatOpenAIBudgetService


@dataclass(frozen=True)
class OpenAIReconciliationResult:
    stale_dispatches_marked_unknown: int
    unknown_calls_settled_at_ceiling: int


class ChatOpenAIUsageReconciler:
    """Make ambiguous calls durable and conservatively terminal in two passes.

    Responses use ``store:false`` and therefore cannot be retrieved after a
    terminal usage frame is lost. The organization usage API is aggregate, so
    it cannot safely attribute usage to one provider-call ID. The second pass
    charges the reserved ceiling and labels that source explicitly.
    """

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def run_once(
        self, *, now: datetime | None = None, batch_size: int = 100
    ) -> OpenAIReconciliationResult:
        service = ChatOpenAIBudgetService(self.db, self.settings)
        settled = service.settle_stale_unknown_at_reserved_ceiling(
            now=now, batch_size=batch_size
        )
        marked = service.mark_stale_dispatched_unknown(now=now, batch_size=batch_size)
        self.db.commit()
        return OpenAIReconciliationResult(marked, settled)
