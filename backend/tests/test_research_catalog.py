from __future__ import annotations

import io

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.routers import research_catalog
from backend.services import paper_markdown_service


def test_paper_read_is_anonymous(monkeypatch):
    monkeypatch.setattr(
        research_catalog,
        "read_paper_markdown_bounded",
        lambda *_args, **_kwargs: ("public markdown", False),
    )

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/research/papers/1706.03762/read")

    assert response.status_code == 200
    assert response.text == "public markdown"


def test_paper_read_is_publicly_cached_and_reports_truncation(monkeypatch):
    seen: dict = {}

    def fake_read(paper_id, **kwargs):
        seen.update(paper_id=paper_id, **kwargs)
        return ("bounded markdown", True)

    monkeypatch.setattr(research_catalog, "read_paper_markdown_bounded", fake_read)

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/research/papers/1706.03762/read")

    assert response.status_code == 200
    assert (
        response.headers["cache-control"]
        == research_catalog._PUBLIC_MARKDOWN_CACHE_CONTROL
    )
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
    paper_markdown_service._read_paper_markdown_bytes.cache_clear()

    try:
        markdown, truncated = paper_markdown_service.read_paper_markdown_bounded(
            "1706.03762v4",
            bucket_id="owner/content",
            token="private-token",
            max_bytes=7,
        )
    finally:
        paper_markdown_service._read_paper_markdown_bytes.cache_clear()

    assert reads == [8]
    assert markdown == "ααα"
    assert truncated is True


def test_bounded_markdown_read_caches_the_public_artifact(monkeypatch):
    opens = 0

    class FakeFileSystem:
        def __init__(self, *, token):
            assert token == "private-token"

        def open(self, _path, _mode, *, block_size):
            nonlocal opens
            assert block_size == 0
            opens += 1
            return io.BytesIO(b"# Cached paper\n")

    monkeypatch.setattr(paper_markdown_service, "HfFileSystem", FakeFileSystem)
    paper_markdown_service._read_paper_markdown_bytes.cache_clear()

    try:
        first = paper_markdown_service.read_paper_markdown_bounded(
            "1706.03762",
            bucket_id="owner/content",
            token="private-token",
            max_bytes=1024,
        )
        second = paper_markdown_service.read_paper_markdown_bounded(
            "1706.03762v4",
            bucket_id="owner/content",
            token="private-token",
            max_bytes=1024,
        )
    finally:
        paper_markdown_service._read_paper_markdown_bytes.cache_clear()

    assert first == second == ("# Cached paper\n", False)
    assert opens == 1
