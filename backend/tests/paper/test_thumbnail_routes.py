from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.database.connection import get_database_session
from backend.models.database import Paper as DBPaper
from backend.routers import thumbnails as thumbnails_router
from backend.routers.thumbnails import serve_custom_thumbnail, serve_thumbnail
from backend.services import thumbnail_service as thumbnail_service_module
from backend.services.thumbnail_service import ThumbnailService
from backend.utils.auth import require_admin


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


def _stats_service(tmp_path, backend="local"):
    service = ThumbnailService.__new__(ThumbnailService)
    service.storage_backend = backend
    service.temp_cache_dir = tmp_path
    service.legacy_cache_dir = tmp_path
    service.bucket_id = "org/secret-bucket"
    service.bucket_prefix = "thumbnails"
    return service


def _thumbnail_client(service, db=None, admin=False):
    app = FastAPI()
    app.include_router(thumbnails_router.router, prefix="/api")
    app.dependency_overrides[thumbnails_router.get_thumbnail_service] = lambda: service
    app.dependency_overrides[get_database_session] = lambda: db
    if admin:
        app.dependency_overrides[require_admin] = lambda: {"role": "admin"}
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_cache_stats(monkeypatch):
    monkeypatch.setattr(thumbnail_service_module, "_cache_stats_cache", {})


def test_cache_stats_requires_admin(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.utils.auth.get_settings",
        lambda: SimpleNamespace(admin_api_token="expected-token"),
    )
    monkeypatch.setattr("backend.utils.auth._session_actor", lambda _request: None)
    client = _thumbnail_client(_stats_service(tmp_path))

    assert client.get("/api/thumbnails/cache/stats").status_code == 401
    response = client.get(
        "/api/thumbnails/cache/stats", headers={"X-Admin-Token": "wrong"}
    )
    assert response.status_code == 401


def test_cache_stats_omits_server_paths_and_bucket_ids(tmp_path):
    (tmp_path / "a.jpg").write_bytes(b"x" * 1024)
    (tmp_path / "b.jpg").write_bytes(b"x" * 1024)
    (tmp_path / "ignored.png").write_bytes(b"x")
    client = _thumbnail_client(_stats_service(tmp_path, "hf_bucket"), admin=True)

    response = client.get("/api/thumbnails/cache/stats")

    assert response.status_code == 200
    assert response.json() == {
        "total_files": 2,
        "total_size_mb": 0.0,
        "storage_backend": "hf_bucket",
    }
    assert str(tmp_path) not in response.text
    assert "secret-bucket" not in response.text


def test_cache_stats_reuses_recent_walk(tmp_path, monkeypatch):
    service = _stats_service(tmp_path)
    (tmp_path / "a.jpg").write_bytes(b"x")
    assert service.get_cache_stats()["total_files"] == 1

    (tmp_path / "b.jpg").write_bytes(b"x")
    assert service.get_cache_stats()["total_files"] == 1

    monkeypatch.setattr(thumbnail_service_module, "CACHE_STATS_TTL_SECONDS", 0.0)
    assert service.get_cache_stats()["total_files"] == 2


class _FakeDb:
    def __init__(self, row):
        self.row = row
        self.committed = False

    def get(self, model, paper_id):
        assert model is DBPaper
        return self.row if paper_id == self.row.id else None

    def commit(self):
        self.committed = True


def test_generate_persists_discovered_external_thumbnail(monkeypatch):
    api_paper = SimpleNamespace(
        id=42,
        source="external",
        source_url="https://example.com/report",
        thumbnail_url=None,
    )
    monkeypatch.setattr(
        thumbnails_router.PaperService,
        "get_paper_by_id",
        lambda _self, _paper_id: api_paper,
    )
    db_row = SimpleNamespace(id=42, thumbnail_url=None)
    db = _FakeDb(db_row)
    url = "/api/thumbnails/custom/external_42.jpg"
    service = SimpleNamespace(get_external_thumbnail_url=lambda _paper_id: url)
    client = _thumbnail_client(service, db=db, admin=True)

    response = client.post("/api/thumbnails/generate/42")

    assert response.status_code == 200
    assert response.json()["status"] == "cached"
    assert db_row.thumbnail_url == url
    assert db.committed
