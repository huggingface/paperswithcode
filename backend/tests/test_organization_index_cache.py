"""The public organization directory is cached and refreshed on PostgreSQL."""

from contextlib import nullcontext
from types import SimpleNamespace

from backend.models.organizations import Organizations
from backend.services import organization_service
from backend.services.organization_service import OrganizationService


def test_stale_directory_cards_are_served_while_one_refresh_runs(monkeypatch):
    bind = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"), url="postgresql://catalog"
    )
    service = OrganizationService(SimpleNamespace(get_bind=lambda: bind))
    calls = []

    def build(curated_only):
        calls.append(curated_only)
        return Organizations(count=len(calls), results=[])

    threads = []

    class RecordedThread:
        def __init__(self, target, args, **_kwargs):
            self.run = lambda: target(*args)

        def start(self):
            threads.append(self)

    clock = iter([100.0, 200.0, 800.0, 801.0, 802.0, 803.0])
    monkeypatch.setattr(service, "get_organizations", build)
    monkeypatch.setattr(organization_service.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(organization_service.threading, "Thread", RecordedThread)
    monkeypatch.setattr(organization_service, "Session", lambda bind: nullcontext())
    monkeypatch.setattr(
        organization_service,
        "OrganizationService",
        lambda _db: SimpleNamespace(get_organizations=build),
    )
    monkeypatch.setattr(organization_service, "_organization_index_cache", {})
    monkeypatch.setattr(organization_service, "_organization_index_refreshing", set())

    assert service.get_organization_index().count == 1
    assert service.get_organization_index().count == 1
    # Past the TTL the stale cards return at once and only one refresh starts.
    assert service.get_organization_index().count == 1
    assert service.get_organization_index().count == 1
    assert len(threads) == 1

    threads[0].run()
    assert service.get_organization_index().count == 2
    assert calls == [True, True]
    assert organization_service._organization_index_refreshing == set()
