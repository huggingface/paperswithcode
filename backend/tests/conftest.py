"""Keep the backend test suite away from live PostgreSQL databases.

DB-backed tests commit through ``db_manager.session_local()``. Run with
``backend/keys.env`` they would write fixture rows into the live catalog, so
every PostgreSQL connection opened under pytest is refused unless the run opts
into a disposable test database with ``PWC_TEST_DATABASE=1`` and is not
configured as production or staging. SQLite and mocked tests are unaffected.
"""

from __future__ import annotations

import os

import psycopg2
import pytest

TEST_DATABASE_OPT_IN = "PWC_TEST_DATABASE"
LIVE_ENVIRONMENTS = {"production", "staging"}


class LiveDatabaseRefused(RuntimeError):
    """Raised when a test tries to connect to a database not marked as a test DB."""


def database_refusal_reason(environ) -> str | None:
    if environ.get(TEST_DATABASE_OPT_IN) != "1":
        return (
            f"{TEST_DATABASE_OPT_IN}=1 is not set, so the configured PostgreSQL "
            "database is assumed to be live"
        )
    environment = environ.get("PWC_ENVIRONMENT", "development").lower()
    if environment in LIVE_ENVIRONMENTS:
        return f"PWC_ENVIRONMENT={environment} names a live environment"
    return None


def pytest_configure(config):
    real_connect = psycopg2.connect

    def guarded_connect(*args, **kwargs):
        reason = database_refusal_reason(os.environ)
        if reason is not None:
            raise LiveDatabaseRefused(
                f"Refusing a PostgreSQL connection from the test suite: {reason}. "
                "DB-backed tests commit rows, so point PWC_DB_* at a disposable "
                f"database and set {TEST_DATABASE_OPT_IN}=1 "
                "(see docs/development-guide.md#database-backed-tests)."
            )
        return real_connect(*args, **kwargs)

    # SQLAlchemy's psycopg2 dialect resolves ``psycopg2.connect`` at connect
    # time, so this also covers engines built from ``db_manager``.
    psycopg2.connect = guarded_connect
    config.add_cleanup(lambda: setattr(psycopg2, "connect", real_connect))


@pytest.fixture(autouse=True)
def _build_as_the_test_user(monkeypatch):
    """Run deploy build steps directly when the suite itself runs as root.

    ``deploy.build_sandbox`` drops to the ``pwc-build`` account whenever the
    caller is root, which on a deployment host would also apply to tests.
    ``test_build_sandbox.py`` covers the privilege drop explicitly.
    """

    from deploy import build_sandbox

    monkeypatch.setattr(build_sandbox, "enabled", lambda: False)
