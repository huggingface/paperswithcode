"""Voice dictation tickets for the chat composers.

See :mod:`backend.services.dictation_service` for the relay design. The
``/api/internal/dictation/authorize`` route answers nginx's ``auth_request``
subrequest only: public nginx locations return 404 for that path, and the
route additionally requires the relay header nginx sets on the subrequest.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.connection import get_database_session
from backend.routers.auth import decode_request_session
from backend.services.dictation_service import (
    DictationService,
    DictationTicketRejected,
    DictationUnavailable,
    ticket_from_uri,
)
from backend.utils.auth import require_user

router = APIRouter(prefix="/dictation", tags=["dictation"])
internal_router = APIRouter(prefix="/internal/dictation", include_in_schema=False)

RELAY_HEADER = "X-PwC-Dictation-Relay"
RELAY_VALUE = "auth-request"
WS_PATH = "/api/v1/dictation/ws"

Provider = Literal["voxtral", "openai"]


class DictationStatusResponse(BaseModel):
    enabled: bool
    signed_in: bool
    provider: Provider | None = Field(
        None,
        description="Provider a new session would use; null when none can take one",
    )
    reason: str | None = Field(
        None, description="Why no provider is available: starting, busy, or daily_limit"
    )
    max_seconds: int
    remaining_seconds: int | None = None


class DictationSessionResponse(BaseModel):
    session_id: uuid.UUID
    ws_url: str = Field(
        ..., description="Same-origin WebSocket path including the ticket"
    )
    provider: Provider
    model: str
    sample_rate: int
    max_seconds: int
    prompt: str | None = None


class DictationFinishRequest(BaseModel):
    seconds: float = Field(..., ge=0, le=3600)


def _require_enabled(settings: Settings) -> None:
    if not settings.dictation_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Voice input is not enabled")


@router.get("/status", response_model=DictationStatusResponse)
def dictation_status(
    request: Request,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> DictationStatusResponse:
    """Whether voice input is available, and which provider would serve it.

    It does not wake the scale-to-zero speech endpoint unless no fallback can
    serve: page views alone must not keep the GPU running. A mic tap
    (``POST /sessions``) wakes it, and that session uses OpenAI meanwhile.
    """

    base = {"max_seconds": settings.dictation_session_seconds}
    if not settings.dictation_enabled:
        return DictationStatusResponse(enabled=False, signed_in=False, **base)
    payload = decode_request_session(request) or {}
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        return DictationStatusResponse(enabled=True, signed_in=False, **base)
    choice = DictationService(db, settings).status(subject)
    return DictationStatusResponse(
        enabled=True,
        signed_in=True,
        provider=choice.provider,
        reason=choice.reason,
        remaining_seconds=choice.remaining_seconds,
        **base,
    )


@router.post("/sessions", response_model=DictationSessionResponse)
def create_dictation_session(
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> DictationSessionResponse:
    """Issue a single-use, 30-second ticket for one dictation WebSocket."""

    _require_enabled(settings)
    try:
        issued = DictationService(db, settings).issue(user["hf_subject"])
    except DictationUnavailable as error:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS
            if error.reason in {"daily_limit", "already_dictating"}
            else status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": error.reason},
        ) from error
    return DictationSessionResponse(
        session_id=issued.session_id,
        ws_url=f"{WS_PATH}?ticket={issued.ticket}",
        provider=issued.provider,
        model=issued.model,
        sample_rate=issued.sample_rate,
        max_seconds=issued.max_seconds,
        prompt=issued.prompt,
    )


@router.post("/sessions/{session_id}/finish", status_code=status.HTTP_204_NO_CONTENT)
def finish_dictation_session(
    session_id: uuid.UUID,
    body: DictationFinishRequest,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Record how long the session recorded, releasing the rest of its reservation."""

    _require_enabled(settings)
    DictationService(db, settings).finish(user["hf_subject"], session_id, body.seconds)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@internal_router.get("/authorize", status_code=status.HTTP_204_NO_CONTENT)
def authorize_dictation_relay(
    request: Request,
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    """nginx ``auth_request``: consume the ticket and name the upstream."""

    if (
        not settings.dictation_enabled
        or request.headers.get(RELAY_HEADER) != RELAY_VALUE
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    ticket = ticket_from_uri(request.headers.get("X-Original-URI", ""))
    try:
        upstream = DictationService(db, settings).authorize(ticket)
    except DictationTicketRejected as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN) from error
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={
            "X-PwC-Dictation-Upstream": upstream.url,
            "X-PwC-Dictation-Authorization": upstream.authorization,
            "Cache-Control": "no-store",
        },
    )
