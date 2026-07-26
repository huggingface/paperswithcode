from pathlib import Path

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
