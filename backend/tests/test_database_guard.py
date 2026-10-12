"""The test suite must never open a connection to a live PostgreSQL database."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from backend.tests.conftest import LiveDatabaseRefused, database_refusal_reason


@pytest.mark.parametrize(
    "environ",
    [
        {},
        {"PWC_ENVIRONMENT": "production"},
        {"PWC_TEST_DATABASE": "true"},
        {"PWC_TEST_DATABASE": "1", "PWC_ENVIRONMENT": "production"},
        {"PWC_TEST_DATABASE": "1", "PWC_ENVIRONMENT": "Staging"},
    ],
)
def test_refuses_unless_explicit_test_database(environ):
    assert database_refusal_reason(environ) is not None


@pytest.mark.parametrize(
    "environ",
    [
        {"PWC_TEST_DATABASE": "1"},
        {"PWC_TEST_DATABASE": "1", "PWC_ENVIRONMENT": "development"},
    ],
)
def test_allows_explicit_test_database(environ):
    assert database_refusal_reason(environ) is None


def test_sqlalchemy_postgres_engine_is_refused_without_opt_in(monkeypatch):
    monkeypatch.delenv("PWC_TEST_DATABASE", raising=False)
    # Port 9 is unused; the guard must refuse before any network attempt.
    engine = create_engine("postgresql://guard@127.0.0.1:9/paperswithcode_hf")
    with pytest.raises(LiveDatabaseRefused, match="PWC_TEST_DATABASE=1"):
        with engine.connect():
            pass


def test_sqlite_is_unaffected(monkeypatch):
    monkeypatch.delenv("PWC_TEST_DATABASE", raising=False)
    with create_engine("sqlite://").connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar() == 1
