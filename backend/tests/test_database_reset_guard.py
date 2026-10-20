"""``reset`` must never drop tables outside a confirmed disposable database."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.database import connection
from backend.database.connection import (
    DatabaseManager,
    DestructiveDatabaseOperationRefused,
    drop_refusal_reason,
)


def make_settings(environment="development", db_name="pwc_scratch"):
    return SimpleNamespace(
        environment=environment,
        db_name=db_name,
        database_log_identifier=f"postgres@127.0.0.1:55441/{db_name}",
    )


@pytest.mark.parametrize(
    ("environment", "confirm"),
    [
        ("production", "pwc_scratch"),
        ("Staging", "pwc_scratch"),
        ("development", None),
        ("development", ""),
        ("development", "paperswithcode_hf"),
    ],
)
def test_refuses_live_environments_and_unconfirmed_databases(environment, confirm):
    assert drop_refusal_reason(make_settings(environment), confirm) is not None


def test_allows_confirmed_disposable_database():
    assert drop_refusal_reason(make_settings(), "pwc_scratch") is None


def manager_with(settings):
    manager = DatabaseManager.__new__(DatabaseManager)
    manager.settings = settings
    manager._engine = object()
    manager._session_local = None
    return manager


def test_drop_tables_refuses_without_touching_the_database():
    manager = manager_with(make_settings("production"))
    with patch.object(connection.Base.metadata, "drop_all") as drop_all:
        with pytest.raises(DestructiveDatabaseOperationRefused, match="production"):
            manager.drop_tables("pwc_scratch")
        with pytest.raises(DestructiveDatabaseOperationRefused):
            manager_with(make_settings()).drop_tables()
    drop_all.assert_not_called()


def test_drop_tables_runs_for_confirmed_disposable_database():
    manager = manager_with(make_settings())
    with patch.object(connection.Base.metadata, "drop_all") as drop_all:
        manager.drop_tables("pwc_scratch")
    drop_all.assert_called_once_with(bind=manager._engine)


def test_reset_cli_requires_confirmation(capsys):
    with patch.object(connection, "reset_database") as reset:
        with pytest.raises(SystemExit) as exit_info:
            connection.main(["reset"])
    assert exit_info.value.code == 2
    reset.assert_not_called()
    assert "--confirm" in capsys.readouterr().err


def test_reset_cli_refuses_mismatched_confirmation(capsys):
    manager = manager_with(make_settings(db_name="paperswithcode_hf"))
    with (
        patch.object(connection, "db_manager", manager),
        patch.object(connection.Base.metadata, "drop_all") as drop_all,
        patch.object(connection.Base.metadata, "create_all") as create_all,
    ):
        assert connection.main(["reset", "--confirm", "pwc_scratch"]) == 1
    drop_all.assert_not_called()
    create_all.assert_not_called()
    assert "does not match" in capsys.readouterr().out


def test_reset_cli_drops_and_recreates_confirmed_database():
    manager = manager_with(make_settings())
    with (
        patch.object(connection, "db_manager", manager),
        patch.object(connection.Base.metadata, "drop_all") as drop_all,
        patch.object(connection.Base.metadata, "create_all") as create_all,
    ):
        assert connection.main(["reset", "--confirm", "pwc_scratch"]) == 0
    drop_all.assert_called_once_with(bind=manager._engine)
    create_all.assert_called_once_with(bind=manager._engine)


def test_init_cli_creates_tables_without_confirmation():
    with patch.object(connection, "init_database") as init:
        assert connection.main(["init"]) == 0
    init.assert_called_once_with()
