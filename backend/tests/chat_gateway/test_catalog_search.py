"""Gateway catalog search never spends the shared query-embedding endpoint."""

from __future__ import annotations

from backend.config import Settings
from backend.services.chat_gateway_service import ChatGatewayService


def test_chat_search_never_calls_shared_query_embedding_endpoint(monkeypatch):
    calls = []

    class PaperService:
        def __init__(self, _db):
            pass

        def search_papers_page(self, query, page, limit, *, mode):
            calls.append((query, page, limit, mode))
            return {"results": []}

    from backend.services import chat_gateway_service

    monkeypatch.setattr(chat_gateway_service, "PaperService", PaperService)
    result = ChatGatewayService(object(), Settings(_env_file=None)).catalog(
        "search",
        {"query": "vision transformers", "mode": "hybrid", "limit": 5},
    )

    assert result == {"results": []}
    assert calls == [("vision transformers", 1, 5, "keyword")]
