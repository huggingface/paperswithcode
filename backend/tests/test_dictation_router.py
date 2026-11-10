from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from backend.config import Settings
from backend.models.database import DictationSession
from backend.routers import dictation
from backend.services import dictation_service


def _settings(**overrides) -> Settings:
    values = dict(
        _env_file=None,
        dictation_enabled=True,
        dictation_endpoint_url="https://voxtral.example",
        hf_token="hf_test",
        openai_api_key="sk-test",
    )
    values.update(overrides)
    return Settings(**values)


def _request(headers: dict[str, str] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/internal/dictation/authorize",
            "headers": [
                (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
            ],
            "query_string": b"",
            "scheme": "https",
            "server": ("paperswithcode.co", 443),
            "client": ("127.0.0.1", 1234),
        }
    )


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(
        dictation_service, "probe_endpoint", lambda url, token, *, wake: True
    )
    engine = create_engine("sqlite://")
    DictationSession.__table__.create(engine)
    with Session(engine) as session:
        yield session


def _issue(db, settings) -> dictation.DictationSessionResponse:
    return dictation.create_dictation_session({"hf_subject": "hf-alice"}, db, settings)


def test_session_returns_a_same_origin_ticket_url(db):
    issued = _issue(db, _settings())
    assert issued.ws_url.startswith("/api/v1/dictation/ws?ticket=")
    assert issued.provider == "voxtral"


def test_authorize_returns_upstream_only_in_headers(db):
    settings = _settings()
    issued = _issue(db, settings)
    response = dictation.authorize_dictation_relay(
        _request(
            {"X-PwC-Dictation-Relay": "auth-request", "X-Original-URI": issued.ws_url}
        ),
        db,
        settings,
    )
    assert response.status_code == 204
    assert response.body == b""
    assert (
        response.headers["X-PwC-Dictation-Upstream"]
        == "https://voxtral.example/v1/realtime"
    )
    assert response.headers["X-PwC-Dictation-Authorization"] == "Bearer hf_test"


def test_authorize_requires_the_relay_header(db):
    settings = _settings()
    issued = _issue(db, settings)
    with pytest.raises(HTTPException) as error:
        dictation.authorize_dictation_relay(
            _request({"X-Original-URI": issued.ws_url}), db, settings
        )
    assert error.value.status_code == 404


def test_authorize_rejects_a_used_ticket(db):
    settings = _settings()
    issued = _issue(db, settings)
    headers = {"X-PwC-Dictation-Relay": "auth-request", "X-Original-URI": issued.ws_url}
    dictation.authorize_dictation_relay(_request(headers), db, settings)
    with pytest.raises(HTTPException) as error:
        dictation.authorize_dictation_relay(_request(headers), db, settings)
    assert error.value.status_code == 403


def test_disabled_dictation_hides_every_route(db):
    settings = _settings(dictation_enabled=False)
    status = dictation.dictation_status(_request(), db, settings)
    assert status.enabled is False
    with pytest.raises(HTTPException) as error:
        _issue(db, settings)
    assert error.value.status_code == 404


def test_anonymous_status_does_not_wake_the_endpoint(db, monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("anonymous visitors must not wake the GPU")

    monkeypatch.setattr(dictation_service, "probe_endpoint", fail)
    status = dictation.dictation_status(_request(), db, _settings())
    assert status.enabled is True
    assert status.signed_in is False
    assert status.provider is None


def test_unavailable_maps_to_status_codes(db):
    settings = _settings(dictation_user_daily_seconds=0)
    with pytest.raises(HTTPException) as error:
        _issue(db, settings)
    assert error.value.status_code == 429
    assert error.value.detail == {"code": "daily_limit"}
