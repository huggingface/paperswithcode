"""PostgreSQL integration coverage for weighted paper full-text search."""

import json
import subprocess
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.database.migrations.backfill_paper_search_vector import backfill
from backend.main import create_app
from backend.models.database import (
    Author as DBAuthor,
    Base,
    Method as DBMethod,
    Paper as DBPaper,
    PaperMethod,
    PaperRepository,
    PaperTask,
    Repository as DBRepository,
    Task as DBTask,
)
from backend.models.papers import PaperReferenceQuery
from backend.services.paper_reference_service import PaperReferenceService
from backend.services.paper_retrieval_service import PaperRetrievalService
from backend.services.paper_service import PaperService


MIGRATIONS = Path(__file__).parents[2] / "database" / "migrations"


@pytest.fixture(scope="module")
def search_database_url():
    """Create a disposable PostgreSQL database without touching the app DB."""
    settings = get_settings()
    database_name = f"pwc_search_test_{uuid4().hex[:12]}"
    subprocess.run(
        [
            "runuser",
            "-u",
            "postgres",
            "--",
            "createdb",
            "--owner",
            settings.db_user,
            database_name,
        ],
        check=True,
    )

    url = make_url(settings.database_url).set(database=database_name)
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        subprocess.run(
            [
                "runuser",
                "-u",
                "postgres",
                "--",
                "dropdb",
                "--force",
                database_name,
            ],
            check=True,
        )


@pytest.fixture(scope="module")
def search_engine(search_database_url):
    engine = create_engine(search_database_url)
    Base.metadata.create_all(engine)
    # Prove the idempotent schema migration adds the model-declared column,
    # rather than merely relying on metadata.create_all in this test.
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE papers DROP COLUMN search_vector"))
        connection.exec_driver_sql(
            (MIGRATIONS / "add_paper_search_vector.sql").read_text()
        )
        connection.exec_driver_sql(
            (MIGRATIONS / "add_paper_search_vector.sql").read_text()
        )
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(
            (MIGRATIONS / "add_paper_search_vector_index.sql").read_text()
        )
        connection.exec_driver_sql(
            (MIGRATIONS / "add_paper_search_vector_index.sql").read_text()
        )
        connection.exec_driver_sql(
            (MIGRATIONS / "add_paper_normalized_title_index.sql").read_text()
        )
        connection.exec_driver_sql((MIGRATIONS / "enable_pg_trgm.sql").read_text())
        connection.exec_driver_sql((MIGRATIONS / "enable_pg_trgm.sql").read_text())
        connection.exec_driver_sql(
            (MIGRATIONS / "add_paper_title_trigram_index.sql").read_text()
        )
        author_index_statements = (
            (MIGRATIONS / "add_author_filter_indexes.sql").read_text().split(";")
        )
        for _ in range(2):
            connection.exec_driver_sql(
                (MIGRATIONS / "add_author_search_vector_index.sql").read_text()
            )
            for statement in author_index_statements:
                if statement.strip():
                    connection.exec_driver_sql(statement)
        connection.exec_driver_sql(
            (MIGRATIONS / "add_paper_title_trigram_index.sql").read_text()
        )
        for _ in range(2):
            connection.exec_driver_sql(
                (MIGRATIONS / "add_paper_title_fingerprint_index.sql").read_text()
            )
            connection.exec_driver_sql(
                (MIGRATIONS / "add_paper_title_fingerprint_statistics.sql").read_text()
            )
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def session_factory(search_engine):
    return sessionmaker(bind=search_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def clean_papers(search_engine):
    with search_engine.begin() as connection:
        connection.execute(
            text("TRUNCATE paper_authors, papers RESTART IDENTITY CASCADE")
        )


def add_paper(session, **overrides):
    values = {
        "title": "Untitled Search Paper",
        "abstract": "A neutral abstract.",
        "arxiv_id": f"2607.{uuid4().int % 100000:05d}",
        "version": "v1",
        "is_latest_version": True,
        "date_published": date(2026, 7, 1),
        "citation_count": 0,
    }
    values.update(overrides)
    paper = DBPaper(**values)
    session.add(paper)
    session.flush()
    return paper


def search(session, query, limit=10, mode="keyword"):
    service = PaperService(session)._retrieval_service()
    service.settings.paper_search_mode = mode
    return service.search_papers(query, limit)


def test_paper_implementation_coverage_unions_repositories_across_versions(
    session_factory,
):
    with session_factory() as session:
        first = add_paper(
            session,
            title="Versioned Implementation Paper",
            arxiv_id="2607.09990",
            version="v1",
            is_latest_version=False,
        )
        latest = add_paper(
            session,
            title="Versioned Implementation Paper",
            arxiv_id="2607.09990",
            version="v2",
            is_latest_version=True,
        )
        official = DBRepository(
            url="https://github.com/example/official",
            owner="example",
            name="official",
        )
        community = DBRepository(
            url="https://github.com/example/community",
            owner="example",
            name="community",
        )
        session.add_all((official, community))
        session.flush()
        session.add_all(
            (
                PaperRepository(
                    paper_id=first.id,
                    repository_id=official.id,
                    is_official=True,
                ),
                PaperRepository(
                    paper_id=latest.id,
                    repository_id=community.id,
                    is_official=False,
                ),
            )
        )
        session.commit()

        response = PaperService(session).get_paper_by_id(
            latest.id, include_resources=True
        )

        assert response.has_official_implementation is True
        assert response.code_repository_count == 2
        assert {repository.url for repository in response.repositories or []} == {
            official.url,
            community.url,
        }


def test_recent_paper_summaries_include_family_implementation_coverage(
    session_factory,
):
    with session_factory() as session:
        first = add_paper(
            session,
            title="Summary Coverage Paper",
            arxiv_id="2607.09991",
            version="v1",
            is_latest_version=False,
        )
        latest = add_paper(
            session,
            title="Summary Coverage Paper",
            arxiv_id="2607.09991",
            version="v2",
            is_latest_version=True,
        )
        repository = DBRepository(
            url="https://github.com/example/summary-official",
            owner="example",
            name="summary-official",
        )
        session.add(repository)
        session.flush()
        session.add(
            PaperRepository(
                paper_id=first.id,
                repository_id=repository.id,
                is_official=True,
            )
        )
        session.commit()

        summaries = PaperService(session).get_recent_papers(limit=10)
        summary = next(item for item in summaries if item.id == str(latest.id))

        assert summary.has_official_implementation is True
        assert summary.code_repository_count == 1


def test_paper_list_filters_to_family_official_implementations_and_confirms_filter(
    session_factory,
):
    with session_factory() as session:
        older = add_paper(
            session,
            title="Official Family Paper",
            arxiv_id="2607.09992",
            version="v1",
            is_latest_version=False,
        )
        latest = add_paper(
            session,
            title="Official Family Paper",
            arxiv_id="2607.09992",
            version="v2",
            is_latest_version=True,
        )
        community_only = add_paper(
            session,
            title="Community Only Paper",
            arxiv_id="2607.09993",
        )
        official_repository = DBRepository(
            url="https://github.com/example/family-official",
            owner="example",
            name="family-official",
        )
        community_repository = DBRepository(
            url="https://github.com/example/community-only",
            owner="example",
            name="community-only",
        )
        session.add_all((official_repository, community_repository))
        session.flush()
        session.add_all(
            (
                PaperRepository(
                    paper_id=older.id,
                    repository_id=official_repository.id,
                    is_official=True,
                ),
                PaperRepository(
                    paper_id=community_only.id,
                    repository_id=community_repository.id,
                    is_official=False,
                ),
            )
        )
        session.commit()

        app = create_app()

        def override_get_database_session():
            yield session

        app.dependency_overrides[get_database_session] = override_get_database_session
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/papers/",
                params={
                    "order_by": "date_published",
                    "has_official_implementation": "true",
                },
            )

        assert response.status_code == 200
        payload = response.json()
        assert [paper["id"] for paper in payload["results"]] == [str(latest.id)]
        assert payload["results"][0]["has_official_implementation"] is True
        assert payload["applied_filters"]["has_official_implementation"] == "true"


def test_paper_search_filters_to_family_official_implementations_and_confirms_filter(
    session_factory,
):
    with session_factory() as session:
        older = add_paper(
            session,
            title="Official Search Family",
            abstract="implementation coverage tracer",
            arxiv_id="2607.09994",
            version="v1",
            is_latest_version=False,
        )
        latest = add_paper(
            session,
            title="Official Search Family",
            abstract="implementation coverage tracer",
            arxiv_id="2607.09994",
            version="v2",
            is_latest_version=True,
        )
        add_paper(
            session,
            title="Community Search Result",
            abstract="implementation coverage tracer",
            arxiv_id="2607.09995",
            citation_count=10_000,
        )
        repository = DBRepository(
            url="https://github.com/example/search-official",
            owner="example",
            name="search-official",
        )
        session.add(repository)
        session.flush()
        session.add(
            PaperRepository(
                paper_id=older.id,
                repository_id=repository.id,
                is_official=True,
            )
        )
        session.commit()

        app = create_app()

        def override_get_database_session():
            yield session

        app.dependency_overrides[get_database_session] = override_get_database_session
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/papers/search",
                params={
                    "q": "implementation coverage tracer",
                    "mode": "keyword",
                    "page_size": 1,
                    "has_official_implementation": "true",
                },
            )

        assert response.status_code == 200
        payload = response.json()
        assert [paper["id"] for paper in payload["results"]] == [str(latest.id)]
        assert payload["next_page"] is None
        assert payload["applied_filters"]["has_official_implementation"] == "true"


def test_exact_title_beats_more_cited_abstract_match(session_factory):
    with session_factory() as session:
        exact = add_paper(
            session,
            title="Neural Widget Search",
            citation_count=2,
            arxiv_id="2607.00001",
        )
        add_paper(
            session,
            title="Popular but Unrelated Systems",
            abstract="We mention neural widget search in passing.",
            citation_count=50_000,
            arxiv_id="2607.00002",
        )
        session.commit()
        assert search(session, "  neural   widget SEARCH  ")[0].id == str(exact.id)


def test_title_weight_outranks_abstract_only_match(session_factory):
    with session_factory() as session:
        title_match = add_paper(
            session, title="Quantum Frobnication", arxiv_id="2607.00003"
        )
        add_paper(
            session,
            title="Other Work",
            abstract="Quantum frobnication for systems.",
            arxiv_id="2607.00004",
        )
        session.commit()
        assert search(session, "quantum frobnication")[0].id == str(title_match.id)


def test_search_by_author_name_returns_their_papers(session_factory):
    with session_factory() as session:
        author = DBAuthor(name="Noam Shazeer")
        first = add_paper(
            session,
            title="First Author Search Result",
            arxiv_id="2607.00991",
            citation_count=20,
        )
        second = add_paper(
            session,
            title="Second Author Search Result",
            arxiv_id="2607.00992",
            citation_count=10,
        )
        add_paper(
            session,
            title="Unrelated Author Search Result",
            arxiv_id="2607.00993",
            citation_count=1_000,
        )
        first.authors.append(author)
        second.authors.append(author)
        session.commit()

        assert [paper.id for paper in search(session, "Noam Shazeer")] == [
            str(first.id),
            str(second.id),
        ]


def test_paper_list_filters_by_normalized_author_name_and_topic(session_factory):
    with session_factory() as session:
        author = DBAuthor(name="\tKaiming He\n")
        target = add_paper(
            session,
            title="Generative Modeling via Drifting",
            abstract="A drifting field for one-step generative modeling.",
            arxiv_id="2602.04770",
            date_published=date(2026, 2, 4),
        )
        unrelated = add_paper(
            session,
            title="Drift Detection without the Requested Author",
            abstract="A study of drift.",
            arxiv_id="2602.04771",
            date_published=date(2026, 2, 5),
        )
        target.authors.append(author)
        session.add_all((target, unrelated))
        session.commit()

    def override_get_database_session():
        with session_factory() as request_session:
            yield request_session

    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/papers/",
                params=[
                    ("author", "  KAIMING   HE  "),
                    ("search", "drift"),
                    ("order_by", "date_published"),
                    ("order_dir", "desc"),
                ],
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert [paper["arxiv_id"] for paper in payload["results"]] == ["2602.04770"]
    assert payload["applied_filters"]["authors"] == [
        {"id": str(author.id), "name": "\tKaiming He\n", "hf_username": None}
    ]


def test_paper_list_repeated_authors_require_every_resolved_author(session_factory):
    with session_factory() as session:
        first_author = DBAuthor(name="Mingyang Deng", hf_username="Goodeat-filter")
        second_author = DBAuthor(name="Yilun Du", hf_username="yilundu-filter")
        shared = add_paper(
            session,
            title="Shared Author Paper",
            arxiv_id="2602.04772",
        )
        first_only = add_paper(
            session,
            title="First Author Only",
            arxiv_id="2602.04773",
        )
        shared.authors.extend((first_author, second_author))
        first_only.authors.append(first_author)
        session.commit()

    def override_get_database_session():
        with session_factory() as request_session:
            yield request_session

    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/papers/",
                params=[
                    ("author", str(first_author.id)),
                    ("author", "@YILUNDU-filter"),
                    ("order_by", "date_published"),
                ],
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert [paper["arxiv_id"] for paper in payload["results"]] == ["2602.04772"]
    assert [author["id"] for author in payload["applied_filters"]["authors"]] == [
        str(first_author.id),
        str(second_author.id),
    ]


def test_paper_list_rejects_ambiguous_author_name_with_candidates(session_factory):
    with session_factory() as session:
        first = DBAuthor(name="Alex Kim", hf_username="alex-kim-one")
        second = DBAuthor(name="  ALEX   KIM  ", hf_username="alex-kim-two")
        session.add_all((first, second))
        session.commit()

    def override_get_database_session():
        with session_factory() as request_session:
            yield request_session

    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/papers/", params=[("author", "alex kim")])
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "ambiguous_author"
    assert detail["reference"] == "alex kim"
    assert detail["candidates"] == [
        {"id": str(first.id), "name": "Alex Kim", "hf_username": "alex-kim-one"},
        {
            "id": str(second.id),
            "name": "  ALEX   KIM  ",
            "hf_username": "alex-kim-two",
        },
    ]


@pytest.mark.parametrize(
    ("authors", "status", "detail"),
    [
        (["Missing Person"], 404, "Author 'Missing Person' not found"),
        (["@"], 422, "Hugging Face author references require a username after @"),
        ([str(index) for index in range(11)], 422, "At most 10 author filters"),
        (["999999999999999999999999999999"], 404, "Author"),
    ],
)
def test_paper_list_rejects_invalid_author_filters(
    session_factory, authors, status, detail
):
    def override_get_database_session():
        with session_factory() as request_session:
            yield request_session

    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/papers/", params=[("author", author) for author in authors]
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status
    assert detail in str(response.json()["detail"])


def test_stemming_multi_term_quotes_and_punctuation_are_safe(session_factory):
    with session_factory() as session:
        paper = add_paper(
            session,
            title="Graph Neural Runners",
            abstract="The models are running efficiently.",
            arxiv_id="2607.00005",
        )
        session.commit()
        assert search(session, "run")[0].id == str(paper.id)
        assert search(session, "graph neural")[0].id == str(paper.id)
        assert search(session, '"graph neural"')[0].id == str(paper.id)
        assert isinstance(search(session, 'graph (neural) - "unterminated'), list)


@pytest.mark.parametrize(
    "query",
    [
        "1706.03762",
        "1706.03762v7",
        "https://arxiv.org/abs/1706.03762v7",
        "https://arxiv.org/pdf/1706.03762v7.pdf",
    ],
)
def test_arxiv_id_normalization(session_factory, query):
    with session_factory() as session:
        paper = add_paper(
            session,
            title="Attention Is All You Need",
            arxiv_id="1706.03762",
        )
        session.commit()
        assert search(session, query)[0].id == str(paper.id)


def test_latest_filter_limit_and_stable_tie_order(session_factory):
    with session_factory() as session:
        add_paper(
            session,
            id=90,
            title="Stable Ranking Token",
            arxiv_id="2607.00090",
            is_latest_version=False,
            citation_count=999,
        )
        first = add_paper(
            session, id=20, title="Stable Ranking Token Alpha", arxiv_id="2607.00020"
        )
        second = add_paper(
            session, id=21, title="Stable Ranking Token Beta", arxiv_id="2607.00021"
        )
        add_paper(
            session, id=22, title="Stable Ranking Token Gamma", arxiv_id="2607.00022"
        )
        session.commit()
        results = search(session, "stable ranking token", limit=2)
        assert [item.id for item in results] == [str(first.id), str(second.id)]


def test_fts_candidate_limit_preserves_citation_date_and_id_ties(session_factory):
    with session_factory() as session:
        for paper_id, citations, published, latest in [
            (10, 999, date(2026, 7, 3), False),
            (20, 9, date(2026, 7, 3), True),
            (30, 10, None, True),
            (41, 10, date(2026, 7, 2), True),
            (40, 10, date(2026, 7, 2), True),
        ]:
            add_paper(
                session,
                id=paper_id,
                title="Ranking Token",
                citation_count=citations,
                date_published=published,
                is_latest_version=latest,
            )
        session.commit()
        retrieval = PaperService(session)._retrieval_service()
        for limit in (1, 2, 4):
            assert [p.id for p in retrieval._search_papers_fts("ranking", limit)] == [
                40,
                41,
                30,
                20,
            ][:limit]


def test_fts_candidate_limit_deduplicates_author_and_identity_lanes(session_factory):
    with session_factory() as session:
        exact = add_paper(session, title="Quasar", citation_count=1)
        exact.authors.extend([DBAuthor(name="Quasar"), DBAuthor(name="Quasar")])
        lexical = add_paper(session, title="Other Quasar Work", citation_count=999)
        session.commit()
        retrieval = PaperService(session)._retrieval_service()
        assert [p.id for p in retrieval._search_papers_fts("quasar", 2)] == [
            exact.id,
            lexical.id,
        ]


def test_author_search_index_supports_the_search_expression(search_engine):
    with search_engine.begin() as connection:
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        plan = connection.execute(
            text("""
            EXPLAIN (FORMAT JSON) SELECT id FROM authors
            WHERE to_tsvector('simple', name) @@ websearch_to_tsquery('simple', 'Ada Lovelace')
        """)
        ).scalar_one()
        assert "idx_authors_name_search_vector" in json.dumps(plan)


def test_blank_query_returns_without_executing_sql(session_factory):
    with session_factory() as session:
        statements = []

        def record(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement)

        event.listen(session.bind, "before_cursor_execute", record)
        try:
            assert search(session, " \n\t ") == []
        finally:
            event.remove(session.bind, "before_cursor_execute", record)
        assert statements == []


@pytest.mark.parametrize(
    ("mode", "retrieval_method"),
    [
        ("keyword", "_search_papers_fts"),
        ("semantic", "_search_papers_semantic"),
        ("hybrid", "_search_papers_hybrid"),
    ],
)
def test_exact_method_entity_promotes_source_paper_in_every_mode(
    session_factory, monkeypatch, mode, retrieval_method
):
    with session_factory() as session:
        source = add_paper(
            session,
            title="A Foundational Architecture",
            arxiv_id=f"2607.{uuid4().int % 100000:05d}",
            citation_count=500,
        )
        followup = add_paper(
            session,
            title="AtlasNet at Scale",
            arxiv_id=f"2607.{uuid4().int % 100000:05d}",
            citation_count=50_000,
        )
        method = DBMethod(
            name="AtlasNet",
            full_name="Atlas Network",
            slug=f"atlasnet-{uuid4().hex}",
            source_paper_id=source.id,
        )
        session.add(method)
        session.flush()
        session.add(PaperMethod(paper_id=followup.id, method_id=method.id))
        session.commit()

        service = PaperService(session)._retrieval_service()
        monkeypatch.setattr(
            service, retrieval_method, lambda _query, _limit, **_kwargs: [followup]
        )

        results = service.search_papers("AtlasNet", limit=2, mode=mode)
        assert [result.id for result in results] == [str(source.id), str(followup.id)]


def test_official_filter_applies_before_method_promotion_and_truncation(
    session_factory, monkeypatch
):
    with session_factory() as session:
        source = add_paper(session, title="Community FilterNet Source")
        official = add_paper(session, title="Official FilterNet Result")
        method = DBMethod(
            name="FilterNet",
            slug=f"filternet-{uuid4().hex}",
            source_paper_id=source.id,
        )
        repository = DBRepository(
            url="https://github.com/example/official-filternet",
            owner="example",
            name="official-filternet",
        )
        session.add_all((method, repository))
        session.flush()
        community_papers = [
            add_paper(
                session,
                title=f"Community FilterNet Follow-up {index}",
                arxiv_id=f"2607.{10000 + index:05d}",
                citation_count=10_000 - index,
            )
            for index in range(100)
        ]
        session.add_all(
            PaperMethod(paper_id=paper.id, method_id=method.id)
            for paper in community_papers
        )
        session.add(
            PaperRepository(
                paper_id=official.id,
                repository_id=repository.id,
                is_official=True,
            )
        )
        session.commit()

        service = PaperService(session)._retrieval_service()
        monkeypatch.setattr(
            service,
            "_search_papers_fts",
            lambda _query, _limit, **_kwargs: [official],
        )
        monkeypatch.setattr(
            service, "_fuzzy_title_candidates", lambda *_args, **_kwargs: []
        )

        results = service.search_papers(
            "FilterNet",
            limit=1,
            mode="keyword",
            has_official_implementation=True,
        )

        assert [result.id for result in results] == [str(official.id)]


def test_date_filter_drops_out_of_range_promotion_without_underfilling(
    session_factory, monkeypatch
):
    with session_factory() as session:
        source = add_paper(
            session,
            title="A Foundational Date Filter Architecture",
            date_published=date(2025, 1, 1),
        )
        in_range = [
            add_paper(
                session,
                title=f"RangeNet Follow-up {index}",
                date_published=date(2026, 7, 10),
            )
            for index in range(21)
        ]
        session.add(
            DBMethod(
                name="RangeNet",
                slug=f"rangenet-{uuid4().hex}",
                source_paper_id=source.id,
            )
        )
        session.commit()

        service = PaperService(session)._retrieval_service()
        monkeypatch.setattr(
            service,
            "_search_papers_fts",
            lambda _query, _limit, **_kwargs: in_range,
        )

        results = service.search_papers(
            "RangeNet",
            limit=21,
            mode="keyword",
            start_date=date(2026, 7, 1),
        )

        assert [result.id for result in results] == [
            str(paper.id) for paper in in_range
        ]


def test_method_full_name_and_origin_intent_resolve_without_query_rules(
    session_factory,
):
    with session_factory() as session:
        source = add_paper(
            session,
            title="Patch-Based Recognition at Scale",
            arxiv_id=f"2607.{uuid4().int % 100000:05d}",
        )
        session.add(
            DBMethod(
                name="PBR",
                full_name="Patch Based Recognizer",
                slug=f"pbr-{uuid4().hex}",
                source_paper_id=source.id,
            )
        )
        session.commit()

        service = PaperService(session)._retrieval_service()
        assert service.search_papers("Patch-Based Recognizer", mode="keyword")[
            0
        ].id == str(source.id)
        assert service.search_papers("original PBR paper", mode="keyword")[0].id == str(
            source.id
        )


def test_missing_source_uses_semantic_scholar_citations_within_method_papers(
    session_factory,
):
    with session_factory() as session:
        less_cited = add_paper(
            session,
            title="First Candidate Architecture",
            arxiv_id=f"2607.{uuid4().int % 100000:05d}",
            citation_count=20,
        )
        canonical = add_paper(
            session,
            title="Second Candidate Architecture",
            arxiv_id=f"2607.{uuid4().int % 100000:05d}",
            citation_count=2_000,
        )
        method = DBMethod(
            name="CitationNet",
            slug=f"citationnet-{uuid4().hex}",
        )
        session.add(method)
        session.flush()
        session.add_all(
            [
                PaperMethod(paper_id=less_cited.id, method_id=method.id),
                PaperMethod(paper_id=canonical.id, method_id=method.id),
            ]
        )
        session.commit()

        results = search(session, "CitationNet")
        assert results[0].id == str(canonical.id)


def test_topical_method_query_is_not_forced_to_source_paper(session_factory):
    with session_factory() as session:
        source = add_paper(
            session,
            title="A Foundational Architecture",
            arxiv_id=f"2607.{uuid4().int % 100000:05d}",
            citation_count=10_000,
        )
        topical = add_paper(
            session,
            title="AtlasPrune Compression",
            abstract="AtlasPrune pruning for efficient inference.",
            arxiv_id=f"2607.{uuid4().int % 100000:05d}",
        )
        method = DBMethod(
            name="AtlasPrune",
            slug=f"atlasprune-{uuid4().hex}",
            source_paper_id=source.id,
        )
        session.add(method)
        session.commit()

        results = search(session, "AtlasPrune pruning")
        assert results[0].id == str(topical.id)


def test_ambiguous_taxonomy_alias_does_not_force_a_canonical_paper(
    session_factory, monkeypatch
):
    with session_factory() as session:
        baseline = add_paper(
            session,
            title="Gemini Systems Overview",
            arxiv_id=f"2607.{uuid4().int % 100000:05d}",
        )
        first_source = add_paper(
            session,
            title="First Source",
            arxiv_id=f"2607.{uuid4().int % 100000:05d}",
        )
        second_source = add_paper(
            session,
            title="Second Source",
            arxiv_id=f"2607.{uuid4().int % 100000:05d}",
        )
        session.add_all(
            [
                DBMethod(
                    name="Gemini Alpha",
                    full_name="Gemini",
                    slug=f"gemini-alpha-{uuid4().hex}",
                    source_paper_id=first_source.id,
                ),
                DBMethod(
                    name="Gemini Beta",
                    full_name="Gemini",
                    slug=f"gemini-beta-{uuid4().hex}",
                    source_paper_id=second_source.id,
                ),
            ]
        )
        session.commit()

        service = PaperService(session)._retrieval_service()
        monkeypatch.setattr(
            service,
            "_search_papers_fts",
            lambda _query, _limit, **_kwargs: [baseline],
        )
        results = service.search_papers("Gemini", mode="keyword")
        assert results[0].id == str(baseline.id)


@pytest.mark.parametrize(
    ("query", "alias", "expected_kind"),
    [
        ("transformer", "Transformer", 0),
        ("visiontransformer", "Vision Transformer", 1),
        ("transf", "Transformer", 2),
        ("vision tra", "Vision Transformer", 2),
        ("viion transformer", "Vision Transformer", 3),
    ],
)
def test_entity_alias_matching_supports_spacing_prefixes_and_typos(
    query, alias, expected_kind
):
    quality = PaperRetrievalService._entity_alias_match_quality(query, alias)
    assert quality is not None
    assert quality[0] == expected_kind


def test_entity_alias_matching_rejects_broad_topical_queries():
    assert (
        PaperRetrievalService._entity_alias_match_quality("bert compression", "BERT")
        is None
    )
    assert (
        PaperRetrievalService._entity_alias_match_quality("tra", "Transformer") is None
    )


def test_incomplete_and_typo_queries_use_taxonomy_prefixes_and_fuzzy_titles(
    session_factory,
):
    with session_factory() as session:
        attention = add_paper(
            session,
            title="Attention Is All You Need",
            arxiv_id="1706.03762",
            citation_count=184_799,
        )
        transfusion = add_paper(
            session,
            title="Transfusion: Predict the Next Token and Diffuse Images with One Multi-Modal Model",
            arxiv_id="2408.11039",
            citation_count=444,
        )
        counting = add_paper(
            session,
            title="The Counting Power of Transformers",
            arxiv_id="2505.11199",
            citation_count=5,
        )
        vision_transformer = add_paper(
            session,
            title="An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale",
            arxiv_id="2010.11929",
            citation_count=65_968,
        )
        swin = add_paper(
            session,
            title="Swin Transformer: Hierarchical Vision Transformer using Shifted Windows",
            arxiv_id="2103.14030",
            citation_count=33_662,
        )
        add_paper(
            session,
            title="Swin-Free: Cross-Window Attention",
            arxiv_id="2306.13776",
            citation_count=20,
        )
        segformer = add_paper(
            session,
            title="SegFormer: Simple and Efficient Design for Semantic Segmentation with Transformers",
            arxiv_id="2105.15203",
            citation_count=8_707,
        )
        add_paper(
            session,
            title="Segformer++: Efficient Token-Merging Strategies",
            arxiv_id="2405.14467",
            citation_count=10,
        )
        smolvla = add_paper(
            session,
            title="SmolVLA: A Vision-Language-Action Model for Affordable and Efficient Robotics",
            arxiv_id="2506.01844",
            citation_count=387,
        )
        add_paper(
            session,
            title="SmolLM2: When Smol Goes Big",
            arxiv_id="2502.02737",
            citation_count=200,
        )
        transformer_method = DBMethod(
            name="Transformer",
            full_name="Transformer",
            slug=f"transformer-{uuid4().hex}",
            source_paper_id=attention.id,
        )
        vision_method = DBMethod(
            name="Vision Transformer",
            full_name="Vision Transformer",
            slug=f"vision-transformer-{uuid4().hex}",
            source_paper_id=vision_transformer.id,
        )
        session.add_all([transformer_method, vision_method])
        session.flush()
        session.add_all(
            [
                PaperMethod(paper_id=attention.id, method_id=transformer_method.id),
                PaperMethod(paper_id=transfusion.id, method_id=transformer_method.id),
                PaperMethod(paper_id=counting.id, method_id=transformer_method.id),
                PaperMethod(
                    paper_id=vision_transformer.id,
                    method_id=transformer_method.id,
                ),
                PaperMethod(paper_id=swin.id, method_id=transformer_method.id),
                PaperMethod(paper_id=segformer.id, method_id=transformer_method.id),
                PaperMethod(paper_id=vision_transformer.id, method_id=vision_method.id),
            ]
        )
        session.commit()

        transf_results = search(session, "transf", limit=5)
        assert transf_results[0].arxiv_id == attention.arxiv_id
        assert transfusion.arxiv_id in {paper.arxiv_id for paper in transf_results}
        assert search(session, "vision tra")[0].arxiv_id == vision_transformer.arxiv_id
        assert (
            search(session, "viion transformer")[0].arxiv_id
            == vision_transformer.arxiv_id
        )
        assert search(session, "swin")[0].arxiv_id == swin.arxiv_id
        assert search(session, "segormer")[0].arxiv_id == segformer.arxiv_id
        assert search(session, "smolva")[0].arxiv_id == smolvla.arxiv_id
        transformer_results = search(session, "Transformer", limit=5)
        assert transformer_results[0].arxiv_id == attention.arxiv_id
        assert counting.arxiv_id not in {
            paper.arxiv_id for paper in transformer_results
        }


@pytest.mark.parametrize(
    ("mode", "retrieval_method"),
    [
        ("keyword", "_search_papers_fts"),
        ("semantic", "_search_papers_semantic"),
        ("hybrid", "_search_papers_hybrid"),
    ],
)
def test_fuzzy_title_repair_is_shared_by_every_search_mode(
    session_factory, monkeypatch, mode, retrieval_method
):
    with session_factory() as session:
        corrected = add_paper(
            session,
            title="SmolVLA: An Efficient Robotics Model",
            arxiv_id=f"2607.{uuid4().int % 100000:05d}",
            citation_count=400,
        )
        baseline = add_paper(
            session,
            title="SmolLM: A Small Language Model",
            arxiv_id=f"2607.{uuid4().int % 100000:05d}",
            citation_count=100,
        )
        session.commit()

        service = PaperService(session)._retrieval_service()
        monkeypatch.setattr(
            service, retrieval_method, lambda _query, _limit, **_kwargs: [baseline]
        )
        results = service.search_papers("smolva", mode=mode)
        assert results[0].id == str(corrected.id)


def test_search_endpoint_returns_paginated_summaries(session_factory):
    with session_factory() as session:
        paper = add_paper(
            session,
            title="Serialized Search Result",
            arxiv_id="2607.00040",
            citation_count=7,
        )
        session.commit()

    app = create_app()

    def override_database():
        with session_factory() as request_session:
            service_settings = get_settings()
            previous_mode = service_settings.paper_search_mode
            service_settings.paper_search_mode = "keyword"
            try:
                yield request_session
            finally:
                service_settings.paper_search_mode = previous_mode

    app.dependency_overrides[get_database_session] = override_database
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/papers/search",
            params={"q": "serialized", "mode": "keyword"},
        )
        long_query = client.get("/api/v1/papers/search", params={"q": "x" * 301})
        deep_page = client.get(
            "/api/v1/papers/search", params={"q": "serialized", "page": 101}
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert long_query.status_code == 422
    assert deep_page.status_code == 422
    assert response.json() == {
        "next_page": None,
        "previous_page": None,
        "applied_filters": {},
        "results": [
            {
                "id": str(paper.id),
                "title": "Serialized Search Result",
                "arxiv_id": "2607.00040",
                "source": "arxiv",
                "source_url": None,
                "authors": [],
                "published": "2026-07-01",
                "url_abs": "https://arxiv.org/abs/2607.00040",
                "citation_count": 7,
                "thumbnail_url": None,
                "has_official_implementation": False,
                "code_repository_count": 0,
            }
        ],
    }


def test_search_endpoint_filters_results_by_inclusive_publication_dates(
    session_factory,
):
    with session_factory() as session:
        inside = add_paper(
            session,
            title="Daterange Search Inside",
            arxiv_id="2607.00041",
            date_published=date(2026, 7, 10),
        )
        add_paper(
            session,
            title="Daterange Search Before",
            arxiv_id="2607.00042",
            date_published=date(2026, 7, 9),
        )
        add_paper(
            session,
            title="Daterange Search After",
            arxiv_id="2607.00043",
            date_published=date(2026, 7, 11),
        )
        session.commit()

    app = create_app()

    def override_database():
        with session_factory() as request_session:
            yield request_session

    app.dependency_overrides[get_database_session] = override_database
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/papers/search",
            params={
                "q": "daterange search",
                "mode": "keyword",
                "start_date": "2026-07-10",
                "end_date": "2026-07-10",
            },
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [paper["id"] for paper in response.json()["results"]] == [str(inside.id)]


def test_search_endpoint_pages_through_all_ranked_results(session_factory):
    with session_factory() as session:
        for index in range(11):
            add_paper(
                session,
                title=f"Paginationneedle Paper {index}",
                arxiv_id=f"2607.01{index:03d}",
                citation_count=100 - index,
            )
        session.commit()

    app = create_app()

    def override_database():
        with session_factory() as request_session:
            yield request_session

    app.dependency_overrides[get_database_session] = override_database
    with TestClient(app) as client:
        first = client.get(
            "/api/v1/papers/search",
            params={
                "q": "paginationneedle",
                "mode": "keyword",
                "page": 1,
                "page_size": 10,
            },
        )
        second = client.get(
            "/api/v1/papers/search",
            params={
                "q": "paginationneedle",
                "mode": "keyword",
                "page": 2,
                "page_size": 10,
            },
        )
    app.dependency_overrides.clear()

    assert first.status_code == 200
    assert len(first.json()["results"]) == 10
    assert first.json()["previous_page"] is None
    assert first.json()["next_page"] == 2
    assert second.status_code == 200
    assert len(second.json()["results"]) == 1
    assert second.json()["previous_page"] == 1
    assert second.json()["next_page"] is None


def test_search_feed_uses_stable_top_100_pool_across_sorts_and_includes_external(
    session_factory,
):
    with session_factory() as session:
        for index in range(101):
            add_paper(
                session,
                title=f"Feedneedle Paper {index}",
                arxiv_id=f"2607.2{index:04d}",
                date_published=date(2026, 7, 1 + index % 20),
                citation_count=500 - index,
            )
        external = add_paper(
            session,
            title="Feedneedle External Technical Report",
            arxiv_id=None,
            source="external",
            source_url="https://example.com/feedneedle-report",
            citation_count=10_000,
        )
        add_paper(
            session,
            title="Feedneedle Superseded Version",
            arxiv_id="2607.29999",
            version="v1",
            is_latest_version=False,
            citation_count=20_000,
        )
        session.commit()

    app = create_app()

    def override_database():
        with session_factory() as request_session:
            yield request_session

    app.dependency_overrides[get_database_session] = override_database
    pools = {}
    with TestClient(app) as client:
        for order_by in ("relevance", "date_published", "citation_count"):
            ids = []
            final_page = None
            for page in range(1, 6):
                response = client.get(
                    "/api/v1/papers/search/feed",
                    params={
                        "q": "feedneedle",
                        "mode": "keyword",
                        "order_by": order_by,
                        "page": page,
                    },
                )
                assert response.status_code == 200
                payload = response.json()
                ids.extend(paper["id"] for paper in payload["results"])
                final_page = payload
            assert len(ids) == 100
            assert len(set(ids)) == 100
            assert final_page["cap"] == 100
            assert final_page["cap_reached"] is True
            assert final_page["exhausted"] is True
            assert final_page["next_page"] is None
            pools[order_by] = set(ids)
    app.dependency_overrides.clear()

    assert pools["relevance"] == pools["date_published"] == pools["citation_count"]
    assert str(external.id) in pools["relevance"]


def test_search_feed_applies_code_and_hf_filters_before_keyword_ranking(
    session_factory,
):
    with session_factory() as session:
        code_paper = add_paper(session, title="Filterneedle Code Paper")
        hf_paper = add_paper(
            session,
            title="Filterneedle Artifact Paper",
            hf_models=["https://huggingface.co/example/model"],
        )
        plain_paper = add_paper(session, title="Filterneedle Plain Paper")
        repository = DBRepository(
            url="https://github.com/example/filterneedle",
            owner="example",
            name="filterneedle",
        )
        session.add(repository)
        session.flush()
        session.add(
            PaperRepository(
                paper_id=code_paper.id,
                repository_id=repository.id,
                is_official=False,
            )
        )
        session.commit()

    app = create_app()

    def override_database():
        with session_factory() as request_session:
            yield request_session

    app.dependency_overrides[get_database_session] = override_database
    with TestClient(app) as client:
        code = client.get(
            "/api/v1/papers/search/feed",
            params={"q": "filterneedle", "mode": "keyword", "has_code": True},
        )
        artifacts = client.get(
            "/api/v1/papers/search/feed",
            params={
                "q": "filterneedle",
                "mode": "keyword",
                "has_hf_artifacts": True,
            },
        )
    app.dependency_overrides.clear()

    assert code.status_code == 200
    assert [paper["id"] for paper in code.json()["results"]] == [str(code_paper.id)]
    assert code.json()["applied_filters"] == {"has_code": "true"}
    assert artifacts.status_code == 200
    assert [paper["id"] for paper in artifacts.json()["results"]] == [str(hf_paper.id)]
    assert artifacts.json()["applied_filters"] == {"has_hf_artifacts": "true"}
    assert str(plain_paper.id) not in {
        paper["id"] for paper in code.json()["results"] + artifacts.json()["results"]
    }


def test_related_endpoint_uses_task_fallback_without_embedding_schema(session_factory):
    with session_factory() as session:
        task = DBTask(name="Related Test", slug=f"related-{uuid4().hex}", level=0)
        session.add(task)
        session.flush()
        source = add_paper(session, title="Source Paper", arxiv_id="2607.00100")
        related = add_paper(
            session,
            title="Fallback Related Paper",
            arxiv_id="2607.00101",
            citation_count=12,
        )
        session.add_all(
            [
                task,
                PaperTask(paper_id=source.id, task_id=task.id, source="manual"),
                PaperTask(paper_id=related.id, task_id=task.id, source="manual"),
            ]
        )
        session.commit()

    app = create_app()

    def override_database():
        with session_factory() as request_session:
            yield request_session

    settings = get_settings()
    previous_mode = settings.related_papers_mode
    settings.related_papers_mode = "task"
    app.dependency_overrides[get_database_session] = override_database
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/papers/{source.arxiv_id}/related")
    finally:
        settings.related_papers_mode = previous_mode
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(related.id)
    assert response.json()[0]["provenance"] == "task_fallback"


def test_trigger_insert_update_coverage_and_partial_index(search_engine):
    with search_engine.begin() as connection:
        paper_id = connection.execute(
            text("""
                INSERT INTO papers (
                    title, abstract, source, arxiv_id, version,
                    is_latest_version, citation_count, urls_extracted
                ) VALUES (
                    'Trigger Insert Token', 'abstract token', 'arxiv',
                    '2607.00050', 'v1', true, 0, false
                ) RETURNING id
            """)
        ).scalar_one()
        inserted = connection.execute(
            text("SELECT search_vector::text FROM papers WHERE id = :id"),
            {"id": paper_id},
        ).scalar_one()
        assert "'trigger':1A" in inserted

        connection.execute(
            text("UPDATE papers SET title = 'Updated Vector Token' WHERE id = :id"),
            {"id": paper_id},
        )
        updated = connection.execute(
            text("SELECT search_vector::text FROM papers WHERE id = :id"),
            {"id": paper_id},
        ).scalar_one()
        assert "'updat':1A" in updated
        assert "'trigger'" not in updated

        connection.execute(
            text(
                "UPDATE papers SET abstract = 'Changed Abstract Marker' WHERE id = :id"
            ),
            {"id": paper_id},
        )
        abstract_updated = connection.execute(
            text("SELECT search_vector::text FROM papers WHERE id = :id"),
            {"id": paper_id},
        ).scalar_one()
        assert "'chang':4B" in abstract_updated
        assert "'abstract':5B" in abstract_updated

        coverage = connection.execute(
            text("""
                SELECT count(*) FILTER (WHERE search_vector IS NOT NULL), count(*)
                FROM papers WHERE is_latest_version
            """)
        ).one()
        assert coverage[0] == coverage[1]

        index_valid = connection.execute(
            text("""
                SELECT i.indisvalid AND i.indisready
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = 'idx_papers_latest_search_vector'
            """)
        ).scalar_one()
        assert index_valid is True
        title_index_valid = connection.execute(
            text("""
                SELECT i.indisvalid AND i.indisready
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = 'idx_papers_latest_normalized_title'
            """)
        ).scalar_one()
        assert title_index_valid is True
        trigram_index_valid = connection.execute(
            text("""
                SELECT i.indisvalid AND i.indisready
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indexrelid
                WHERE c.relname = 'idx_papers_latest_title_trgm'
            """)
        ).scalar_one()
        assert trigram_index_valid is True

        # Give the planner a representative selective shape; on a one-row
        # table either a sequential scan or the boolean latest-version index is
        # rational even though the GIN index is healthy.
        connection.execute(
            text("""
                INSERT INTO papers (
                    title, abstract, source, arxiv_id, version,
                    is_latest_version, citation_count, urls_extracted
                )
                SELECT
                    'Common Filler Paper ' || n,
                    'common benchmark material',
                    'arxiv',
                    '2606.' || lpad(n::text, 5, '0'),
                    'v1', true, 0, false
                FROM generate_series(1, 2000) AS n
            """)
        )
        # The fixture created the GIN index while the table was empty, so the
        # bulk insert above initially lives in GIN's pending list. Reindexing
        # models the post-backfill production build (index built over populated
        # rows) before collecting the representative plan.
        connection.execute(text("REINDEX INDEX idx_papers_latest_search_vector"))
        connection.execute(text("ANALYZE papers"))
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in connection.execute(
                text("""
                    EXPLAIN (ANALYZE, BUFFERS)
                    SELECT id FROM papers
                    WHERE is_latest_version
                      AND search_vector @@ websearch_to_tsquery('english', 'updated')
                """)
            )
        )
        assert "idx_papers_latest_search_vector" in plan
        assert "Bitmap Index Scan" in plan
        trigram_plan = "\n".join(
            row[0]
            for row in connection.execute(
                text("""
                    EXPLAIN (ANALYZE, BUFFERS)
                    WITH nearest AS MATERIALIZED (
                        SELECT id, title, citation_count,
                               word_similarity('smolva', lower(title)) AS similarity
                        FROM papers
                        WHERE is_latest_version
                        ORDER BY CAST('smolva' AS text) <<-> lower(title)
                        LIMIT 100
                    )
                    SELECT id FROM nearest
                    ORDER BY similarity DESC, citation_count DESC NULLS LAST, id
                """)
            )
        )
        assert "idx_papers_latest_title_trgm" in trigram_plan
        assert "Index Scan" in trigram_plan


def test_backfill_is_bounded_and_resumable(search_engine, search_database_url):
    with search_engine.begin() as connection:
        for suffix in range(3):
            connection.execute(
                text("""
                    INSERT INTO papers (
                        title, abstract, source, arxiv_id, version,
                        is_latest_version, citation_count, urls_extracted
                    ) VALUES (
                        :title, 'backfill abstract', 'arxiv', :arxiv_id,
                        'v1', true, 0, false
                    )
                """),
                {
                    "title": f"Backfill Paper {suffix}",
                    "arxiv_id": f"2607.0010{suffix}",
                },
            )
        connection.execute(text("UPDATE papers SET search_vector = NULL"))

    updated, remaining = backfill(search_database_url, batch_size=2, max_batches=1)
    assert (updated, remaining) == (2, 1)
    updated, remaining = backfill(search_database_url, batch_size=2, max_batches=1)
    assert (updated, remaining) == (1, 0)


def test_reference_lookup_matches_arxiv_ids_and_title_fingerprints(session_factory):
    with session_factory() as session:
        add_paper(
            session,
            title="Mamba: Linear-Time Sequence Modeling with Selective State Spaces",
            arxiv_id="2312.00752",
            version="v1",
            is_latest_version=False,
        )
        mamba = add_paper(
            session,
            title="Mamba: Linear-Time Sequence Modeling with Selective State Spaces",
            arxiv_id="2312.00752",
            version="v2",
            citation_count=5000,
        )
        lora = add_paper(
            session,
            title="LoRA: Low-Rank Adaptation of Large Language Models",
            arxiv_id="2106.09685",
        )
        session.commit()

        response = PaperReferenceService(session).resolve(
            [
                PaperReferenceQuery(key="cite.hu2022", arxiv_id="2106.09685v2"),
                PaperReferenceQuery(
                    key="cite.gu2024",
                    titles=[
                        "Albert Gu and Tri Dao",
                        "Mamba: Linear-time sequence mod- eling with selective state spaces",
                        "In Conference on Language Modeling (COLM), 2024",
                    ],
                ),
                PaperReferenceQuery(
                    key="cite.missing", titles=["A title nobody indexed"]
                ),
            ]
        )

        resolved = {entry.key: entry for entry in response.references}
        assert resolved["cite.hu2022"].matched_by == "arxiv_id"
        assert resolved["cite.hu2022"].paper.id == str(lora.id)
        assert resolved["cite.gu2024"].matched_by == "title"
        assert resolved["cite.gu2024"].paper.id == str(mamba.id)
        assert resolved["cite.gu2024"].paper.citation_count == 5000
        assert resolved["cite.missing"].paper is None
