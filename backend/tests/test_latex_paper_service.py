from __future__ import annotations

import hashlib
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from starlette.responses import Response

from backend.config import Settings
from backend.models.database import (
    Base,
    ChatArtifact,
    ChatArtifactVersion,
    ChatLatexPaperFigureBlob,
    ChatLatexPaperFigureReference,
    ChatLatexPaperStorageCleanup,
    ChatLatexPaperVersion,
    ChatSession,
)
from backend.services.chat_artifact_service import (
    LocalArtifactStorage,
    StoredArtifactFile,
    owner_artifact_storage_bytes,
)
from backend.services.latex_paper_service import LatexPaperService
from latex_compiler_contract import (
    CompileLimits,
    CompilerDiagnostic,
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


def _session(
    db: Session, *, owner: str = "owner-1", paper_reader: bool = False
) -> uuid.UUID:
    session_id = uuid.uuid4()
    db.add(
        ChatSession(
            id=session_id,
            hf_user_id=owner,
            hf_username="owner",
            selected_model="model",
            execution_backend="modal_cli",
            primary_paper_id=1 if paper_reader else None,
        )
    )
    db.flush()
    return session_id


class _Compiler:
    def __init__(
        self,
        state: CompilerJobState = CompilerJobState.SUCCEEDED,
        *,
        pdf: bytes = b"%PDF-1.7\nscaffold\n",
    ):
        self.state = state
        self.pdf = pdf
        self.submitted: tuple[str, bytes, str] | None = None

    def submit(self, *, job_id: str, bundle: bytes, entrypoint: str, limits=None):
        self.submitted = (job_id, bundle, entrypoint)
        return CompilerStatus(job_id=job_id, state=self.state)

    def status(self, job_id: str):
        return CompilerStatus(job_id=job_id, state=self.state)

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
        if self.state == CompilerJobState.SUCCEEDED:
            return CompilerResult.succeeded(
                envelope,
                pdf=self.pdf,
                log_tail="",
                compiler_image="test-image",
                engine_version="pdfTeX",
            )
        return CompilerResult.failed(
            envelope,
            diagnostics=[
                CompilerDiagnostic(
                    severity="error",
                    file="main.tex",
                    line=7,
                    message="Undefined control sequence",
                )
            ],
            log_tail="bad TeX",
            compiler_image="test-image",
            engine_version="pdfTeX",
            elapsed_ms=1,
        )

    def cancel(self, job_id: str):
        return CompilerStatus(job_id=job_id, state=CompilerJobState.CANCELED)


def test_create_scaffold_persists_immutable_source_and_preview(db, settings):
    session_id = _session(db)
    compiler = _Compiler()
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    service = LatexPaperService(db, settings, storage=storage, compiler=compiler)

    descriptor = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id, title="Careful Draft"
    )

    assert descriptor.title == "Careful Draft"
    assert descriptor.source_head is not None
    assert descriptor.preview_head is not None
    assert descriptor.source_head.version == 1
    assert descriptor.source_head.compile_status == "succeeded"
    assert descriptor.source_head.version_id == descriptor.preview_head.version_id
    artifact = db.get(ChatArtifact, descriptor.artifact_id)
    version = db.get(ChatLatexPaperVersion, descriptor.source_head.version_id)
    assert artifact is not None and version is not None
    assert artifact.source_head_version_id == version.id
    assert artifact.preview_head_version_id == version.id
    assert storage.read_file(
        f"{version.storage_key}/main.tex", max_bytes=100_000
    ).startswith(b"\\documentclass")
    assert storage.read_file(
        f"{version.storage_key}/preview.pdf", max_bytes=100_000
    ).startswith(b"%PDF")
    assert service.read_source_file(
        "owner-1", descriptor.artifact_id, version.id, "main.tex"
    ).data.startswith(b"\\documentclass")
    with pytest.raises(Exception, match="not found"):
        service.read_preview_pdf("another-owner", descriptor.artifact_id, version.id)
    storage.write_file(f"{version.storage_key}/preview.pdf", BytesIO(b"%PDF-tampered"))
    with pytest.raises(Exception, match="invalid"):
        service.read_preview_pdf("owner-1", descriptor.artifact_id, version.id)


def test_failed_compile_keeps_source_head_without_preview(db, settings):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(CompilerJobState.FAILED),
    )

    descriptor = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id, title="Broken Draft"
    )

    assert descriptor.source_head is not None
    assert descriptor.source_head.compile_status == "failed"
    assert descriptor.preview_head is None


def test_failed_human_save_keeps_last_good_preview_and_exposes_diagnostics(
    db, settings
):
    session_id = _session(db)
    compiler = _Compiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None
    compiler.state = CompilerJobState.FAILED

    failed = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\badcommand"},
    )

    assert failed.source_head is not None and failed.preview_head is not None
    assert failed.source_head.compile_status == "failed"
    assert failed.source_head.parent_version_id == initial.source_head.version_id
    assert failed.preview_head.version_id == initial.preview_head.version_id
    assert [item.model_dump() for item in failed.source_head.compile_diagnostics] == [
        {
            "severity": "error",
            "phase": "compiler_error",
            "file": "main.tex",
            "line": 7,
            "message": "Undefined control sequence",
        }
    ]
    assert failed.source_head.repair_attempts_remaining == 3


def test_failed_ai_repairs_are_ephemeral_until_a_successful_candidate(db, settings):
    session_id = _session(db)
    compiler = _Compiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None
    compiler.state = CompilerJobState.FAILED
    failed = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\badcommand"},
    )
    assert failed.source_head is not None

    attempt = service.repair_failed_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=failed.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\stillbad"},
        provenance={"model": "selected-model", "repair": True},
    )

    assert attempt.repaired is False
    assert attempt.exhausted is False
    assert attempt.descriptor.source_head is not None
    assert attempt.descriptor.source_head.version_id == failed.source_head.version_id
    assert attempt.descriptor.source_head.repair_attempts_remaining == 2
    assert (
        db.scalar(
            select(func.count())
            .select_from(ChatLatexPaperVersion)
            .where(ChatLatexPaperVersion.artifact_id == initial.artifact_id)
        )
        == 2
    )

    compiler.state = CompilerJobState.SUCCEEDED
    repaired = service.repair_failed_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=failed.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Fixed\\end{document}"
        },
        provenance={"model": "selected-model", "repair": True},
    )

    assert repaired.repaired is True
    assert repaired.exhausted is False
    assert repaired.descriptor.source_head is not None
    assert repaired.descriptor.source_head.compile_status == "succeeded"
    assert (
        repaired.descriptor.source_head.parent_version_id
        == failed.source_head.version_id
    )
    assert repaired.descriptor.source_head.generation_provenance == {
        "model": "selected-model",
        "repair": True,
    }


def test_quota_rejected_repair_candidate_keeps_the_failed_head_ephemeral(db, settings):
    """A compiled AI repair cannot publish when its preview fails quota admission."""
    compiler = _Compiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    initial = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=_session(db)
    )
    assert initial.source_head is not None and initial.preview_head is not None
    compiler.state = CompilerJobState.FAILED
    failed = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\badcommand"},
    )
    assert failed.source_head is not None
    repair_source = b"\\documentclass{article}\\begin{document}Fixed\\end{document}"
    preview = b"%PDF-1.7\n" + b"repair-preview" * 100
    compiler.state = CompilerJobState.SUCCEEDED
    compiler.pdf = preview
    service.settings = settings.model_copy(
        update={
            "chat_artifact_owner_quota_bytes": (
                owner_artifact_storage_bytes(db, "owner-1")
                + len(repair_source)
                + len(preview)
                - 1
            )
        }
    )

    outcome = service.repair_failed_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=failed.source_head.version_id,
        files={"main.tex": repair_source},
        provenance={"model": "selected-model", "repair": True},
    )

    assert outcome.repaired is False
    assert outcome.exhausted is False
    assert outcome.descriptor.source_head is not None
    assert outcome.descriptor.source_head.version_id == failed.source_head.version_id
    assert outcome.descriptor.preview_head is not None
    assert outcome.descriptor.preview_head.version_id == initial.preview_head.version_id
    assert outcome.descriptor.source_head.repair_attempts_remaining == 2
    assert (
        db.scalar(
            select(func.count())
            .select_from(ChatLatexPaperVersion)
            .where(ChatLatexPaperVersion.artifact_id == initial.artifact_id)
        )
        == 2
    )


def test_successful_repair_carries_forward_deduplicated_figure_references(db, settings):
    """An ephemeral repair candidate must compile against its failed parent's figures."""
    compiler = _Compiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    initial = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=_session(db)
    )
    assert initial.source_head is not None
    figure = b"\x89PNG\r\n\x1a\nrepair-figure"
    with_figure = service.upload_figure(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        path="figures/result.png",
        data=figure,
        declared_media_type="image/png",
    )
    assert with_figure.source_head is not None
    compiler.state = CompilerJobState.FAILED
    failed = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=with_figure.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\badcommand"},
    )
    assert failed.source_head is not None

    compiler.state = CompilerJobState.SUCCEEDED
    repaired = service.repair_failed_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=failed.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Fixed\\end{document}"
        },
        provenance={"model": "selected-model", "repair": True},
    )

    assert repaired.repaired is True
    assert repaired.descriptor.source_head is not None
    assert (
        service.read_figure(
            "owner-1",
            initial.artifact_id,
            repaired.descriptor.source_head.version_id,
            "figures/result.png",
        ).data
        == figure
    )
    assert db.scalar(select(func.count()).select_from(ChatLatexPaperFigureBlob)) == 1


def test_async_repair_waits_for_terminal_sandbox_result(db, settings, monkeypatch):
    class AsyncCompiler(_Compiler):
        def __init__(self):
            super().__init__(CompilerJobState.QUEUED)
            self.status_calls = 0
            self.canceled = False

        def status(self, job_id: str):
            self.status_calls += 1
            self.state = CompilerJobState.SUCCEEDED
            return super().status(job_id)

        def cancel(self, job_id: str):
            self.canceled = True
            return super().cancel(job_id)

    compiler = _Compiler()
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    service = LatexPaperService(db, settings, storage=storage, compiler=compiler)
    initial = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=_session(db)
    )
    assert initial.source_head is not None
    compiler.state = CompilerJobState.FAILED
    failed = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\badcommand"},
    )
    assert failed.source_head is not None

    async_compiler = AsyncCompiler()
    service.compiler = async_compiler
    monkeypatch.setattr(
        "backend.services.latex_paper_service.time.sleep", lambda _: None
    )
    repaired = service.repair_failed_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=failed.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Fixed\\end{document}"
        },
        provenance={"selected_model": "test-model", "repair": True},
    )

    assert repaired.repaired is True
    assert async_compiler.status_calls == 1
    assert async_compiler.canceled is False
    assert repaired.descriptor.source_head is not None
    assert repaired.descriptor.source_head.provenance.action == "ai_repair"
    assert repaired.descriptor.source_head.provenance.model_identity == "test-model"


def test_async_repair_cancels_when_sandbox_polling_fails(db, settings, monkeypatch):
    class PollingFailureCompiler(_Compiler):
        def __init__(self):
            super().__init__(CompilerJobState.QUEUED)
            self.canceled = False

        def status(self, job_id: str):
            raise RuntimeError("Sandbox connection lost")

        def cancel(self, job_id: str):
            self.canceled = True
            return super().cancel(job_id)

    compiler = _Compiler()
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    service = LatexPaperService(db, settings, storage=storage, compiler=compiler)
    initial = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=_session(db)
    )
    assert initial.source_head is not None
    compiler.state = CompilerJobState.FAILED
    failed = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\badcommand"},
    )
    assert failed.source_head is not None

    failing_compiler = PollingFailureCompiler()
    service.compiler = failing_compiler
    monkeypatch.setattr(
        "backend.services.latex_paper_service.time.sleep", lambda _: None
    )
    outcome = service.repair_failed_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=failed.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Fixed\\end{document}"
        },
        provenance={"selected_model": "test-model", "repair": True},
    )

    assert outcome.repaired is False
    assert failing_compiler.canceled is True
    assert outcome.descriptor.source_head is not None
    assert outcome.descriptor.source_head.version_id == failed.source_head.version_id


def test_repair_budget_leaves_the_failed_human_source_intact_after_three_attempts(
    db, settings
):
    session_id = _session(db)
    compiler = _Compiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None
    compiler.state = CompilerJobState.FAILED
    failed = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\badcommand"},
    )
    assert failed.source_head is not None

    for _ in range(3):
        outcome = service.repair_failed_version(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            expected_parent_version_id=failed.source_head.version_id,
            files={"main.tex": b"\\documentclass{article}\\stillbad"},
            provenance={"model": "selected-model", "repair": True},
        )
    assert outcome.exhausted is True
    compiler.state = CompilerJobState.SUCCEEDED

    exhausted = service.repair_failed_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=failed.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Fixed\\end{document}"
        },
        provenance={"model": "selected-model", "repair": True},
    )

    assert exhausted.repaired is False
    assert exhausted.exhausted is True
    assert exhausted.descriptor.source_head is not None
    assert exhausted.descriptor.source_head.version_id == failed.source_head.version_id
    assert exhausted.descriptor.preview_head is not None
    assert (
        exhausted.descriptor.preview_head.version_id == initial.preview_head.version_id
    )


def test_restart_reconciliation_resubmits_the_durable_version_job_id(db, settings):
    session_id = _session(db)
    first_compiler = _Compiler(CompilerJobState.COMPILING)
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    service = LatexPaperService(db, settings, storage=storage, compiler=first_compiler)
    descriptor = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id
    )
    version = db.get(ChatLatexPaperVersion, descriptor.source_head.version_id)
    assert version is not None
    assert first_compiler.submitted is not None
    assert first_compiler.submitted[0] == str(version.id)

    restarted = _Compiler(CompilerJobState.SUCCEEDED)
    recovery = LatexPaperService(db, settings, storage=storage, compiler=restarted)
    assert recovery.reconcile_pending_compiles(limit=1) == 1

    assert restarted.submitted is not None
    assert restarted.submitted[0] == str(version.id)
    assert version.compile_status == "succeeded"


def test_restart_reconciliation_reattaches_the_saved_sandbox_job(db, settings):
    class SandboxCompiler(_Compiler):
        provider_job_id = "opaque-sandbox-job"

        def __init__(self, *, resumed: bool = False):
            super().__init__(CompilerJobState.COMPILING)
            self.resumed = resumed
            self.resume_calls: list[tuple[str, str]] = []

        def submit(self, *, job_id: str, bundle: bytes, entrypoint: str, limits=None):
            self.submitted = (job_id, bundle, entrypoint)
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.COMPILING,
                provider_job_id=self.provider_job_id,
            )

        def resume(
            self, *, job_id: str, provider_job_id: str, bundle: bytes, entrypoint: str
        ):
            self.resume_calls.append((job_id, provider_job_id))
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.COMPILING,
                provider_job_id=provider_job_id,
            )

    session_id = _session(db)
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    original = SandboxCompiler()
    service = LatexPaperService(db, settings, storage=storage, compiler=original)
    descriptor = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id
    )
    version = db.get(ChatLatexPaperVersion, descriptor.source_head.version_id)
    assert version is not None
    assert version.compile_diagnostics["provider_job_id"] == "opaque-sandbox-job"

    restarted = SandboxCompiler(resumed=True)
    recovery = LatexPaperService(db, settings, storage=storage, compiler=restarted)
    assert recovery.reconcile_pending_compiles(limit=1) == 1

    assert restarted.resume_calls == [(str(version.id), "opaque-sandbox-job")]
    assert restarted.submitted is None


def test_restart_reconciliation_preserves_sandbox_after_initial_status_transport_failure(
    db, settings
):
    class SandboxCompiler(_Compiler):
        provider_job_id = "opaque-sandbox-job"

        def __init__(self, *, fail_initial_status: bool = False) -> None:
            super().__init__(CompilerJobState.COMPILING)
            self.fail_initial_status = fail_initial_status
            self.resume_calls: list[tuple[str, str]] = []

        def submit(self, *, job_id: str, bundle: bytes, entrypoint: str, limits=None):
            self.submitted = (job_id, bundle, entrypoint)
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.COMPILING,
                provider_job_id=self.provider_job_id,
            )

        def status(self, job_id: str):
            if self.fail_initial_status:
                raise httpx.ConnectError(
                    "compiler transport unavailable",
                    request=httpx.Request("GET", "https://compiler.invalid/status"),
                )
            return CompilerStatus(job_id=job_id, state=CompilerJobState.COMPILING)

        def resume(
            self, *, job_id: str, provider_job_id: str, bundle: bytes, entrypoint: str
        ):
            self.resume_calls.append((job_id, provider_job_id))
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.COMPILING,
                provider_job_id=provider_job_id,
            )

    session_id = _session(db)
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    original = SandboxCompiler(fail_initial_status=True)
    service = LatexPaperService(db, settings, storage=storage, compiler=original)
    descriptor = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id
    )
    version = db.get(ChatLatexPaperVersion, descriptor.source_head.version_id)
    assert version is not None
    assert version.compile_status == "queued"
    assert version.compile_diagnostics == {
        "job_id": str(version.id),
        "failure_category": "transport_failure",
        "provider_job_id": "opaque-sandbox-job",
    }

    restarted = SandboxCompiler()
    recovery = LatexPaperService(db, settings, storage=storage, compiler=restarted)
    assert recovery.reconcile_pending_compiles(limit=1) == 1

    assert restarted.resume_calls == [(str(version.id), "opaque-sandbox-job")]
    assert restarted.submitted is None


def test_restart_reconciliation_preserves_sandbox_after_resume_transport_failure(
    db, settings
):
    class SandboxCompiler(_Compiler):
        provider_job_id = "opaque-sandbox-job"

        def __init__(self, *, fail_resume: bool = False) -> None:
            super().__init__(CompilerJobState.COMPILING)
            self.fail_resume = fail_resume
            self.resume_calls: list[tuple[str, str]] = []

        def submit(self, *, job_id: str, bundle: bytes, entrypoint: str, limits=None):
            self.submitted = (job_id, bundle, entrypoint)
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.COMPILING,
                provider_job_id=self.provider_job_id,
            )

        def resume(
            self, *, job_id: str, provider_job_id: str, bundle: bytes, entrypoint: str
        ):
            self.resume_calls.append((job_id, provider_job_id))
            if self.fail_resume:
                raise httpx.ConnectError(
                    "compiler transport unavailable",
                    request=httpx.Request("POST", "https://compiler.invalid/resume"),
                )
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.COMPILING,
                provider_job_id=provider_job_id,
            )

    session_id = _session(db)
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    original = SandboxCompiler()
    service = LatexPaperService(db, settings, storage=storage, compiler=original)
    descriptor = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id
    )
    version = db.get(ChatLatexPaperVersion, descriptor.source_head.version_id)
    assert version is not None
    assert version.compile_diagnostics["provider_job_id"] == "opaque-sandbox-job"

    transport_failed = SandboxCompiler(fail_resume=True)
    recovery = LatexPaperService(
        db, settings, storage=storage, compiler=transport_failed
    )
    assert recovery.reconcile_pending_compiles(limit=1) == 1
    assert version.compile_diagnostics == {
        "job_id": str(version.id),
        "failure_category": "transport_failure",
        "provider_job_id": "opaque-sandbox-job",
    }

    restarted = SandboxCompiler()
    recovery = LatexPaperService(db, settings, storage=storage, compiler=restarted)
    assert recovery.reconcile_pending_compiles(limit=1) == 1

    assert restarted.resume_calls == [(str(version.id), "opaque-sandbox-job")]
    assert restarted.submitted is None


def test_reconciliation_rechecks_pending_version_after_artifact_lock(
    db, settings, monkeypatch
):
    session_id = _session(db)
    compiler = _Compiler(CompilerJobState.QUEUED)
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    service = LatexPaperService(db, settings, storage=storage, compiler=compiler)
    descriptor = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id
    )
    version = db.get(ChatLatexPaperVersion, descriptor.source_head.version_id)
    assert version is not None
    assert version.compile_status == "queued"

    def lock_then_complete(artifact_id: uuid.UUID):
        assert artifact_id == version.artifact_id
        version.compile_status = "succeeded"
        version.compiled_pdf_path = f"{version.storage_key}/preview.pdf"
        db.flush()
        return db.get(ChatArtifact, artifact_id)

    monkeypatch.setattr(
        service, "_lock_reconcile_artifact", lock_then_complete, raising=False
    )
    monkeypatch.setattr(
        service,
        "_compile",
        lambda *_args: pytest.fail("completed version must not submit a Sandbox"),
    )

    assert service.reconcile_pending_compiles(limit=1) == 0


def test_paper_is_private_general_chat_only_and_unique(db, settings):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    with pytest.raises(Exception, match="already has a paper"):
        service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    with pytest.raises(Exception, match="not found"):
        service.get_descriptor("another-owner", session_id)

    reader_id = _session(db, paper_reader=True)
    with pytest.raises(Exception, match="general chat"):
        service.create_neutral_scaffold(owner_id="owner-1", session_id=reader_id)


def test_owner_exports_last_good_pdf_and_an_explicit_immutable_source_version(
    db, settings
):
    """Exporting must keep the last successful preview and selected source private."""
    session_id = _session(db)
    compiler = _Compiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    initial = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id, title="Careful / Draft"
    )
    assert initial.source_head is not None
    compiler.state = CompilerJobState.FAILED
    failed = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\badcommand"},
    )
    assert failed.source_head is not None

    pdf = service.export_last_successful_pdf("owner-1", initial.artifact_id)
    source = service.export_source_zip(
        "owner-1", initial.artifact_id, failed.source_head.version_id
    )

    assert pdf.data == b"%PDF-1.7\nscaffold\n"
    assert pdf.filename == "careful-draft.pdf"
    assert source.filename == "careful-draft-v2-source.zip"
    with zipfile.ZipFile(BytesIO(source.data)) as archive:
        assert archive.namelist() == ["main.tex"]
        assert archive.read("main.tex") == b"\\documentclass{article}\\badcommand"
        assert all(
            not name.startswith("/") and ".." not in name.split("/")
            for name in archive.namelist()
        )

    with pytest.raises(Exception, match="not found"):
        service.export_last_successful_pdf("another-owner", initial.artifact_id)
    with pytest.raises(Exception, match="not found"):
        service.export_source_zip(
            "another-owner", initial.artifact_id, failed.source_head.version_id
        )


def test_human_save_creates_a_child_and_advances_both_heads(db, settings):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None

    saved = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Edited\\end{document}",
            "references.bib": b"@comment{Edited}\n",
        },
    )

    assert saved.source_head is not None and saved.preview_head is not None
    assert saved.source_head.version == 2
    assert saved.editing_enabled is True
    assert saved.source_head.parent_version_id == initial.source_head.version_id
    assert saved.source_head.version_id == saved.preview_head.version_id
    version = db.get(ChatLatexPaperVersion, saved.source_head.version_id)
    assert version is not None and version.actor_type == "human"
    assert db.get(ChatArtifact, saved.artifact_id).latest_version == 2
    assert service.read_source_file(
        "owner-1", saved.artifact_id, version.id, "main.tex"
    ).data.endswith(b"\\end{document}")


def test_figure_upload_is_signature_checked_deduplicated_and_preserved_across_saves(
    db, settings
):
    """A text-only save must retain one durable, safely-addressed figure blob."""
    session_id = _session(db)
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    service = LatexPaperService(db, settings, storage=storage, compiler=_Compiler())
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None

    png = b"\x89PNG\r\n\x1a\nresearch-image"
    uploaded = service.upload_figure(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        path="figures/result.png",
        data=png,
        declared_media_type="image/png",
    )
    assert uploaded.source_head is not None
    assert uploaded.source_head.version == 2
    figure = service.read_figure(
        "owner-1",
        initial.artifact_id,
        uploaded.source_head.version_id,
        "figures/result.png",
    )
    assert figure.data == png
    assert figure.media_type == "image/png"

    saved = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=uploaded.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Edited\\end{document}"
        },
    )
    assert saved.source_head is not None
    assert (
        service.read_figure(
            "owner-1",
            initial.artifact_id,
            saved.source_head.version_id,
            "figures/result.png",
        ).data
        == png
    )
    assert len(list(Path(settings.chat_artifact_local_dir).glob("**/blobs/*"))) == 1


@pytest.mark.parametrize(
    ("path", "data", "media_type"),
    [
        ("figures/result.jpg", b"\xff\xd8\xffjpeg", "image/jpeg"),
        ("figures/result.pdf", b"%PDF-1.7\npdf", "application/pdf"),
    ],
)
def test_figure_upload_accepts_each_non_png_type(db, settings, path, data, media_type):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None

    uploaded = service.upload_figure(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        path=path,
        data=data,
        declared_media_type=media_type,
    )

    assert uploaded.source_head is not None
    assert (
        service.read_figure(
            "owner-1", initial.artifact_id, uploaded.source_head.version_id, path
        ).media_type
        == media_type
    )


def test_figure_upload_rejects_mismatched_signature_and_owner_quota_before_publication(
    db, settings
):
    """Bad media and over-quota bytes must not advance the immutable source head."""
    constrained = settings.model_copy(update={"chat_artifact_owner_quota_bytes": 6_000})
    session_id = _session(db)
    service = LatexPaperService(
        db,
        constrained,
        storage=LocalArtifactStorage(Path(constrained.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None
    with pytest.raises(Exception, match="signature"):
        service.upload_figure(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            expected_parent_version_id=initial.source_head.version_id,
            path="figures/not-a-png.png",
            data=b"not a PNG",
            declared_media_type="image/png",
        )
    assert (
        service.get_artifact_descriptor(
            "owner-1", initial.artifact_id
        ).source_head.version
        == 1
    )
    with pytest.raises(Exception, match="safe relative paths"):
        service.upload_figure(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            expected_parent_version_id=initial.source_head.version_id,
            path="../outside.png",
            data=b"\x89PNG\r\n\x1a\noutside",
            declared_media_type="image/png",
        )
    with pytest.raises(Exception, match="safe relative paths"):
        service.upload_figure(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            expected_parent_version_id=initial.source_head.version_id,
            path="figures//inside.png",
            data=b"\x89PNG\r\n\x1a\ninside",
            declared_media_type="image/png",
        )

    first = service.upload_figure(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        path="figures/large.png",
        data=b"\x89PNG\r\n\x1a\n" + b"a" * 5_000,
        declared_media_type="image/png",
    )
    assert first.source_head is not None
    with pytest.raises(Exception, match="quota"):
        service.upload_figure(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            expected_parent_version_id=first.source_head.version_id,
            path="figures/another.png",
            data=b"\x89PNG\r\n\x1a\n" + b"b" * 1_000,
            declared_media_type="image/png",
        )
    assert (
        service.get_artifact_descriptor(
            "owner-1", initial.artifact_id
        ).source_head.version_id
        == first.source_head.version_id
    )


def test_figure_quota_charges_an_owner_for_a_cross_owner_deduplicated_blob(
    db, settings
):
    """A global dedup hit is still new durable storage for a second owner."""
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    service = LatexPaperService(db, settings, storage=storage, compiler=_Compiler())
    first_owner = service.create_neutral_scaffold(
        owner_id="owner-a", session_id=_session(db, owner="owner-a")
    )
    second_owner = service.create_neutral_scaffold(
        owner_id="owner-b", session_id=_session(db, owner="owner-b")
    )
    assert first_owner.source_head is not None
    assert second_owner.source_head is not None
    figure = b"\x89PNG\r\n\x1a\n" + b"shared-research-image" * 20
    first_upload = service.upload_figure(
        owner_id="owner-a",
        artifact_id=first_owner.artifact_id,
        expected_parent_version_id=first_owner.source_head.version_id,
        path="figures/shared.png",
        data=figure,
        declared_media_type="image/png",
    )
    assert first_upload.source_head is not None

    second_owner_used = owner_artifact_storage_bytes(db, "owner-b")
    service.settings = settings.model_copy(
        update={"chat_artifact_owner_quota_bytes": second_owner_used + len(figure) - 1}
    )
    with pytest.raises(Exception, match="quota"):
        service.upload_figure(
            owner_id="owner-b",
            artifact_id=second_owner.artifact_id,
            expected_parent_version_id=second_owner.source_head.version_id,
            path="figures/shared.png",
            data=figure,
            declared_media_type="image/png",
        )
    assert (
        service.get_artifact_descriptor(
            "owner-b", second_owner.artifact_id
        ).source_head.version_id
        == second_owner.source_head.version_id
    )


def test_compile_preview_quota_counts_the_current_pdf_once(db, settings):
    """A preview admitted exactly at the owner boundary must not be double charged."""
    pdf = b"%PDF-1.7\n" + b"preview" * 200
    compiler = _Compiler(pdf=pdf)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    initial = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=_session(db)
    )
    assert initial.source_head is not None
    edited_source = b"\\documentclass{article}\\begin{document}Boundary\\end{document}"
    service.settings = settings.model_copy(
        update={
            "chat_artifact_owner_quota_bytes": (
                owner_artifact_storage_bytes(db, "owner-1")
                + len(edited_source)
                + len(pdf)
            )
        }
    )

    saved = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={"main.tex": edited_source},
    )

    assert saved.source_head is not None and saved.preview_head is not None
    assert saved.source_head.compile_status == "succeeded"
    assert saved.preview_head.version_id == saved.source_head.version_id
    assert owner_artifact_storage_bytes(db, "owner-1") == (
        service.settings.chat_artifact_owner_quota_bytes
    )


def test_deleting_unreferenced_versions_and_project_reclaims_only_orphaned_figures(
    db, settings
):
    """Version removal drops its reference, but a shared figure survives until project cleanup."""

    class TransientDeleteStorage(LocalArtifactStorage):
        fail_deletes = False

        def delete_prefix(self, prefix: str) -> None:
            if self.fail_deletes:
                raise OSError("temporary storage outage")
            super().delete_prefix(prefix)

    session_id = _session(db)
    storage = TransientDeleteStorage(Path(settings.chat_artifact_local_dir))
    service = LatexPaperService(db, settings, storage=storage, compiler=_Compiler())
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None
    uploaded = service.upload_figure(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        path="figures/result.png",
        data=b"\x89PNG\r\n\x1a\nresearch-image",
        declared_media_type="image/png",
    )
    assert uploaded.source_head is not None
    saved = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=uploaded.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Version three\\end{document}"
        },
    )
    assert saved.source_head is not None
    service.delete_version(
        "owner-1", initial.artifact_id, uploaded.source_head.version_id
    )
    assert len(list(Path(settings.chat_artifact_local_dir).glob("**/blobs/*"))) == 1
    service.delete_project("owner-1", initial.artifact_id)
    # Object deletion is deliberately deferred until the DB reference removal
    # commits, so a concurrent upload cannot reuse an about-to-be-deleted blob.
    assert len(list(Path(settings.chat_artifact_local_dir).glob("**/blobs/*"))) == 1
    storage.fail_deletes = True
    db.commit()
    assert service.reconcile_storage_cleanup(limit=20) == 0
    storage.fail_deletes = False
    assert service.reconcile_storage_cleanup(limit=20) > 0
    db.commit()
    assert list(Path(settings.chat_artifact_local_dir).glob("**/blobs/*/content")) == []


def test_delete_project_cancels_pending_sandbox_by_provider_handle_without_resubmit(
    db, settings
):
    class ProviderHandleCompiler(_Compiler):
        provider_job_id = "opaque-sandbox-job"

        def __init__(self) -> None:
            super().__init__(CompilerJobState.QUEUED)
            self.submit_calls = 0
            self.provider_cancellations: list[str] = []

        def submit(self, *, job_id: str, bundle: bytes, entrypoint: str, limits=None):
            self.submit_calls += 1
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.QUEUED,
                provider_job_id=self.provider_job_id,
            )

        def status(self, job_id: str):
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.QUEUED,
                provider_job_id=self.provider_job_id,
            )

        def cancel_provider_job(self, provider_job_id: str) -> None:
            self.provider_cancellations.append(provider_job_id)

    compiler = ProviderHandleCompiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    paper = service.create_neutral_scaffold(owner_id="owner-1", session_id=_session(db))
    assert paper.source_head is not None

    service.delete_project("owner-1", paper.artifact_id)

    assert compiler.provider_cancellations == ["opaque-sandbox-job"]
    assert compiler.submit_calls == 1
    assert (
        db.scalar(
            select(ChatLatexPaperVersion.id).where(
                ChatLatexPaperVersion.artifact_id == paper.artifact_id
            )
        )
        is None
    )


def test_delete_version_cancels_a_pending_nonhead_sandbox_by_provider_handle(
    db, settings
):
    class ProviderHandleCompiler(_Compiler):
        def __init__(self) -> None:
            super().__init__(CompilerJobState.QUEUED)
            self.submit_calls = 0
            self.provider_job_ids: dict[str, str] = {}
            self.provider_cancellations: list[str] = []

        def submit(self, *, job_id: str, bundle: bytes, entrypoint: str, limits=None):
            self.submit_calls += 1
            provider_job_id = f"opaque-sandbox-job-{self.submit_calls}"
            self.provider_job_ids[job_id] = provider_job_id
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.QUEUED,
                provider_job_id=provider_job_id,
            )

        def status(self, job_id: str):
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.QUEUED,
                provider_job_id=self.provider_job_ids[job_id],
            )

        def cancel_provider_job(self, provider_job_id: str) -> None:
            self.provider_cancellations.append(provider_job_id)

    compiler = ProviderHandleCompiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    first = service.create_neutral_scaffold(owner_id="owner-1", session_id=_session(db))
    assert first.source_head is not None
    second = service.save_human_version(
        owner_id="owner-1",
        artifact_id=first.artifact_id,
        expected_parent_version_id=first.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}v2\\end{document}"
        },
    )
    assert second.source_head is not None

    service.delete_version("owner-1", first.artifact_id, first.source_head.version_id)

    assert compiler.provider_cancellations == ["opaque-sandbox-job-1"]
    assert compiler.submit_calls == 2
    assert db.get(ChatLatexPaperVersion, first.source_head.version_id) is None
    assert db.get(ChatLatexPaperVersion, second.source_head.version_id) is not None


def test_delete_project_preserves_deletion_when_provider_cancellation_fails(
    db, settings, caplog
):
    class FailingProviderHandleCompiler(_Compiler):
        provider_job_id = "opaque-sandbox-job"

        def submit(self, *, job_id: str, bundle: bytes, entrypoint: str, limits=None):
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.QUEUED,
                provider_job_id=self.provider_job_id,
            )

        def status(self, job_id: str):
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.QUEUED,
                provider_job_id=self.provider_job_id,
            )

        def cancel_provider_job(self, provider_job_id: str) -> None:
            raise RuntimeError("untrusted-provider-detail")

    compiler = FailingProviderHandleCompiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    paper = service.create_neutral_scaffold(owner_id="owner-1", session_id=_session(db))
    caplog.set_level("WARNING", logger="backend.services.latex_paper_service")

    service.delete_project("owner-1", paper.artifact_id)

    assert (
        db.scalar(select(ChatArtifact.id).where(ChatArtifact.id == paper.artifact_id))
        is None
    )
    assert "untrusted-provider-detail" not in caplog.text
    assert "delete_pending_sandbox_cancellation_failed" in caplog.text


def test_figure_admission_counts_durable_posterly_storage(db, settings):
    """The owner limit is shared by Posterly and paper artifacts."""
    constrained = settings.model_copy(update={"chat_artifact_owner_quota_bytes": 6_000})
    session_id = _session(db)
    service = LatexPaperService(
        db,
        constrained,
        storage=LocalArtifactStorage(Path(constrained.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    paper = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert paper.source_head is not None
    poster = ChatArtifact(
        id=uuid.uuid4(),
        session_id=_session(db),
        identifier="poster",
        kind="posterly",
        title="Poster",
        latest_version=1,
    )
    db.add(poster)
    db.flush()
    db.add(
        ChatArtifactVersion(
            id=uuid.uuid4(),
            artifact=poster,
            turn_id=uuid.uuid4(),
            version=1,
            manifest={},
            bundle_digest="a" * 64,
            byte_count=6_000,
            storage_key="private/poster",
            preview_path="poster.pdf",
            preview_mime="application/pdf",
            gate_status="passed",
            state="ready",
        )
    )
    db.flush()

    with pytest.raises(Exception, match="quota"):
        service.upload_figure(
            owner_id="owner-1",
            artifact_id=paper.artifact_id,
            expected_parent_version_id=paper.source_head.version_id,
            path="figures/result.png",
            data=b"\x89PNG\r\n\x1a\nresearch-image",
            declared_media_type="image/png",
        )


def test_figure_response_forces_private_download_headers(monkeypatch, settings):
    """A PDF figure is downloaded privately instead of executing in the app origin."""
    from backend.routers import chat as chat_router

    class Service:
        def __init__(self, *_args, **_kwargs):
            pass

        def read_figure(self, *_args):
            return StoredArtifactFile(
                data=b"%PDF-1.7\nfigure",
                media_type="application/pdf",
                filename="plot.pdf",
            )

    monkeypatch.setattr(chat_router, "LatexPaperService", Service)
    response = chat_router.get_latex_paper_figure(
        uuid.uuid4(),
        uuid.uuid4(),
        "figures/plot.pdf",
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=object(),
        settings=settings,
    )
    assert response.headers["content-disposition"] == 'attachment; filename="plot.pdf"'
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "sandbox; default-src 'none'"


def test_paper_export_routes_are_owner_scoped_and_never_cache_bytes(
    monkeypatch, settings
):
    """The download endpoints must proxy owner-only bytes without cache reuse."""
    from backend.routers import chat as chat_router

    artifact_id, version_id = uuid.uuid4(), uuid.uuid4()
    calls: list[tuple[str, uuid.UUID, uuid.UUID | None]] = []

    class Service:
        def __init__(self, *_args, **_kwargs):
            pass

        def export_last_successful_pdf(self, owner, artifact):
            calls.append((owner, artifact, None))
            return StoredArtifactFile(
                data=b"%PDF-1.7\nexport",
                media_type="application/pdf",
                filename="draft.pdf",
            )

        def export_source_zip(self, owner, artifact, version):
            calls.append((owner, artifact, version))
            return StoredArtifactFile(
                data=b"PK\x03\x04",
                media_type="application/zip",
                filename="draft-v2-source.zip",
            )

    monkeypatch.setattr(chat_router, "LatexPaperService", Service)
    pdf = chat_router.download_latex_paper_pdf(
        artifact_id,
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=object(),
        settings=settings,
    )
    source = chat_router.download_latex_paper_source_zip(
        artifact_id,
        version_id,
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=object(),
        settings=settings,
    )

    assert calls == [
        ("owner-1", artifact_id, None),
        ("owner-1", artifact_id, version_id),
    ]
    assert pdf.headers["cache-control"] == "private, no-store"
    assert source.headers["cache-control"] == "private, no-store"
    assert pdf.headers["content-disposition"] == 'attachment; filename="draft.pdf"'
    assert (
        source.headers["content-disposition"]
        == 'attachment; filename="draft-v2-source.zip"'
    )


def test_paper_manifest_response_never_caches_private_metadata(monkeypatch, settings):
    """Owner-only source metadata must not survive a browser cache boundary."""
    from backend.routers import chat as chat_router

    class ArtifactService:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_artifact(self, *_args):
            return type("Artifact", (), {"kind": "latex_paper"})()

    class PaperService:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_manifest(self, *_args):
            return {"root_document": "main.tex", "files": []}

    monkeypatch.setattr(chat_router, "ChatArtifactService", ArtifactService)
    monkeypatch.setattr(chat_router, "LatexPaperService", PaperService)
    response = Response()
    chat_router.get_artifact_manifest(
        uuid.uuid4(),
        uuid.uuid4(),
        response,
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=object(),
        settings=settings,
    )

    assert response.headers["Cache-Control"] == "private, no-store"


def test_version_delete_route_uses_paper_reference_cleanup(monkeypatch, settings):
    """The public version route must not send a paper ID through Posterly deletion."""
    from backend.routers import chat as chat_router

    called: list[tuple[str, uuid.UUID, uuid.UUID]] = []
    csrf_requests: list[object] = []

    class ArtifactService:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_artifact(self, *_args):
            return type("Artifact", (), {"kind": "latex_paper"})()

    class PaperService:
        def __init__(self, *_args, **_kwargs):
            pass

        def delete_version(self, owner, artifact_id, version_id):
            called.append((owner, artifact_id, version_id))

    class Db:
        def commit(self):
            pass

        def rollback(self):
            raise AssertionError("the owner cleanup route should not roll back")

    monkeypatch.setattr(chat_router, "ChatArtifactService", ArtifactService)
    monkeypatch.setattr(chat_router, "LatexPaperService", PaperService)
    monkeypatch.setattr(
        chat_router,
        "_require_same_origin_csrf",
        lambda request, _settings: csrf_requests.append(request),
    )
    artifact_id, version_id = uuid.uuid4(), uuid.uuid4()
    request = object()
    response = chat_router.delete_artifact_version(
        artifact_id,
        version_id,
        request,
        user={"hf_user_id": "owner-1", "username": "owner"},
        db=Db(),
        settings=settings,
    )
    assert response.status_code == 204
    assert called == [("owner-1", artifact_id, version_id)]
    assert csrf_requests == [request]


def test_human_save_rejects_a_stale_parent_without_overwriting(db, settings):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None
    saved = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}One\\end{document}"
        },
    )

    with pytest.raises(Exception, match="updated elsewhere"):
        service.save_human_version(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            expected_parent_version_id=initial.source_head.version_id,
            files={
                "main.tex": b"\\documentclass{article}\\begin{document}Two\\end{document}"
            },
        )
    assert (
        db.get(ChatArtifact, initial.artifact_id).source_head_version_id
        == saved.source_head.version_id
    )


def test_human_save_rejects_a_zip_archive_over_the_version_bound(db, settings):
    """The signed compiler archive has the same bound as aggregate source bytes."""
    constrained = settings.model_copy(update={"chat_artifact_max_version_bytes": 4_096})
    service = LatexPaperService(
        db,
        constrained,
        storage=LocalArtifactStorage(Path(constrained.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    initial = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=_session(db)
    )
    assert initial.source_head is not None
    files = {"main.tex": b"x"}
    files.update({f"references/{index}.bib": b"x" * 40 for index in range(99)})
    assert sum(len(data) for data in files.values()) <= 4_096

    with pytest.raises(Exception, match="archive exceeds"):
        service.save_human_version(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            expected_parent_version_id=initial.source_head.version_id,
            files=files,
        )

    assert (
        service.get_artifact_descriptor(
            "owner-1", initial.artifact_id
        ).source_head.version_id
        == initial.source_head.version_id
    )


def test_history_is_paginated_and_exposes_only_bounded_version_audit_data(db, settings):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    initial = service.create_neutral_scaffold(
        owner_id="owner-1",
        session_id=session_id,
        actor_type="ai",
        model_identity="gpt-test",
    )
    assert initial.source_head is not None
    human = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Human\\end{document}"
        },
    )
    assert human.source_head is not None
    repaired = service.save_ai_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=human.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Repair\\end{document}"
        },
        model_identity="gpt-test",
        change_summary="Fixed the compilation error.",
        changed_files=["main.tex"],
        reference_changes=["Added one verified reference."],
        is_repair=True,
    )
    assert repaired.source_head is not None

    first = service.list_history(
        owner_id="owner-1", artifact_id=initial.artifact_id, limit=2
    )
    assert [item.version for item in first.items] == [3, 2]
    assert first.next_cursor == "2"
    assert first.items[0].actor_type == "ai"
    assert first.items[0].created_at is not None
    assert first.items[0].provenance.action == "ai_repair"
    assert first.items[0].provenance.model_identity == "gpt-test"
    assert first.items[0].provenance.changed_files == ["main.tex"]
    assert first.items[0].provenance.reference_changes == [
        "Added one verified reference."
    ]
    assert first.items[1].actor_type == "human"
    assert first.items[1].provenance.action == "human_save"
    assert not hasattr(first.items[0], "files")

    second = service.list_history(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        limit=2,
        cursor=first.next_cursor,
    )
    assert [item.version for item in second.items] == [1]
    assert second.next_cursor is None
    assert second.items[0].provenance.action == "ai_draft"


def test_restore_creates_a_new_head_and_retains_the_last_good_preview_on_failure(
    db, settings
):
    session_id = _session(db)
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    initial_service = LatexPaperService(
        db, settings, storage=storage, compiler=_Compiler()
    )
    initial = initial_service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id
    )
    assert initial.source_head is not None
    edited = initial_service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}New head\\end{document}"
        },
    )
    assert edited.source_head is not None and edited.preview_head is not None

    restoring = LatexPaperService(
        db, settings, storage=storage, compiler=_Compiler(CompilerJobState.FAILED)
    )
    restored = restoring.restore_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        source_version_id=initial.source_head.version_id,
        expected_parent_version_id=edited.source_head.version_id,
    )

    assert restored.source_head is not None and restored.preview_head is not None
    assert restored.source_head.version == 3
    assert restored.source_head.parent_version_id == edited.source_head.version_id
    assert restored.source_head.compile_status == "failed"
    assert restored.source_head.provenance.action == "restore"
    assert restored.preview_head.version_id == edited.preview_head.version_id
    restored_row = db.get(ChatLatexPaperVersion, restored.source_head.version_id)
    original_row = db.get(ChatLatexPaperVersion, initial.source_head.version_id)
    assert restored_row is not None and original_row is not None
    assert restored_row.source_digest == original_row.source_digest
    assert restored_row.id != original_row.id
    assert restored.source_head.provenance.restored_from_version_id == original_row.id
    assert (
        initial_service.read_source_file(
            "owner-1", initial.artifact_id, restored_row.id, "main.tex"
        ).data
        == initial_service.read_source_file(
            "owner-1", initial.artifact_id, original_row.id, "main.tex"
        ).data
    )

    with pytest.raises(Exception, match="updated elsewhere"):
        restoring.restore_version(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            source_version_id=initial.source_head.version_id,
            expected_parent_version_id=edited.source_head.version_id,
        )


def test_restore_rejects_the_current_head(db, settings):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None

    with pytest.raises(Exception, match="historical version"):
        service.restore_version(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            source_version_id=initial.source_head.version_id,
            expected_parent_version_id=initial.source_head.version_id,
        )


def test_restore_keeps_figure_reference_after_source_version_is_deleted(db, settings):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None
    figure = b"\x89PNG\r\n\x1a\nrestore-figure"
    uploaded = service.upload_figure(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        path="figures/result.png",
        data=figure,
        declared_media_type="image/png",
    )
    assert uploaded.source_head is not None
    newer = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=uploaded.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}newer\\end{document}"
        },
    )
    assert newer.source_head is not None
    restored = service.restore_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        source_version_id=uploaded.source_head.version_id,
        expected_parent_version_id=newer.source_head.version_id,
    )
    assert restored.source_head is not None
    service.delete_version(
        "owner-1", initial.artifact_id, uploaded.source_head.version_id
    )
    assert (
        service.read_figure(
            "owner-1",
            initial.artifact_id,
            restored.source_head.version_id,
            "figures/result.png",
        ).data
        == figure
    )


def test_pending_human_save_advances_preview_when_polled(db, settings):
    class DelayedCompiler(_Compiler):
        def __init__(self):
            super().__init__(CompilerJobState.QUEUED)
            self.calls = 0

        def submit(self, *, job_id: str, bundle: bytes, entrypoint: str, limits=None):
            self.calls += 1
            self.submitted = (job_id, bundle, entrypoint)
            self.state = (
                CompilerJobState.QUEUED
                if self.calls == 2
                else CompilerJobState.SUCCEEDED
            )
            return CompilerStatus(job_id=job_id, state=self.state)

    session_id = _session(db)
    compiler = DelayedCompiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None
    pending = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Queued\\end{document}"
        },
    )
    assert pending.source_head is not None
    assert pending.source_head.compile_status == "queued"
    assert pending.preview_head is not None
    assert pending.preview_head.version_id == initial.preview_head.version_id

    completed = service.refresh_compile(
        owner_id="owner-1", artifact_id=initial.artifact_id
    )
    assert completed.source_head is not None and completed.preview_head is not None
    assert completed.source_head.compile_status == "succeeded"
    assert completed.preview_head.version_id == completed.source_head.version_id


def test_owner_poll_reattaches_a_pending_sandbox_instead_of_submitting_again(
    db, settings
):
    class ResumeCompiler(_Compiler):
        def __init__(self) -> None:
            super().__init__(CompilerJobState.QUEUED)
            self.submit_calls = 0
            self.resume_calls: list[tuple[str, str]] = []

        def submit(self, *, job_id: str, bundle: bytes, entrypoint: str, limits=None):
            self.submit_calls += 1
            if self.submit_calls > 1:
                raise AssertionError("owner poll must not create another Sandbox")
            self.submitted = (job_id, bundle, entrypoint)
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.QUEUED,
                provider_job_id="opaque-sandbox-job",
            )

        def resume(
            self, *, job_id: str, provider_job_id: str, bundle: bytes, entrypoint: str
        ):
            self.resume_calls.append((job_id, provider_job_id))
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.QUEUED,
                provider_job_id=provider_job_id,
            )

    session_id = _session(db)
    compiler = ResumeCompiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    descriptor = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id
    )

    service.refresh_compile(owner_id="owner-1", artifact_id=descriptor.artifact_id)

    assert compiler.submit_calls == 1
    assert compiler.resume_calls == [
        (str(descriptor.source_head.version_id), "opaque-sandbox-job")
    ]


@pytest.mark.parametrize(
    "files, message",
    [
        ({"main.tex": b"x", "unsafe.sty": b"x"}, "supported TeX or BibTeX"),
        ({"main.tex": b"x", "../outside.tex": b"x"}, "safe relative path"),
        ({"main.tex": b"x", "dir//outside.tex": b"x"}, "safe relative path"),
        ({"main.tex": b"x", "nul\x00.tex": b"x"}, "safe relative path"),
        ({"main.tex": b"x", "folder\\outside.tex": b"x"}, "safe relative path"),
        ({"references.bib": b"x"}, "root document"),
    ],
)
def test_human_save_rejects_invalid_file_sets(db, settings, files, message):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None
    with pytest.raises(Exception, match=message):
        service.save_human_version(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            expected_parent_version_id=initial.source_head.version_id,
            files=files,
        )


def test_database_rejects_a_second_paper_even_if_service_is_bypassed(db):
    session_id = _session(db)
    db.add_all(
        [
            ChatArtifact(
                id=uuid.uuid4(),
                session_id=session_id,
                identifier="one",
                kind="latex_paper",
                title="One",
            ),
            ChatArtifact(
                id=uuid.uuid4(),
                session_id=session_id,
                identifier="two",
                kind="latex_paper",
                title="Two",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        db.flush()
