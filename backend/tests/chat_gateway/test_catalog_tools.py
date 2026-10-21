"""Chat gateway output budgets and catalog tool contracts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.chat_execution_policy import (
    MAX_POSTER_PROVIDER_REQUESTS,
    MAX_PROVIDER_REQUESTS,
    MAX_PROVIDER_TURN_TOKENS,
)
from backend.chat_gateway_app import (
    CatalogRequest,
    PaperCommandRequest,
    catalog,
    paper_command,
)
from backend.services.chat_provider_gateway.lifecycle import (
    MAX_POSTER_PROVIDER_TURN_TOKENS,
    MAX_PROVIDER_OUTPUT_TOKENS,
)
from backend.services.chat_provider_gateway.lifecycle import (
    output_tokens_allowed as _output_tokens_allowed,
)
from backend.services.chat_provider_gateway.lifecycle import (
    provider_turn_limits as _provider_turn_limits,
)
from backend.models.database import ChatSession
from backend.services.chat_capability_service import (
    ChatCapabilityService,
)
from backend.services.chat_gateway_service import ChatGatewayService
from backend.services.catalog_errors import CatalogNotFoundError
from backend.utils.exceptions import PaperNotFoundError


def test_gateway_accepts_configured_output_token_limit_and_rejects_larger():
    assert MAX_PROVIDER_OUTPUT_TOKENS == 8_000
    assert MAX_PROVIDER_TURN_TOKENS >= 8 * MAX_PROVIDER_OUTPUT_TOKENS
    assert _output_tokens_allowed(8_000)
    assert not _output_tokens_allowed(8_001)


def test_gateway_expands_model_budget_only_after_artifact_or_paper_grant():
    ordinary = SimpleNamespace(scopes=["model", "catalog"])
    artifact = SimpleNamespace(scopes=["model", "catalog", "artifact"])
    paper_available = SimpleNamespace(scopes=["model", "catalog", "paper"])
    paper_granted = SimpleNamespace(scopes=["model", "catalog", "paper", "paper_grant"])

    assert _provider_turn_limits(ordinary) == (
        MAX_PROVIDER_REQUESTS,
        MAX_PROVIDER_TURN_TOKENS,
    )
    assert _provider_turn_limits(artifact) == (
        MAX_POSTER_PROVIDER_REQUESTS,
        MAX_POSTER_PROVIDER_TURN_TOKENS,
    )
    assert _provider_turn_limits(paper_available) == _provider_turn_limits(ordinary)
    assert _provider_turn_limits(paper_granted) == _provider_turn_limits(artifact)
    assert MAX_POSTER_PROVIDER_REQUESTS >= 20 + 2
    assert MAX_POSTER_PROVIDER_TURN_TOKENS > MAX_PROVIDER_TURN_TOKENS


def test_gateway_catalog_returns_not_found_for_unknown_task(monkeypatch):
    class DB:
        def commit(self):
            pass

    monkeypatch.setattr(
        "backend.chat_gateway_app._scope",
        lambda *_args, **_kwargs: SimpleNamespace(scopes=["catalog"]),
    )
    monkeypatch.setattr(
        ChatCapabilityService, "meter_catalog", lambda *_args, **_kwargs: None
    )

    def missing_task(*_args, **_kwargs):
        raise PaperNotFoundError(
            "Task with ID, slug, or name 'speech recognition' not found"
        )

    monkeypatch.setattr(ChatGatewayService, "catalog", missing_task)

    with pytest.raises(HTTPException) as exc_info:
        catalog(
            CatalogRequest(
                operation="benchmark_trending",
                arguments={"task": "speech recognition"},
            ),
            authorization="Bearer test",
            x_pwc_session=str(uuid.uuid4()),
            x_pwc_turn=str(uuid.uuid4()),
            turn_fence=None,
            db=DB(),
            settings=SimpleNamespace(chat_max_direct_search_calls=4),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == (
        "Task with ID, slug, or name 'speech recognition' not found"
    )


def test_gateway_catalog_maps_typed_not_found_errors(monkeypatch):
    class DB:
        def commit(self):
            pass

    monkeypatch.setattr(
        "backend.chat_gateway_app._scope",
        lambda *_args, **_kwargs: SimpleNamespace(scopes=["catalog"]),
    )
    monkeypatch.setattr(
        ChatCapabilityService, "meter_catalog", lambda *_args, **_kwargs: None
    )

    def missing_catalog_entity(*_args, **_kwargs):
        raise CatalogNotFoundError("Method 'missing' not found")

    monkeypatch.setattr(ChatGatewayService, "catalog", missing_catalog_entity)

    with pytest.raises(HTTPException) as exc_info:
        catalog(
            CatalogRequest(operation="method_detail", arguments={"method": "missing"}),
            authorization="Bearer test",
            x_pwc_session=str(uuid.uuid4()),
            x_pwc_turn=str(uuid.uuid4()),
            turn_fence=None,
            db=DB(),
            settings=SimpleNamespace(chat_max_direct_search_calls=4),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Method 'missing' not found"


@pytest.mark.parametrize("operation", ["draft", "repair"])
def test_gateway_paper_mutation_rejects_same_owner_artifact_from_another_chat(
    monkeypatch, operation: str
):
    session_id = uuid.uuid4()
    other_artifact_id = uuid.uuid4()
    current_artifact_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    parent_id = uuid.uuid4()
    calls: list[dict] = []

    class Descriptor:
        def __init__(self, artifact_id: uuid.UUID):
            self.artifact_id = artifact_id

        def model_dump(self, **_kwargs):
            return {"artifact_id": str(self.artifact_id)}

    class DB:
        def get(self, model, identifier):
            assert model is ChatSession
            assert identifier == session_id
            return SimpleNamespace(
                active_turn_id=turn_id,
                primary_paper_id=None,
                selected_model="gpt-5.6-luna@openai",
            )

        def rollback(self):
            pass

        def commit(self):
            pass

    def unexpected_mutation(**kwargs):
        calls.append(kwargs)
        if operation == "draft":
            return Descriptor(other_artifact_id)
        return SimpleNamespace(
            descriptor=Descriptor(other_artifact_id), repaired=False, exhausted=False
        )

    paper_service = SimpleNamespace(
        get_descriptor=lambda owner_id, requested_session_id: (
            Descriptor(current_artifact_id)
            if owner_id == "same-owner" and requested_session_id == session_id
            else None
        ),
        save_ai_version=unexpected_mutation,
        repair_failed_version=unexpected_mutation,
    )
    capability = SimpleNamespace(
        chat_session_id=session_id,
        turn_id=turn_id,
        scopes=["paper"],
        expires_at=datetime.now(UTC),
    )
    monkeypatch.setattr(
        "backend.chat_gateway_app._scope", lambda *_args, **_kwargs: capability
    )
    monkeypatch.setattr(
        "backend.chat_gateway_app._capability_owner",
        lambda *_args, **_kwargs: "same-owner",
    )
    monkeypatch.setattr(
        "backend.chat_gateway_app.LatexPaperService", lambda *_args: paper_service
    )

    with pytest.raises(HTTPException) as exc_info:
        paper_command(
            PaperCommandRequest(
                operation=operation,
                artifact_id=other_artifact_id,
                expected_parent_version_id=parent_id,
            ),
            authorization="Bearer capability",
            x_pwc_session=str(session_id),
            x_pwc_turn=str(turn_id),
            turn_fence=None,
            db=DB(),
            settings=SimpleNamespace(
                chat_artifacts_enabled=True,
                chat_latex_paper_enabled=True,
                chat_latex_compiler_jobs_enabled=True,
                chat_latex_paper_timeout_seconds=600,
            ),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "paper_missing"
    assert calls == []


@pytest.mark.parametrize(
    ("operation", "require_failed"),
    [("edit-context", False), ("repair-context", True)],
)
def test_gateway_paper_context_checks_out_the_current_head(
    monkeypatch, operation: str, require_failed: bool
):
    session_id = uuid.uuid4()
    artifact_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    calls: list[dict] = []
    descriptor = SimpleNamespace(
        artifact_id=artifact_id,
        model_dump=lambda **_kwargs: {"artifact_id": str(artifact_id)},
    )

    class DB:
        def get(self, model, identifier):
            return SimpleNamespace(
                active_turn_id=turn_id,
                primary_paper_id=None,
                selected_model="gpt-5.6-luna@openai",
            )

        def rollback(self):
            pass

        def commit(self):
            pass

    def source_context(**kwargs):
        calls.append(kwargs)
        return descriptor, {"main.tex": b"current"}

    paper_service = SimpleNamespace(
        get_descriptor=lambda *_args: descriptor,
        source_context=source_context,
    )
    monkeypatch.setattr(
        "backend.chat_gateway_app._scope",
        lambda *_args, **_kwargs: SimpleNamespace(
            chat_session_id=session_id,
            turn_id=turn_id,
            scopes=["paper", "paper_grant"],
            expires_at=datetime.now(UTC),
        ),
    )
    monkeypatch.setattr(
        "backend.chat_gateway_app._capability_owner",
        lambda *_args, **_kwargs: "owner",
    )
    monkeypatch.setattr(
        "backend.chat_gateway_app.LatexPaperService", lambda *_args: paper_service
    )

    result = paper_command(
        PaperCommandRequest(operation=operation),
        authorization="Bearer capability",
        x_pwc_session=str(session_id),
        x_pwc_turn=str(turn_id),
        turn_fence=None,
        db=DB(),
        settings=SimpleNamespace(
            chat_artifacts_enabled=True,
            chat_latex_paper_enabled=True,
            chat_latex_compiler_jobs_enabled=True,
            chat_latex_paper_timeout_seconds=600,
        ),
    )

    assert result["files"] == [{"path": "main.tex", "content": "current"}]
    assert calls == [
        {
            "owner_id": "owner",
            "artifact_id": artifact_id,
            "require_failed": require_failed,
        }
    ]


def test_gateway_paper_read_uses_bounded_diskless_reader(monkeypatch):
    calls = []

    def read(paper, **options):
        calls.append((paper, options))
        return "# EoMT", True

    monkeypatch.setattr(
        "backend.services.chat_gateway_service.read_paper_markdown_bounded", read
    )
    settings = SimpleNamespace(
        paper_markdown_hf_bucket_id="papers",
        hf_token="token",
    )

    result = ChatGatewayService(object(), settings).catalog(
        "paper_read", {"paper": "2503.19108"}
    )

    assert result == {"markdown": "# EoMT", "truncated": True}
    assert calls == [
        (
            "2503.19108",
            {"bucket_id": "papers", "token": "token", "max_bytes": 256 * 1024},
        )
    ]


def test_gateway_paper_list_forwards_every_advertised_catalog_filter(monkeypatch):
    calls = []

    class Service:
        def __init__(self, db):
            assert db == "db"

        def get_papers(self, **options):
            calls.append(options)
            return {"count": 0, "results": [], "applied_filters": options}

    monkeypatch.setattr("backend.services.chat_gateway_service.PaperService", Service)

    result = ChatGatewayService("db", SimpleNamespace()).catalog(
        "paper_list",
        {
            "start_date": "2026-08-01",
            "end_date": "2026-08-21",
            "task": "Vision",
            "method": "Transformer",
            "conference": "CVPR 2026",
            "framework": "PyTorch",
            "organization": "Hugging Face",
            "authors": ["Kaiming He", "@yilundu"],
        },
    )

    assert result["count"] == 0
    assert calls[0]["start_date"].isoformat() == "2026-08-01"
    assert calls[0]["end_date"].isoformat() == "2026-08-21"
    assert {
        name: calls[0][name]
        for name in ("task", "method", "conference", "framework", "organization")
    } == {
        "task": "Vision",
        "method": "Transformer",
        "conference": "CVPR 2026",
        "framework": "PyTorch",
        "organization": "Hugging Face",
    }
    assert calls[0]["authors"] == ["Kaiming He", "@yilundu"]


def test_gateway_search_forwards_the_publication_date_range(monkeypatch):
    calls = []

    class Service:
        def __init__(self, db):
            assert db == "db"

        def search_papers_page(self, *args, **options):
            calls.append((args, options))
            return {"results": []}

    monkeypatch.setattr("backend.services.chat_gateway_service.PaperService", Service)

    ChatGatewayService("db", SimpleNamespace()).catalog(
        "search",
        {
            "query": "date filtering",
            "start_date": "2026-08-01",
            "end_date": "2026-08-21",
        },
    )

    assert calls[0][0] == ("date filtering", 1, 10)
    assert calls[0][1]["start_date"].isoformat() == "2026-08-01"
    assert calls[0][1]["end_date"].isoformat() == "2026-08-21"


def test_gateway_exposes_advertised_taxonomy_detail_operations(monkeypatch):
    class Tasks:
        def __init__(self, db):
            assert db == "db"

        def get_task_by_id(self, task):
            return {"kind": "task", "id": task}

        def get_task_by_slug(self, task):
            return {"kind": "task", "slug": task}

        def get_task_page(self, task, *, is_open):
            return {"kind": "task_page", "task": task, "is_open": is_open}

        def get_task_papers(self, task, **options):
            return {"kind": "task_papers", "task": task, "options": options}

    class Methods:
        def __init__(self, db):
            assert db == "db"

        def get_method_by_id(self, method):
            return {"kind": "method", "id": method}

        def get_method_by_name(self, method):
            return {"kind": "method", "name": method}

    class Conferences:
        def __init__(self, db):
            assert db == "db"

        def get_conference(self, conference):
            return {"kind": "conference", "slug": conference}

    class Organizations:
        def __init__(self, db):
            assert db == "db"

        def get_organizations(self, *, featured_only):
            return {"kind": "organizations", "featured_only": featured_only}

        def get_organization(self, organization):
            return {"kind": "organization", "slug": organization}

    class Frameworks:
        def __init__(self, db):
            assert db == "db"

        def get_catalog(self):
            return {"kind": "frameworks"}

    monkeypatch.setattr("backend.services.chat_gateway_service.TaskService", Tasks)
    monkeypatch.setattr("backend.services.chat_gateway_service.MethodService", Methods)
    monkeypatch.setattr(
        "backend.services.chat_gateway_service.ConferenceService", Conferences
    )
    monkeypatch.setattr(
        "backend.services.chat_gateway_service.OrganizationService", Organizations
    )
    monkeypatch.setattr(
        "backend.services.chat_gateway_service.FrameworkService", Frameworks
    )
    gateway = ChatGatewayService("db", SimpleNamespace())

    assert gateway.catalog("task_detail", {"task": "17"})["id"] == "17"
    assert (
        gateway.catalog("task_page", {"task": "vision", "is_open": "true"})["is_open"]
        is True
    )
    assert gateway.catalog("task_papers", {"task": "vision"})["kind"] == "task_papers"
    assert (
        gateway.catalog("method_detail", {"method": "transformer"})["name"]
        == "transformer"
    )
    assert (
        gateway.catalog("conference_detail", {"conference": "cvpr-2026"})["slug"]
        == "cvpr-2026"
    )
    assert (
        gateway.catalog("organization_list", {"featured_only": True})["featured_only"]
        is True
    )
    assert (
        gateway.catalog("organization_detail", {"organization": "hugging-face"})["slug"]
        == "hugging-face"
    )
    assert gateway.catalog("framework_list", {}) == {"kind": "frameworks"}


def test_gateway_paper_info_includes_normalized_hf_artifacts(monkeypatch):
    calls = []

    class Service:
        def __init__(self, db):
            assert db == "db"

        def get_paper_by_id_or_arxiv(self, paper, include_resources):
            calls.append((paper, include_resources))
            return {
                "id": "7",
                "hf_models": ["https://huggingface.co/org/model-a"],
                "hf_datasets": [],
                "hf_spaces": [],
            }

        def get_linked_hf_artifact_urls(self, paper_id):
            assert paper_id == 7
            return {
                "hf_models": [
                    "https://huggingface.co/org/model-a",
                    "https://huggingface.co/org/model-b",
                ],
                "hf_datasets": ["https://huggingface.co/datasets/org/data"],
                "hf_spaces": [],
            }

    monkeypatch.setattr("backend.services.chat_gateway_service.PaperService", Service)

    result = ChatGatewayService("db", SimpleNamespace()).catalog(
        "paper_info", {"paper": "2605.20613", "include_resources": True}
    )

    assert calls == [("2605.20613", True)]
    assert result["hf_models"] == [
        "https://huggingface.co/org/model-a",
        "https://huggingface.co/org/model-b",
    ]
    assert result["hf_datasets"] == ["https://huggingface.co/datasets/org/data"]


def test_gateway_paper_evaluations_uses_bounded_service_arguments(monkeypatch):
    calls = []

    class Service:
        def __init__(self, db):
            assert db == "db"

        def get_evaluations(self, **options):
            calls.append(options)
            return {"count": 0, "results": []}

    monkeypatch.setattr(
        "backend.services.chat_gateway_service.EvaluationService", Service
    )

    result = ChatGatewayService("db", SimpleNamespace()).catalog(
        "paper_evaluations",
        {
            "paper": "42",
            "page": "2",
            "page_size": "500",
            "ordering": "-benchmark_popularity",
        },
    )

    assert result == {"count": 0, "results": []}
    assert calls == [
        {
            "page": 2,
            "page_size": 100,
            "paper_id": 42,
            "order_by": "benchmark_popularity",
            "order_dir": "desc",
        }
    ]


def test_gateway_benchmark_evaluations_forwards_parameter_bound(monkeypatch):
    calls = []

    class Service:
        def __init__(self, db):
            assert db == "db"

        def get_evaluations(self, **options):
            calls.append(options)
            return {"count": 0, "results": []}

    monkeypatch.setattr(
        "backend.services.chat_gateway_service.EvaluationService", Service
    )

    result = ChatGatewayService("db", SimpleNamespace()).catalog(
        "benchmark_evaluations",
        {
            "dataset": "124",
            "page": "1",
            "page_size": "100",
            "max_parameters_exclusive": "1000000001",
        },
    )

    assert result == {"count": 0, "results": []}
    assert calls == [
        {
            "page": 1,
            "page_size": 100,
            "dataset_id": 124,
            "is_open": None,
            "max_parameters_exclusive": 1_000_000_001,
            "order_by": "best_rank",
            "order_dir": "asc",
        }
    ]


def test_gateway_method_list_uses_bounded_service_arguments(monkeypatch):
    calls = []

    class Service:
        def __init__(self, db):
            assert db == "db"

        def get_methods(self, **options):
            calls.append(options)
            return {"count": 0, "results": []}

    monkeypatch.setattr("backend.services.chat_gateway_service.MethodService", Service)

    result = ChatGatewayService("db", SimpleNamespace()).catalog(
        "method_list",
        {
            "page": "2",
            "page_size": "500",
            "area_id": "3",
            "introduced_year": "2020",
            "ordering": "-paper_count",
        },
    )

    assert result == {"count": 0, "results": []}
    assert calls == [
        {
            "page": 2,
            "page_size": 500,
            "area_id": 3,
            "introduced_year": 2020,
            "order_by": "paper_count",
            "order_dir": "desc",
        }
    ]


def test_gateway_paper_read_returns_controlled_upstream_error(monkeypatch):
    class DB:
        def commit(self):
            pass

    monkeypatch.setattr(
        "backend.chat_gateway_app._scope",
        lambda *_args, **_kwargs: SimpleNamespace(scopes=["catalog"]),
    )
    monkeypatch.setattr(
        ChatCapabilityService, "meter_catalog", lambda *_args, **_kwargs: None
    )

    def failed(*_args, **_kwargs):
        raise OSError("read-only cache failure")

    monkeypatch.setattr(ChatGatewayService, "catalog", failed)
    with pytest.raises(HTTPException) as exc_info:
        catalog(
            CatalogRequest(operation="paper_read", arguments={"paper": "2503.19108"}),
            authorization="Bearer test",
            x_pwc_session=str(uuid.uuid4()),
            x_pwc_turn=str(uuid.uuid4()),
            turn_fence=None,
            db=DB(),
            settings=SimpleNamespace(chat_max_direct_search_calls=4),
        )
    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Paper Markdown could not be read"


@pytest.mark.parametrize(
    "path, metered_as",
    [
        ("paper/search", "search"),
        ("/paper/search/match/", "search"),
        ("paper/CorpusId:1234/references", "semantic_scholar"),
    ],
)
def test_gateway_meters_every_semantic_scholar_search_as_a_search(
    monkeypatch, path, metered_as
):
    class DB:
        def commit(self):
            pass

    metered: list[str] = []
    monkeypatch.setattr(
        "backend.chat_gateway_app._scope", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(
        ChatCapabilityService,
        "meter_catalog",
        lambda _self, _capability, operation, **_kwargs: metered.append(operation),
    )
    monkeypatch.setattr(
        "backend.chat_gateway_app.fetch_semantic_scholar",
        lambda *_args, **_kwargs: {"data": []},
    )

    catalog(
        CatalogRequest(
            operation="semantic_scholar",
            arguments={"path": path, "query": {"query": "mamba"}},
        ),
        authorization="Bearer test",
        x_pwc_session=str(uuid.uuid4()),
        x_pwc_turn=str(uuid.uuid4()),
        turn_fence=None,
        db=DB(),
        settings=SimpleNamespace(chat_max_direct_search_calls=4),
    )

    assert metered == [metered_as]
