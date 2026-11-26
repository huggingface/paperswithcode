"""Regression tests for the public API feedback in issues #1191-#1208."""

import asyncio
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import (
    Base,
    Dataset as DBDataset,
    Metric as DBMetric,
    Paper as DBPaper,
    Task as DBTask,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.models.evaluations import Dataset
from backend.models.papers import (
    RepositoryTrendingPaper,
    RepositoryTrendingRepository,
    RepositoryTrendingScore,
)
from backend.routers.public_api import rate_limit_policy
from backend.services import paper_markdown_identity
from backend.services.catalog_errors import CatalogNotFoundError
from backend.services.leaderboard_metric_service import LeaderboardMetricService
from backend.services.public_api_docs_service import markdown_to_html
from backend.utils.forwarded_scheme import UnixSocketForwardedSchemeMiddleware


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
def _sqlite_json(_type, _compiler, **_kwargs):
    return "TEXT"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            model.__table__
            for model in (
                DBPaper,
                DBTask,
                DBDataset,
                DBMetric,
                TaskDataset,
                TaskDatasetMetric,
            )
        ],
    )
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_leaderboard_metrics_404_for_an_unlinked_task(db):
    db.add_all(
        [
            DBTask(id=1, name="Image Classification", slug="image-classification"),
            DBTask(id=19, name="Image Generation", slug="image-generation"),
            DBDataset(id=399, name="Bench", slug="bench"),
            TaskDataset(task_id=19, dataset_id=399),
        ]
    )
    db.commit()
    service = LeaderboardMetricService(db)
    assert service.get_leaderboard_metrics(19, 399)["metrics"] == []
    with pytest.raises(CatalogNotFoundError):
        service.get_leaderboard_metrics(1, 399)


def test_read_resolves_catalog_ids_to_their_markdown_key(db, monkeypatch):
    monkeypatch.setattr(
        paper_markdown_identity,
        "lookup_paper_merge_redirect",
        lambda _db, paper_id: "1706.03762" if paper_id == 9 else None,
    )
    db.add_all(
        [
            DBPaper(id=755, title="Attention", source="arxiv", arxiv_id="1706.03762"),
            DBPaper(
                id=800,
                title="Blog",
                source="external",
                source_url="https://example.org/blog",
            ),
        ]
    )
    db.commit()
    resolve = paper_markdown_identity.resolve_markdown_paper_id
    assert resolve(db, "755") == "1706.03762"
    assert resolve(db, "800") == "800"
    assert resolve(db, "9") == "1706.03762"
    assert resolve(db, "1706.03762v7") == "1706.03762v7"
    assert resolve(db, "9" * 30) == "9" * 30
    assert resolve(db, "²") == "²"


@pytest.mark.parametrize(
    ("order_by", "value", "paper_id"),
    [
        ("date_published", 5, 1),
        ("date_published", True, 1),
        ("date_published", "not-a-date", 1),
        ("citation_count", "12", 1),
        ("citation_count", True, 1),
        ("citation_count", 5, 2**70),
        ("citation_count", 5, "1"),
    ],
)
def test_cursor_rejects_values_of_the_wrong_type(order_by, value, paper_id):
    from backend.services.paper_cursor import InvalidPaperCursorError, PaperCursor

    token = PaperCursor(order_by, "desc", value, paper_id).encode()
    with pytest.raises(InvalidPaperCursorError):
        PaperCursor.decode(token, order_by, "desc")


@pytest.mark.parametrize(
    ("client", "header", "scheme"),
    [
        (None, b"https", "https"),
        (("127.0.0.1", 5000), b"https", "http"),
        (None, b"gopher", "http"),
    ],
)
def test_forwarded_scheme_is_trusted_only_on_the_unix_socket(client, header, scheme):
    seen = {}

    async def app(scope, _receive, _send):
        seen.update(scope)

    middleware = UnixSocketForwardedSchemeMiddleware(app)
    scope = {
        "type": "http",
        "scheme": "http",
        "client": client,
        "headers": [(b"x-forwarded-proto", header)],
    }
    asyncio.run(middleware(scope, None, None))
    assert seen["scheme"] == scheme


def test_rate_limit_policy_matches_the_nginx_zones():
    both = '"catalog";q=120;w=60, "list";q=60;w=60'
    assert rate_limit_policy("/api/v1/papers/") == both
    assert rate_limit_policy("/api/v1/papers/search") == both
    assert rate_limit_policy("/api/v1/tasks") == both
    assert rate_limit_policy("/api/v1/papers/1706.03762") == '"catalog";q=120;w=60'
    assert rate_limit_policy("/api/v1/research/papers/755/read") is None


def test_additive_fields_mirror_existing_values():
    dataset = Dataset(id="72", name="ImageNet", slug="imagenet-1k")
    assert dataset.model_dump()["catalog_url"] == (
        "https://paperswithcode.co/benchmark/imagenet-1k"
    )
    trending = RepositoryTrendingPaper(
        paper_id="755",
        arxiv_id="1706.03762",
        source="arxiv",
        source_url=None,
        title="Attention",
        abstract=None,
        authors=[],
        date_published=date(2017, 6, 12),
        thumbnail_url=None,
        tasks=[],
        repository=RepositoryTrendingRepository.model_construct(),
        trending=RepositoryTrendingScore.model_construct(),
        paper_age_days=1.0,
        has_official_implementation=True,
        code_repository_count=1,
    )
    dumped = trending.model_dump()
    assert dumped["id"] == "755" and dumped["published"] == date(2017, 6, 12)


def test_metric_values_are_numbers_or_null():
    from backend.models.evaluations import _metric_number

    assert _metric_number("94.9") == 94.9
    assert _metric_number(3) == 3.0
    assert _metric_number("n/a") is None
    assert _metric_number("nan") is None


def test_docs_markdown_renders_headings_lists_and_code():
    html = markdown_to_html(
        "# Title\n\nText with `code`.\n\n- one\n  continued\n- two\n\n"
        '1. first\n\n```\ncurl "x?a=1&b=2"\n```\n'
    )
    assert html == (
        "<h1>Title</h1><p>Text with <code>code</code>.</p>"
        "<ul><li>one continued</li><li>two</li></ul>"
        "<ol><li>first</li></ol>"
        "<pre><code>curl &quot;x?a=1&amp;b=2&quot;</code></pre>"
    )
