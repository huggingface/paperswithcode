from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from backend.config import Settings
from backend.routers import paper_reader
from backend.services import paper_layout_service
from backend.services.paper_layout_service import (
    PaperLayoutNotFoundError,
    citable_markdown,
    read_paper_layout,
)


def test_citable_markdown_rewrites_layout_comments():
    markdown = "<!-- pwc:page 2 -->\n\n<!-- pwc:p2b1 -->\n# Method\n\n<!-- pwc:p2b4 -->\nText.\n"

    assert citable_markdown(markdown) == "[page 2]\n\n{p2b1} # Method\n\n{p2b4} Text.\n"


class _FakeFileSystem:
    objects: dict[str, bytes] = {}

    def __init__(self, token=None):
        self.token = token

    def open(self, path, mode, block_size=0):
        import io

        if path not in self.objects:
            raise FileNotFoundError(path)
        return io.BytesIO(self.objects[path])


def test_read_paper_layout_slims_blocks_and_caches(monkeypatch):
    sidecar = {
        "page_count": 12,
        "processed_pages": 12,
        "blocks": {
            "p1b2": {
                "page": 1,
                "label": "Text",
                "bbox": [10, 20, 30, 40],
                "section": None,
                "text": "x" * 1000,
            }
        },
    }
    _FakeFileSystem.objects = {
        "hf://buckets/owner/pages/2610/2610.20533.blocks.json": json.dumps(
            sidecar
        ).encode()
    }
    monkeypatch.setattr(paper_layout_service, "HfFileSystem", _FakeFileSystem)
    paper_layout_service._cache.clear()

    layout = read_paper_layout(
        "2610.20533", source="arxiv", bucket_id="owner/pages", token=None
    )

    block = layout["blocks"]["p1b2"]
    assert layout["page_count"] == 12
    assert block["bbox"] == [10, 20, 30, 40]
    assert len(block["text"]) == paper_layout_service.PREVIEW_CHARS
    _FakeFileSystem.objects = {}
    assert (
        read_paper_layout(
            "2610.20533", source="arxiv", bucket_id="owner/pages", token=None
        )
        is layout
    )
    with pytest.raises(PaperLayoutNotFoundError):
        read_paper_layout("123", source="external", bucket_id="owner/pages", token=None)
    paper_layout_service._cache.clear()


def test_layout_endpoint_is_gated_and_reports_missing_layouts(monkeypatch):
    with pytest.raises(HTTPException) as disabled:
        paper_reader.get_paper_layout("2610.20533", Settings())
    assert disabled.value.status_code == 404

    calls = []

    def read(route_id, **kwargs):
        calls.append((route_id, kwargs["source"]))
        if route_id == "123":
            raise PaperLayoutNotFoundError(route_id)
        return {"page_count": 1, "processed_pages": 1, "blocks": {}}

    monkeypatch.setattr(paper_reader, "read_paper_layout", read)
    enabled = Settings(paper_reader_citations_enabled=True)

    response = paper_reader.get_paper_layout("2610.20533", enabled)
    assert json.loads(response.body)["page_count"] == 1
    with pytest.raises(HTTPException) as missing:
        paper_reader.get_paper_layout("123", enabled)
    assert missing.value.status_code == 404
    assert calls == [("2610.20533", "arxiv"), ("123", "external")]
