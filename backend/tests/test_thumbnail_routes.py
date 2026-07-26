import pytest
from fastapi import HTTPException

from backend.routers.thumbnails import serve_custom_thumbnail, serve_thumbnail


class MissingThumbnailService:
    def get_existing_custom_thumbnail_path(self, _filename):
        return None

    def get_local_thumbnail_path(self, _filename):
        return None


class ExistingThumbnailService:
    def __init__(self, path):
        self.path = path

    def get_existing_custom_thumbnail_path(self, _filename):
        return self.path

    def get_local_thumbnail_path(self, _filename):
        return self.path


@pytest.mark.parametrize(
    "endpoint",
    [serve_thumbnail, serve_custom_thumbnail],
)
def test_missing_thumbnail_is_not_browser_cached(endpoint):
    with pytest.raises(HTTPException) as exc_info:
        endpoint("missing.jpg", MissingThumbnailService())

    assert exc_info.value.status_code == 404
    assert exc_info.value.headers == {"Cache-Control": "no-store"}


@pytest.mark.parametrize(
    "endpoint",
    [serve_thumbnail, serve_custom_thumbnail],
)
def test_thumbnail_response_contains_the_jpeg_body(endpoint, tmp_path):
    body = b"\xff\xd8thumbnail-body\xff\xd9"
    thumbnail = tmp_path / "thumbnail.jpg"
    thumbnail.write_bytes(body)

    response = endpoint("thumbnail.jpg", ExistingThumbnailService(thumbnail))

    assert response.body == body
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["content-length"] == str(len(body))
    assert response.headers["cache-control"] == (
        "public, s-maxage=604800, max-age=604800"
    )
