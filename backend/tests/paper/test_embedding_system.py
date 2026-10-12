"""Fast unit coverage for embedding contracts, fusion, inference fallback, and CLI plans."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import numpy as np
import pytest

from backend.cli import build_parser
from backend.scripts.benchmark_paper_search import metrics as search_metrics
from backend.scripts.evaluate_embedding_bakeoff import evaluate_related
from backend.scripts.build_embedding_bakeoff_run import exact_neighbors
from backend.services.embedding_contracts import (
    EmbeddingRunManifest,
    ShardManifest,
    build_embedding_input,
    content_hash,
    sha256_file,
)
from backend.services.embedding_retrieval_service import (
    ActiveGeneration,
    EmbeddingRetrievalService,
    RankedCandidate,
    reciprocal_rank_fusion,
)
from backend.services.paper_embedding_pipeline import (
    activate_generation,
    bucket_retention_plan,
)
from backend.services.paper_service import PaperService
from backend.services.query_embedding_client import (
    QueryEmbeddingClient,
    QueryEmbeddingContract,
    QueryEmbeddingUnavailable,
)


def test_embedding_input_and_hash_are_deterministic():
    assert build_embedding_input("  A   Title ", " Line 1\n Line 2 ") == (
        "A Title\n\nLine 1 Line 2"
    )
    assert build_embedding_input("Title", None) == "Title"
    assert content_hash(" A Title", "Abstract ") == content_hash(
        "A   Title", " Abstract"
    )
    assert content_hash("A Title", "Abstract") != content_hash("a title", "Abstract")


def test_manifest_round_trip_and_checksums(tmp_path: Path):
    shard = tmp_path / "papers.jsonl"
    shard.write_text('{"paper_id":1}\n', encoding="utf-8")
    manifest = EmbeddingRunManifest.create(
        run_id="test-run",
        model_name="test/model",
        model_revision="abc123",
        dimensions=32,
        corpus_snapshot="1:2:",
        row_count=1,
        shards=[ShardManifest(shard.name, 1, sha256_file(shard))],
    )
    path = tmp_path / "manifest.json"
    manifest.write(path)
    loaded = EmbeddingRunManifest.read(path)
    loaded.validate_files(tmp_path)
    assert loaded == manifest


def test_rrf_uses_ranks_and_retains_component_diagnostics():
    fused = reciprocal_rank_fusion(
        [
            ([RankedCandidate(1, 1), RankedCandidate(2, 2)], 1.0),
            ([RankedCandidate(2, 1), RankedCandidate(3, 2)], 1.0),
        ]
    )
    assert [item[0] for item in fused] == [2, 1, 3]
    assert fused[0][2] == {"lexical": 2, "semantic": 1}


def test_stale_source_vector_orders_arxiv_versions_numerically():
    statements = []

    class EmptyResult:
        def mappings(self):
            return self

        def one_or_none(self):
            return None

    class FakeDatabase:
        def execute(self, statement, _params):
            statements.append(str(statement))
            return EmptyResult()

    source = type("PaperStub", (), {"id": 1, "arxiv_id": "2601.00001"})()
    generation = ActiveGeneration(
        1, "model", "revision", 32, "input", "query", "dense-v1"
    )

    candidates, stale = EmbeddingRetrievalService(FakeDatabase()).related_dense(
        source, generation
    )

    assert candidates == []
    assert stale is False
    assert (
        "CAST(SUBSTRING(p.version FROM 2) AS integer) DESC NULLS LAST" in statements[0]
    )
    assert "p.version DESC" not in statements[0]


def test_activation_locks_paper_corpus_until_generation_flip():
    statements = []

    class Result:
        def __init__(self, rows=()):
            self.rows = rows

        def scalar_one_or_none(self):
            return "ready"

        def yield_per(self, _size):
            return iter(self.rows)

    class FakeDatabase:
        committed = False

        def execute(self, statement, _params=None):
            sql = str(statement)
            statements.append(sql)
            return Result()

        def commit(self):
            self.committed = True

    db = FakeDatabase()
    activate_generation(db, 7)

    lock_index = statements.index("LOCK TABLE papers IN SHARE MODE")
    coverage_index = next(
        index
        for index, sql in enumerate(statements)
        if "LEFT JOIN paper_embeddings" in sql
    )
    activation_index = next(
        index for index, sql in enumerate(statements) if "SET status='active'" in sql
    )
    assert lock_index < coverage_index < activation_index
    assert db.committed is True


def test_search_metrics_enforce_expected_top_result():
    cases = [
        {
            "query": "ExampleNet",
            "expected_top": "1234.56789",
            "required": [{"arxiv_id": "1234.56789", "max_rank": 1}],
            "relevant": [{"arxiv_id": "1234.56789", "grade": 2}],
        },
        {
            "query": "AnotherNet",
            "expected_top": "9876.54321",
            "relevant": [{"arxiv_id": "9876.54321", "grade": 2}],
        },
    ]
    report = search_metrics(cases, [["1234.56789"], ["0000.00000"]])
    assert report["expected_top1_accuracy"] == 0.5
    assert report["expected_top1_passed"] == 1
    assert report["expected_top1_total"] == 2
    assert report["required_rank_accuracy"] == 1.0
    assert report["required_rank_passed"] == 1
    assert report["required_rank_total"] == 1


@pytest.mark.parametrize(
    ("mode", "method_name"),
    [
        ("keyword", "_search_papers_fts"),
        ("semantic", "_search_papers_semantic"),
        ("hybrid", "_search_papers_hybrid"),
    ],
)
def test_search_mode_dispatch_is_explicit(monkeypatch, mode, method_name):
    service = PaperService(None)._retrieval_service()
    called = []
    for name in (
        "_search_papers_fts",
        "_search_papers_semantic",
        "_search_papers_hybrid",
    ):
        monkeypatch.setattr(
            service,
            name,
            lambda query, limit, selected=name, **_kwargs: (
                called.append((selected, query, limit)) or []
            ),
        )

    assert service.search_papers("retrieval query", 7, mode=mode) == []
    assert called == [(method_name, "retrieval query", 20)]


def test_unknown_search_mode_is_rejected():
    with pytest.raises(Exception, match="Unsupported paper search mode"):
        PaperService(None)._retrieval_service().search_papers("query", mode="unknown")


@pytest.mark.parametrize(
    "method_name", ["_search_papers_semantic", "_search_papers_hybrid"]
)
def test_online_search_modes_fall_back_to_keyword(monkeypatch, method_name):
    service = PaperService(None)._retrieval_service()
    expected = [type("PaperStub", (), {"id": 1})()]

    def unavailable(_query, _limit, **_kwargs):
        raise QueryEmbeddingUnavailable("endpoint unavailable")

    monkeypatch.setattr(service, "_semantic_candidates", unavailable)
    monkeypatch.setattr(
        service,
        "_search_papers_fts",
        lambda query, limit, **_kwargs: expected,
    )
    assert getattr(service, method_name)("retrieval query", 5) == expected


def test_related_bakeoff_metrics_use_graded_judgments():
    judgments = {
        "judgments": [
            {"source_paper_id": 1, "related_paper_id": 2, "grade": 2},
            {"source_paper_id": 1, "related_paper_id": 3, "grade": 1},
        ]
    }
    metrics = evaluate_related(
        judgments,
        [{"source_paper_id": 1, "ranked_paper_ids": [2, 3, 4, 5]}],
    )
    assert metrics["ndcg_at_4"] == 1.0
    assert metrics["recall_at_20"] == 1.0


def test_exact_bakeoff_neighbors_exclude_source_and_preserve_rank():
    ids = np.asarray([10, 20, 30])
    vectors = np.asarray([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]], dtype=np.float32)
    result = exact_neighbors(ids, vectors, [10], 2)
    assert result[0]["ranked_paper_ids"] == [20, 30]


def test_query_client_validates_caches_and_does_not_log_query(caplog):
    calls = 0

    def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        assert json.loads(request.content)["dimensions"] == 2
        return httpx.Response(200, json=[[1.0, 0.0]])

    client = QueryEmbeddingClient(
        endpoint_url="https://endpoint.example",
        token="secret",
        transport=httpx.MockTransport(handler),
    )
    contract = QueryEmbeddingContract(7, "model", "rev", 2, "query-v1")
    query = "private raw query"
    assert client.encode(query, contract) == [1.0, 0.0]
    assert client.encode(query, contract) == [1.0, 0.0]
    assert calls == 1
    assert query not in caplog.text


def test_query_client_opens_circuit_after_malformed_responses():
    calls = 0

    def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=[[0.5]])

    client = QueryEmbeddingClient(
        endpoint_url="https://endpoint.example",
        token="secret",
        failure_threshold=2,
        transport=httpx.MockTransport(handler),
    )
    contract = QueryEmbeddingContract(7, "model", "rev", 2, "query-v1")
    with pytest.raises(QueryEmbeddingUnavailable):
        client.encode("q1", contract)
    with pytest.raises(QueryEmbeddingUnavailable):
        client.encode("q2", contract)
    with pytest.raises(QueryEmbeddingUnavailable, match="circuit_open"):
        client.encode("q3", contract)
    assert calls == 2


def test_query_client_timeout_then_recovers_after_circuit_window():
    calls = 0

    def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("cold start", request=request)
        return httpx.Response(200, json=[[1.0, 0.0]])

    client = QueryEmbeddingClient(
        endpoint_url="https://endpoint.example",
        token="secret",
        failure_threshold=1,
        recovery_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    contract = QueryEmbeddingContract(7, "model", "rev", 2, "query-v1")
    with pytest.raises(QueryEmbeddingUnavailable):
        client.encode("cold", contract)
    assert client.encode("warm", contract) == [1.0, 0.0]


def test_job_and_endpoint_cli_default_to_dry_run(capsys):
    parser = build_parser()
    job = parser.parse_args(
        [
            "embeddings",
            "run",
            "--input",
            "/bucket/input",
            "--output",
            "/bucket/output",
            "--volume",
            "hf://buckets/me/bucket:/bucket",
            "--model",
            "test/model",
            "--revision",
            "abc",
            "--dimensions",
            "32",
            "--reuse-snapshot",
        ]
    )
    assert job.handler(job) == 0
    job_plan = json.loads(capsys.readouterr().out)
    assert job_plan["dry_run"] is True
    assert "--reuse-snapshot" in job_plan["command"]

    endpoint = parser.parse_args(
        [
            "embeddings",
            "endpoint-plan",
            "--name",
            "pwc-query",
            "--namespace",
            "me",
            "--model",
            "test/model",
            "--revision",
            "abc",
        ]
    )
    assert endpoint.handler(endpoint) == 0
    commands = json.loads(capsys.readouterr().out)["commands"]
    assert commands[0][1:4] == ["endpoints", "catalog", "deploy"]
    assert commands[1][1:3] == ["endpoints", "update"]
    assert commands[1][commands[1].index("--revision") + 1] == "abc"
    assert commands[1][commands[1].index("--min-replica") + 1] == "0"


def test_retention_protects_active_previous_and_pinned():
    runs = [
        {
            "prefix": "old-failed",
            "created_at": "2026-01-01T00:00:00+00:00",
            "status": "failed",
        },
        {
            "prefix": "active",
            "created_at": "2026-01-01T00:00:00+00:00",
            "status": "complete",
            "active": True,
        },
        {
            "prefix": "old-success",
            "created_at": "2026-01-01T00:00:00+00:00",
            "status": "complete",
        },
    ]
    plan = bucket_retention_plan(runs)
    assert {item["prefix"] for item in plan} == {"old-failed", "old-success"}
