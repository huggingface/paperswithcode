"""The public organization directory is cached briefly on PostgreSQL."""

from types import SimpleNamespace

from backend.models.organizations import Organizations
from backend.services import organization_service
from backend.services.organization_service import OrganizationService


def test_directory_cards_are_cached_until_the_ttl_expires(monkeypatch):
    bind = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"), url="postgresql://catalog"
    )
    service = OrganizationService(SimpleNamespace(get_bind=lambda: bind))
    calls = []

    def build(curated_only):
        calls.append(curated_only)
        return Organizations(count=len(calls), results=[])

    clock = iter([100.0, 200.0, 800.0])
    monkeypatch.setattr(service, "get_organizations", build)
    monkeypatch.setattr(organization_service.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(organization_service, "_organization_index_cache", {})

    assert service.get_organization_index().count == 1
    assert service.get_organization_index().count == 1
    assert service.get_organization_index().count == 2
    assert calls == [True, True]
