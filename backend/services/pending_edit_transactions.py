"""Transaction boundaries for standalone reviews and autonomous callbacks."""

import logging

from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy.orm import Session

from backend.models.database import PendingPaperEdit
from backend.services.pending_edit_errors import (
    PendingEditApplyError,
    PendingEditConflictError,
)


logger = logging.getLogger(__name__)


@contextmanager
def review_transaction(db: Session) -> Iterator[None]:
    """Commit the entire review, or persist diagnostics only after rolling it back.

    Approval execution carries plain diagnostic values on its errors so rollback
    cannot discard them. The second transaction never contains catalog changes,
    callback attestations, or review-claim completion from the failed attempt.
    """
    try:
        yield
        db.commit()
    except Exception as error:
        db.rollback()
        if isinstance(error, PendingEditApplyError):
            logger.warning(
                "submission_apply_failed id=%s error_type=%s",
                error.edit_id,
                type(error.error).__name__,
            )
        if isinstance(error, (PendingEditConflictError, PendingEditApplyError)):
            if error.edit_id is not None:
                with db.begin():
                    _persist_diagnostic(db, error)
            if isinstance(error, PendingEditApplyError):
                raise error.error from None
        raise


def _persist_diagnostic(
    db: Session, error: PendingEditConflictError | PendingEditApplyError
) -> None:
    row = (
        db.query(PendingPaperEdit)
        .filter(PendingPaperEdit.id == error.edit_id)
        .with_for_update()
        .first()
    )
    if row is not None and row.status == "pending":
        if isinstance(error, PendingEditConflictError):
            row.conflict_payload = error.conflict_payload
        else:
            row.failure_reason = str(error.error)[:2000]
