"""Scaffold creation and failed compiles keep the last good preview."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import func, select

from backend.models.database import (
    ChatArtifact,
    ChatLatexPaperVersion,
)
from backend.services.chat_artifact_service import (
    LocalArtifactStorage,
    owner_artifact_storage_bytes,
)
from backend.services.latex_paper_service import LatexPaperService
from latex_compiler_contract import (
    CompilerJobState,
)
from backend.tests.latex_papers.service.harness import (
    _Compiler,
    _session,
)


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


def test_paper_heads_point_only_at_versions_already_inserted(db, settings):
    """PostgreSQL checks head foreign keys per statement; SQLite does not."""
    from sqlalchemy import event

    statements: list[str] = []

    def record(_connection, _cursor, statement, *_args):
        statements.append(" ".join(statement.split()).lower())

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
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
        service.save_human_version(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            expected_parent_version_id=initial.source_head.version_id,
            files={
                "main.tex": b"\\documentclass{article}\\begin{document}x\\end{document}"
            },
        )
    finally:
        event.remove(engine, "before_cursor_execute", record)

    inserted = 0
    for statement in statements:
        if statement.startswith("insert into chat_latex_paper_versions"):
            inserted += 1
        elif statement.startswith("update chat_artifacts") and (
            "source_head_version_id" in statement
            or "preview_head_version_id" in statement
        ):
            assert inserted, "a head pointer was written before its version row"
    assert inserted == 2


def test_scaffold_preloads_the_packages_authors_cannot_add():
    from backend.services.latex_paper_service import _neutral_scaffold

    source = _neutral_scaffold("Survey")["main.tex"].decode()
    preamble = source.split("\\begin{document}", 1)[0]
    for package in ("amsmath", "amssymb", "graphicx", "booktabs", "url", "natbib"):
        assert f"\\usepackage{{{package}}}" in preamble, package
    # hyperref must load after natbib to patch its citation links.
    assert preamble.index("{natbib}") < preamble.index("{hyperref}")
