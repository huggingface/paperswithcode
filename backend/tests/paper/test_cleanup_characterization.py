from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.papers import Paper
from backend.models.database import (
    PaperRepository as DBPaperRepository,
    Dataset as DBDataset,
    Framework as DBFramework,
    PaperAuthor,
    PaperConference as DBPaperConference,
    PaperRelation as DBPaperRelation,
)
from backend.services.paper_relation_loader import PaperRelationLoader, PaperRelations
from backend.services.thumbnail_service import ThumbnailService


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _TrendingDatabase:
    def __init__(self, papers, tasks=(), authors=()):
        self.papers = list(papers)
        self.tasks = list(tasks)
        self.authors = list(authors)
        self.executions = []

    def execute(self, statement, parameters):
        sql = str(statement)
        self.executions.append((sql, dict(parameters)))
        if "FROM paper_tasks" in sql:
            return _Rows(self.tasks)
        if "FROM paper_authors" in sql:
            return _Rows(self.authors)
        return _Rows(self.papers)


@pytest.fixture
def trending_client():
    app = create_app()
    state = {}

    def override_get_database_session():
        yield state["db"]

    app.dependency_overrides[get_database_session] = override_get_database_session
    with TestClient(app) as client:
        yield client, state
    app.dependency_overrides.clear()


def test_trending_route_payload_order_batching_and_filter_forwarding(
    trending_client, monkeypatch
):
    client, state = trending_client
    state["db"] = db = _TrendingDatabase(
        papers=[
            (
                101,
                "2608.00001",
                "First by trending score",
                date(2026, 8, 8),
                201,
                "https://github.com/example/first",
                "example",
                "first",
                1200,
                Decimal("2.5"),
                Decimal("4.75"),
                60,
                Decimal("2"),
                "First abstract",
                "arxiv",
                None,
                None,
                "v3",
            ),
            (
                102,
                None,
                "Second by trending score",
                date(2026, 8, 7),
                202,
                "https://github.com/example/second",
                "example",
                "second",
                800,
                Decimal("1.25"),
                Decimal("3.5"),
                30,
                Decimal("3"),
                "External abstract",
                "external",
                "https://example.com/technical-report",
                None,
                "v1",
            ),
        ],
        tasks=[
            (101, "Image Classification", "image-classification"),
            (101, "Representation Learning", "representation-learning"),
            (102, "Language Modeling", "language-modeling"),
        ],
        authors=[
            (101, "Ada Lovelace"),
            (101, "Grace Hopper"),
            (102, "Katherine Johnson"),
        ],
    )
    external_thumbnail_calls = []

    def external_thumbnail(_service, paper_id):
        external_thumbnail_calls.append(paper_id)
        return "/api/thumbnails/custom/external_102.jpg?fit=fit9"

    monkeypatch.setattr(
        ThumbnailService,
        "get_external_thumbnail_url",
        external_thumbnail,
    )

    response = client.get(
        "/api/v1/papers/trending",
        params={"limit": 7, "max_age_days": 42, "min_velocity": 1.25},
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "paper_id": "101",
            "arxiv_id": "2608.00001",
            "source": "arxiv",
            "source_url": None,
            "title": "First by trending score",
            "abstract": "First abstract",
            "authors": ["Ada Lovelace", "Grace Hopper"],
            "date_published": "2026-08-08",
            "thumbnail_url": "/api/thumbnails/2608_00001_v3.jpg?fit=fit9",
            "tasks": [
                {"name": "Image Classification", "slug": "image-classification"},
                {
                    "name": "Representation Learning",
                    "slug": "representation-learning",
                },
            ],
            "repository": {
                "id": "201",
                "url": "https://github.com/example/first",
                "owner": "example",
                "name": "first",
                "num_stars": 1200,
            },
            "trending": {
                "velocity_24h": 2.5,
                "trending_score": 4.75,
                "stars_gained_24h": 60,
            },
            "paper_age_days": 2.0,
        },
        {
            "paper_id": "102",
            "arxiv_id": None,
            "source": "external",
            "source_url": "https://example.com/technical-report",
            "title": "Second by trending score",
            "abstract": "External abstract",
            "authors": ["Katherine Johnson"],
            "date_published": "2026-08-07",
            "thumbnail_url": "/api/thumbnails/custom/external_102.jpg?fit=fit9",
            "tasks": [{"name": "Language Modeling", "slug": "language-modeling"}],
            "repository": {
                "id": "202",
                "url": "https://github.com/example/second",
                "owner": "example",
                "name": "second",
                "num_stars": 800,
            },
            "trending": {
                "velocity_24h": 1.25,
                "trending_score": 3.5,
                "stars_gained_24h": 30,
            },
            "paper_age_days": 3.0,
        },
    ]
    assert len(db.executions) == 3
    assert db.executions[0][1] == {
        "limit": 7,
        "max_age_days": 42,
        "min_velocity": 1.25,
    }
    assert db.executions[1][1] == {"paper_ids": [101, 102]}
    assert db.executions[2][1] == {"paper_ids": [101, 102]}
    ranked_sql = " ".join(db.executions[0][0].split())
    assert (
        "ORDER BY trending_score DESC NULLS LAST, current_stars DESC LIMIT :limit"
        in ranked_sql
    )
    assert external_thumbnail_calls == [102]


class _RelationQuery:
    def __init__(self, database, entities):
        self.database = database
        self.entities = entities

    def select_from(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def group_by(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        self.database.executed_entities.append(self.entities)
        return self.database.rows_for(self.entities)


class _RelationDatabase:
    def __init__(self):
        self.executed_entities = []

    def query(self, *entities):
        return _RelationQuery(self, entities)

    @staticmethod
    def rows_for(entities):
        first = entities[0]
        if first is PaperAuthor.paper_id:
            return [(1, 11, "Ada Lovelace", "ada")]
        if first is DBDataset:
            return [
                SimpleNamespace(
                    id=21,
                    introducing_paper_id=1,
                    name="Characterized Benchmark",
                    slug="characterized-benchmark",
                    full_name=None,
                    introduced_year=2026,
                )
            ]
        if first is DBFramework:
            return [
                SimpleNamespace(
                    id=31,
                    introducing_paper_id=1,
                    name="Characterized Framework",
                    slug="characterized-framework",
                )
            ]
        if first is DBPaperRelation.source_paper_id:
            return [(1, _related_paper(2, "Successor"))]
        if first is DBPaperRelation.target_paper_id:
            return [(1, _related_paper(3, "Predecessor"))]
        if first is DBPaperConference.paper_id:
            return [(1, SimpleNamespace(name="ICML 2026", slug="icml-2026"))]
        return []


def _related_paper(paper_id, title):
    return SimpleNamespace(
        id=paper_id,
        title=title,
        arxiv_id=f"2608.{paper_id:05d}",
        source="arxiv",
        source_url=None,
        date_published=date(2026, 8, paper_id),
    )


@pytest.mark.parametrize(
    ("loader_method", "include_resources", "expected_queries"),
    [
        ("load_cards", False, 6),
        ("load_details", False, 11),
        ("load_cards", True, 8),
        ("load_details", True, 13),
    ],
)
@pytest.mark.parametrize(
    "paper_ids",
    [[1], list(range(1, 51))],
    ids=["one-paper", "fifty-papers"],
)
def test_paper_relation_query_count_is_constant_in_paper_count(
    paper_ids, loader_method, include_resources, expected_queries
):
    db = _RelationDatabase()
    loader = PaperRelationLoader(db)

    relations = getattr(loader, loader_method)(paper_ids)
    if include_resources:
        loader.load_resources(paper_ids, relations)

    assert isinstance(relations, PaperRelations)
    assert len(db.executed_entities) == expected_queries


class _RepositoryDatabase(_RelationDatabase):
    @staticmethod
    def rows_for(entities):
        if len(entities) == 3 and entities[1] is DBPaperRepository.is_official:
            return [
                (
                    1,
                    is_official,
                    SimpleNamespace(
                        id=repo_id,
                        url=f"https://github.com/o/r{repo_id}",
                        owner="o",
                        name=f"r{repo_id}",
                        num_stars=stars,
                        source="manual",
                        trending_score=None,
                        trending_score_updated_at=None,
                        created_at=None,
                        updated_at=None,
                    ),
                )
                for repo_id, is_official, stars in [
                    (1, True, 5),
                    (2, False, 900),
                    (3, False, 50),
                ]
            ]
        return []


@pytest.mark.parametrize(("repository_limit", "expected"), [(None, 3), (1, 1), (2, 2)])
def test_load_resources_caps_repositories_per_paper(repository_limit, expected):
    relations = PaperRelations()
    PaperRelationLoader(_RepositoryDatabase()).load_resources(
        [1], relations, repository_limit
    )

    repositories = relations.repositories[1]
    assert len(repositories) == expected
    assert repositories[0].is_official


def test_card_relations_link_displayed_authors_and_exclude_detail_projection():
    card_db = _RelationDatabase()
    detail_db = _RelationDatabase()

    card = PaperRelationLoader(card_db).load_cards([1])
    detail = PaperRelationLoader(detail_db).load_details([1])

    assert card.authors[1] == ["Ada Lovelace"]
    assert [link.model_dump() for link in card.author_links[1]] == [
        {"id": "11", "name": "Ada Lovelace", "hf_username": "ada"}
    ]
    assert all(entities[0] is not DBDataset for entities in card_db.executed_entities)
    assert all(entities[0] is not DBFramework for entities in card_db.executed_entities)
    assert card.introduced_benchmarks.get(1, []) == []
    assert card.introduced_frameworks.get(1, []) == []
    assert card.predecessor_papers.get(1, []) == []
    assert card.successor_papers.get(1, []) == []
    assert card.conferences.get(1) is None

    assert [link.model_dump() for link in detail.author_links[1]] == [
        {"id": "11", "name": "Ada Lovelace", "hf_username": "ada"}
    ]
    assert detail.introduced_benchmarks[1][0].name == "Characterized Benchmark"
    assert detail.introduced_frameworks[1][0].name == "Characterized Framework"
    assert detail.predecessor_papers[1][0].title == "Predecessor"
    assert detail.successor_papers[1][0].title == "Successor"
    assert detail.conferences[1].slug == "icml-2026"


class _ManyAuthorsDatabase(_RelationDatabase):
    @staticmethod
    def rows_for(entities):
        if entities[0] is PaperAuthor.paper_id:
            return [(1, 10 + i, f"Author {i}", None) for i in range(5)]
        return _RelationDatabase.rows_for(entities)


def test_card_author_links_cover_only_the_displayed_authors():
    card = PaperRelationLoader(_ManyAuthorsDatabase()).load_cards([1])
    detail = PaperRelationLoader(_ManyAuthorsDatabase()).load_details([1])

    assert len(card.authors[1]) == 5
    assert [link.name for link in card.author_links[1]] == [
        "Author 0",
        "Author 1",
        "Author 2",
    ]
    assert len(detail.author_links[1]) == 5


# Fields declared by the frontend's public `Paper` interface and read by its
# feed cards, paper preview, paper detail, saved-paper, and chat surfaces.
FRONTEND_PAPER_FIELDS = {
    "id",
    "arxiv_id",
    "source",
    "source_url",
    "url_abs",
    "url_pdf",
    "thumbnail_url",
    "title",
    "abstract",
    "tldr",
    "num_pages",
    "authors",
    "author_links",
    "published",
    "conference",
    "conference_url_abs",
    "conference_url_pdf",
    "proceeding",
    "conference_slug",
    "conference_name",
    "conference_award",
    "version",
    "is_latest_version",
    "citation_count",
    "semantic_scholar_id",
    "repositories",
    "project_pages",
    "hf_models",
    "hf_datasets",
    "hf_spaces",
    "hf_artifact_summary",
    "tasks",
    "methods",
    "introduced_benchmarks",
    "introduced_frameworks",
    "predecessor_papers",
    "successor_papers",
    "organizations",
    "leaderboard_ranks",
}


def test_public_paper_schema_retains_frontend_fields():
    schema = Paper.model_json_schema()

    assert FRONTEND_PAPER_FIELDS <= set(schema["properties"])
    assert schema["required"] == ["id", "title", "authors"]
