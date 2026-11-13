from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import fitz
import httpx
import pytest
from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    Base,
    ChatArtifact,
    ChatArtifactVersion,
    ChatSandboxLease,
    ChatSession,
    ChatShare,
    ChatSharedArtifact,
    ChatUploadedFile,
)
from backend.services.chat_file_probe import FileProbeError, count_pdf_pages, sniff
from backend.services.chat_file_service import (
    ChatFileService,
    LocalChatFileStorage,
    estimate_tokens,
    safe_filename,
)
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
    owner_storage_bytes,
)

LUNA = "gpt-5.6-luna@openai"
OWNER = ChatOwner(hf_user_id="owner-1", hf_username="owner")


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _sqlite_jsonb_typeof(connection, _record):
        connection.create_function("jsonb_typeof", 1, lambda _value: "array")

    Base.metadata.create_all(
        engine,
        tables=[
            ChatSession.__table__,
            ChatArtifact.__table__,
            ChatArtifactVersion.__table__,
            ChatSandboxLease.__table__,
            ChatShare.__table__,
            ChatSharedArtifact.__table__,
            ChatUploadedFile.__table__,
        ],
    )
    with Session(engine) as session:
        yield session


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        chat_file_uploads_enabled=True,
        chat_file_storage_backend="local",
        chat_file_local_dir=str(tmp_path / "files"),
    )


class FakeOpenAIFiles:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.uploaded: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def upload(self, filename: str, data: bytes, media_type: str) -> str:
        if self.fail:
            raise httpx.ConnectError("down")
        file_id = f"file-{len(self.uploaded) + 1}"
        self.uploaded[file_id] = data
        return file_id

    def delete(self, file_id: str) -> None:
        self.deleted.append(file_id)


def _session(db: Session, model: str = LUNA) -> uuid.UUID:
    session_id = uuid.uuid4()
    db.add(
        ChatSession(
            id=session_id,
            hf_user_id=OWNER.hf_user_id,
            hf_username=OWNER.hf_username,
            selected_model=model,
            execution_backend="modal_cli",
        )
    )
    db.commit()
    return session_id


def _pdf(pages: int) -> bytes:
    with fitz.open() as document:
        for _ in range(pages):
            document.new_page()
        return document.tobytes()


def _service(db, settings, openai=None):
    openai = openai or FakeOpenAIFiles()
    storage = LocalChatFileStorage(Path(settings.chat_file_local_dir))
    return (
        ChatFileService(db, settings, storage=storage, openai_files=openai),
        storage,
        openai,
    )


def test_pdf_upload_stores_both_copies_and_estimates_tokens(db, settings):
    session_id = _session(db)
    service, storage, openai = _service(db, settings)
    data = _pdf(3)

    row = service.upload(OWNER, session_id, filename="../draft.pdf", data=data)

    assert row.state == "ready"
    assert row.filename == "draft.pdf"
    assert (row.media_type, row.page_count, row.pdf_detail) == (
        "application/pdf",
        3,
        "high",
    )
    assert row.token_estimate == estimate_tokens("application/pdf", len(data), 3)[0]
    assert storage.read(row.storage_key) == data
    assert openai.uploaded[row.openai_file_id] == data
    assert [file.id for file in service.list_files(OWNER, session_id)] == [row.id]
    assert owner_storage_bytes(db, OWNER.hf_user_id) == len(data)


def test_upload_refuses_non_luna_sessions(db, settings):
    session_id = _session(db, model="deepseek-ai/DeepSeek-V4.1-Flash-1017")
    service, _, _ = _service(db, settings)

    with pytest.raises(ChatServiceError) as error:
        service.upload(OWNER, session_id, filename="a.txt", data=b"hello")
    assert error.value.code == "file_upload_model_unsupported"


def test_upload_refuses_other_owners(db, settings):
    session_id = _session(db)
    service, _, _ = _service(db, settings)

    with pytest.raises(ChatServiceError) as error:
        service.upload(
            ChatOwner(hf_user_id="intruder", hf_username="x"),
            session_id,
            filename="a.txt",
            data=b"hello",
        )
    assert error.value.status_code == 404


def test_upload_enforces_limits(db, settings):
    session_id = _session(db)
    service, _, _ = _service(db, settings)
    for index in range(settings.chat_file_max_per_session):
        service.upload(OWNER, session_id, filename=f"{index}.txt", data=b"x")

    with pytest.raises(ChatServiceError) as error:
        service.upload(OWNER, session_id, filename="extra.txt", data=b"x")
    assert error.value.code == "file_limit_reached"

    other = _session(db)
    settings.chat_file_max_pdf_pages = 2
    with pytest.raises(ChatServiceError) as error:
        service.upload(OWNER, other, filename="long.pdf", data=_pdf(3))
    assert error.value.code == "file_too_many_pages"


def test_upload_counts_against_the_chat_quota(db, settings):
    session_id = _session(db)
    settings.chat_user_byte_limit = 1024
    service, _, _ = _service(db, settings)

    with pytest.raises(ChatServiceError) as error:
        service.upload(OWNER, session_id, filename="big.txt", data=b"x" * 2000)
    assert error.value.code == "chat_storage_quota_exceeded"


def test_failed_openai_upload_leaves_nothing_behind(db, settings):
    session_id = _session(db)
    service, storage, _ = _service(db, settings, FakeOpenAIFiles(fail=True))

    with pytest.raises(ChatServiceError) as error:
        service.upload(OWNER, session_id, filename="a.md", data=b"# notes")
    assert error.value.code == "file_upload_failed"
    assert db.scalars(select(ChatUploadedFile)).all() == []
    assert not any(
        path.is_file() for path in Path(settings.chat_file_local_dir).rglob("*")
    )


def test_delete_file_removes_both_copies(db, settings):
    session_id = _session(db)
    service, storage, openai = _service(db, settings)
    row = service.upload(OWNER, session_id, filename="a.txt", data=b"hello")
    key, file_id = row.storage_key, row.openai_file_id

    service.delete_file(OWNER, session_id, row.id)
    db.commit()

    assert openai.deleted == [file_id]
    with pytest.raises(FileNotFoundError):
        storage.read(key)
    assert service.list_files(OWNER, session_id) == []


def test_stale_pending_rows_are_cleaned_up(db, settings):
    session_id = _session(db)
    service, storage, openai = _service(db, settings)
    storage.write("chat-files/stale", b"partial")
    db.add(
        ChatUploadedFile(
            id=uuid.uuid4(),
            session_id=session_id,
            hf_user_id=OWNER.hf_user_id,
            filename="a.txt",
            media_type="text/plain",
            size_bytes=7,
            sha256="0" * 64,
            token_estimate=2,
            storage_key="chat-files/stale",
            openai_file_id="file-stale",
            state="pending",
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    db.commit()

    assert service.remove_stale_pending(OWNER.hf_user_id) == 1
    db.commit()
    assert openai.deleted == ["file-stale"]
    assert db.scalars(select(ChatUploadedFile)).all() == []


def test_session_deletion_receipt_lists_uploaded_files(db, settings):
    session_id = _session(db)
    service, _, _ = _service(db, settings)
    row = service.upload(OWNER, session_id, filename="a.txt", data=b"hello")
    key, file_id = row.storage_key, row.openai_file_id

    receipt = ChatSessionService(db, settings).delete_session(OWNER, session_id)

    assert receipt.uploaded_file_keys == (key,)
    assert receipt.openai_file_ids == (file_id,)


def test_sniff_accepts_content_not_claims():
    assert sniff("x.txt", b"%PDF-1.7").media_type == "application/pdf"
    assert sniff("photo", b"\x89PNG\r\n\x1a\n...").media_type == "image/png"
    assert sniff("notes.md", "# héllo".encode()).media_type == "text/markdown"
    with pytest.raises(FileProbeError):
        sniff("script.exe", b"MZ\x90\x00")
    with pytest.raises(FileProbeError):
        sniff("data.csv", b"a,b\x00c")
    with pytest.raises(FileProbeError):
        sniff("data.csv", b"\xff\xfe\xfa")


def test_pdf_probe_rejects_garbage(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\nnot really a pdf")
    with pytest.raises(FileProbeError):
        count_pdf_pages(path)


def test_safe_filename_strips_paths_and_controls():
    assert safe_filename("C:\\Users\\me\\paper\x07.pdf") == "paper.pdf"
    assert safe_filename("") == "file"


def test_file_routes_are_hidden_while_disabled(db):
    from fastapi import HTTPException
    from starlette.responses import Response

    from backend.routers.chat import list_chat_files

    with pytest.raises(HTTPException) as error:
        list_chat_files(
            uuid.uuid4(),
            Response(),
            user={"hf_user_id": OWNER.hf_user_id, "username": OWNER.hf_username},
            db=db,
            settings=Settings(chat_file_uploads_enabled=False),
        )
    assert error.value.status_code == 404


def test_quota_ignores_uploads_table_while_disabled():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[ChatSession.__table__])
    with Session(engine) as db:
        assert owner_storage_bytes(db, "owner-1", include_uploads=False) == 0


def test_upload_racing_chat_deletion_removes_the_openai_copy(db, settings):
    session_id = _session(db)

    class DeletesRowDuringUpload(FakeOpenAIFiles):
        def upload(self, filename, data, media_type):
            # A concurrent chat deletion cascades the pending row away.
            db.execute(
                delete(ChatUploadedFile).execution_options(synchronize_session=False)
            )
            return super().upload(filename, data, media_type)

    openai = DeletesRowDuringUpload()
    service, _, _ = _service(db, settings, openai)

    with pytest.raises(ChatServiceError) as error:
        service.upload(OWNER, session_id, filename="a.txt", data=b"hello")
    assert error.value.code == "file_upload_failed"
    assert openai.deleted == list(openai.uploaded)
    assert not any(
        path.is_file() for path in Path(settings.chat_file_local_dir).rglob("*")
    )


def test_stale_cleanup_keeps_rows_it_cannot_remove(db, settings):
    session_id = _session(db)

    class DeleteFails(FakeOpenAIFiles):
        def delete(self, file_id):
            raise httpx.ConnectError("down")

    service, _, _ = _service(db, settings, DeleteFails())
    db.add(
        ChatUploadedFile(
            id=uuid.uuid4(),
            session_id=session_id,
            hf_user_id=OWNER.hf_user_id,
            filename="a.txt",
            media_type="text/plain",
            size_bytes=7,
            sha256="0" * 64,
            token_estimate=2,
            storage_key="chat-files/stale",
            openai_file_id="file-stale",
            state="pending",
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )
    db.commit()

    assert service.remove_stale_pending(OWNER.hf_user_id) == 0
    assert len(db.scalars(select(ChatUploadedFile)).all()) == 1


def test_turn_files_validates_and_orders_attachments(db, settings):
    from backend.services.chat_file_service import prompt_file_ids, prompt_with_files

    session_id = _session(db)
    service, _, _ = _service(db, settings)
    first = service.upload(OWNER, session_id, filename="a.txt", data=b"one")
    second = service.upload(OWNER, session_id, filename="b.md", data=b"two")

    rows = service.turn_files(OWNER, session_id, [second.id, first.id, second.id])
    assert [row.id for row in rows] == [second.id, first.id]

    prompt = prompt_with_files("<user_request>\nhi\n</user_request>", rows)
    assert prompt.startswith(f'<user_files>\n<pwc_user_file id="{second.id}"/>\n')
    assert prompt.endswith("<user_request>\nhi\n</user_request>")
    assert prompt_file_ids(prompt) == [second.id, first.id]
    assert prompt_file_ids("hi") == []
    assert prompt_with_files("hi", []) == "hi"


def test_turn_files_refuses_foreign_missing_and_disabled(db, settings):
    session_id = _session(db)
    service, _, _ = _service(db, settings)
    other = _session(db)
    foreign = service.upload(OWNER, other, filename="a.txt", data=b"one")

    with pytest.raises(ChatServiceError) as error:
        service.turn_files(OWNER, session_id, [foreign.id])
    assert error.value.code == "file_not_found"
    with pytest.raises(ChatServiceError) as error:
        service.turn_files(OWNER, None, [foreign.id])
    assert error.value.code == "file_not_found"
    with pytest.raises(ChatServiceError) as error:
        service.turn_files(
            ChatOwner(hf_user_id="intruder", hf_username="x"), other, [foreign.id]
        )
    assert error.value.status_code == 404
    settings.chat_file_uploads_enabled = False
    with pytest.raises(ChatServiceError) as error:
        service.turn_files(OWNER, other, [foreign.id])
    assert error.value.code == "file_uploads_disabled"
    assert service.turn_files(OWNER, other, []) == []


def test_attachments_map_user_messages_to_their_files(db, settings):
    from types import SimpleNamespace

    from backend.services.chat_file_service import prompt_with_files

    session_id = _session(db)
    service, _, _ = _service(db, settings)
    row = service.upload(OWNER, session_id, filename="a.pdf", data=_pdf(2))
    message_id = uuid.uuid4()
    messages = [
        SimpleNamespace(
            id=message_id, role="user", effective_prompt=prompt_with_files("hi", [row])
        ),
        SimpleNamespace(id=uuid.uuid4(), role="assistant", effective_prompt=None),
        SimpleNamespace(id=uuid.uuid4(), role="user", effective_prompt="plain"),
    ]

    attachments = service.attachments(messages)

    assert list(attachments) == [message_id]
    assert [file.filename for file in attachments[message_id]] == ["a.pdf"]
    settings.chat_file_uploads_enabled = False
    assert service.attachments(messages) == {}


def test_shared_chats_show_attachment_names_only(db, settings):
    from types import SimpleNamespace

    from backend.services.chat_share_service import _public_projection

    session_id = _session(db)
    service, _, _ = _service(db, settings)
    row = service.upload(OWNER, session_id, filename="secret.txt", data=b"hidden")
    message = SimpleNamespace(
        id=uuid.uuid4(),
        role="user",
        content="see file",
        paper_mentions=[],
        paper_selection=None,
        status="complete",
    )

    [public] = _public_projection([message], {}, {message.id: [row]})

    dumped = public.model_dump()
    assert dumped["attached_files"] == [
        {
            "filename": "secret.txt",
            "media_type": "text/plain",
            "size_bytes": 6,
            "page_count": None,
        }
    ]
    assert "hidden" not in str(dumped) and str(row.id) not in str(dumped)


def test_upload_writes_both_copies_concurrently(db, settings):
    import threading

    session_id = _session(db)
    # Each side waits for the other: this only finishes when both run at once.
    barrier = threading.Barrier(2, timeout=5)

    class WaitingStorage(LocalChatFileStorage):
        def write(self, key, data):
            barrier.wait()
            super().write(key, data)

    class WaitingOpenAI(FakeOpenAIFiles):
        def upload(self, filename, data, media_type):
            barrier.wait()
            return super().upload(filename, data, media_type)

    storage = WaitingStorage(Path(settings.chat_file_local_dir))
    openai = WaitingOpenAI()
    service = ChatFileService(db, settings, storage=storage, openai_files=openai)

    row = service.upload(OWNER, session_id, filename="a.txt", data=b"hello")

    assert row.state == "ready"
    assert storage.read(row.storage_key) == b"hello"
    assert openai.uploaded[row.openai_file_id] == b"hello"


def test_failed_bucket_write_still_deletes_the_openai_copy(db, settings):
    session_id = _session(db)

    class FailingStorage(LocalChatFileStorage):
        def write(self, key, data):
            raise OSError("bucket down")

    openai = FakeOpenAIFiles()
    service = ChatFileService(
        db,
        settings,
        storage=FailingStorage(Path(settings.chat_file_local_dir)),
        openai_files=openai,
    )

    with pytest.raises(ChatServiceError) as error:
        service.upload(OWNER, session_id, filename="a.txt", data=b"hello")
    assert error.value.code == "file_upload_failed"
    assert openai.deleted == list(openai.uploaded) and openai.deleted
    assert db.scalars(select(ChatUploadedFile)).all() == []


def test_bucket_storage_client_is_shared_per_process():
    from backend.services.chat_file_service import chat_file_storage_from_settings

    settings = Settings(
        chat_file_storage_backend="hf_bucket",
        chat_file_hf_bucket_id="someone/chat-files",
    )
    assert chat_file_storage_from_settings(settings) is chat_file_storage_from_settings(
        settings
    )


def test_unexpected_failure_still_removes_both_copies(db, settings):
    session_id = _session(db)

    class BrokenStorage(LocalChatFileStorage):
        def write(self, key, data):
            raise RuntimeError("unexpected client bug")

    openai = FakeOpenAIFiles()
    service = ChatFileService(
        db,
        settings,
        storage=BrokenStorage(Path(settings.chat_file_local_dir)),
        openai_files=openai,
    )

    with pytest.raises(RuntimeError):
        service.upload(OWNER, session_id, filename="a.txt", data=b"hello")
    assert openai.deleted == list(openai.uploaded) and openai.deleted
    assert db.scalars(select(ChatUploadedFile)).all() == []
