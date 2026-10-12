import asyncio
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from backend.models.database import ChatSandboxComputeInterval
from backend.scripts import qualify_chat_sandbox_spend
from backend.services.chat_sandbox_spend_service import ChatSandboxSpendService
from backend.tests.chat_sandbox.test_spend_service import factory, settings


def test_deliver_all_spend_alerts_drains_bounded_batches(monkeypatch):
    batches = iter((10, 2, 0))

    class Manager:
        def __init__(self, settings):
            assert settings is sentinel

        async def deliver_spend_alerts(self):
            return next(batches)

    sentinel = object()
    monkeypatch.setattr(qualify_chat_sandbox_spend, "SandboxSessionManager", Manager)

    assert (
        asyncio.run(qualify_chat_sandbox_spend.deliver_all_spend_alerts(sentinel)) == 12
    )


def test_fallback_probe_selects_only_the_warning_transition():
    statement = qualify_chat_sandbox_spend.fallback_spend_event_statement(
        "production-q-probe-f"
    )
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )

    assert "event_type = 'warning_entered'" in compiled
    assert "environment = 'production-q-probe-f'" in compiled


def test_concurrent_reservation_probe_releases_every_admitted_reservation():
    session_local = factory()
    base = settings(environment="production-q-probe")
    with session_local() as db:
        reservation = ChatSandboxSpendService(db, base).reservation_amount()
    reservation_settings = base.model_copy(
        update={
            "environment": "production-q-probe-r",
            "chat_sandbox_warning_microusd": 1,
            "chat_sandbox_application_cap_microusd": reservation * 3 + 1,
            "chat_sandbox_environment_cap_microusd": reservation * 4 + 1,
            "chat_sandbox_workspace_cap_microusd": reservation * 5 + 1,
            "chat_sandbox_budget_attestation": "synthetic-concurrency-v1",
        }
    )
    now = datetime(2026, 10, 12, tzinfo=UTC)

    # SQLite shares one connection, so admit sequentially; production uses 8.
    accepted = qualify_chat_sandbox_spend.qualify_concurrent_reservations(
        session_local, reservation_settings, now, workers=1
    )

    assert len(accepted) == 3
    with session_local() as db:
        rows = db.execute(select(ChatSandboxComputeInterval)).scalars().all()
    assert len(rows) == 3
    assert {row.environment for row in rows} == {"production-q-probe-r"}
    assert all(row.terminal_at is not None for row in rows)
    assert {row.terminal_reason for row in rows} == {"qualification_complete"}
    assert {row.reserved_microusd for row in rows} == {0}
