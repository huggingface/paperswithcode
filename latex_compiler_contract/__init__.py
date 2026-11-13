"""Versioned, secret-free contract shared by PwC and the compiler Space."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from enum import StrEnum
from pathlib import PurePosixPath

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator

COMPILER_CONTRACT_VERSION = "latex-compiler-v1"
MAX_FILES = 100
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_LOG_BYTES = 64 * 1024
MAX_ENVELOPE_LIFETIME_SECONDS = 10 * 60
SANDBOX_WORKSPACE_ISOLATION_ATTESTATION = "sandbox-tmpfs-96m-v1"
SANDBOX_WORKSPACE_LIMIT_BYTES = 96 * 1024 * 1024
# A published Modal image ID is immutable: it names one built image layer set.
_QUALIFIED_COMPILER_IMAGE = re.compile(r"^im-[A-Za-z0-9]{20,32}$")
STAGING_COMPILER_MODAL_ENVIRONMENT = "pwc-latex-staging"


class EnvelopeError(ValueError):
    """A request cannot be trusted at the compiler boundary."""


class CompilerJobState(StrEnum):
    QUEUED = "queued"
    COMPILING = "compiling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    LOST = "lost"


class CompileLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    timeout_seconds: int = Field(default=120, ge=1, le=120)
    max_files: int = Field(default=MAX_FILES, ge=1, le=MAX_FILES)
    max_source_bytes: int = Field(default=MAX_SOURCE_BYTES, ge=1, le=MAX_SOURCE_BYTES)
    max_pdf_bytes: int = Field(default=MAX_PDF_BYTES, ge=1, le=MAX_PDF_BYTES)
    max_log_bytes: int = Field(default=MAX_LOG_BYTES, ge=1024, le=MAX_LOG_BYTES)


class CompilerEnvelope(BaseModel):
    """The exact metadata covered by an Ed25519 request signature."""

    model_config = ConfigDict(extra="forbid", strict=True)

    contract_version: str = COMPILER_CONTRACT_VERSION
    job_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_bytes: int = Field(ge=1, le=MAX_SOURCE_BYTES)
    entrypoint: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,299}\.tex$")
    limits: CompileLimits
    expires_at: int = Field(ge=1)

    @field_validator("contract_version")
    @classmethod
    def validate_contract_version(cls, value: str) -> str:
        if value != COMPILER_CONTRACT_VERSION:
            raise ValueError("Unsupported compiler contract version")
        return value

    @field_validator("entrypoint")
    @classmethod
    def validate_entrypoint(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("Compiler entrypoint must be a normalized relative path")
        return value


class CompileSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    envelope: CompilerEnvelope
    signature: str = Field(min_length=1, max_length=256)
    bundle_base64: str = Field(
        min_length=1, max_length=((MAX_SOURCE_BYTES + 2) // 3) * 4
    )


class CompilerDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    severity: str = Field(pattern=r"^(error|warning)$")
    message: str = Field(min_length=1, max_length=1000)
    file: str | None = Field(default=None, max_length=300)
    line: int | None = Field(default=None, ge=1, le=1_000_000)


class CompilerStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    job_id: str
    state: CompilerJobState
    # The backend persists this opaque provider handle only for a per-job
    # transport. The compiler API itself never needs to know about it.
    provider_job_id: str | None = Field(default=None, max_length=300)


class CompilerResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    job_id: str
    state: CompilerJobState
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    pdf_base64: str | None = None
    pdf_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    failure_category: str | None = Field(
        default=None,
        pattern=r"^(invalid_bundle|timeout|resource_limit|compiler_error|execution_error|service_error|transport_failure|canceled|lost)$",
    )
    diagnostics: list[CompilerDiagnostic] = Field(default_factory=list, max_length=100)
    log_tail: str = Field(default="", max_length=MAX_LOG_BYTES)
    compiler_image: str = Field(min_length=1, max_length=500)
    engine_version: str = Field(min_length=1, max_length=500)
    elapsed_ms: int = Field(default=0, ge=0, le=120_000)
    source_bytes: int = Field(ge=0, le=MAX_SOURCE_BYTES)
    pdf_bytes: int = Field(ge=0, le=MAX_PDF_BYTES)

    @property
    def pdf(self) -> bytes | None:
        if self.pdf_base64 is None:
            return None
        return _decode_base64(self.pdf_base64, "PDF")

    @classmethod
    def succeeded(
        cls,
        envelope: CompilerEnvelope,
        *,
        pdf: bytes,
        log_tail: str,
        compiler_image: str,
        engine_version: str,
        elapsed_ms: int = 0,
        diagnostics: list[CompilerDiagnostic] | None = None,
    ) -> CompilerResult:
        return cls(
            job_id=envelope.job_id,
            state=CompilerJobState.SUCCEEDED,
            source_digest=envelope.source_digest,
            pdf_base64=base64.b64encode(pdf).decode("ascii"),
            pdf_digest=hashlib.sha256(pdf).hexdigest(),
            diagnostics=diagnostics or [],
            log_tail=_bounded_text(log_tail),
            compiler_image=compiler_image,
            engine_version=engine_version,
            elapsed_ms=elapsed_ms,
            source_bytes=envelope.source_bytes,
            pdf_bytes=len(pdf),
        )

    @classmethod
    def failed(
        cls,
        envelope: CompilerEnvelope,
        *,
        diagnostics: list[CompilerDiagnostic],
        log_tail: str,
        compiler_image: str,
        engine_version: str,
        elapsed_ms: int,
        failure_category: str = "compiler_error",
    ) -> CompilerResult:
        return cls(
            job_id=envelope.job_id,
            state=CompilerJobState.FAILED,
            source_digest=envelope.source_digest,
            failure_category=failure_category,
            diagnostics=diagnostics,
            log_tail=_bounded_text(log_tail),
            compiler_image=compiler_image,
            engine_version=engine_version,
            elapsed_ms=elapsed_ms,
            source_bytes=envelope.source_bytes,
            pdf_bytes=0,
        )

    @classmethod
    def canceled(
        cls, envelope: CompilerEnvelope, *, compiler_image: str, engine_version: str
    ) -> CompilerResult:
        return cls(
            job_id=envelope.job_id,
            state=CompilerJobState.CANCELED,
            source_digest=envelope.source_digest,
            failure_category="canceled",
            compiler_image=compiler_image,
            engine_version=engine_version,
            source_bytes=envelope.source_bytes,
            pdf_bytes=0,
        )


def canonical_envelope_bytes(envelope: CompilerEnvelope) -> bytes:
    return json.dumps(
        envelope.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def sign_envelope(envelope: CompilerEnvelope, private_key: Ed25519PrivateKey) -> str:
    return _encode_base64(private_key.sign(canonical_envelope_bytes(envelope)))


def verify_envelope(
    envelope: CompilerEnvelope,
    signature: str,
    public_key_base64: str,
    *,
    now: float | None = None,
) -> None:
    now = time.time() if now is None else now
    if envelope.expires_at <= now:
        raise EnvelopeError("Compiler envelope has expired")
    if envelope.expires_at > now + MAX_ENVELOPE_LIFETIME_SECONDS:
        raise EnvelopeError("Compiler envelope expiry is too far in the future")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            _decode_base64(public_key_base64, "public key")
        )
        public_key.verify(
            _decode_base64(signature, "signature"), canonical_envelope_bytes(envelope)
        )
    except (ValueError, InvalidSignature) as error:
        raise EnvelopeError("Compiler envelope signature is invalid") from error


def validate_public_key(public_key_base64: str) -> None:
    try:
        Ed25519PublicKey.from_public_bytes(
            _decode_base64(public_key_base64, "public key")
        )
    except ValueError as error:
        raise EnvelopeError("Compiler public key is invalid") from error


def validate_qualified_compiler_image(image: str) -> str:
    """Require the exact immutable Modal image identity used by a sandbox."""
    if not _QUALIFIED_COMPILER_IMAGE.fullmatch(image):
        raise EnvelopeError("Compiler qualified image must be a Modal image ID")
    return image


def validate_staging_compiler_identity(image: str, environment: str) -> str:
    """Bind user-facing compiler work to the one approved staging environment."""
    if environment != STAGING_COMPILER_MODAL_ENVIRONMENT:
        raise EnvelopeError(
            "Compiler sandbox must use the approved staging compiler environment"
        )
    return validate_qualified_compiler_image(image)


def validate_result(result: CompilerResult, *, expected: CompilerEnvelope) -> None:
    if (
        result.job_id != expected.job_id
        or result.source_digest != expected.source_digest
    ):
        raise EnvelopeError("Compiler result does not match the submitted job")
    if result.source_bytes != expected.source_bytes:
        raise EnvelopeError("Compiler result source byte count is invalid")
    if result.state == CompilerJobState.SUCCEEDED:
        pdf = result.pdf
        if pdf is None or result.pdf_digest != hashlib.sha256(pdf).hexdigest():
            raise EnvelopeError("Compiler result PDF digest is invalid")
        if len(pdf) != result.pdf_bytes or len(pdf) > expected.limits.max_pdf_bytes:
            raise EnvelopeError("Compiler result PDF byte count is invalid")
    elif result.pdf is not None or result.pdf_digest is not None or result.pdf_bytes:
        raise EnvelopeError("Non-successful compiler result contains a PDF")


def _encode_base64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64(value: str, label: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, UnicodeEncodeError) as error:
        raise EnvelopeError(f"Compiler {label} encoding is invalid") from error


def _bounded_text(value: str) -> str:
    encoded = value.encode("utf-8")[-MAX_LOG_BYTES:]
    return encoded.decode("utf-8", errors="replace")
