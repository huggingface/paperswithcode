"""CLI-facing orchestration for regenerating and validating paper thumbnails."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy.orm import Session

from backend.services.thumbnail_service import (
    EXPECTED_THUMBNAIL_WIDTH,
    ThumbnailService,
    build_custom_thumbnail_url,
    build_external_thumbnail_filename,
    build_thumbnail_filename,
    build_thumbnail_url,
    is_thumbnail_valid,
)
from backend.utils.paper_reference import resolve_paper


@dataclass(frozen=True)
class ThumbnailImageStats:
    path: str
    width: int
    height: int
    ratio: float
    valid: bool
    content_height_pct: float | None
    bottom_margin_px: int | None


@dataclass(frozen=True)
class PaperThumbnailResult:
    paper_id: int
    arxiv_id: str | None
    source: str
    previous: ThumbnailImageStats | None
    generated: ThumbnailImageStats
    thumbnail_url: str
    expected_size: tuple[int, int | None]
    force: bool
    success: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def describe_thumbnail(path: Path | None) -> ThumbnailImageStats | None:
    if path is None or not path.exists():
        return None
    with Image.open(path) as image:
        mask = (
            image.convert("RGB")
            .point(lambda value: 255 if value < 245 else 0)
            .convert("L")
        )
        bbox = mask.getbbox()
        content_height_pct = None
        bottom_margin_px = None
        if bbox:
            content_height_pct = round(
                100 * (bbox[3] - bbox[1]) / image.height,
                1,
            )
            bottom_margin_px = image.height - bbox[3]
        return ThumbnailImageStats(
            path=str(path),
            width=image.width,
            height=image.height,
            ratio=round(image.height / image.width, 4),
            valid=is_thumbnail_valid(path),
            content_height_pct=content_height_pct,
            bottom_margin_px=bottom_margin_px,
        )


def _local_thumbnail_path(
    service: ThumbnailService,
    *,
    paper_id: int,
    source: str,
    arxiv_id: str | None,
    version: str,
) -> Path | None:
    if source == "external":
        filename = build_external_thumbnail_filename(paper_id)
        return service.get_local_custom_thumbnail_path(filename)
    if not arxiv_id:
        raise ValueError(f"Paper {paper_id} has no arXiv ID")
    filename = build_thumbnail_filename(arxiv_id, version)
    return service.get_local_thumbnail_path(filename)


async def regenerate_paper_thumbnail(
    db: Session,
    paper_reference: str,
    *,
    force: bool = True,
    service: ThumbnailService | None = None,
) -> PaperThumbnailResult:
    paper, _route_id = resolve_paper(db, paper_reference)
    thumbnail_service = service or ThumbnailService()
    version = paper.version or "v1"
    previous_path = _local_thumbnail_path(
        thumbnail_service,
        paper_id=paper.id,
        source=paper.source,
        arxiv_id=paper.arxiv_id,
        version=version,
    )
    previous = describe_thumbnail(previous_path)

    if paper.source == "external":
        if not paper.source_url:
            raise ValueError(f"External paper {paper.id} has no source URL")
        generated_path = await thumbnail_service.generate_external_thumbnail(
            paper.id,
            paper.source_url,
            force=force,
            title=paper.title,
            pdf_url=paper.conference_url_pdf,
        )
        filename = build_external_thumbnail_filename(paper.id)
        cache_bust = str(generated_path.stat().st_mtime_ns)
        thumbnail_url = build_custom_thumbnail_url(filename, cache_bust=cache_bust)
        paper.thumbnail_url = thumbnail_url
        db.commit()
    else:
        if not paper.arxiv_id:
            raise ValueError(f"Paper {paper.id} has no arXiv ID")
        generated_path = await thumbnail_service.generate_thumbnail(
            paper.arxiv_id,
            version,
            force=force,
        )
        filename = build_thumbnail_filename(paper.arxiv_id, version)
        # The API gives an explicit thumbnail_url precedence over its derived
        # arXiv URL. Persist a per-generation version so a regenerated image
        # cannot remain hidden behind a browser/CDN cache or an older explicit
        # URL on the paper row.
        cache_bust = str(generated_path.stat().st_mtime_ns)
        thumbnail_url = build_thumbnail_url(filename, cache_bust=cache_bust)
        paper.thumbnail_url = thumbnail_url
        db.commit()

    generated = describe_thumbnail(generated_path)
    if generated is None:
        raise ValueError("Thumbnail generation returned no readable file")

    expected_size = (EXPECTED_THUMBNAIL_WIDTH, generated.height)
    warnings = []
    if not generated.valid:
        warnings.append("thumbnail failed JPEG or dimension validation")
    if generated.width != EXPECTED_THUMBNAIL_WIDTH:
        warnings.append(
            f"expected width {expected_size[0]}, got "
            f"{generated.width}x{generated.height}"
        )
    return PaperThumbnailResult(
        paper_id=paper.id,
        arxiv_id=paper.arxiv_id,
        source=paper.source,
        previous=previous,
        generated=generated,
        thumbnail_url=thumbnail_url,
        expected_size=expected_size,
        force=force,
        success=not warnings,
        warnings=tuple(warnings),
    )
