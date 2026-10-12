"""JSONB-on-SQLite compilation and the db/settings fixtures for LaTeX service tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    Base,
    ChatArtifact,
    ChatArtifactVersion,
    ChatLatexPaperFigureBlob,
    ChatLatexPaperFigureReference,
    ChatLatexPaperStorageCleanup,
    ChatLatexPaperVersion,
    ChatSession,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _sqlite_jsonb_typeof(connection, _record):
        connection.create_function("jsonb_typeof", 1, lambda _value: "array")

    Base.metadata.create_all(
        engine,
        tables=[
            ChatSession.__table__,
            ChatArtifact.__table__,
            ChatArtifactVersion.__table__,
            ChatLatexPaperVersion.__table__,
            ChatLatexPaperFigureBlob.__table__,
            ChatLatexPaperFigureReference.__table__,
            ChatLatexPaperStorageCleanup.__table__,
        ],
    )
    with Session(engine) as session:
        yield session


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        chat_artifacts_enabled=True,
        chat_latex_paper_enabled=True,
        chat_latex_compiler_jobs_enabled=True,
        chat_artifact_storage_backend="local",
        chat_artifact_local_dir=str(tmp_path / "storage"),
    )
