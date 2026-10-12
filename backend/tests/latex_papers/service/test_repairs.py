"""AI repair candidates, async sandbox repairs, and repair budgets."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select

from backend.models.database import (
    ChatLatexPaperFigureBlob,
)
from backend.services.chat_artifact_service import (
    LocalArtifactStorage,
)
from backend.services.latex_paper_service import LatexPaperService
from latex_compiler_contract import (
    CompilerJobState,
)
from backend.tests.latex_papers.service.harness import (
    _Compiler,
    _session,
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
