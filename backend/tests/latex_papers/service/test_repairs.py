"""AI repair candidates, async sandbox repairs, and repair budgets."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from backend.models.database import (
    ChatLatexPaperFigureBlob,
)
from backend.services.chat_artifact_service import (
    ArtifactError,
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


def test_repair_wait_covers_a_full_compile_inside_the_cli_timeout():
    import re

    from backend.services import latex_paper_service

    cli = (
        Path(__file__).resolve().parents[3] / "chat_sandbox_worker" / "paper_cli.py"
    ).read_text()
    cli_timeout = int(re.search(r"urlopen\(request, timeout=(\d+)\)", cli).group(1))
    deadline = latex_paper_service._REPAIR_DEADLINE_SECONDS

    assert deadline >= 90
    # Polling stops at the deadline; the result read and storage need the rest.
    assert deadline + 25 <= cli_timeout
    assert (
        latex_paper_service._REPAIR_POLL_ATTEMPTS
        * latex_paper_service._REPAIR_POLL_SECONDS
        >= deadline
    )


def test_repair_cancels_at_its_wall_clock_deadline(db, settings, monkeypatch):
    from backend.services import latex_paper_service

    class SlowCompiler(_Compiler):
        def __init__(self):
            super().__init__(CompilerJobState.QUEUED)
            self.canceled = False

        def status(self, job_id: str):
            # Each poll is slow: the compile never finishes inside the budget.
            clock[0] += 30.0
            return super().status(job_id)

        def cancel(self, job_id: str):
            self.canceled = True
            return super().cancel(job_id)

    clock = [0.0]
    compiler = _Compiler()
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    service = LatexPaperService(db, settings, storage=storage, compiler=compiler)
    initial = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=_session(db)
    )
    compiler.state = CompilerJobState.FAILED
    failed = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\badcommand"},
    )
    slow = SlowCompiler()
    service.compiler = slow
    monkeypatch.setattr(latex_paper_service.time, "sleep", lambda _: None)
    monkeypatch.setattr(latex_paper_service.time, "monotonic", lambda: clock[0])

    outcome = service.repair_failed_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=failed.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\stillslow"},
        provenance={"selected_model": "test-model", "repair": True},
    )

    assert slow.canceled is True
    assert outcome.repaired is False
    assert outcome.exhausted is False
    assert clock[0] <= latex_paper_service._REPAIR_DEADLINE_SECONDS + 30.0


def test_edit_context_checks_out_a_compiled_head_but_repair_context_does_not(
    db, settings
):
    import pytest

    from backend.services.chat_artifact_service import ArtifactError

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
    source = b"\\documentclass{article}\\begin{document}Compiled\\end{document}"
    compiled = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={"main.tex": source},
    )
    assert compiled.source_head is not None

    descriptor, files = service.source_context(
        owner_id="owner-1", artifact_id=initial.artifact_id
    )

    assert descriptor.source_head is not None
    assert descriptor.source_head.version_id == compiled.source_head.version_id
    assert files["main.tex"] == source
    with pytest.raises(ArtifactError, match="has not failed"):
        service.repair_context(owner_id="owner-1", artifact_id=initial.artifact_id)


def test_retried_ai_draft_and_repair_return_the_head_they_already_published(
    db, settings
):
    """A gateway can drop the reply after the service published the candidate."""
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
    compiler.state = CompilerJobState.FAILED
    broken = {"main.tex": b"\\documentclass{article}\\badcommand"}
    draft = service.save_ai_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files=broken,
        model_identity="selected-model",
    )
    assert draft.source_head is not None
    assert (
        service.save_ai_version(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            expected_parent_version_id=initial.source_head.version_id,
            files=broken,
            model_identity="selected-model",
        ).source_head
        == draft.source_head
    )

    compiler.state = CompilerJobState.SUCCEEDED
    fixed = {
        "main.tex": b"\\documentclass{article}\\begin{document}Fixed\\end{document}"
    }
    repair = {
        "owner_id": "owner-1",
        "artifact_id": initial.artifact_id,
        "expected_parent_version_id": draft.source_head.version_id,
        "provenance": {"model": "selected-model", "repair": True},
    }
    repaired = service.repair_failed_version(files=fixed, **repair)
    replayed = service.repair_failed_version(files=fixed, **repair)

    assert replayed.repaired is True
    assert replayed.descriptor.source_head == repaired.descriptor.source_head
    assert (
        service.list_history(owner_id="owner-1", artifact_id=initial.artifact_id)
        .items[0]
        .version
        == 3
    )
    with pytest.raises(ArtifactError, match="updated elsewhere"):
        service.repair_failed_version(
            files={"main.tex": b"\\documentclass{article}different"}, **repair
        )


def test_paper_cli_retries_once_when_an_edge_proxy_drops_the_reply(monkeypatch):
    import io
    import json
    import urllib.error

    from backend.chat_sandbox_worker import paper_cli

    replies = [
        urllib.error.HTTPError("url", 502, "Bad Gateway", {}, io.BytesIO(b"")),
        io.BytesIO(json.dumps({"paper": {"artifact_id": "a"}}).encode()),
    ]

    def urlopen(request, timeout):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(paper_cli.urllib.request, "urlopen", urlopen)

    assert paper_cli._command("begin-edit") == {"paper": {"artifact_id": "a"}}
    assert replies == []


def test_paper_cli_does_not_retry_a_create_whose_reply_was_lost(monkeypatch):
    import io
    import urllib.error

    from backend.chat_sandbox_worker import paper_cli

    calls = []

    def urlopen(request, timeout):
        calls.append(request)
        raise urllib.error.HTTPError("url", 502, "Bad Gateway", {}, io.BytesIO(b""))

    monkeypatch.setattr(paper_cli.urllib.request, "urlopen", urlopen)

    with pytest.raises(RuntimeError):
        paper_cli._command("create", title="Survey")
    assert len(calls) == 1
