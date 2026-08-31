from types import SimpleNamespace

from backend.database.connection import database_pool_configuration


def test_staging_pool_can_serve_32_simultaneous_chat_turns():
    settings = SimpleNamespace(environment="staging")

    assert database_pool_configuration(settings) == {
        "pool_size": 32,
        "max_overflow": 8,
        "pool_timeout": 5,
    }


def test_production_pool_remains_conservative():
    settings = SimpleNamespace(environment="production")

    assert database_pool_configuration(settings) == {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_timeout": 5,
    }
