"""The public organization directory is cached and refreshed on PostgreSQL."""

import threading
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
    monkeypatch.setattr(organization_service, "_organization_index_warmed", {})

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


def test_startup_warm_fills_the_cache_without_a_duplicate_refresh(monkeypatch):
    bind = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"), url="postgresql://catalog"
    )
    threads = []

    class RecordedThread:
        def __init__(self, target, args=(), **_kwargs):
            self.run = lambda: target(*args)

        def start(self):
            threads.append(self)

    built = Organizations(count=7, results=[])
    monkeypatch.setattr(organization_service.threading, "Thread", RecordedThread)
    monkeypatch.setattr(organization_service, "Session", lambda bind: nullcontext())
    monkeypatch.setattr(
        organization_service,
        "OrganizationService",
        lambda _db: SimpleNamespace(get_organizations=lambda curated_only: built),
    )
    monkeypatch.setattr(organization_service, "_organization_index_cache", {})
    monkeypatch.setattr(organization_service, "_organization_index_refreshing", set())
    monkeypatch.setattr(organization_service, "_organization_index_warmed", {})

    organization_service.warm_organization_index(bind)
    assert organization_service._organization_index_refreshing == {
        "postgresql://catalog"
    }

    threads[0].run()
    assert (
        organization_service._organization_index_cache["postgresql://catalog"][1]
        is built
    )
    assert organization_service._organization_index_refreshing == set()


def test_cold_request_waits_for_the_startup_warm_instead_of_rebuilding(monkeypatch):
    bind = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"), url="postgresql://catalog"
    )
    release = threading.Event()
    calls = []

    def build(curated_only):
        calls.append(curated_only)
        release.wait(5)
        return Organizations(count=len(calls), results=[])

    service = OrganizationService(SimpleNamespace(get_bind=lambda: bind))
    monkeypatch.setattr(service, "get_organizations", build)
    monkeypatch.setattr(organization_service, "Session", lambda bind: nullcontext())
    monkeypatch.setattr(
        organization_service,
        "OrganizationService",
        lambda _db: SimpleNamespace(get_organizations=build),
    )
    monkeypatch.setattr(organization_service, "_organization_index_cache", {})
    monkeypatch.setattr(organization_service, "_organization_index_refreshing", set())
    monkeypatch.setattr(organization_service, "_organization_index_warmed", {})

    organization_service.warm_organization_index(bind)
    threading.Timer(0.05, release.set).start()

    assert service.get_organization_index().count == 1
    assert calls == [True]
