"""Domain workflow for public ArXiv and external paper submissions."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models.papers import Paper
from backend.services.paper_ingestion_service import (
    PaperIngestionError,
    PaperIngestionService,
)
from backend.services.paper_service import PaperService
from backend.services.pending_edit_service import (
    PendingEditError,
    PendingEditService,
    SubmissionRateLimitError,
    SubmissionSuspendedError,
)
from backend.utils.exceptions import DatabaseError, PaperNotFoundError
from backend.utils.urls import parse_arxiv_url, validate_arxiv_id

_ARXIV_ID_WITH_VERSION_RE = re.compile(r"^(\d{4}\.\d{4,5})(v\d+)?$")
_STAGING_ARXIV_DETAIL = (
    "ArXiv submissions mutate the canonical catalog and are disabled on staging. "
    "External paper URLs may still be queued for staging-local review."
)


@dataclass(frozen=True)
class PaperSubmissionCommand:
    arxiv_id: str | None
    source_url: str | None
    title: str | None
    abstract: str | None
    authors: tuple[str, ...]
    date_published: date | None
    actor_username: str
    actor_subject: str
    actor_role: str | None
    source_ip: str | None
    idempotency_key: str | None


@dataclass(frozen=True)
class ArxivSubmissionTarget:
    arxiv_id: str


@dataclass(frozen=True)
class ExternalSubmissionTarget:
    source_url: str


@dataclass(frozen=True)
class PaperSubmissionResult:
    created: bool
    paper: Paper | None = None
    route_identifier: str | None = None
    refreshed: bool = False
    previous_version: str | None = None
    latest_version: str | None = None
    submission_id: int | None = None
    pending_review: bool = False


class PaperSubmissionError(Exception):
    """Base class for expected public paper-submission failures."""


class PaperSubmissionValidationError(PaperSubmissionError):
    """The submitted identifiers or pending-edit payload are invalid."""


class PaperSubmissionForbiddenError(PaperSubmissionError):
    """The actor or environment cannot accept this submission."""


class PaperSubmissionRateLimitError(PaperSubmissionError):
    def __init__(self, message: str, *, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


class PaperSubmissionArxivMetadataError(PaperSubmissionError):
    def __init__(self, arxiv_id: str, error_type: str | None):
        super().__init__(error_type or "upstream_error")
        self.arxiv_id = arxiv_id
        self.error_type = error_type


class PaperSubmissionInternalError(PaperSubmissionError):
    """The workflow failed after transport validation succeeded."""


class PaperSubmissionDatabaseError(PaperSubmissionError):
    """A catalog lookup failed before the mutation path was selected."""


def normalize_submission_arxiv_id(raw: str) -> str | None:
    """Normalize the public submit form's explicit ArXiv-ID field."""
    candidate = raw.strip()
    if not candidate:
        return None

    match = _ARXIV_ID_WITH_VERSION_RE.match(candidate)
    if match:
        candidate = match.group(1)

    return candidate if validate_arxiv_id(candidate) else None


class PaperSubmissionService:
    """Route and execute one public paper submission."""

    def __init__(
        self,
        db: Session,
        *,
        indexing_logger: logging.Logger | None = None,
    ) -> None:
        self.db = db
        self._logger = indexing_logger or logging.getLogger(__name__)

    async def submit(self, command: PaperSubmissionCommand) -> PaperSubmissionResult:
        target = self._resolve_target(command)
        if isinstance(target, ArxivSubmissionTarget):
            return await self._submit_arxiv(target)
        return self._submit_external(target, command)

    @staticmethod
    def _resolve_target(
        command: PaperSubmissionCommand,
    ) -> ArxivSubmissionTarget | ExternalSubmissionTarget:
        arxiv_id_input = (command.arxiv_id or "").strip()
        source_url = (command.source_url or "").strip()
        if not arxiv_id_input and not source_url:
            raise PaperSubmissionValidationError(
                "Provide an ArXiv ID or a paper URL to submit."
            )

        if arxiv_id_input:
            arxiv_id = normalize_submission_arxiv_id(arxiv_id_input)
            if arxiv_id is None:
                raise PaperSubmissionValidationError(
                    f"Invalid ArXiv ID: {arxiv_id_input}"
                )
            return ArxivSubmissionTarget(arxiv_id)

        parsed = parse_arxiv_url(source_url)
        if parsed is not None:
            return ArxivSubmissionTarget(parsed[0])
        return ExternalSubmissionTarget(source_url)

    async def _submit_arxiv(
        self, target: ArxivSubmissionTarget
    ) -> PaperSubmissionResult:
        if get_settings().environment == "staging":
            raise PaperSubmissionForbiddenError(_STAGING_ARXIV_DETAIL)

        paper_service = PaperService(self.db)
        try:
            existing = paper_service.get_paper_by_arxiv_id(
                target.arxiv_id, version=None
            )
        except PaperNotFoundError:
            existing = None
        except DatabaseError as exc:
            raise PaperSubmissionDatabaseError(str(exc)) from exc

        if existing is not None:
            return await self._refresh_existing(target.arxiv_id, paper_service)

        try:
            paper = await PaperIngestionService(self.db).get_or_import_api_paper(
                target.arxiv_id,
                source_endpoint="submit",
                indexing_logger=self._logger,
            )
        except PaperIngestionError as exc:
            raise PaperSubmissionArxivMetadataError(
                target.arxiv_id, exc.error_type
            ) from exc
        except Exception as exc:
            raise PaperSubmissionInternalError(
                f"Error indexing paper: {exc!s}"
            ) from exc
        return PaperSubmissionResult(
            paper=paper,
            route_identifier=paper.arxiv_id or str(paper.id),
            created=True,
            refreshed=False,
            latest_version=paper.version,
        )

    @staticmethod
    async def _refresh_existing(
        arxiv_id: str, paper_service: PaperService
    ) -> PaperSubmissionResult:
        try:
            result = await paper_service.refresh_arxiv_paper(arxiv_id)
        except DatabaseError as exc:
            message = str(exc)
            if message.startswith("arxiv_metadata_error:"):
                raise PaperSubmissionArxivMetadataError(
                    arxiv_id, message.split(":", 1)[1]
                ) from exc
            raise PaperSubmissionInternalError(message) from exc
        return PaperSubmissionResult(
            paper=result.paper,
            route_identifier=result.paper.arxiv_id or str(result.paper.id),
            created=result.created,
            refreshed=result.refreshed,
            previous_version=result.previous_version,
            latest_version=result.latest_version,
        )

    def _submit_external(
        self,
        target: ExternalSubmissionTarget,
        command: PaperSubmissionCommand,
    ) -> PaperSubmissionResult:
        try:
            row = PendingEditService(self.db).submit(
                paper_id=None,
                hf_username=command.actor_username,
                hf_subject=command.actor_subject,
                source_ip=command.source_ip,
                idempotency_key=command.idempotency_key,
                exempt_from_limits=command.actor_role in {"admin", "contributor"},
                edit_type="new_external_paper",
                proposed_payload={
                    "source_url": target.source_url,
                    "title": command.title,
                    "abstract": command.abstract,
                    "authors": list(command.authors),
                    "date_published": (
                        command.date_published.isoformat()
                        if command.date_published is not None
                        else None
                    ),
                },
            )
        except SubmissionRateLimitError as exc:
            raise PaperSubmissionRateLimitError(
                str(exc), retry_after=exc.retry_after
            ) from exc
        except SubmissionSuspendedError as exc:
            raise PaperSubmissionForbiddenError(str(exc)) from exc
        except PendingEditError as exc:
            raise PaperSubmissionValidationError(str(exc)) from exc
        return PaperSubmissionResult(
            created=False,
            submission_id=row.id,
            pending_review=True,
        )
