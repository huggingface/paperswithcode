from __future__ import annotations

import io

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.routers import research_catalog
from backend.services import paper_markdown_service
from backend.utils.auth import require_user


def test_paper_read_requires_authentication(monkeypatch):
    monkeypatch.setattr(
        research_catalog,
        "read_paper_markdown_bounded",
        lambda *_args, **_kwargs: ("secret", False),
    )

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/research/papers/1706.03762/read")

    assert response.status_code == 401


def test_paper_read_is_private_and_reports_truncation(monkeypatch):
    seen: dict = {}

    def fake_read(paper_id, **kwargs):
        seen.update(paper_id=paper_id, **kwargs)
        return ("bounded markdown", True)

    monkeypatch.setattr(research_catalog, "read_paper_markdown_bounded", fake_read)
    app = create_app()
    app.dependency_overrides[require_user] = lambda: {
        "source": "cookie",
        "username": "tester",
        "hf_user_id": "hf-test-sub",
    }

    with TestClient(app) as client:
        response = client.get("/api/v1/research/papers/1706.03762/read")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-pwc-truncated"] == "1"
    assert response.text.endswith(
        "[document truncated; request a narrower catalog view]\n"
    )
    assert seen["paper_id"] == "1706.03762"
    assert seen["max_bytes"] == research_catalog._MARKDOWN_MAX_BYTES


def test_bounded_markdown_read_never_requests_the_full_object(monkeypatch):
    raw = ("α" * 20).encode()
    reads: list[int] = []

    class TrackedFile(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            return super().read(size)

    class FakeFileSystem:
        def __init__(self, *, token):
            assert token == "private-token"

        def open(self, path, mode, *, block_size):
            assert path == "hf://buckets/owner/content/1706/1706.03762.md"
            assert mode == "rb"
            assert block_size == 0
            return TrackedFile(raw)

    monkeypatch.setattr(paper_markdown_service, "HfFileSystem", FakeFileSystem)

    markdown, truncated = paper_markdown_service.read_paper_markdown_bounded(
        "1706.03762v4",
        bucket_id="owner/content",
        token="private-token",
        max_bytes=7,
    )

    assert reads == [8]
    assert markdown == "ααα"
    assert truncated is True
