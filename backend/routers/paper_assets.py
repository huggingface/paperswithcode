"""Public, immutable serving for OCR-extracted paper images."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from backend.config import get_settings
from backend.services.paper_markdown_service import (
    read_paper_asset,
    stream_external_paper_pdf,
)

router = APIRouter(prefix="/paper-assets", tags=["paper_assets"])

ASSET_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=31536000, immutable",
    "X-Content-Type-Options": "nosniff",
}
MISSING_ASSET_HEADERS = {"Cache-Control": "no-store"}


@router.get("/{prefix}/{paper_id}/{filename}")
def get_paper_asset(prefix: str, paper_id: str, filename: str) -> Response:
    settings = get_settings()
    source = "external" if prefix == "external" else "arxiv"
    if source == "external" and filename == "paper.pdf":
        try:
            chunks, size = stream_external_paper_pdf(
                paper_id,
                bucket_id=settings.paper_markdown_hf_bucket_id,
                token=settings.hf_token,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=404,
                detail="Paper PDF is still being prepared",
                headers=MISSING_ASSET_HEADERS,
            ) from error
        return StreamingResponse(
            chunks,
            media_type="application/pdf",
            headers={**ASSET_CACHE_HEADERS, "Content-Length": str(size)},
        )
    if source == "arxiv" and prefix != paper_id[:4]:
        raise HTTPException(
            status_code=404,
            detail="Paper asset not found",
            headers=MISSING_ASSET_HEADERS,
        )
    try:
        data, media_type = read_paper_asset(
            paper_id,
            filename,
            source=source,
            bucket_id=settings.paper_markdown_hf_bucket_id,
            token=settings.hf_token,
            max_bytes=settings.paper_markdown_image_max_bytes,
            max_pixels=settings.paper_markdown_image_max_pixels,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail="Paper asset not found",
            headers=MISSING_ASSET_HEADERS,
        ) from error
    return Response(
        content=data,
        media_type=media_type,
        headers=ASSET_CACHE_HEADERS,
    )
