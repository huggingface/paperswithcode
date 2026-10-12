"""Restart reconciliation of pending compile jobs and sandboxes."""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import pytest

from backend.models.database import (
    ChatArtifact,
    ChatLatexPaperVersion,
)
from backend.services.chat_artifact_service import (
    LocalArtifactStorage,
)
from backend.services.latex_paper_service import LatexPaperService
from latex_compiler_contract import (
    CompilerJobState,
    CompilerStatus,
)
from backend.tests.latex_papers.service.harness import (
    _Compiler,
    _session,
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
