from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    Base,
    ChatArtifact,
    ChatArtifactVersion,
    ChatLatexPaperFigureBlob,
    ChatLatexPaperFigureReference,
    ChatLatexPaperStorageCleanup,
    ChatLatexPaperVersion,
    ChatSandboxLease,
    ChatSession,
    ChatShare,
    ChatSharedArtifact,
)
from backend.services import latex_paper_service
from backend.services.chat_artifact_service import LocalArtifactStorage
from backend.services.chat_session_service import ChatOwner, ChatSessionService
from backend.services.latex_paper_service import LatexPaperService
from latex_compiler_contract import (
    CompileLimits,
    CompilerEnvelope,
    CompilerJobState,
    CompilerResult,
    CompilerStatus,
)


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
            ChatLatexPaperVersion.__table__,
            ChatLatexPaperFigureBlob.__table__,
            ChatLatexPaperFigureReference.__table__,
            ChatLatexPaperStorageCleanup.__table__,
            ChatSandboxLease.__table__,
            ChatShare.__table__,
            ChatSharedArtifact.__table__,
        ],
    )
    with Session(engine) as session:
        yield session


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        chat_artifacts_enabled=True,
        chat_latex_paper_enabled=True,
        chat_latex_compiler_jobs_enabled=True,
        chat_artifact_storage_backend="local",
        chat_artifact_local_dir=str(tmp_path / "storage"),
    )


class _Compiler:
    def __init__(self) -> None:
        self.submitted: tuple[str, bytes, str] | None = None

    def submit(self, *, job_id: str, bundle: bytes, entrypoint: str, limits=None):
        self.submitted = (job_id, bundle, entrypoint)
        return CompilerStatus(job_id=job_id, state=CompilerJobState.SUCCEEDED)

    def status(self, job_id: str):
        return CompilerStatus(job_id=job_id, state=CompilerJobState.SUCCEEDED)

    def result(self, job_id: str):
        assert self.submitted is not None
        _, bundle, entrypoint = self.submitted
        envelope = CompilerEnvelope(
            job_id=job_id,
            source_digest=hashlib.sha256(bundle).hexdigest(),
            source_bytes=len(bundle),
            entrypoint=entrypoint,
            limits=CompileLimits(),
            expires_at=1,
        )
        return CompilerResult.succeeded(
            envelope,
            pdf=b"%PDF-1.7\nscaffold\n",
            log_tail="",
            compiler_image="test-image",
            engine_version="pdfTeX",
        )


def _session(db: Session) -> uuid.UUID:
    session_id = uuid.uuid4()
    db.add(
        ChatSession(
            id=session_id,
            hf_user_id="owner-1",
            hf_username="owner",
            selected_model="model",
            execution_backend="modal_cli",
        )
    )
    db.flush()
    return session_id


def test_session_deletion_reclaims_paper_versions_and_orphaned_figure_blobs(
    db, settings, monkeypatch
):
    """Deleting a chat must clean every immutable paper object only after commit."""

    class TransientDeleteStorage(LocalArtifactStorage):
        fail_deletes = False

        def delete_prefix(self, prefix: str) -> None:
            if self.fail_deletes:
                raise OSError("temporary storage outage")
            super().delete_prefix(prefix)

    storage = TransientDeleteStorage(Path(settings.chat_artifact_local_dir))
    monkeypatch.setattr(
        latex_paper_service,
        "artifact_storage_from_settings",
        lambda _settings: storage,
    )
    paper_service = LatexPaperService(
        db, settings, storage=storage, compiler=_Compiler()
    )
    session_id = _session(db)
    initial = paper_service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id
    )
    assert initial.source_head is not None
    uploaded = paper_service.upload_figure(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        path="figures/result.png",
        data=b"\x89PNG\r\n\x1a\nresearch-image",
        declared_media_type="image/png",
    )
    assert uploaded.source_head is not None
    db.commit()

    version_prefixes = set(
        db.scalars(
            select(ChatLatexPaperVersion.storage_key).where(
                ChatLatexPaperVersion.artifact_id == initial.artifact_id
            )
        )
    )
    blob = db.scalar(select(ChatLatexPaperFigureBlob))
    assert blob is not None
    blob_prefix = blob.storage_key.rsplit("/", 1)[0]
    assert all(
        storage._path(prefix).exists() for prefix in version_prefixes | {blob_prefix}
    )

    ChatSessionService(db, settings).delete_session(
        ChatOwner(hf_user_id="owner-1", hf_username="owner"), session_id
    )

    # The durable cleanup queue is written in the same transaction, while
    # object-store deletion waits for that transaction to commit.
    assert set(db.scalars(select(ChatLatexPaperStorageCleanup.storage_prefix))) == (
        version_prefixes | {blob_prefix}
    )
    assert all(
        storage._path(prefix).exists() for prefix in version_prefixes | {blob_prefix}
    )

    storage.fail_deletes = True
    db.commit()

    assert db.get(ChatArtifact, initial.artifact_id) is None
    assert list(db.scalars(select(ChatLatexPaperVersion))) == []
    assert list(db.scalars(select(ChatLatexPaperFigureReference))) == []
    assert db.get(ChatLatexPaperFigureBlob, blob.digest) is None
    assert set(db.scalars(select(ChatLatexPaperStorageCleanup.storage_prefix))) == (
        version_prefixes | {blob_prefix}
    )
    assert all(
        storage._path(prefix).exists() for prefix in version_prefixes | {blob_prefix}
    )

    storage.fail_deletes = False
    assert paper_service.reconcile_storage_cleanup(limit=20) == len(
        version_prefixes | {blob_prefix}
    )
    db.commit()

    assert list(db.scalars(select(ChatLatexPaperStorageCleanup))) == []
    assert all(
        not storage._path(prefix).exists()
        for prefix in version_prefixes | {blob_prefix}
    )
