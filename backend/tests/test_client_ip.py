"""Client IP resolution behind production's unix-socket nginx upstream."""

import asyncio

import pytest
from fastapi import Response
from starlette.requests import Request

from backend.routers import paper_edits as paper_edits_router
from backend.routers import papers as papers_router
from backend.routers import pending_edits as pending_edits_router
from backend.models.paper_edits import DeviceStart
from backend.services.paper_edit_access import token_hash
from backend.utils.client_ip import get_proxied_client_ip

USER = {"username": "submitter", "hf_subject": "hf-subject", "role": "user"}


def _request(client, real_ip=None) -> Request:
    headers = [(b"x-real-ip", real_ip.encode())] if real_ip is not None else []
    return Request(
        {"type": "http", "method": "POST", "client": client, "headers": headers}
    )


class Captured(Exception):
    pass


@pytest.mark.parametrize(
    ("client", "real_ip", "expected"),
    [
        (None, "203.0.113.8", "203.0.113.8"),
        (None, " 2001:db8::1 ", "2001:db8::1"),
        (None, None, None),
        (None, "not-an-ip", None),
        (("127.0.0.1", 1), "203.0.113.8", "203.0.113.8"),
        (("127.0.0.1", 1), None, "127.0.0.1"),
        (("198.51.100.4", 1), "203.0.113.8", "198.51.100.4"),
    ],
)
def test_proxied_client_ip(client, real_ip, expected):
    assert get_proxied_client_ip(_request(client, real_ip)) == expected


def test_paper_submission_records_unix_socket_client_ip(monkeypatch):
    commands = []

    class SubmissionService:
        def __init__(self, db, indexing_logger):
            pass

        async def submit(self, command):
            commands.append(command)
            raise Captured

    monkeypatch.setattr(papers_router, "PaperSubmissionService", SubmissionService)
    with pytest.raises(Captured):
        asyncio.run(
            papers_router.submit_paper(
                http_request=_request(None, "203.0.113.8"),
                response=Response(),
                request=papers_router.PaperSubmitRequest(
                    source_url="https://example.com/paper"
                ),
                idempotency_key=None,
                user=USER,
                db=object(),
            )
        )
    assert commands[0].source_ip == "203.0.113.8"


def test_pending_edit_records_unix_socket_client_ip(monkeypatch):
    calls = []

    class PendingService:
        def __init__(self, db):
            pass

        def submit(self, **kwargs):
            calls.append(kwargs)
            raise Captured

    monkeypatch.setattr(pending_edits_router, "PendingEditService", PendingService)
    with pytest.raises(Captured):
        pending_edits_router.submit_pending_paper_edit(
            body=pending_edits_router.PendingEditSubmitRequest(
                paper_id=1, edit_type="tasks", proposed_payload={"task_ids": [1]}
            ),
            request=_request(None, "203.0.113.8"),
            response=Response(),
            idempotency_key=None,
            user=USER,
            db=object(),
        )
    assert calls[0]["source_ip"] == "203.0.113.8"


def test_paper_edit_authorization_keys_on_unix_socket_client_ip(monkeypatch):
    client_keys = []

    class AuthorizationService:
        def __init__(self, db):
            pass

        def start(self, paper_id, client_key):
            client_keys.append(client_key)
            return {}

    monkeypatch.setattr(
        paper_edits_router, "PaperEditAuthorizationService", AuthorizationService
    )
    paper_edits_router.start_authorization(
        DeviceStart(paper_id=1), Response(), _request(None, "203.0.113.8"), object()
    )
    assert client_keys == [token_hash("203.0.113.8")]
