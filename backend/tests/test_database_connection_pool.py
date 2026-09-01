from types import SimpleNamespace

from backend.database.connection import database_pool_configuration


def test_single_staging_worker_can_serve_32_simultaneous_chat_turns(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    settings = SimpleNamespace(environment="staging")

    assert database_pool_configuration(settings) == {
        "pool_size": 32,
        "max_overflow": 8,
        "pool_timeout": 5,
    }


def test_staging_pool_budget_is_partitioned_across_web_workers(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    settings = SimpleNamespace(environment="staging")

    assert database_pool_configuration(settings) == {
        "pool_size": 8,
        "max_overflow": 2,
        "pool_timeout": 5,
    }


def test_production_pool_remains_conservative():
    settings = SimpleNamespace(environment="production")

    assert database_pool_configuration(settings) == {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 5,
    }
