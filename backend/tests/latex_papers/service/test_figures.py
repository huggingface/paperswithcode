"""Figure uploads, quotas, and orphaned figure reclamation."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.chat_artifact_service import (
    LocalArtifactStorage,
    owner_artifact_storage_bytes,
)
from backend.services.latex_paper_service import LatexPaperService
from backend.tests.latex_papers.service.harness import (
    _Compiler,
    _session,
)


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
    constrained = settings.model_copy(update={"chat_artifact_owner_quota_bytes": 6_600})
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
