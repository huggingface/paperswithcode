"""Private paper ownership, exports, and human saves."""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

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
)
from backend.tests.latex_papers.service.harness import (
    _Compiler,
    _session,
)


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
