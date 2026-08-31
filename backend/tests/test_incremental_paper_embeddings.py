"""Tests for bounded active-generation embedding refreshes."""

from __future__ import annotations

import json

import httpx
import pytest

from backend.services.embedding_contracts import content_hash
from backend.services.incremental_paper_embeddings import (
    ActiveEmbeddingGeneration,
    EmbeddingCandidate,
    embedding_backlog_counts,
    encode_documents,
    find_refresh_candidates,
    upsert_current_embeddings,
)


def test_refresh_candidates_compare_hash_even_without_timestamp_hint():
    class Result:
        def __init__(self, rows):
            self.rows = rows

        def mappings(self):
            return self

        def all(self):
            return list(self.rows)

        def yield_per(self, _size):
            return iter(self.rows)

        def close(self):
            pass

    class FakeDatabase:
        execution_options = []

        def execute(self, statement, _params=None):
            if "e.paper_id IS NULL" in str(statement):
                return Result([])
            self.execution_options.append(statement.get_execution_options())
            return Result(
                [
                    {
                        "id": 7,
                        "title": "Stale",
                        "abstract": "Body",
                        "content_hash": "bad",
                    },
                    {
                        "id": 8,
                        "title": "Current",
                        "abstract": "Body",
                        "content_hash": content_hash("Current", "Body"),
                    },
                ]
            )

    database = FakeDatabase()
    candidates = find_refresh_candidates(database, generation_id=1, limit=10)

    assert [candidate.paper_id for candidate in candidates] == [7]
    assert database.execution_options[0]["stream_results"] is True


def test_embedding_backlog_counts_missing_and_hash_mismatches():
    class Result:
        def mappings(self):
            return self

        def yield_per(self, _size):
            return iter(
                [
                    {"title": "Missing", "abstract": None, "content_hash": None},
                    {"title": "Stale", "abstract": "Body", "content_hash": "bad"},
                    {
                        "title": "Current",
                        "abstract": "Body",
                        "content_hash": content_hash("Current", "Body"),
                    },
                ]
            )

    class FakeDatabase:
        def execute(self, _statement, _params=None):
            return Result()

    assert embedding_backlog_counts(FakeDatabase(), generation_id=7) == (1, 1)


def test_encode_documents_uses_document_contract():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret"
        payload = json.loads(request.content)
        assert payload == {
            "inputs": ["Title\n\nAbstract"],
            "dimensions": 2,
            "normalize": True,
            "prompt_name": "document",
        }
        return httpx.Response(200, json=[[1.0, 0.0]])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        vectors = encode_documents(
            client,
            endpoint_url="https://endpoint.example",
            token="secret",
            texts=["Title\n\nAbstract"],
            dimensions=2,
        )
    assert vectors == [[1.0, 0.0]]


def test_encode_documents_retries_cold_endpoint(monkeypatch):
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=[[1.0, 0.0]])

    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        vectors = encode_documents(
            client,
            endpoint_url="https://endpoint.example",
            token="secret",
            texts=["paper"],
            dimensions=2,
        )
    assert vectors == [[1.0, 0.0]]
    assert calls == 2


@pytest.mark.parametrize(
    "payload",
    [
        [[1.0]],
        [[0.5, 0.0]],
        [[float("nan"), 0.0]],
    ],
)
def test_encode_documents_rejects_invalid_vectors(payload):
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(ValueError):
            encode_documents(
                client,
                endpoint_url="https://endpoint.example",
                token="secret",
                texts=["paper"],
                dimensions=2,
            )


def test_upsert_discards_source_that_changed_during_inference():
    statements = []

    class Result:
        def mappings(self):
            return self

        def __iter__(self):
            return iter([{"id": 7, "title": "Changed", "abstract": "New abstract"}])

    class FakeDatabase:
        committed = False

        def execute(self, statement, _params=None):
            statements.append(str(statement))
            return Result()

        def commit(self):
            self.committed = True

    candidate = EmbeddingCandidate(
        paper_id=7,
        title="Original",
        abstract="Old abstract",
        content_hash="0" * 64,
    )
    embedded, stale = upsert_current_embeddings(
        FakeDatabase(),
        generation=ActiveEmbeddingGeneration(1, "model", "rev", 2, "input"),
        candidates=[candidate],
        vectors=[[1.0, 0.0]],
    )
    assert (embedded, stale) == (0, 1)
    assert len(statements) == 1
