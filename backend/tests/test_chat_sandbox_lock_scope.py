"""Advisory lock keys must never be shared across environments.

Production and staging share one PostgreSQL database, so an unscoped
advisory key lets one environment's watchdog block the other's requests.
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from backend.services.chat_sandbox_capacity_repository import (
    CAPACITY_LOCK_NAME,
    capacity_lock_key,
    lock_capacity,
)
from backend.services.chat_sandbox_pool_maintenance_coordinator import (
    POOL_MAINTENANCE_LOCK_NAME,
    lock_pool_maintenance,
    pool_maintenance_lock_key,
)


class _Bind:
    class dialect:
        name = "postgresql"


class _Session:
    """Record the statement a lock helper issues without a database."""

    def __init__(self, result: object = True):
        self.statements: list[str] = []
        self._result = result

    def get_bind(self):
        return _Bind()

    def scalar(self, statement):
        self.statements.append(
            str(
                statement.compile(
                    dialect=postgresql.dialect(),
                    compile_kwargs={"literal_binds": True},
                )
            )
        )
        return self._result


def test_lock_keys_are_scoped_by_environment():
    assert capacity_lock_key("production") != capacity_lock_key("staging")
    assert capacity_lock_key("production").startswith(CAPACITY_LOCK_NAME)
    assert pool_maintenance_lock_key("production") != pool_maintenance_lock_key(
        "staging"
    )
    assert pool_maintenance_lock_key("staging").startswith(POOL_MAINTENANCE_LOCK_NAME)


def test_lock_capacity_hashes_the_environment_scoped_key():
    db = _Session()

    assert lock_capacity(db, environment="production") is True

    (statement,) = db.statements
    assert "pg_advisory_xact_lock" in statement
    assert capacity_lock_key("production") in statement
    assert f"'{CAPACITY_LOCK_NAME}'" not in statement


def test_lock_capacity_try_variant_reports_contention():
    db = _Session(result=False)

    assert lock_capacity(db, wait=False, environment="staging") is False

    (statement,) = db.statements
    assert "pg_try_advisory_xact_lock" in statement
    assert capacity_lock_key("staging") in statement


def test_lock_capacity_defaults_to_the_configured_environment(monkeypatch):
    from backend.services import chat_sandbox_capacity_repository as module

    class Settings:
        environment = "staging"

    monkeypatch.setattr(module, "get_settings", lambda: Settings())
    db = _Session()

    lock_capacity(db)

    assert capacity_lock_key("staging") in db.statements[0]


def test_lock_pool_maintenance_hashes_the_environment_scoped_key():
    db = _Session(result=True)

    assert lock_pool_maintenance(db, environment="production") is True

    (statement,) = db.statements
    assert "pg_try_advisory_xact_lock" in statement
    assert pool_maintenance_lock_key("production") in statement
