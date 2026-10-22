"""Each owner has an aggregate budget for paid compiler sandboxes."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.services import latex_paper_service
from backend.services.chat_artifact_service import ArtifactError, LocalArtifactStorage
from backend.services.latex_paper_service import LatexPaperService
from backend.tests.latex_papers.service.harness import _Compiler, _session
from latex_compiler_contract import CompilerJobState


def _service(db, settings, compiler):
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    return LatexPaperService(db, settings, storage=storage, compiler=compiler)


def test_owner_cannot_start_more_compiles_while_two_are_running(db, settings):
    service = _service(db, settings, _Compiler(CompilerJobState.COMPILING))
    # One paper per chat, so each compile comes from its own chat.
    for title in ("First", "Second"):
        service.create_neutral_scaffold(
            owner_id="owner-1", session_id=_session(db), title=title
        )

    with pytest.raises(ArtifactError) as error:
        service.create_neutral_scaffold(
            owner_id="owner-1", session_id=_session(db), title="Third"
        )
    assert error.value.code == "compile_capacity_exceeded"

    # Another owner's budget is independent.
    service.create_neutral_scaffold(
        owner_id="owner-2", session_id=_session(db, owner="owner-2"), title="Own"
    )


def test_owner_daily_compile_budget_is_enforced(db, settings, monkeypatch):
    monkeypatch.setattr(latex_paper_service, "_MAX_COMPILES_PER_OWNER_PER_DAY", 2)
    service = _service(db, settings, _Compiler())
    # One paper per chat, so each compile comes from its own chat.
    for title in ("First", "Second"):
        service.create_neutral_scaffold(
            owner_id="owner-1", session_id=_session(db), title=title
        )

    with pytest.raises(ArtifactError, match="Daily paper compile limit") as error:
        service.create_neutral_scaffold(
            owner_id="owner-1", session_id=_session(db), title="Third"
        )
    assert error.value.code == "compile_capacity_exceeded"
