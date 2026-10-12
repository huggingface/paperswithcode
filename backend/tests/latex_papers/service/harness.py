"""Chat session and fake compiler builders for LaTeX paper service tests."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy.orm import Session

from backend.models.database import (
    ChatSession,
)
from latex_compiler_contract import (
    CompileLimits,
    CompilerDiagnostic,
    CompilerEnvelope,
    CompilerJobState,
    CompilerResult,
    CompilerStatus,
)


def _session(
    db: Session, *, owner: str = "owner-1", paper_reader: bool = False
) -> uuid.UUID:
    session_id = uuid.uuid4()
    db.add(
        ChatSession(
            id=session_id,
            hf_user_id=owner,
            hf_username="owner",
            selected_model="model",
            execution_backend="modal_cli",
            primary_paper_id=1 if paper_reader else None,
        )
    )
    db.flush()
    return session_id


class _Compiler:
    def __init__(
        self,
        state: CompilerJobState = CompilerJobState.SUCCEEDED,
        *,
        pdf: bytes = b"%PDF-1.7\nscaffold\n",
    ):
        self.state = state
        self.pdf = pdf
        self.submitted: tuple[str, bytes, str] | None = None

    def submit(self, *, job_id: str, bundle: bytes, entrypoint: str, limits=None):
        self.submitted = (job_id, bundle, entrypoint)
        return CompilerStatus(job_id=job_id, state=self.state)

    def status(self, job_id: str):
        return CompilerStatus(job_id=job_id, state=self.state)

    def result(self, job_id: str):
        assert self.submitted is not None
        _, bundle, entrypoint = self.submitted
        envelope = CompilerEnvelope(
            job_id=job_id,
            source_digest=hashlib.sha256(bundle).hexdigest(),
            source_bytes=len(bundle),
            entrypoint=entrypoint,
            limits=CompileLimits(),
            expires_at=1,
        )
        if self.state == CompilerJobState.SUCCEEDED:
            return CompilerResult.succeeded(
                envelope,
                pdf=self.pdf,
                log_tail="",
                compiler_image="test-image",
                engine_version="pdfTeX",
            )
        return CompilerResult.failed(
            envelope,
            diagnostics=[
                CompilerDiagnostic(
                    severity="error",
                    file="main.tex",
                    line=7,
                    message="Undefined control sequence",
                )
            ],
            log_tail="bad TeX",
            compiler_image="test-image",
            engine_version="pdfTeX",
            elapsed_ms=1,
        )

    def cancel(self, job_id: str):
        return CompilerStatus(job_id=job_id, state=CompilerJobState.CANCELED)
