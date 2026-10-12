import asyncio

from sqlalchemy.dialects import postgresql

from backend.scripts import qualify_chat_sandbox_spend


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
