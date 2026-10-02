from types import SimpleNamespace

import pytest

from backend.services.paper_service import PaperService
from backend.services.thumbnail_service import ThumbnailService


def thumbnail_service(tmp_path):
    service = object.__new__(ThumbnailService)
    service._get_active_cache_path = lambda filename: tmp_path / filename
    service._get_legacy_cache_path = lambda filename: tmp_path / "legacy" / filename
    return service


def paper_service(thumbnails):
    service = object.__new__(PaperService)
    service._thumbnail_service = thumbnails
    return service


def paper(arxiv_id, version="v1", thumbnail_url=None):
    return SimpleNamespace(
        source="arxiv",
        arxiv_id=arxiv_id,
        version=version,
        thumbnail_url=thumbnail_url,
    )


@pytest.mark.parametrize(
    ("arxiv_id", "version"),
    [("0306050", "v1"), ("2401.00001", "invalid"), ("2401.00001", "../v1")],
)
def test_invalid_catalog_thumbnail_does_not_abort_batch(tmp_path, arxiv_id, version):
    service = paper_service(thumbnail_service(tmp_path))
    (tmp_path / "2401_00002_v1.jpg").touch()

    urls = [
        service._resolve_thumbnail_url(row)
        for row in [paper(arxiv_id, version), paper("2401.00002")]
    ]

    assert urls[0] is None
    assert urls[1].startswith("/api/thumbnails/2401_00002_v1.jpg?")


def test_existing_thumbnail_url_needs_no_filename_resolution(tmp_path):
    service = paper_service(thumbnail_service(tmp_path))
    assert (
        service._resolve_thumbnail_url(
            paper("0306050", thumbnail_url="https://example.com/thumbnail.jpg")
        )
        == "https://example.com/thumbnail.jpg"
    )


def test_thumbnail_storage_errors_remain_visible(tmp_path):
    thumbnails = thumbnail_service(tmp_path)

    def unavailable(_filename):
        raise OSError("cache unavailable")

    thumbnails._get_active_cache_path = unavailable
    with pytest.raises(OSError, match="cache unavailable"):
        paper_service(thumbnails)._resolve_thumbnail_url(paper("2401.00001"))
