from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import DictationSession
from backend.services.dictation_service import (
    OPENAI,
    OPENAI_REALTIME_URL,
    VOXTRAL,
    DictationService,
    DictationTicketRejected,
    DictationUnavailable,
    hash_ticket,
    ticket_from_uri,
)

ENDPOINT = "https://voxtral.endpoints.huggingface.cloud"


def _settings(**overrides) -> Settings:
    values = dict(
        _env_file=None,
        dictation_enabled=True,
        dictation_endpoint_url=ENDPOINT,
        hf_token="hf_test",
        openai_api_key="sk-test",
        dictation_session_seconds=120,
        dictation_user_daily_seconds=1800,
        dictation_openai_daily_seconds=600,
        dictation_voxtral_capacity=2,
    )
    values.update(overrides)
    return Settings(**values)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    DictationSession.__table__.create(engine)
    with Session(engine) as session:
        yield session


def _service(db, *, ready=True, clock=None, **overrides) -> DictationService:
    return DictationService(
        db,
        _settings(**overrides),
        probe=lambda url, token, *, wake: ready,
        now=clock or Clock(),
    )


def test_ticket_is_single_use_and_names_the_voxtral_upstream(db):
    service = _service(db)
    issued = service.issue("user-1")

    assert issued.provider == VOXTRAL
    assert issued.sample_rate == 16_000
    assert issued.prompt is None
    stored = db.scalar(select(DictationSession))
    assert stored.ticket_hash == hash_ticket(issued.ticket) != issued.ticket

    upstream = service.authorize(issued.ticket)
    assert upstream.url == f"{ENDPOINT}/v1/realtime"
    assert upstream.authorization == "Bearer hf_test"
    with pytest.raises(DictationTicketRejected):
        service.authorize(issued.ticket)


def test_ticket_expires_after_thirty_seconds(db):
    clock = Clock()
    service = _service(db, clock=clock)
    issued = service.issue("user-1")
    clock.advance(seconds=31)
    with pytest.raises(DictationTicketRejected):
        service.authorize(issued.ticket)


def test_unknown_ticket_is_rejected(db):
    with pytest.raises(DictationTicketRejected):
        _service(db).authorize("not-a-ticket")


def test_cold_endpoint_falls_back_to_openai_with_vocabulary(db):
    service = _service(db, ready=False)
    issued = service.issue("user-1")

    assert issued.provider == OPENAI
    assert issued.sample_rate == 24_000
    assert "LoRA" in issued.prompt
    upstream = service.authorize(issued.ticket)
    assert upstream.url == OPENAI_REALTIME_URL
    assert upstream.authorization == "Bearer sk-test"


def test_full_voxtral_overflows_to_openai(db):
    service = _service(db)
    for user in ("a", "b"):
        service.authorize(service.issue(user).ticket)

    assert service.issue("c").provider == OPENAI


def test_no_provider_while_cold_and_openai_cap_spent(db):
    clock = Clock()
    service = _service(db, ready=False, clock=clock, dictation_openai_daily_seconds=200)
    first = service.issue("a")
    service.authorize(first.ticket)
    service.finish("a", first.session_id, 120)

    assert service.status("b").provider is None
    assert service.status("b").reason == "starting"
    with pytest.raises(DictationUnavailable) as error:
        service.issue("b")
    assert error.value.reason == "starting"


def test_busy_when_voxtral_full_and_no_openai_key(db):
    service = _service(db, openai_api_key="", dictation_voxtral_capacity=1)
    service.authorize(service.issue("a").ticket)
    assert service.status("b").reason == "busy"


def test_one_live_session_per_user(db):
    clock = Clock()
    service = _service(db, clock=clock)
    service.authorize(service.issue("a").ticket)
    with pytest.raises(DictationUnavailable) as error:
        service.issue("a")
    assert error.value.reason == "already_dictating"

    clock.advance(seconds=136)
    assert service.issue("a").provider == VOXTRAL


def test_new_ticket_replaces_an_unused_one(db):
    service = _service(db)
    stale = service.issue("a")
    fresh = service.issue("a")
    with pytest.raises(DictationTicketRejected):
        service.authorize(stale.ticket)
    service.authorize(fresh.ticket)


def test_daily_allowance_charges_reservations_until_finished(db):
    clock = Clock()
    service = _service(db, clock=clock, dictation_user_daily_seconds=300)
    first = service.issue("a")
    service.authorize(first.ticket)
    assert service.status("a").remaining_seconds == 180

    service.finish("a", first.session_id, 42.4)
    assert service.status("a").remaining_seconds == 258

    # Finishing again, or as someone else, changes nothing.
    service.finish("a", first.session_id, 0)
    service.finish("b", first.session_id, 0)
    assert service.status("a").remaining_seconds == 258


def test_reported_seconds_are_clamped_to_the_reservation(db):
    service = _service(db)
    issued = service.issue("a")
    service.authorize(issued.ticket)
    service.finish("a", issued.session_id, 9_999)
    assert db.get(DictationSession, issued.session_id).used_seconds == 120


def test_unused_tickets_cost_nothing(db):
    clock = Clock()
    service = _service(db, clock=clock, dictation_user_daily_seconds=120)
    service.issue("a")
    clock.advance(seconds=40)
    assert service.status("a").remaining_seconds == 120


def test_daily_limit_blocks_and_resets_next_day(db):
    clock = Clock()
    service = _service(db, clock=clock, dictation_user_daily_seconds=120)
    issued = service.issue("a")
    service.authorize(issued.ticket)
    service.finish("a", issued.session_id, 120)

    assert service.status("a").reason == "daily_limit"
    with pytest.raises(DictationUnavailable):
        service.issue("a")

    clock.advance(days=1)
    assert service.status("a").provider == VOXTRAL


def test_last_session_of_the_day_is_shortened_to_the_allowance(db):
    service = _service(db, dictation_user_daily_seconds=150)
    first = service.issue("a")
    service.authorize(first.ticket)
    service.finish("a", first.session_id, 120)
    assert service.issue("a").max_seconds == 30


def test_ticket_is_read_from_the_original_uri():
    assert ticket_from_uri("/api/v1/dictation/ws?ticket=abc-123") == "abc-123"
    assert ticket_from_uri("/api/v1/dictation/ws") == ""


def test_status_does_not_wake_the_endpoint_but_a_tap_does(db):
    calls = []

    def probe(url, token, *, wake):
        calls.append(wake)
        return wake

    service = DictationService(db, _settings(), probe=probe, now=Clock())
    assert service.status("a").provider == OPENAI
    assert calls == [False]
    assert service.issue("a").provider == VOXTRAL
    assert calls == [False, True]


def test_status_wakes_the_endpoint_when_openai_cannot_serve(db):
    calls = []

    def probe(url, token, *, wake):
        calls.append(wake)
        return False

    service = DictationService(
        db, _settings(openai_api_key=""), probe=probe, now=Clock()
    )
    assert service.status("a").reason == "starting"
    assert calls == [True]


def test_probe_without_wake_sends_nothing_and_reuses_a_fresh_answer(monkeypatch):
    from backend.services import dictation_service

    sent = []

    def fake_get(url, **_kwargs):
        sent.append(url)
        return type("Response", (), {"status_code": 200})()

    monkeypatch.setattr(dictation_service.httpx, "get", fake_get)
    monkeypatch.setattr(dictation_service, "_probe_cache", {})
    url = "https://wake-test.example"
    assert dictation_service.probe_endpoint(url, "t", wake=False) is False
    assert sent == []
    assert dictation_service.probe_endpoint(url, "t") is True
    assert dictation_service.probe_endpoint(url, "t", wake=False) is True
    assert sent == [f"{url}/health"]
