"""Project and version deletion cancels pending sandboxes."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

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
