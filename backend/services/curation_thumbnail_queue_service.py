"""Durable thumbnail handoff for remote paper-curation jobs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models.database import Paper, PaperCurationJob
from backend.services.paper_thumbnail_service import regenerate_paper_thumbnail

TERMINAL_THUMBNAIL_STATUSES = {"succeeded", "failed"}
MAX_THUMBNAIL_ERROR_LENGTH = 4_000
DEFAULT_STALE_AFTER = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(UTC)


def queue_thumbnail(row: PaperCurationJob) -> None:
    """Reset one curation row to a fresh durable thumbnail request."""
    row.thumbnail_status = "queued"
    row.thumbnail_requested_at = _now()
    row.thumbnail_claimed_at = None
    row.thumbnail_finished_at = None
    row.thumbnail_attempt_count = 0
    row.thumbnail_url = None
    row.thumbnail_previous_width = None
    row.thumbnail_previous_height = None
    row.thumbnail_generated_width = None
    row.thumbnail_generated_height = None
    row.thumbnail_warnings = None
    row.thumbnail_error = None


def queue_missing_paper_thumbnail(
    db: Session, row: PaperCurationJob, paper: Paper | None
) -> bool:
    """Queue one missing paper thumbnail without duplicating active work."""
    if paper is None or paper.thumbnail_url:
        return False
    active = (
        db.query(PaperCurationJob.id)
        .filter(
            PaperCurationJob.paper_id == paper.id,
            PaperCurationJob.id != row.id,
            PaperCurationJob.thumbnail_status.in_({"queued", "processing"}),
        )
        .first()
    )
    if active is not None:
        return False
    queue_thumbnail(row)
    return True


def serialize_thumbnail(row: PaperCurationJob) -> dict:
    requested_at = getattr(row, "thumbnail_requested_at", None)
    status = getattr(row, "thumbnail_status", None)
    previous_width = getattr(row, "thumbnail_previous_width", None)
    previous_height = getattr(row, "thumbnail_previous_height", None)
    generated_width = getattr(row, "thumbnail_generated_width", None)
    generated_height = getattr(row, "thumbnail_generated_height", None)
    requested = requested_at is not None
    return {
        "requested": requested,
        "status": status if requested else "not_requested",
        "attempt_count": getattr(row, "thumbnail_attempt_count", 0),
        "requested_at": requested_at,
        "claimed_at": getattr(row, "thumbnail_claimed_at", None),
        "finished_at": getattr(row, "thumbnail_finished_at", None),
        "thumbnail_url": getattr(row, "thumbnail_url", None),
        "previous_dimensions": (
            [previous_width, previous_height]
            if previous_width is not None and previous_height is not None
            else None
        ),
        "generated_dimensions": (
            [generated_width, generated_height]
            if generated_width is not None and generated_height is not None
            else None
        ),
        "success": (
            status == "succeeded" if status in TERMINAL_THUMBNAIL_STATUSES else None
        ),
        "warnings": list(getattr(row, "thumbnail_warnings", None) or []),
        "error": getattr(row, "thumbnail_error", None),
    }


@dataclass(frozen=True)
class ThumbnailClaim:
    job_id: object
    paper_id: int


class CurationThumbnailQueueService:
    """Claim and finish one-to-one thumbnail work stored on curation jobs."""

    def claim_next(
        self,
        db: Session,
        *,
        retry_failed: bool = False,
        stale_after: timedelta = DEFAULT_STALE_AFTER,
        exclude_job_ids: set | None = None,
    ) -> ThumbnailClaim | None:
        cutoff = _now() - stale_after
        statuses = [PaperCurationJob.thumbnail_status == "queued"]
        statuses.append(
            (PaperCurationJob.thumbnail_status == "processing")
            & (PaperCurationJob.thumbnail_claimed_at < cutoff)
        )
        if retry_failed:
            statuses.append(PaperCurationJob.thumbnail_status == "failed")
        query = db.query(PaperCurationJob).filter(or_(*statuses))
        if exclude_job_ids:
            query = query.filter(PaperCurationJob.id.notin_(exclude_job_ids))
        row = (
            query.order_by(
                PaperCurationJob.thumbnail_requested_at,
                PaperCurationJob.created_at,
            )
            .with_for_update(skip_locked=True)
            .first()
        )
        if row is None:
            return None
        paper_id = row.paper_id
        if paper_id is None:
            paper_id = (row.mutation_result or {}).get("paper_id")
        if paper_id is None:
            raise RuntimeError("Thumbnail request has no target paper")
        row.thumbnail_status = "processing"
        row.thumbnail_claimed_at = _now()
        row.thumbnail_finished_at = None
        row.thumbnail_attempt_count += 1
        row.thumbnail_error = None
        db.commit()
        return ThumbnailClaim(job_id=row.id, paper_id=int(paper_id))

    def succeed(self, db: Session, claim: ThumbnailClaim, result) -> None:
        row = db.get(PaperCurationJob, claim.job_id)
        if row is None or row.thumbnail_status != "processing":
            return
        row.thumbnail_status = "succeeded" if result.success else "failed"
        row.thumbnail_finished_at = _now()
        row.thumbnail_url = result.thumbnail_url
        if result.previous:
            row.thumbnail_previous_width = result.previous.width
            row.thumbnail_previous_height = result.previous.height
        row.thumbnail_generated_width = result.generated.width
        row.thumbnail_generated_height = result.generated.height
        row.thumbnail_warnings = list(result.warnings)
        row.thumbnail_error = (
            None
            if result.success
            else "Thumbnail generation completed but validation failed."
        )
        db.commit()

    def fail(self, db: Session, claim: ThumbnailClaim, exc: Exception) -> None:
        row = db.get(PaperCurationJob, claim.job_id)
        if row is None or row.thumbnail_status != "processing":
            return
        detail = " ".join(str(exc).split())
        row.thumbnail_status = "failed"
        row.thumbnail_finished_at = _now()
        row.thumbnail_error = (
            f"Thumbnail worker failed ({type(exc).__name__})"
            + (f": {detail}" if detail else ".")
        )[:MAX_THUMBNAIL_ERROR_LENGTH]
        db.commit()

    async def process_claim(self, db: Session, claim: ThumbnailClaim) -> None:
        try:
            result = await regenerate_paper_thumbnail(
                db, str(claim.paper_id), force=True
            )
        except Exception as exc:  # noqa: BLE001 - every worker failure must persist
            db.rollback()
            self.fail(db, claim, exc)
            return
        self.succeed(db, claim, result)

    def process_batch(
        self,
        db: Session,
        *,
        limit: int = 10,
        retry_failed: bool = False,
    ) -> int:
        processed = 0
        attempted_job_ids: set = set()
        while processed < limit:
            claim = self.claim_next(
                db,
                retry_failed=retry_failed,
                exclude_job_ids=attempted_job_ids,
            )
            if claim is None:
                break
            attempted_job_ids.add(claim.job_id)
            asyncio.run(self.process_claim(db, claim))
            processed += 1
        return processed


curation_thumbnail_queue_service = CurationThumbnailQueueService()
