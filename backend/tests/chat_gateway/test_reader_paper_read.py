import asyncio
from types import SimpleNamespace

import pytest

import backend.services.chat_reader_paper_read as reader_read
from backend.services.chat_reader_paper_read import (
    CHUNK_BYTES,
    ReaderPaperCursorError,
    read_reader_paper,
)
from backend.services.paper_layout_service import PaperLayoutNotFoundError

CONTEXT = {
    "route_id": "131293",
    "paper_id": "131293",
    "arxiv_id": None,
    "source": "external",
    "content_origin": "layout_markdown",
}
SETTINGS = SimpleNamespace(paper_layout_hf_bucket_id="org/pages", hf_token="")


class FakeDb:
    def __init__(self, context):
        self.context = context

    def scalar(self, _statement):
        return self.context


def layout_markdown(blocks: int) -> str:
    return "<!-- pwc:page 1 -->\n\n" + "".join(
        f"<!-- pwc:p1b{i} -->\nBlock {i} text é {'x' * 400}\n\n" for i in range(blocks)
    )


@pytest.fixture
def layout(monkeypatch):
    state = {"markdown": layout_markdown(3), "pages": (1, 1), "reads": []}

    def read_markdown(markdown_id, **kwargs):
        state["reads"].append((markdown_id, kwargs["source"], kwargs["bucket_id"]))
        return state["markdown"], False

    def read_layout(markdown_id, **kwargs):
        processed, total = state["pages"]
        return {"page_count": total, "processed_pages": processed, "blocks": {}}

    monkeypatch.setattr(reader_read, "read_paged_markdown_bounded", read_markdown)
    monkeypatch.setattr(reader_read, "read_paper_layout", read_layout)
    return state


def test_primary_reader_paper_reads_the_tagged_text(layout):
    result = read_reader_paper(FakeDb(CONTEXT), SETTINGS, "turn", {"paper": "131293"})

    page = result["structuredContent"]
    assert page["markdown"].startswith("[page 1]\n\n{p1b0} Block 0")
    assert "<!--" not in page["markdown"]
    assert page["truncated"] is False and page["next_cursor"] is None
    assert layout["reads"] == [("131293", "external", "org/pages")]


def test_offset_counts_the_tagged_bytes_and_cursor_continues(layout):
    layout["markdown"] = layout_markdown(400)
    tagged = reader_read.citable_markdown(layout["markdown"]).encode()
    offset = 1001

    first = read_reader_paper(
        FakeDb(CONTEXT), SETTINGS, "turn", {"paper": "131293", "offset": offset}
    )["structuredContent"]
    assert first["truncated"] is True
    assert len(first["markdown"].encode()) <= CHUNK_BYTES
    # Chunk boundaries never split a UTF-8 character.
    assert tagged.startswith(first["markdown"].encode(), offset)

    pieces = [first["markdown"]]
    cursor = first["next_cursor"]
    while cursor:
        page = read_reader_paper(
            FakeDb(CONTEXT), SETTINGS, "turn", {"paper": "131293", "cursor": cursor}
        )["structuredContent"]
        pieces.append(page["markdown"])
        cursor = page["next_cursor"]
    assert "".join(pieces).encode() == tagged[offset:]


def test_page_capped_layout_hands_off_to_untagged_markdown(layout):
    layout["pages"] = (30, 37)

    page = read_reader_paper(FakeDb(CONTEXT), SETTINGS, "turn", {"paper": "131293"})[
        "structuredContent"
    ]

    assert "ends after page 30 of 37" in page["markdown"]
    assert page["next_cursor"].startswith(reader_read.UNTAGGED_CURSOR_PREFIX)


def test_stale_layout_cursor_is_rejected(layout):
    with pytest.raises(ReaderPaperCursorError):
        read_reader_paper(
            FakeDb(CONTEXT),
            SETTINGS,
            "turn",
            {"paper": "131293", "cursor": "layout:0000000000000000:10"},
        )


@pytest.mark.parametrize(
    "context,arguments",
    [
        (None, {"paper": "131293"}),
        ({**CONTEXT, "content_origin": "pdf_text"}, {"paper": "131293"}),
        (CONTEXT, {"paper": "2508.11919"}),
        (CONTEXT, {"paper": "131293", "cursor": "mcp-opaque-token"}),
    ],
)
def test_other_reads_use_the_hosted_mcp(layout, context, arguments):
    assert read_reader_paper(FakeDb(context), SETTINGS, "turn", arguments) is None
    assert layout["reads"] == []


def test_missing_layout_falls_back_to_the_hosted_mcp(monkeypatch):
    def missing(*args, **kwargs):
        raise PaperLayoutNotFoundError("missing")

    monkeypatch.setattr(reader_read, "read_paged_markdown_bounded", missing)
    assert (
        read_reader_paper(FakeDb(CONTEXT), SETTINGS, "turn", {"paper": "131293"})
        is None
    )


def test_arxiv_reader_paper_is_addressed_by_arxiv_id(layout):
    context = {**CONTEXT, "paper_id": "7", "route_id": "2508.11919"}
    context.update(arxiv_id="2508.11919", source="arxiv")

    assert read_reader_paper(FakeDb(context), SETTINGS, "turn", {"paper": "7"})
    assert layout["reads"] == [("2508.11919", "arxiv", "org/pages")]


def gateway_request(calls):
    import backend.chat_gateway_app as gateway

    async def call(client, method, params, endpoint, identity):
        calls.append(params)
        return {"structuredContent": {"markdown": "untagged"}}

    async def disconnected():
        await asyncio.sleep(1)
        return False

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(pwc_mcp_client=None)),
        headers={"x-pwc-turn": "turn-1", "x-pwc-session": "session-1"},
        is_disconnected=disconnected,
    )
    return gateway, call, request


def test_gateway_answers_reader_reads_without_the_hosted_mcp(monkeypatch):
    calls, seen = [], []
    gateway, call, request = gateway_request(calls)
    monkeypatch.setattr(gateway, "request_mcp", call)

    def reader(db, settings, turn_id, arguments):
        seen.append((turn_id, arguments))
        return {"structuredContent": {"markdown": "{p1b1} tagged"}}

    monkeypatch.setattr(gateway, "read_reader_paper", reader)
    result = asyncio.run(
        gateway.catalog_mcp(
            gateway.McpCatalogRequest(tool="read_paper", arguments={"paper": "1"}),
            request,
            db=None,
            settings=None,
        )
    )

    assert result == {"result": {"structuredContent": {"markdown": "{p1b1} tagged"}}}
    assert seen == [("turn-1", {"paper": "1"})] and calls == []


def test_gateway_untagged_cursor_restarts_the_hosted_read(monkeypatch):
    calls = []
    gateway, call, request = gateway_request(calls)
    monkeypatch.setattr(gateway, "request_mcp", call)
    monkeypatch.setattr(
        gateway, "read_reader_paper", lambda *args: pytest.fail("not a layout read")
    )
    arguments = {"paper": "1", "cursor": "layout-untagged:abc"}

    asyncio.run(
        gateway.catalog_mcp(
            gateway.McpCatalogRequest(tool="read_paper", arguments=arguments),
            request,
            db=None,
            settings=None,
        )
    )

    assert calls == [{"name": "read_paper", "arguments": {"paper": "1"}}]


def test_gateway_reports_a_stale_layout_cursor(monkeypatch):
    from fastapi import HTTPException

    gateway, call, request = gateway_request([])

    def stale(*args):
        raise ReaderPaperCursorError("Paper text changed")

    monkeypatch.setattr(gateway, "read_reader_paper", stale)
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            gateway.catalog_mcp(
                gateway.McpCatalogRequest(
                    tool="read_paper", arguments={"paper": "1", "cursor": "layout:x:1"}
                ),
                request,
                db=None,
                settings=None,
            )
        )
    assert error.value.status_code == 409


def test_unreadable_sidecar_still_returns_the_tagged_text(layout, monkeypatch):
    def unreadable(*args, **kwargs):
        raise OSError("bucket unavailable")

    monkeypatch.setattr(reader_read, "read_paper_layout", unreadable)
    page = read_reader_paper(FakeDb(CONTEXT), SETTINGS, "turn", {"paper": "131293"})[
        "structuredContent"
    ]

    assert page["markdown"].startswith("[page 1]") and page["next_cursor"] is None


def test_truncated_context_prefix_continues_byte_exactly_at_any_cut():
    from backend.services.paper_layout_service import (
        citable_markdown,
        drop_partial_marker,
    )

    raw = layout_markdown(3)
    full = citable_markdown(raw).encode()
    for cut in range(len(raw)):
        prefix = citable_markdown(drop_partial_marker(raw[:cut])).encode()
        assert full.startswith(prefix), cut
