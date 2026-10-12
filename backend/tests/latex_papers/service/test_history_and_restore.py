"""Save validation, version history, restore, and polling."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

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
