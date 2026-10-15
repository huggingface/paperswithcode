"""
Tests for the ranked "Related methods" list on a method page.

Related methods come from curated siblings, then description links in either
direction, then methods co-tagged on the same papers. Same-area popularity is
not a signal: a popular method in the same area must not appear on its own.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, event
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import create_app
from backend.database.connection import get_database_session
from backend.models.database import (
    Area as DBArea,
    Base,
    Method as DBMethod,
    PaperMethod,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(engine, "connect")
def register_jsonb_typeof(dbapi_connection, _connection_record):
    """Let SQLite create PostgreSQL JSONB check constraints in this test DB."""
    dbapi_connection.create_function("jsonb_typeof", 1, lambda _value: "array")


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_database_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)
    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session
    with TestClient(app) as test_client:
        seed_methods(TestingSessionLocal())
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def seed_methods(db):
    db.add(DBArea(id=1, name="General"))
    methods = {
        1: ("XGBoost", "xgboost", "Boosted trees."),
        2: ("LightGBM", "lightgbm", "Faster than [XGBoost](/methods/xgboost)."),
        3: ("CatBoost", "catboost", "Ordered boosting."),
        4: ("Random Forest", "random-forest", "Bagged trees."),
        5: ("Large Language Model", "large-language-model-llm", "Popular."),
        6: ("MCP", "mcp", "Protocol."),
        7: ("Agent Skills", "agent-skills", "Skills."),
    }
    db.add_all(
        DBMethod(id=i, name=name, slug=slug, description=desc, area_id=1)
        for i, (name, slug, desc) in methods.items()
    )
    links = []
    # XGBoost shares 4 papers with Random Forest and 3 with CatBoost.
    links += [(p, 1) for p in range(1, 9)]
    links += [(p, 4) for p in range(1, 5)]
    links += [(p, 3) for p in range(6, 9)]
    # The LLM method is on many papers but shares only 2 with XGBoost.
    links += [(p, 5) for p in [*range(7, 9), *range(100, 200)]]
    db.add_all(PaperMethod(paper_id=p, method_id=m) for p, m in links)
    db.commit()
    db.close()


def related(client, slug):
    response = client.get(f"/api/v1/methods/{slug}/related")
    assert response.status_code == 200
    return [m["slug"] for m in response.json()["results"]]


def test_description_links_come_first_then_co_tagged_methods(client):
    # LightGBM links to XGBoost from its own description, so XGBoost leads
    # even though they share no papers; the popular LLM method never appears.
    assert related(client, "xgboost") == ["lightgbm", "random-forest", "catboost"]
    assert related(client, "lightgbm") == ["xgboost"]


def test_curated_siblings_are_listed(client):
    assert related(client, "mcp") == ["agent-skills"]


def test_method_without_signals_has_no_related_methods(client):
    assert related(client, "large-language-model-llm") == []


def test_mixed_case_slug_resolves(client):
    assert related(client, "LightGBM") == ["xgboost"]
    assert related(client, "Random-Forest") == ["xgboost"]


def test_unknown_method_returns_404(client):
    assert client.get("/api/v1/methods/nope/related").status_code == 404
