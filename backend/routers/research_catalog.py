"""Bounded read-only contracts consumed by the standalone ``pwc`` client."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from backend.config import Settings, get_settings
from backend.database.connection import get_database_session
from backend.services.paper_lineage_service import get_paper_lineage
from backend.services.paper_markdown_service import (
    PaperMarkdownNotFoundError,
    PaperMarkdownRangeError,
    PaperMarkdownStorageError,
    PaperMarkdownVersionMismatchError,
    read_paper_markdown_bounded,
    read_paper_markdown_chunk,
)

router = APIRouter(prefix="/research", tags=["research"])
_MARKDOWN_MAX_BYTES = 256 * 1024
_PUBLIC_MARKDOWN_CACHE_CONTROL = (
    "public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800"
)
_VERSIONED_CHUNK_CACHE_CONTROL = "public, max-age=3600"
_UNVERSIONED_CHUNK_CACHE_CONTROL = "public, max-age=0, must-revalidate"
_INTEGER_QUERY = re.compile(r"(?:0|[1-9]\d*)")
_CONTENT_VERSION_QUERY = re.compile(r"[A-Za-z0-9._~-]{1,256}")


def _query_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=detail,
        headers={"Cache-Control": "no-store"},
    )


def _single_query_value(request: Request, name: str) -> str | None:
    values = request.query_params.getlist(name)
    if len(values) > 1:
        raise _query_error(f"Query parameter {name} must appear at most once")
    return values[0] if values else None


def _integer_query_value(
    value: str | None, *, name: str, default: int, minimum: int, maximum: int
) -> int:
    if value is None:
        return default
    if _INTEGER_QUERY.fullmatch(value) is None:
        raise _query_error(f"Query parameter {name} is invalid")
    parsed = int(value)
    if parsed < minimum or parsed > maximum:
        raise _query_error(f"Query parameter {name} is outside the allowed range")
    return parsed


@router.get("/papers/{paper_id}/read", response_class=PlainTextResponse)
def read_paper(
    request: Request,
    paper_id: str = Path(min_length=1, max_length=64),
    offset: str | None = Query(
        default=None, description="UTF-8 byte offset for versioned chunk mode"
    ),
    limit: str | None = Query(
        default=None, description="Maximum UTF-8 bytes returned in chunk mode"
    ),
    content_version: str | None = Query(
        default=None, description="Opaque version returned by an earlier chunk"
    ),
    settings: Settings = Depends(get_settings),
) -> PlainTextResponse:
    raw_offset = _single_query_value(request, "offset")
    raw_limit = _single_query_value(request, "limit")
    raw_version = _single_query_value(request, "content_version")
    chunk_mode = any(
        value is not None for value in (raw_offset, raw_limit, raw_version)
    )
    if chunk_mode:
        parsed_offset = _integer_query_value(
            raw_offset,
            name="offset",
            default=0,
            minimum=0,
            maximum=2**63 - 1,
        )
        parsed_limit = _integer_query_value(
            raw_limit,
            name="limit",
            default=_MARKDOWN_MAX_BYTES,
            minimum=1,
            maximum=_MARKDOWN_MAX_BYTES,
        )
        if (
            raw_version is not None
            and _CONTENT_VERSION_QUERY.fullmatch(raw_version) is None
        ):
            raise _query_error("Query parameter content_version is invalid")
        if parsed_offset and raw_version is None:
            raise _query_error(
                "Query parameter content_version is required for a nonzero offset"
            )
        try:
            chunk = read_paper_markdown_chunk(
                paper_id,
                bucket_id=settings.paper_markdown_hf_bucket_id,
                token=settings.hf_token or None,
                offset=parsed_offset,
                limit=parsed_limit,
                content_version=raw_version,
            )
        except PaperMarkdownVersionMismatchError as error:
            raise HTTPException(
                status_code=409,
                detail=str(error),
                headers={"Cache-Control": "no-store"},
            ) from error
        except PaperMarkdownRangeError as error:
            raise HTTPException(
                status_code=416,
                detail=str(error),
                headers={"Cache-Control": "no-store"},
            ) from error
        except PaperMarkdownNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail=str(error),
                headers={"Cache-Control": "no-store"},
            ) from error
        except PaperMarkdownStorageError as error:
            raise HTTPException(
                status_code=503,
                detail=str(error),
                headers={"Cache-Control": "no-store"},
            ) from error
        headers = {
            "Cache-Control": (
                _VERSIONED_CHUNK_CACHE_CONTROL
                if raw_version is not None
                else _UNVERSIONED_CHUNK_CACHE_CONTROL
            ),
            "X-PwC-Truncated": "1" if chunk.truncated else "0",
            "X-PwC-Content-Version": chunk.content_version,
        }
        if chunk.next_offset is not None:
            headers["X-PwC-Next-Offset"] = str(chunk.next_offset)
        return PlainTextResponse(chunk.markdown, headers=headers)

    try:
        markdown, truncated = read_paper_markdown_bounded(
            paper_id,
            bucket_id=settings.paper_markdown_hf_bucket_id,
            token=settings.hf_token or None,
            max_bytes=_MARKDOWN_MAX_BYTES,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail="Paper Markdown was not found",
            headers={"Cache-Control": "no-store"},
        ) from error
    if truncated:
        markdown += "\n\n[document truncated; request a narrower catalog view]\n"
    return PlainTextResponse(
        markdown,
        headers={
            "Cache-Control": _PUBLIC_MARKDOWN_CACHE_CONTROL,
            "X-PWC-Truncated": "1" if truncated else "0",
        },
    )


@router.get("/papers/{paper_id}/lineage")
def paper_lineage(
    paper_id: str = Path(min_length=1, max_length=200),
    db: Session = Depends(get_database_session),
) -> dict:
    try:
        return get_paper_lineage(db, paper_id).to_dict()
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
