from __future__ import annotations

import io
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image

from backend.main import create_app
from backend.routers import paper_assets
from backend.services import paper_markdown_service


def _webp_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (12, 8), "teal").save(buffer, format="WEBP")
    return buffer.getvalue()


def test_asset_key_is_scoped_to_a_modern_arxiv_identity():
    assert (
        paper_markdown_service.paper_asset_bucket_key(
            "2607.24653v2", "0123456789abcdef.webp"
        )
        == "2607/2607.24653/images/0123456789abcdef.webp"
    )


def test_external_asset_key_is_scoped_to_the_catalog_paper_id():
    assert (
        paper_markdown_service.paper_asset_bucket_key(
            "109743", "0123456789abcdef.webp", source="external"
        )
        == "external/109743/images/0123456789abcdef.webp"
    )


def test_asset_reader_is_bounded_and_validates_image(monkeypatch):
    data = _webp_bytes()
    reads: list[int] = []

    class TrackedFile(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            return super().read(size)

    class FakeFileSystem:
        def __init__(self, *, token):
            assert token == "private-token"

        def open(self, path, mode, *, block_size):
            assert (
                path == "hf://buckets/owner/content/2607/2607.24653/images/"
                "0123456789abcdef.webp"
            )
            assert mode == "rb"
            assert block_size == 0
            return TrackedFile(data)

    monkeypatch.setattr(paper_markdown_service, "HfFileSystem", FakeFileSystem)
    actual, media_type = paper_markdown_service.read_paper_asset(
        "2607.24653",
        "0123456789abcdef.webp",
        bucket_id="owner/content",
        token="private-token",
        max_bytes=len(data),
        max_pixels=1_000,
    )

    assert reads == [len(data) + 1]
    assert actual == data
    assert media_type == "image/webp"


def test_public_asset_route_is_immutable_and_anonymous(monkeypatch):
    data = _webp_bytes()
    monkeypatch.setattr(
        paper_assets,
        "read_paper_asset",
        lambda *_args, **_kwargs: (data, "image/webp"),
    )

    with TestClient(create_app()) as client:
        response = client.get("/paper-assets/2607/2607.24653/0123456789abcdef.webp")

    assert response.status_code == 200
    assert response.content == data
    assert response.headers["content-type"] == "image/webp"
    assert "immutable" in response.headers["cache-control"]


def test_public_external_asset_route_uses_external_identity(monkeypatch):
    data = _webp_bytes()
    seen = {}

    def fake_read(paper_id, filename, **kwargs):
        seen.update(paper_id=paper_id, filename=filename, **kwargs)
        return data, "image/webp"

    monkeypatch.setattr(paper_assets, "read_paper_asset", fake_read)

    with TestClient(create_app()) as client:
        response = client.get("/paper-assets/external/109743/0123456789abcdef.webp")

    assert response.status_code == 200
    assert seen["paper_id"] == "109743"
    assert seen["source"] == "external"


def test_public_external_pdf_route_streams_the_archived_private_object(monkeypatch):
    pdf = b"%PDF-1.7\nexternal report"
    reads: list[int] = []

    class TrackedFile(io.BytesIO):
        def read(self, size=-1):
            reads.append(size)
            return super().read(size)

    class FakeFileSystem:
        def __init__(self, *, token):
            assert token == "private-token"

        def info(self, path):
            assert path == (
                "hf://buckets/huggingface/pwc-papers-content/external/109743/paper.pdf"
            )
            return {"size": len(pdf)}

        def open(self, path, mode, *, block_size):
            assert path.endswith("/external/109743/paper.pdf")
            assert mode == "rb"
            assert block_size == 0
            return TrackedFile(pdf)

    monkeypatch.setattr(paper_markdown_service, "HfFileSystem", FakeFileSystem)
    monkeypatch.setattr(
        paper_assets,
        "get_settings",
        lambda: SimpleNamespace(
            paper_markdown_hf_bucket_id="huggingface/pwc-papers-content",
            hf_token="private-token",
        ),
    )

    with TestClient(create_app()) as client:
        response = client.get("/paper-assets/external/109743/paper.pdf")

    assert response.status_code == 200
    assert response.content == pdf
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-length"] == str(len(pdf))
    assert reads[0] == 5
    assert all(size != -1 for size in reads)
