"""Repository listings return every owner match and expose paper_count."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.database.connection import get_database_session
from backend.main import create_app
from backend.models.database import Base, PaperRepository, Repository
from backend.services.repository_ordering import primary_repository_order
from backend.services.repository_service import RepositoryService


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine, tables=[Repository.__table__, PaperRepository.__table__]
    )
    session = Session(engine)
    session.add_all(
        [
            Repository(id=1, url="https://github.com/Lab/a", owner="Lab", name="a"),
            Repository(
                id=2, url="https://github.com/lab/b", owner="lab", name="b", num_stars=9
            ),
            Repository(id=3, url="https://github.com/lab2/c", owner="lab2", name="c"),
        ]
    )
    session.add_all(
        [
            PaperRepository(paper_id=10, repository_id=2),
            PaperRepository(paper_id=11, repository_id=2),
            PaperRepository(paper_id=10, repository_id=1),
        ]
    )
    session.commit()
    return session


def _client(session) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_database_session] = lambda: session
    return TestClient(app)


def test_owner_listing_matches_exact_owner_without_page_cap(monkeypatch):
    session = _session()
    service = RepositoryService(session)
    monkeypatch.setattr(service.settings, "max_page_size", 1)

    repositories = service.get_repositories_by_owner("LAB")

    assert [(repo.id, repo.paper_count) for repo in repositories] == [
        ("2", 2),
        ("1", 1),
    ]


def test_owner_route_is_reachable_and_id_route_still_resolves_numbers():
    session = _session()
    with _client(session) as client:
        by_owner = client.get("/api/v1/repositories/lab")
        by_id = client.get("/api/v1/repositories/3")

    assert by_owner.status_code == 200
    assert [repo["name"] for repo in by_owner.json()] == ["b", "a"]
    assert by_owner.json()[0]["paper_count"] == 2
    assert by_id.status_code == 200
    assert by_id.json()["owner"] == "lab2"
    assert "paper_count" not in by_id.json()


def test_repository_list_includes_paper_count():
    session = _session()
    with _client(session) as client:
        response = client.get("/api/v1/repositories/?order_by=paper_count")

    assert response.status_code == 200
    assert [
        (repo["id"], repo["paper_count"]) for repo in response.json()["results"]
    ] == [("2", 2), ("1", 1), ("3", 0)]


def test_repository_list_without_counts_leaves_paper_count_empty():
    session = _session()

    page = RepositoryService(session).get_repositories(
        include_paper_count=False, order_by="name", order_dir="asc"
    )

    assert [(repo.name, repo.paper_count) for repo in page.results] == [
        ("a", None),
        ("b", None),
        ("c", None),
    ]


def test_primary_repository_order_prefers_official_then_stars_then_url():
    session = _session()
    session.add_all(
        [
            Repository(id=4, url="https://github.com/z/top", num_stars=50),
            Repository(id=5, url="https://github.com/a/tie", num_stars=9),
            PaperRepository(paper_id=12, repository_id=1, is_official=True),
            PaperRepository(paper_id=12, repository_id=2),
            PaperRepository(paper_id=12, repository_id=4),
            PaperRepository(paper_id=12, repository_id=5),
        ]
    )
    session.commit()

    ids = session.scalars(
        select(Repository.id)
        .join(PaperRepository, PaperRepository.repository_id == Repository.id)
        .where(PaperRepository.paper_id == 12)
        .order_by(*primary_repository_order())
    ).all()

    assert ids == [1, 4, 5, 2]
