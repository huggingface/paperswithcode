import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image, ImageDraw

from backend.services.thumbnail_service import (
    CARD_THUMB_ASPECT,
    EXPECTED_THUMBNAIL_HEIGHT,
    EXPECTED_THUMBNAIL_WIDTH,
    ThumbnailService,
    _crop_to_card_aspect,
    _prepare_first_page_for_card,
    _resize_to_card_fill,
    _trim_blank_page_margins,
    _trim_leading_blank_rows,
    _trim_sparse_footer_rows,
    _trim_trailing_blank_rows,
    is_thumbnail_valid,
)
from backend.services.arxiv_service import ArxivPdfUnavailableError
from backend.services.safe_outbound_http_service import (
    SafeFetchResult,
    SafeOutboundHttpError,
)
from backend.utils.exceptions import ThumbnailGenerationError, ThumbnailUnavailableError


def test_trim_blank_page_margins_keeps_visible_content_with_padding():
    image = Image.new("RGB", (100, 140), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 30, 79, 109), fill="black")

    trimmed = _trim_blank_page_margins(image)

    assert trimmed.size == (68, 88)
    assert trimmed.getpixel((4, 4)) == (0, 0, 0)


def test_trim_blank_page_margins_leaves_blank_page_unchanged():
    image = Image.new("RGB", (100, 140), "white")

    trimmed = _trim_blank_page_margins(image)

    assert trimmed.size == image.size


def test_trim_trailing_blank_rows_removes_footer_whitespace():
    image = Image.new("RGB", (100, 140), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 79, 99), fill="black")
    draw.text((30, 120), "footer", fill=(120, 120, 120))

    trimmed = _trim_trailing_blank_rows(image)

    assert trimmed.height < image.height
    assert trimmed.getpixel((50, 59)) == (0, 0, 0)


def test_trim_leading_blank_rows_removes_top_whitespace():
    image = Image.new("RGB", (100, 140), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 40, 79, 119), fill="black")

    trimmed = _trim_leading_blank_rows(image)

    assert trimmed.height < image.height
    assert trimmed.getpixel((50, 19)) == (0, 0, 0)


def test_trim_sparse_footer_rows_removes_copyright_line():
    image = Image.new("RGB", (100, 140), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 79, 99), fill="black")
    draw.text((30, 120), "© 2025", fill=(120, 120, 120))

    trimmed = _trim_sparse_footer_rows(image)

    assert trimmed.height < image.height
    assert trimmed.getpixel((50, 59)) == (0, 0, 0)


def test_trim_sparse_footer_rows_preserves_sparse_body_text():
    """Low-density body rows above the footer band must not be cropped away."""
    image = Image.new("RGB", (100, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 79, 99), fill="black")
    for y in range(130, 150):
        draw.point((30, y), fill=(100, 100, 100))
        draw.point((50, y), fill=(100, 100, 100))
    draw.text((30, 190), "© 2025", fill=(120, 120, 120))

    trimmed = _trim_sparse_footer_rows(image)

    assert trimmed.height >= 150
    assert trimmed.getpixel((50, 59)) == (0, 0, 0)
    assert trimmed.getpixel((30, 135)) == (100, 100, 100)


def test_resize_to_card_fill_matches_card_aspect():
    image = Image.new("RGB", (400, 800), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((180, 40, 219, 79), fill="black")

    filled = _resize_to_card_fill(image)

    assert filled.size == (EXPECTED_THUMBNAIL_WIDTH, EXPECTED_THUMBNAIL_HEIGHT)
    # Contain-fit keeps the full page visible; the marker stays near the top.
    assert filled.getpixel((filled.width // 2, 45)) == (0, 0, 0)


def test_prepare_first_page_for_card_preserves_native_page_ratio():
    image = Image.new("RGB", (377, 424), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 350, 400), fill="black")

    prepared = _prepare_first_page_for_card(image)

    assert prepared.size == (EXPECTED_THUMBNAIL_WIDTH, 450)
    assert prepared.width / prepared.height == pytest.approx(
        image.width / image.height, rel=0.01
    )


def test_prepare_first_page_preserves_page_that_already_matches_target_width():
    image = Image.new("RGB", (400, 550), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 30, 390, 45), fill="black")
    draw.rectangle((170, 180, 230, 260), fill="black")
    draw.rectangle((390, 450, 399, 465), fill="black")

    prepared = _prepare_first_page_for_card(image)

    assert prepared.size == (EXPECTED_THUMBNAIL_WIDTH, 550)
    assert prepared.getpixel((10, 35)) == (0, 0, 0)
    assert prepared.getpixel((390, 35)) == (0, 0, 0)
    assert prepared.getpixel((395, 455)) == (0, 0, 0)


def test_crop_to_card_aspect_center_crops_wide_pages():
    image = Image.new("RGB", (400, 504), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((180, 40, 219, 79), fill="black")

    cropped = _crop_to_card_aspect(image)

    assert cropped.width / cropped.height == pytest.approx(CARD_THUMB_ASPECT, rel=0.01)
    assert cropped.getpixel((cropped.width // 2, 59)) == (0, 0, 0)


def _save_jpeg(path: Path, width: int, height: int) -> None:
    Image.new("RGB", (width, height), "white").save(path, "JPEG", quality=85)


def test_is_thumbnail_valid_accepts_expected_dimensions_jpeg(tmp_path: Path):
    path = tmp_path / "good.jpg"
    _save_jpeg(path, EXPECTED_THUMBNAIL_WIDTH, EXPECTED_THUMBNAIL_HEIGHT)
    assert is_thumbnail_valid(path) is True


def test_is_thumbnail_valid_rejects_wrong_height_jpeg(tmp_path: Path):
    path = tmp_path / "wrong_height.jpg"
    _save_jpeg(path, EXPECTED_THUMBNAIL_WIDTH, 380)
    assert is_thumbnail_valid(path) is False


def test_is_thumbnail_valid_accepts_native_letter_page_height(tmp_path: Path):
    path = tmp_path / "letter.jpg"
    _save_jpeg(path, EXPECTED_THUMBNAIL_WIDTH, 518)
    assert is_thumbnail_valid(path) is True


def test_is_thumbnail_valid_rejects_wrong_width_jpeg(tmp_path: Path):
    path = tmp_path / "wrong.jpg"
    _save_jpeg(path, EXPECTED_THUMBNAIL_WIDTH // 2, 280)
    assert is_thumbnail_valid(path) is False


def test_is_thumbnail_valid_rejects_corrupt_file(tmp_path: Path):
    path = tmp_path / "broken.jpg"
    path.write_bytes(b"this is not a JPEG")
    assert is_thumbnail_valid(path) is False


def test_is_thumbnail_valid_rejects_empty_file(tmp_path: Path):
    path = tmp_path / "empty.jpg"
    path.write_bytes(b"")
    assert is_thumbnail_valid(path) is False


def test_is_thumbnail_valid_rejects_missing_file(tmp_path: Path):
    assert is_thumbnail_valid(tmp_path / "missing.jpg") is False


def test_is_thumbnail_valid_rejects_non_jpeg_format(tmp_path: Path):
    path = tmp_path / "wrong_format.jpg"
    Image.new("RGB", (EXPECTED_THUMBNAIL_WIDTH, 560), "white").save(path, "PNG")
    assert is_thumbnail_valid(path) is False


def test_is_thumbnail_valid_rejects_squat_thumbnail(tmp_path: Path):
    # Older buggy renders produced 400x258 (H/W = 0.645) by clipping the
    # height. These are correct width but visually broken in card layouts.
    path = tmp_path / "squat.jpg"
    _save_jpeg(path, EXPECTED_THUMBNAIL_WIDTH, 258)
    assert is_thumbnail_valid(path) is False


def test_is_thumbnail_valid_accepts_custom_native_page_height(tmp_path: Path):
    path = tmp_path / "legacy.jpg"
    _save_jpeg(path, EXPECTED_THUMBNAIL_WIDTH, 599)
    assert is_thumbnail_valid(path) is True


def test_is_thumbnail_valid_accepts_portrait_thumbnail(tmp_path: Path):
    path = tmp_path / "portrait.jpg"
    _save_jpeg(path, EXPECTED_THUMBNAIL_WIDTH, EXPECTED_THUMBNAIL_HEIGHT)
    assert is_thumbnail_valid(path) is True


def test_save_thumbnail_makes_shared_cache_file_publicly_readable(tmp_path: Path):
    path = tmp_path / "thumbnail.jpg"
    path.touch(mode=0o600)
    service = ThumbnailService.__new__(ThumbnailService)
    service.thumbnail_quality = 85

    service._save_thumbnail(Image.new("RGB", (400, 550), "white"), path)

    assert path.stat().st_mode & 0o777 == 0o644


def test_normalize_external_pdf_url_converts_github_blob_to_raw():
    service = ThumbnailService.__new__(ThumbnailService)

    assert (
        service._normalize_external_pdf_url(
            "https://github.com/huggingface/carbon/blob/main/tech-report.pdf"
        )
        == "https://github.com/huggingface/carbon/raw/main/tech-report.pdf"
    )


def test_external_html_source_skips_pdf_download():
    service = ThumbnailService.__new__(ThumbnailService)

    result = asyncio.run(
        service._download_external_pdf(
            "https://docs.lightly.ai/train/stable/object_detection.html"
        )
    )

    assert result is None


def _external_pdf_service() -> ThumbnailService:
    service = ThumbnailService.__new__(ThumbnailService)
    service.max_pdf_size = 1_000_000
    service.pdf_timeout = 10
    return service


@pytest.mark.parametrize(
    "host",
    [
        "aixiv.science",
        "ecmlpkdd-storage.s3.eu-central-1.amazonaws.com",
        "microsoft.ai",
        "www.cv-foundation.org",
    ],
)
def test_approved_external_pdf_host_can_be_rendered(monkeypatch, host: str):
    service = _external_pdf_service()

    async def fetch(url, **kwargs):
        if host not in kwargs["allowed_hosts"]:
            raise SafeOutboundHttpError(403, "The outbound hostname is not approved")
        return SafeFetchResult(url, 200, "application/pdf", b"%PDF-example")

    monkeypatch.setattr(
        "backend.services.thumbnail_service.fetch_public_resource", fetch
    )

    result = asyncio.run(service._download_external_pdf(f"https://{host}/report.pdf"))

    assert result == b"%PDF-example"


@pytest.mark.parametrize("origin_status_code", [403, 404, 410])
def test_permanent_external_pdf_error_generates_metadata_fallback(
    tmp_path: Path, monkeypatch, origin_status_code: int
):
    service = _external_pdf_service()
    service.thumbnail_width = EXPECTED_THUMBNAIL_WIDTH
    service.thumbnail_quality = 85
    service.get_external_filename = lambda _paper_id: "external_42.jpg"
    service.get_existing_custom_thumbnail_path = MagicMock(return_value=None)
    service._get_active_cache_path = MagicMock(
        return_value=tmp_path / "external_42.jpg"
    )
    service._upload_to_bucket = MagicMock()

    async def missing(*_args, **_kwargs):
        raise SafeOutboundHttpError(
            502,
            "The outbound origin returned an error",
            origin_status_code=origin_status_code,
        )

    monkeypatch.setattr(
        "backend.services.thumbnail_service.fetch_public_resource", missing
    )

    path = asyncio.run(
        service.generate_external_thumbnail(
            42,
            "https://openaccess.thecvf.com/missing.pdf",
            title="Missing report",
        )
    )

    assert is_thumbnail_valid(path)
    service._upload_to_bucket.assert_called_once_with(path, "external_42.jpg")


def test_external_thumbnail_prefers_pdf_url_over_landing_page(
    tmp_path: Path, monkeypatch
):
    service = _external_pdf_service()
    service.get_external_filename = lambda _paper_id: "external_42.jpg"
    service.get_existing_custom_thumbnail_path = MagicMock(return_value=None)
    service._get_active_cache_path = MagicMock(
        return_value=tmp_path / "external_42.jpg"
    )
    service._upload_to_bucket = MagicMock()
    service._save_thumbnail = MagicMock()
    service._convert_pdf_to_thumbnail = MagicMock(return_value="rendered")
    service._render_external_metadata_thumbnail = MagicMock()
    fetched: list[str] = []

    async def fetch(url, **_kwargs):
        fetched.append(url)
        return SimpleNamespace(body=b"%PDF-example")

    monkeypatch.setattr(
        "backend.services.thumbnail_service.fetch_public_resource", fetch
    )

    asyncio.run(
        service.generate_external_thumbnail(
            42,
            "https://papers.miccai.org/miccai-2025/0001-Paper.html",
            title="A MICCAI paper",
            pdf_url="https://papers.miccai.org/miccai-2025/paper/0001_paper.pdf",
        )
    )

    assert fetched == ["https://papers.miccai.org/miccai-2025/paper/0001_paper.pdf"]
    service._convert_pdf_to_thumbnail.assert_called_once_with(b"%PDF-example")
    service._render_external_metadata_thumbnail.assert_not_called()


def _external_generation_service(tmp_path: Path):
    service = _external_pdf_service()
    service.get_external_filename = lambda _paper_id: "external_42.jpg"
    service.get_existing_custom_thumbnail_path = MagicMock(return_value=None)
    service._get_active_cache_path = MagicMock(
        return_value=tmp_path / "external_42.jpg"
    )
    service._upload_to_bucket = MagicMock()
    service._save_thumbnail = MagicMock()
    service._convert_pdf_to_thumbnail = MagicMock(return_value="rendered")
    service._render_external_metadata_thumbnail = MagicMock()
    return service


def test_external_thumbnail_fetches_pdf_url_without_pdf_suffix(
    tmp_path: Path, monkeypatch
):
    service = _external_generation_service(tmp_path)
    fetched: list[str] = []

    async def fetch(url, **_kwargs):
        fetched.append(url)
        return SimpleNamespace(body=b"%PDF-example")

    monkeypatch.setattr(
        "backend.services.thumbnail_service.fetch_public_resource", fetch
    )

    asyncio.run(
        service.generate_external_thumbnail(
            42,
            "https://openreview.net/forum?id=abc",
            title="An OpenReview paper",
            pdf_url="https://openreview.net/pdf?id=abc",
        )
    )

    assert fetched == ["https://openreview.net/pdf?id=abc"]
    service._render_external_metadata_thumbnail.assert_not_called()


def test_transient_pdf_url_error_falls_back_to_source_pdf(tmp_path: Path, monkeypatch):
    service = _external_generation_service(tmp_path)

    async def fetch(url, **_kwargs):
        if url.endswith("conference.pdf"):
            raise SafeOutboundHttpError(502, "bad gateway", origin_status_code=503)
        return SimpleNamespace(body=b"%PDF-source")

    monkeypatch.setattr(
        "backend.services.thumbnail_service.fetch_public_resource", fetch
    )

    asyncio.run(
        service.generate_external_thumbnail(
            42,
            "https://openaccess.thecvf.com/source.pdf",
            pdf_url="https://openaccess.thecvf.com/conference.pdf",
        )
    )

    service._convert_pdf_to_thumbnail.assert_called_once_with(b"%PDF-source")


def test_transient_pdf_url_error_does_not_cache_metadata_card(
    tmp_path: Path, monkeypatch
):
    service = _external_generation_service(tmp_path)

    async def fetch(_url, **_kwargs):
        raise SafeOutboundHttpError(502, "bad gateway", origin_status_code=503)

    monkeypatch.setattr(
        "backend.services.thumbnail_service.fetch_public_resource", fetch
    )

    with pytest.raises(ThumbnailGenerationError):
        asyncio.run(
            service.generate_external_thumbnail(
                42,
                "https://www.isca-archive.org/x/paper.html",
                title="A Speech Paper",
                pdf_url="https://www.isca-archive.org/x/paper.pdf",
            )
        )

    service._render_external_metadata_thumbnail.assert_not_called()
    service._upload_to_bucket.assert_not_called()


@pytest.mark.parametrize("safe_status_code", [403, 409, 413, 415, 422])
def test_permanent_safe_fetch_error_uses_metadata_fallback(
    monkeypatch, safe_status_code: int
):
    service = _external_pdf_service()

    async def rejected(*_args, **_kwargs):
        raise SafeOutboundHttpError(safe_status_code, "permanent")

    monkeypatch.setattr(
        "backend.services.thumbnail_service.fetch_public_resource", rejected
    )

    result = asyncio.run(
        service._download_external_pdf("https://example.com/report.pdf")
    )

    assert result is None


@pytest.mark.parametrize("origin_status_code", [None, 503])
def test_transient_external_pdf_error_remains_retryable(
    monkeypatch, origin_status_code: int | None
):
    service = _external_pdf_service()

    async def unavailable(*_args, **_kwargs):
        raise SafeOutboundHttpError(
            502,
            "The outbound origin returned an error",
            origin_status_code=origin_status_code,
        )

    monkeypatch.setattr(
        "backend.services.thumbnail_service.fetch_public_resource", unavailable
    )

    with pytest.raises(ThumbnailGenerationError, match="temporarily unavailable"):
        asyncio.run(
            service._download_external_pdf(
                "https://openaccess.thecvf.com/temporarily-unavailable.pdf"
            )
        )


def test_external_metadata_thumbnail_matches_card_dimensions():
    service = ThumbnailService.__new__(ThumbnailService)
    service.thumbnail_width = EXPECTED_THUMBNAIL_WIDTH

    image = service._render_external_metadata_thumbnail(
        "Object Detection with LightlyTrain",
        "https://docs.lightly.ai/train/stable/object_detection.html",
    )

    assert image.size == (EXPECTED_THUMBNAIL_WIDTH, EXPECTED_THUMBNAIL_HEIGHT)
    assert image.getbbox() == (
        0,
        0,
        EXPECTED_THUMBNAIL_WIDTH,
        EXPECTED_THUMBNAIL_HEIGHT,
    )


def _thumbnail_service_with_missing_pdf(tmp_path: Path, latest_version: str):
    service = ThumbnailService.__new__(ThumbnailService)
    service.arxiv_service = MagicMock()
    service.arxiv_service.download_pdf = AsyncMock(
        side_effect=ArxivPdfUnavailableError("missing")
    )
    service.arxiv_service.get_paper_metadata = AsyncMock(
        return_value=SimpleNamespace(success=True, version=latest_version)
    )
    service.get_filename = lambda arxiv_id, version: f"{arxiv_id}_{version}.jpg"
    service.get_existing_thumbnail_path = MagicMock(return_value=None)
    service._get_cache_path = MagicMock(return_value=tmp_path / "paper.jpg")
    return service


def test_generate_thumbnail_classifies_latest_arxiv_pdf_as_unavailable(tmp_path: Path):
    service = _thumbnail_service_with_missing_pdf(tmp_path, "v4")

    with pytest.raises(ThumbnailUnavailableError):
        asyncio.run(service.generate_thumbnail("2402.17012", "v4"))


def test_generate_thumbnail_keeps_stale_arxiv_version_as_failure(tmp_path: Path):
    service = _thumbnail_service_with_missing_pdf(tmp_path, "v2")

    with pytest.raises(ThumbnailGenerationError, match="version mismatch"):
        asyncio.run(service.generate_thumbnail("2509.18216", "v1"))
