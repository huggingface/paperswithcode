"""
Tests for the Authors API endpoints.

This module contains unit and integration tests for the authors endpoints
to ensure they work correctly with the database and return proper responses.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import create_app
from backend.models.database import (
    Base,
    Author as DBAuthor,
    Paper as DBPaper,
    PaperAuthor,
)
from backend.database.connection import get_database_session


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    """SQLite needs INTEGER primary keys for autoincrement behavior."""
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
def _compile_postgres_container_sqlite(_element, _compiler, **_kw):
    return "TEXT"


# Tables SQLite can create: some chat tables need PostgreSQL functions.
TABLES = [table for table in Base.metadata.sorted_tables if table.name != "chat_shares"]

# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_database_session():
    """Override database session for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    """Create test client with test database."""
    Base.metadata.create_all(bind=engine, tables=TABLES)

    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine, tables=TABLES)


@pytest.fixture
def sample_authors():
    """Create sample authors for testing."""
    db = TestingSessionLocal()

    # Create test authors
    author1 = DBAuthor(
        id=1, name="John Doe", hf_username="johndoe", hf_id="hf123", hf_is_pro=True
    )
    author2 = DBAuthor(
        id=2, name="Jane Smith", hf_username=None, hf_id=None, hf_is_pro=False
    )
    author3 = DBAuthor(
        id=3, name="Alice Johnson", hf_username="alicej", hf_id="hf456", hf_is_pro=False
    )

    db.add_all([author1, author2, author3])
    db.commit()

    # Create test papers
    paper1 = DBPaper(
        id=1,
        title="Test Paper 1",
        abstract="Abstract 1",
        arxiv_id="2023.01001",
        version="v1",
        is_latest_version=True,
    )
    paper2 = DBPaper(
        id=2,
        title="Test Paper 2",
        abstract="Abstract 2",
        arxiv_id="2023.01002",
        version="v1",
        is_latest_version=True,
    )

    db.add_all([paper1, paper2])
    db.commit()

    # Create author-paper relationships
    paper_author1 = PaperAuthor(paper_id=1, author_id=1, claimed=True)
    paper_author2 = PaperAuthor(paper_id=2, author_id=1, claimed=True)
    paper_author3 = PaperAuthor(paper_id=1, author_id=2)
    # Matched to Alice Johnson by name only; she never claimed it on HF.
    paper_author4 = PaperAuthor(paper_id=2, author_id=3)

    db.add_all([paper_author1, paper_author2, paper_author3, paper_author4])
    db.commit()
    db.close()


def test_get_authors_list(client, sample_authors):
    """Test getting list of authors."""
    response = client.get("/api/v1/authors/")

    assert response.status_code == 200
    data = response.json()

    assert "count" in data
    assert "results" in data
    assert data["count"] == 3
    assert len(data["results"]) == 3

    # Check first author
    author = data["results"][0]
    assert "id" in author
    assert "full_name" in author
    assert "paper_count" in author


def test_get_authors_with_pagination(client, sample_authors):
    """Test authors list with pagination."""
    response = client.get("/api/v1/authors/?page=1&page_size=2")

    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 3
    assert len(data["results"]) == 2
    assert data["next_page"] == 2
    assert data["previous_page"] is None


def test_get_authors_hf_filter(client, sample_authors):
    """Test filtering authors by Hugging Face users only."""
    response = client.get("/api/v1/authors/?hf_users_only=true")

    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 2  # Only John Doe and Alice Johnson have HF accounts
    for author in data["results"]:
        assert author["hf_username"] is not None


def test_get_author_by_id(client, sample_authors):
    """Test getting specific author by ID."""
    response = client.get("/api/v1/authors/1")

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == "1"
    assert data["full_name"] == "John Doe"
    assert data["hf_username"] == "johndoe"
    assert data["hf_is_pro"] is True
    assert data["paper_count"] == 2


def test_hf_author_lists_only_claimed_papers(client, sample_authors):
    """An author with an HF account does not get namesake papers by name."""
    author = client.get("/api/v1/authors/3").json()
    papers = client.get("/api/v1/authors/3/papers").json()
    listed = client.get("/api/v1/authors/?search=Alice").json()["results"]

    assert author["paper_count"] == 0
    assert papers["count"] == 0
    assert [entry["paper_count"] for entry in listed] == [0]


def test_name_only_author_lists_every_matched_paper(client, sample_authors):
    """An author without an HF account lists all papers matched to its name."""
    assert client.get("/api/v1/authors/2/papers").json()["count"] == 1


def test_get_author_not_found(client, sample_authors):
    """Test getting non-existent author."""
    response = client.get("/api/v1/authors/999")

    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


def test_get_author_papers(client, sample_authors):
    """Test getting papers by author."""
    response = client.get("/api/v1/authors/1/papers")

    assert response.status_code == 200
    data = response.json()

    assert data["count"] == 2
    assert len(data["results"]) == 2

    # Check paper structure
    paper = data["results"][0]
    assert "id" in paper
    assert "title" in paper
    assert "arxiv_id" in paper


def test_search_authors(client, sample_authors):
    """Test searching authors."""
    response = client.get("/api/v1/authors/?search=John")

    assert response.status_code == 200
    data = response.json()

    assert data["count"] >= 1
    # Should find "John Doe"
    found_john = any(author["full_name"] == "John Doe" for author in data["results"])
    assert found_john


def test_search_authors_by_username(client, sample_authors):
    """Test searching authors by Hugging Face username."""
    response = client.get("/api/v1/authors/?search=alicej")

    assert response.status_code == 200
    data = response.json()

    assert data["count"] >= 1
    # Should find "Alice Johnson"
    found_alice = any(author["hf_username"] == "alicej" for author in data["results"])
    assert found_alice


def test_search_authors_single_character(client, sample_authors):
    """Test that the canonical author filter accepts a single character."""
    response = client.get("/api/v1/authors/?search=a")

    assert response.status_code == 200


def test_authors_ordering(client, sample_authors):
    """Test different ordering options."""
    # Test ordering by name
    response = client.get("/api/v1/authors/?order_by=name&order_dir=asc")

    assert response.status_code == 200
    data = response.json()

    names = [author["full_name"] for author in data["results"]]
    assert names == sorted(names)  # Should be alphabetically sorted


if __name__ == "__main__":
    pytest.main([__file__])
