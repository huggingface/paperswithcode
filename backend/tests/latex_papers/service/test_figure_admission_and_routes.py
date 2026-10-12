"""Figure admission, private download headers, and export routes."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from starlette.responses import Response

from backend.models.database import (
    ChatArtifact,
    ChatArtifactVersion,
)
from backend.services.chat_artifact_service import (
    LocalArtifactStorage,
    StoredArtifactFile,
)
from backend.services.latex_paper_service import LatexPaperService
from backend.tests.latex_papers.service.harness import (
    _Compiler,
    _session,
)


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
