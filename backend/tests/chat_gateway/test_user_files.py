"""Gateway contract for uploaded chat files: placeholder swap, budget, refusal."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import Base, ChatSession, ChatUploadedFile
from backend.services.chat_openai_budget_service import (
    OpenAIRequestBounds,
    safe_maximum_microusd,
)
from backend.services.chat_provider_gateway.lifecycle import ParsedProviderRequest
from backend.services.chat_provider_gateway.openai_responses import (
    OpenAIResponsesProtocol,
)
from backend.services.chat_provider_gateway.user_files import (
    FILE_NOTICE,
    UNAVAILABLE,
    attach_user_files,
    placeholder,
    refuse_placeholders,
)

LUNA = "gpt-5.6-luna@openai"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[ChatSession.__table__, ChatUploadedFile.__table__]
    )
    with Session(engine) as session:
        yield session


def _session(db: Session, owner: str = "owner-1") -> uuid.UUID:
    session_id = uuid.uuid4()
    db.add(
        ChatSession(
            id=session_id,
            hf_user_id=owner,
            hf_username=owner,
            selected_model=LUNA,
            execution_backend="modal_cli",
        )
    )
    db.commit()
    return session_id


def _file(
    db: Session,
    session_id: uuid.UUID,
    *,
    media_type: str = "application/pdf",
    state: str = "ready",
    tokens: int = 5_000,
) -> ChatUploadedFile:
    row = ChatUploadedFile(
        id=uuid.uuid4(),
        session_id=session_id,
        hf_user_id="owner-1",
        filename='draft "v2".pdf',
        media_type=media_type,
        size_bytes=1234,
        sha256="a" * 64,
        page_count=12 if media_type == "application/pdf" else None,
        pdf_detail="high" if media_type == "application/pdf" else None,
        token_estimate=tokens,
        storage_key=f"chat-files/{uuid.uuid4()}",
        openai_file_id=f"file-{uuid.uuid4().hex[:8]}",
        state=state,
    )
    db.add(row)
    db.commit()
    return row


def _user(*texts: str) -> dict:
    return {
        "role": "user",
        "content": [{"type": "input_text", "text": t} for t in texts],
    }


def test_latest_user_message_gets_native_file_with_untrusted_notice(db):
    session_id = _session(db)
    pdf = _file(db, session_id)
    payload = {"input": [_user("Summarize this", placeholder(pdf.id))]}

    attached = attach_user_files(payload, db, session_id)

    notice, native = payload["input"][0]["content"][1:]
    assert FILE_NOTICE in notice["text"]
    assert 'name="draft &quot;v2&quot;.pdf"' in notice["text"]
    assert native == {
        "type": "input_file",
        "file_id": pdf.openai_file_id,
        "detail": "high",
    }
    assert attached.input_tokens == 5_000
    assert attached.trace == [
        {
            "id": str(pdf.id),
            "media_type": "application/pdf",
            "size_bytes": 1234,
            "page_count": 12,
            "pdf_detail": "high",
            "sha256": "a" * 64,
            "token_estimate": 5_000,
        }
    ]


def test_earlier_turns_keep_only_a_text_reference(db):
    session_id = _session(db)
    pdf = _file(db, session_id)
    payload = {
        "input": [
            _user("Summarize this", placeholder(pdf.id)),
            {"type": "message", "role": "assistant", "content": []},
            _user("And the conclusion?"),
        ]
    }

    attached = attach_user_files(payload, db, session_id)

    reference = payload["input"][0]["content"][1]
    assert reference["type"] == "input_text"
    assert "read_user_file" in reference["text"] and str(pdf.id) in reference["text"]
    assert attached.input_tokens == 0
    assert "file_id" not in json.dumps(payload)


def test_tool_output_after_latest_user_message_reattaches_natively(db):
    session_id = _session(db)
    image = _file(db, session_id, media_type="image/png", tokens=800)
    payload = {
        "input": [
            _user("What does the figure show?"),
            {"type": "function_call", "call_id": "c1", "name": "read_user_file"},
            {
                "type": "function_call_output",
                "call_id": "c1",
                "output": placeholder(image.id),
            },
        ]
    }

    attached = attach_user_files(payload, db, session_id)

    output = payload["input"][2]["output"]
    assert output[1] == {
        "type": "input_image",
        "file_id": image.openai_file_id,
        "detail": "auto",
    }
    assert attached.input_tokens == 800


def test_files_from_other_sessions_or_pending_uploads_are_never_attached(db):
    session_id = _session(db)
    foreign = _file(db, _session(db, owner="intruder"))
    pending = _file(db, session_id, state="pending")
    payload = {"input": [_user(placeholder(foreign.id), placeholder(pending.id))]}

    attached = attach_user_files(payload, db, session_id)

    assert payload["input"][0]["content"] == [
        {"type": "input_text", "text": UNAVAILABLE},
        {"type": "input_text", "text": UNAVAILABLE},
    ]
    assert attached.input_tokens == 0


def test_a_file_is_sent_natively_once_per_request(db):
    session_id = _session(db)
    pdf = _file(db, session_id)
    payload = {"input": [_user(placeholder(pdf.id), placeholder(pdf.id))]}

    attached = attach_user_files(payload, db, session_id)

    assert json.dumps(payload).count(pdf.openai_file_id) == 1
    assert attached.input_tokens == 5_000


def test_placeholder_text_inside_a_longer_message_is_left_alone(db):
    session_id = _session(db)
    pdf = _file(db, session_id)
    text = f"Paper quotes {placeholder(pdf.id)} verbatim"
    payload = {"input": [_user(text)]}

    attach_user_files(payload, db, session_id)

    assert payload["input"][0]["content"] == [{"type": "input_text", "text": text}]


def test_budget_reservation_covers_file_tokens():
    settings = Settings(
        _env_file=None,
        chat_openai_pricing_verified_at="2026-11-01",
    )
    now = datetime(2026, 11, 2, tzinfo=UTC)
    plain = safe_maximum_microusd(
        settings,
        OpenAIRequestBounds(request_bytes=1000, maximum_output_tokens=10),
        now=now,
    )
    with_file = safe_maximum_microusd(
        settings,
        OpenAIRequestBounds(
            request_bytes=1000, maximum_output_tokens=10, file_input_tokens=50_000
        ),
        now=now,
    )
    assert with_file > plain


def test_messages_adapter_refuses_placeholders():
    refuse_placeholders({"messages": [{"content": "hello"}]})
    payload = {"messages": [{"content": [{"text": placeholder(uuid.uuid4())}]}]}
    with pytest.raises(HTTPException) as error:
        refuse_placeholders(payload)
    assert error.value.status_code == 409


def _prepare(db, session_id, *, enabled: bool):
    settings = Settings(
        _env_file=None,
        environment="production",
        jwt_secret="test-secret-not-for-production",
        chat_openai_direct_enabled=True,
        openai_api_key="test-openai-key",
        chat_file_uploads_enabled=enabled,
    )
    pdf = _file(db, session_id)
    payload = {
        "model": settings.chat_openai_model,
        "max_output_tokens": 1000,
        "input": [_user("Read this", placeholder(pdf.id))],
    }
    row = SimpleNamespace(
        id=uuid.uuid4(),
        agent_harness="pi",
        provider_mode="openai_funded",
        model=settings.chat_openai_luna_route,
        reasoning_effort="low",
        owner_hash="owner-hash",
        chat_session_id=session_id,
        turn_id=uuid.uuid4(),
    )
    call = OpenAIResponsesProtocol(settings).prepare(
        ParsedProviderRequest(payload=payload, raw=json.dumps(payload).encode()),
        row,
        db,
        lambda: "owner-1",
        turn_id=row.turn_id,
    )
    return call, pdf


def test_responses_prepare_swaps_files_and_reserves_their_tokens(db):
    call, pdf = _prepare(db, _session(db), enabled=True)

    assert pdf.openai_file_id.encode() in call.raw
    assert call.ledger.file_input_tokens == 5_000
    assert call.trace_fields["user_files"][0]["id"] == str(pdf.id)
    assert call.payload["store"] is False


def test_responses_prepare_leaves_placeholders_while_disabled(db):
    call, pdf = _prepare(db, _session(db), enabled=False)

    assert pdf.openai_file_id.encode() not in call.raw
    assert call.ledger.file_input_tokens == 0
    assert "user_files" not in call.trace_fields


@pytest.mark.parametrize("bad_id", ["-" * 36, "a" * 36, "0" * 32 + "----"])
def test_malformed_placeholder_ids_are_left_as_text(db, bad_id):
    session_id = _session(db)
    text = f'<pwc_user_file id="{bad_id}"/>'
    payload = {"input": [_user(text)]}

    attached = attach_user_files(payload, db, session_id)

    assert payload["input"][0]["content"] == [{"type": "input_text", "text": text}]
    assert attached.input_tokens == 0


def test_placeholder_lines_inside_a_prompt_are_split_out(db):
    session_id = _session(db)
    pdf = _file(db, session_id)
    prompt = f"<user_files>\n{placeholder(pdf.id)}\n</user_files>\n<user_request>\nSummarize\n</user_request>"
    payload = {
        "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}]
    }

    attached = attach_user_files(payload, db, session_id)

    content = payload["input"][0]["content"]
    assert [part["type"] for part in content] == [
        "input_text",
        "input_text",
        "input_file",
        "input_text",
    ]
    assert content[0]["text"].strip() == "<user_files>"
    assert "Summarize" in content[3]["text"]
    assert attached.input_tokens == 5_000


def test_tool_output_with_placeholder_line_and_text_is_split(db):
    session_id = _session(db)
    pdf = _file(db, session_id)
    payload = {
        "input": [
            _user("Check the appendix"),
            {
                "type": "function_call_output",
                "call_id": "c1",
                "output": f"Attached again:\n{placeholder(pdf.id)}",
            },
        ]
    }

    attach_user_files(payload, db, session_id)

    output = payload["input"][1]["output"]
    assert output[0] == {"type": "input_text", "text": "Attached again:\n"}
    assert output[2]["file_id"] == pdf.openai_file_id
