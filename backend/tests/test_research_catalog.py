from __future__ import annotations

import hashlib
import io
import json

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.routers import research_catalog
from backend.services import paper_markdown_service


@pytest.fixture(autouse=True)
def _clear_markdown_caches():
    paper_markdown_service._paper_markdown_manifest_key_cache.clear()
    paper_markdown_service._paper_markdown_chunk_cache.clear()
    paper_markdown_service._read_paper_markdown_bytes.cache_clear()
    yield
    paper_markdown_service._paper_markdown_manifest_key_cache.clear()
    paper_markdown_service._paper_markdown_chunk_cache.clear()
    paper_markdown_service._read_paper_markdown_bytes.cache_clear()


def _versioned_files(data: bytes, paper_key: str = "1706.03762") -> dict[str, bytes]:
    digest = hashlib.sha256(data).hexdigest()
    source = "external" if paper_key.startswith("external/") else "arxiv"
    content_key = f"_content/sha256/{digest[:2]}/{digest}.md"
    manifest = {
        "schema_version": 1,
        "paper_key": paper_key,
        "source": source,
        "content_sha256": digest,
        "content_key": content_key,
        "size_bytes": len(data),
    }
    return {
        f"_content/manifests/{paper_key}.json": json.dumps(manifest).encode(),
        content_key: data,
    }


def _install_versioned_filesystem(monkeypatch, files: dict[str, bytes]):
    operations: list[tuple[str, int]] = []

    class TrackedFile(io.BytesIO):
        def seek(self, offset, whence=0):
            operations.append(("seek", offset))
            return super().seek(offset, whence)

        def read(self, size=-1):
            operations.append(("read", size))
            return super().read(size)

    class FakeFileSystem:
        def __init__(self, *, token):
            assert token == "private-token"

        def open(self, path, mode, *, block_size):
            assert mode == "rb"
            assert block_size == 0
            prefix = "hf://buckets/owner/content/"
            assert path.startswith(prefix)
            key = path.removeprefix(prefix)
            if key not in files:
                raise FileNotFoundError(key)
            return TrackedFile(files[key])

    monkeypatch.setattr(paper_markdown_service, "HfFileSystem", FakeFileSystem)
    paper_markdown_service._paper_markdown_chunk_cache.clear()
    return operations


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


def test_paper_chunk_defaults_are_utf8_bytes_and_return_continuation_headers(
    monkeypatch,
):
    seen = {}

    def fake_chunk(paper_id, **kwargs):
        seen.update(paper_id=paper_id, **kwargs)
        return paper_markdown_service.PaperMarkdownChunk(
            markdown="bounded α",
            content_version="a" * 64,
            next_offset=10,
        )

    monkeypatch.setattr(research_catalog, "read_paper_markdown_chunk", fake_chunk)

    with TestClient(create_app()) as client:
        response = client.get("/api/v1/research/papers/1706.03762/read?limit=12")

    assert response.status_code == 200
    assert response.text == "bounded α"
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["x-pwc-truncated"] == "1"
    assert response.headers["x-pwc-next-offset"] == "10"
    assert response.headers["x-pwc-content-version"] == "a" * 64
    assert response.headers["cache-control"] == "public, max-age=0, must-revalidate"
    assert seen["paper_id"] == "1706.03762"
    assert seen["offset"] == 0
    assert seen["limit"] == 12
    assert seen["content_version"] is None


def test_paper_chunk_continuation_is_version_bound_and_terminal(monkeypatch):
    seen = {}

    def fake_chunk(paper_id, **kwargs):
        seen.update(paper_id=paper_id, **kwargs)
        return paper_markdown_service.PaperMarkdownChunk(
            markdown="terminal",
            content_version="b" * 64,
            next_offset=None,
        )

    monkeypatch.setattr(research_catalog, "read_paper_markdown_chunk", fake_chunk)

    with TestClient(create_app()) as client:
        response = client.get(
            "/api/v1/research/papers/1706.03762/read",
            params={"offset": "9", "content_version": "b" * 64},
        )

    assert response.status_code == 200
    assert response.text == "terminal"
    assert response.headers["x-pwc-truncated"] == "0"
    assert "x-pwc-next-offset" not in response.headers
    assert response.headers["cache-control"] == "public, max-age=3600"
    assert seen["offset"] == 9
    assert seen["limit"] == research_catalog._MARKDOWN_MAX_BYTES
    assert seen["content_version"] == "b" * 64


@pytest.mark.parametrize(
    "query",
    [
        "offset=-1",
        "offset=true",
        "offset=9223372036854775808",
        "offset=1&offset=2",
        "offset=1",
        "limit=0",
        "limit=true",
        "limit=262145",
        "limit=1&limit=2",
        "content_version=bad/value",
        "content_version=a&content_version=b",
    ],
)
def test_paper_chunk_rejects_invalid_query_before_bucket_io(monkeypatch, query):
    called = False

    def fake_chunk(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("must not reach storage")

    monkeypatch.setattr(research_catalog, "read_paper_markdown_chunk", fake_chunk)
    with TestClient(create_app()) as client:
        response = client.get(f"/api/v1/research/papers/1706.03762/read?{query}")

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert called is False


def test_paper_chunk_rejects_invalid_paper_id_without_leaking_details():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/research/papers/not-an-id/read?limit=12")

    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "Paper Markdown was not found"}


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (
            paper_markdown_service.PaperMarkdownVersionMismatchError("restart"),
            409,
        ),
        (paper_markdown_service.PaperMarkdownRangeError("invalid range"), 416),
        (paper_markdown_service.PaperMarkdownNotFoundError("not found"), 404),
        (paper_markdown_service.PaperMarkdownStorageError("unavailable"), 503),
    ],
)
def test_paper_chunk_maps_sanitized_errors_without_cache(monkeypatch, error, status):
    def fake_chunk(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(research_catalog, "read_paper_markdown_chunk", fake_chunk)
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/research/papers/1706.03762/read?offset=0")

    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert "hf://" not in response.text


def test_legacy_paper_read_sanitizes_storage_errors(monkeypatch):
    def fake_read(*_args, **_kwargs):
        raise ValueError("hf://buckets/private/secret-object")

    monkeypatch.setattr(research_catalog, "read_paper_markdown_bounded", fake_read)
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/research/papers/1706.03762/read")

    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    assert "secret-object" not in response.text


def test_legacy_paper_read_reports_storage_errors_without_cache(monkeypatch):
    def fake_read(*_args, **_kwargs):
        raise paper_markdown_service.PaperMarkdownStorageError("unavailable")

    monkeypatch.setattr(research_catalog, "read_paper_markdown_bounded", fake_read)
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/research/papers/1706.03762/read")

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"


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
            assert mode == "rb"
            assert block_size == 0
            if path.endswith("/_content/manifests/1706.03762.json"):
                raise FileNotFoundError(path)
            assert path == "hf://buckets/owner/content/1706/1706.03762.md"
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


def test_external_markdown_uses_paper_id_bucket_namespace(monkeypatch):
    assert (
        paper_markdown_service.paper_markdown_bucket_key("109743", source="external")
        == "external/109743.md"
    )

    class FakeFileSystem:
        def __init__(self, *, token):
            assert token == "private-token"

        def open(self, path, mode, *, block_size):
            assert mode == "rb"
            assert block_size == 0
            if path.endswith("/_content/manifests/external/109743.json"):
                raise FileNotFoundError(path)
            assert path == "hf://buckets/owner/content/external/109743.md"
            return io.BytesIO(b"# External paper\n")

    monkeypatch.setattr(paper_markdown_service, "HfFileSystem", FakeFileSystem)
    paper_markdown_service._read_paper_markdown_bytes.cache_clear()
    try:
        assert paper_markdown_service.read_paper_markdown_bounded(
            "109743",
            source="external",
            bucket_id="owner/content",
            token="private-token",
            max_bytes=1024,
        ) == ("# External paper\n", False)
    finally:
        paper_markdown_service._read_paper_markdown_bytes.cache_clear()


def test_bounded_markdown_read_caches_the_public_artifact(monkeypatch):
    opens = 0

    class FakeFileSystem:
        def __init__(self, *, token):
            assert token == "private-token"

        def open(self, _path, _mode, *, block_size):
            nonlocal opens
            assert block_size == 0
            if _path.endswith("/_content/manifests/1706.03762.json"):
                raise FileNotFoundError(_path)
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


def test_bounded_markdown_read_uses_manifest_revision_over_mutable_alias(monkeypatch):
    versioned = b"# Version selected by manifest\n"
    files = _versioned_files(versioned)
    files["1706/1706.03762.md"] = b"# Concurrent mutable alias\n"
    _install_versioned_filesystem(monkeypatch, files)
    paper_markdown_service._read_paper_markdown_bytes.cache_clear()

    try:
        result = paper_markdown_service.read_paper_markdown_bounded(
            "1706.03762",
            bucket_id="owner/content",
            token="private-token",
            max_bytes=1024,
        )
    finally:
        paper_markdown_service._read_paper_markdown_bytes.cache_clear()

    assert result == (versioned.decode(), False)


def test_bounded_markdown_read_treats_missing_manifest_revision_as_storage_error(
    monkeypatch,
):
    files = _versioned_files(b"# Revision not visible yet\n")
    content_key = next(key for key in files if key.startswith("_content/sha256/"))
    del files[content_key]
    _install_versioned_filesystem(monkeypatch, files)

    with pytest.raises(
        paper_markdown_service.PaperMarkdownStorageError,
        match="immutable Paper Markdown revision is unavailable",
    ):
        paper_markdown_service.read_paper_markdown_bounded(
            "1706.03762",
            bucket_id="owner/content",
            token="private-token",
            max_bytes=1024,
        )


def test_bounded_markdown_read_uses_stale_resolution_during_manifest_outage(
    monkeypatch,
):
    now = 0.0
    manifest_reads = 0

    class FakeFileSystem:
        def __init__(self, *, token):
            assert token == "private-token"

        def open(self, path, mode, *, block_size):
            nonlocal manifest_reads
            assert mode == "rb"
            assert block_size == 0
            if path.endswith("/_content/manifests/1706.03762.json"):
                manifest_reads += 1
                if manifest_reads == 1:
                    raise FileNotFoundError(path)
                raise OSError("temporary outage")
            assert path.endswith("/1706/1706.03762.md")
            return io.BytesIO(b"# Cached compatibility paper\n")

    monkeypatch.setattr(paper_markdown_service, "HfFileSystem", FakeFileSystem)
    monkeypatch.setattr(paper_markdown_service.time, "monotonic", lambda: now)
    paper_markdown_service._paper_markdown_manifest_key_cache.clear()
    paper_markdown_service._read_paper_markdown_bytes.cache_clear()
    try:
        first = paper_markdown_service.read_paper_markdown_bounded(
            "1706.03762",
            bucket_id="owner/content",
            token="private-token",
            max_bytes=1024,
        )
        now = paper_markdown_service.PAPER_MARKDOWN_MANIFEST_CACHE_SECONDS + 1
        second = paper_markdown_service.read_paper_markdown_bounded(
            "1706.03762",
            bucket_id="owner/content",
            token="private-token",
            max_bytes=1024,
        )
    finally:
        paper_markdown_service._paper_markdown_manifest_key_cache.clear()
        paper_markdown_service._read_paper_markdown_bytes.cache_clear()

    assert first == second == ("# Cached compatibility paper\n", False)
    assert manifest_reads == 2


def test_versioned_markdown_chunk_reads_bounded_utf8_bytes(monkeypatch):
    data = "aα🙂z".encode()
    files = _versioned_files(data)
    operations = _install_versioned_filesystem(monkeypatch, files)

    first = paper_markdown_service.read_paper_markdown_chunk(
        "1706.03762v4",
        bucket_id="owner/content",
        token="private-token",
        offset=0,
        limit=4,
    )
    second = paper_markdown_service.read_paper_markdown_chunk(
        "1706.03762",
        bucket_id="owner/content",
        token="private-token",
        offset=first.next_offset,
        limit=5,
        content_version=first.content_version,
    )

    assert first.markdown == "aα"
    assert first.next_offset == 3
    assert first.truncated is True
    assert second.markdown == "🙂z"
    assert second.next_offset is None
    assert second.truncated is False
    assert ("read", 8) in operations
    assert ("seek", 3) in operations


def test_versioned_markdown_chunk_validates_offsets_and_versions(monkeypatch):
    data = "aα🙂z".encode()
    files = _versioned_files(data)
    _install_versioned_filesystem(monkeypatch, files)
    kwargs = {
        "bucket_id": "owner/content",
        "token": "private-token",
        "limit": 10,
    }

    with pytest.raises(
        paper_markdown_service.PaperMarkdownRangeError, match="code-point boundary"
    ):
        paper_markdown_service.read_paper_markdown_chunk(
            "1706.03762", offset=2, **kwargs
        )
    with pytest.raises(paper_markdown_service.PaperMarkdownRangeError, match="beyond"):
        paper_markdown_service.read_paper_markdown_chunk(
            "1706.03762", offset=len(data) + 1, **kwargs
        )
    with pytest.raises(
        paper_markdown_service.PaperMarkdownVersionMismatchError, match="restart"
    ):
        paper_markdown_service.read_paper_markdown_chunk(
            "1706.03762", offset=1, content_version="0" * 64, **kwargs
        )

    terminal = paper_markdown_service.read_paper_markdown_chunk(
        "1706.03762", offset=len(data), **kwargs
    )
    assert terminal.markdown == ""
    assert terminal.next_offset is None


def test_versioned_markdown_chunk_rejects_nonadvancing_utf8_limit(monkeypatch):
    files = _versioned_files("🙂".encode())
    _install_versioned_filesystem(monkeypatch, files)

    with pytest.raises(
        paper_markdown_service.PaperMarkdownRangeError, match="cannot fit"
    ):
        paper_markdown_service.read_paper_markdown_chunk(
            "1706.03762",
            bucket_id="owner/content",
            token="private-token",
            offset=0,
            limit=3,
        )


def test_versioned_markdown_chunk_rejects_invalid_manifest_without_leaking_path(
    monkeypatch,
):
    files = {"_content/manifests/1706.03762.json": b'{"content_key":"../secret"}'}
    _install_versioned_filesystem(monkeypatch, files)

    with pytest.raises(
        paper_markdown_service.PaperMarkdownStorageError,
        match="Paper Markdown manifest is invalid",
    ) as captured:
        paper_markdown_service.read_paper_markdown_chunk(
            "1706.03762",
            bucket_id="owner/content",
            token="private-token",
            offset=0,
            limit=10,
        )

    assert "secret" not in str(captured.value)


def test_versioned_markdown_chunk_cache_is_separate_and_avoids_content_reread(
    monkeypatch,
):
    data = b"complete markdown"
    files = _versioned_files(data)
    operations = _install_versioned_filesystem(monkeypatch, files)
    kwargs = {
        "bucket_id": "owner/content",
        "token": "private-token",
        "offset": 0,
        "limit": 8,
    }

    first = paper_markdown_service.read_paper_markdown_chunk("1706.03762", **kwargs)
    reads_after_first = list(operations)
    second = paper_markdown_service.read_paper_markdown_chunk("1706.03762", **kwargs)

    assert first == second
    assert operations[len(reads_after_first) :] == [
        ("read", paper_markdown_service.PAPER_MARKDOWN_MANIFEST_MAX_BYTES + 1)
    ]
