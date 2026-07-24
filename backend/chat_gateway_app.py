"""Private, separately started gateway for sandbox model/catalog/store traffic."""

from __future__ import annotations

import json
import uuid
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.connection import get_database_session
from backend.services.chat_capability_service import (
    CapabilityError,
    ChatCapabilityService,
)
from backend.services.chat_gateway_service import ChatGatewayService
from backend.services.chat_session_store_gateway import (
    ChatSessionStoreGateway,
    SessionStoreCommand,
    SessionStoreGatewayError,
)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
MAX_PROVIDER_OUTPUT_TOKENS = 32_000


class CatalogRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str = Field(max_length=64)
    arguments: dict[str, Any]


class StoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    key: dict[str, Any] | None = None
    entries: list[dict[str, Any]] | None = None
    project_key: str | None = None


def _bearer(authorization: Annotated[str, Header()]) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid capability")
    return token


def _output_tokens_allowed(value: int) -> bool:
    return 1 <= value <= MAX_PROVIDER_OUTPUT_TOKENS


def _scope(
    token: str,
    scope: str,
    session_id: str,
    turn_id: str,
    db: Session,
    *,
    model: str | None = None,
):
    try:
        row = ChatCapabilityService(db).validate(
            token,
            scope=scope,
            chat_session_id=uuid.UUID(session_id),
            turn_id=uuid.UUID(turn_id),
            model=model,
        )
        return row
    except (CapabilityError, ValueError):
        db.rollback()
        raise HTTPException(status_code=403, detail="Capability rejected") from None


@app.post("/catalog")
def catalog(
    body: CatalogRequest,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    token = _bearer(authorization)
    capability = _scope(token, "catalog", x_pwc_session, x_pwc_turn, db)
    try:
        ChatCapabilityService(db).meter_catalog(
            capability,
            body.operation,
            maximum_searches=settings.chat_max_direct_search_calls,
        )
        db.commit()
    except CapabilityError:
        db.rollback()
        raise HTTPException(
            status_code=429, detail="Catalog execution limit reached"
        ) from None
    try:
        result = ChatGatewayService(db, settings).catalog(
            body.operation, body.arguments
        )
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"result": result}


@app.post("/session-store")
def session_store(
    body: StoreRequest,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    token = _bearer(authorization)
    capability = _scope(token, "session_store", x_pwc_session, x_pwc_turn, db)
    try:
        result = ChatSessionStoreGateway(db, settings).execute(
            capability,
            SessionStoreCommand(
                action=body.action,
                key=body.key,
                entries=body.entries,
                project_key=body.project_key,
            ),
        )
        db.commit()
        return {"result": result}
    except SessionStoreGatewayError as error:
        db.rollback()
        raise HTTPException(status_code=error.status_code, detail=str(error)) from None


@app.post("/v1/messages")
async def messages(
    request: Request,
    authorization: Annotated[str, Header()],
    x_pwc_session: Annotated[str, Header()],
    x_pwc_turn: Annotated[str, Header()],
    db: Session = Depends(get_database_session),
    settings: Settings = Depends(get_settings),
):
    token = _bearer(authorization)
    raw = await request.body()
    if len(raw) > 512 * 1024:
        raise HTTPException(status_code=413, detail="Model request is too large")
    try:
        payload = json.loads(raw)
        model = str(payload["model"])
        maximum_tokens = int(payload.get("max_tokens", 0))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="Invalid model request") from None
    if not _output_tokens_allowed(maximum_tokens):
        raise HTTPException(status_code=422, detail="max_tokens is out of range")
    row = _scope(token, "model", x_pwc_session, x_pwc_turn, db, model=model)
    try:
        ChatCapabilityService(db).meter_provider(
            row,
            request_tokens=max(1, len(raw) // 4) + maximum_tokens,
            maximum_requests=16,
            maximum_tokens=128_000,
        )
        db.commit()
    except CapabilityError:
        db.rollback()
        raise HTTPException(
            status_code=429, detail="Model execution limit reached"
        ) from None

    client = httpx.AsyncClient(timeout=180, follow_redirects=False)
    upstream_headers = {
        "Authorization": f"Bearer {settings.hf_token}",
        "Content-Type": "application/json",
        "Accept": request.headers.get("accept", "application/json"),
        "Anthropic-Version": request.headers.get("anthropic-version", "2023-06-01"),
    }
    if request.headers.get("anthropic-beta"):
        upstream_headers["Anthropic-Beta"] = request.headers["anthropic-beta"]
    if settings.chat_hf_bill_to:
        upstream_headers["X-HF-Bill-To"] = settings.chat_hf_bill_to
    upstream = await client.send(
        client.build_request(
            "POST",
            "https://router.huggingface.co/v1/messages",
            content=raw,
            headers=upstream_headers,
        ),
        stream=True,
    )

    async def chunks():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() in {"content-type", "request-id"}
    }
    if payload.get("stream"):
        return StreamingResponse(
            chunks(), status_code=upstream.status_code, headers=headers
        )
    body = await upstream.aread()
    await upstream.aclose()
    await client.aclose()
    return Response(body, status_code=upstream.status_code, headers=headers)
