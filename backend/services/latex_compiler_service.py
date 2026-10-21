"""Transport boundary for private, per-job LaTeX compilation."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, ParamSpec, Protocol, TypeVar

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from modal.exception import Error as ModalError
from modal.stream_type import StreamType

from backend.config import Settings
from latex_compiler_contract import (
    CompileLimits,
    CompilerEnvelope,
    CompilerJobState,
    CompilerResult,
    CompilerStatus,
    CompileSubmission,
    EnvelopeError,
    SANDBOX_WORKSPACE_ISOLATION_ATTESTATION,
    SANDBOX_WORKSPACE_LIMIT_BYTES,
    sign_envelope,
    validate_result,
    validate_staging_compiler_identity,
)

logger = logging.getLogger(__name__)
_MODAL_APP_NAME = "pwc-latex-compiler"
_SANDBOX_EGRESS_ATTESTATION = "sandbox-netns-v1"
# A compile is capped at 120 CPU seconds; the sandbox also outlives one
# backend restart so reconciliation can reattach to it.
_SANDBOX_LIFETIME_SECONDS = 600
# Modal ignores the image's USER, so every process drops to the image's
# unprivileged compiler account before it touches manuscript bytes.
_AS_COMPILER = ("setpriv", "--reuid=10001", "--regid=10001", "--init-groups", "--")
# add_python puts Modal's interpreter first on PATH; the compiler's
# dependencies live in the image's Debian interpreter.
_COMPILER_PYTHON = "/usr/bin/python3"
_SandboxParameters = ParamSpec("_SandboxParameters")
_SandboxResult = TypeVar("_SandboxResult")


def _fail_closed_sandbox_errors(
    operation: Callable[_SandboxParameters, _SandboxResult],
) -> Callable[_SandboxParameters, _SandboxResult]:
    """Prevent provider diagnostics from crossing the compiler boundary."""

    @wraps(operation)
    def guarded(
        *args: _SandboxParameters.args, **kwargs: _SandboxParameters.kwargs
    ) -> _SandboxResult:
        try:
            return operation(*args, **kwargs)
        except ModalError:
            raise RuntimeError("LaTeX Sandbox provider operation failed") from None

    return guarded


class CompilerRequestRejected(RuntimeError):
    """The in-sandbox compiler answered with an HTTP error status."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"LaTeX Sandbox compiler rejected the request ({status_code})")
        self.status_code = status_code


class LatexCompilerTransport(Protocol):
    def submit(
        self,
        *,
        job_id: str,
        bundle: bytes,
        entrypoint: str,
        limits: CompileLimits | None = None,
    ) -> CompilerStatus: ...

    def status(self, job_id: str) -> CompilerStatus: ...

    def result(self, job_id: str) -> CompilerResult: ...

    def cancel(self, job_id: str) -> CompilerStatus: ...


def _submission(
    *,
    job_id: str,
    bundle: bytes,
    entrypoint: str,
    limits: CompileLimits | None,
    private_key: Ed25519PrivateKey,
    clock: Callable[[], float],
) -> tuple[CompilerEnvelope, CompileSubmission]:
    envelope = CompilerEnvelope(
        job_id=job_id,
        source_digest=hashlib.sha256(bundle).hexdigest(),
        source_bytes=len(bundle),
        entrypoint=entrypoint,
        limits=limits or CompileLimits(),
        expires_at=int(clock()) + 5 * 60,
    )
    return envelope, CompileSubmission(
        envelope=envelope,
        signature=sign_envelope(envelope, private_key),
        bundle_base64=base64.b64encode(bundle).decode("ascii"),
    )


@dataclass
class _SandboxSession:
    sandbox: Any
    envelope: CompilerEnvelope


@dataclass
class _LoopbackResponse:
    status_code: int
    content: bytes

    def json(self) -> object:
        return json.loads(self.content)


class ModalSandboxLatexCompilerTransport:
    """One disposable, network-blocked Modal sandbox per compile."""

    def __init__(
        self,
        *,
        image_id: str,
        environment: str,
        private_key: Ed25519PrivateKey,
        sandbox_create: Callable[..., Any] | None = None,
        sandbox_from_id: Callable[[str], Any] | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.image = validate_staging_compiler_identity(image_id, environment)
        self.environment = environment
        if sandbox_create is None or sandbox_from_id is None:
            import modal

            def create(**options: Any) -> Any:
                app = modal.App.lookup(
                    _MODAL_APP_NAME,
                    create_if_missing=True,
                    environment_name=environment,
                )
                # The app binds the sandbox to the compiler's environment.
                return modal.Sandbox.create(
                    app=app, image=modal.Image.from_id(self.image), **options
                )

            sandbox_create = sandbox_create or create
            sandbox_from_id = sandbox_from_id or modal.Sandbox.from_id
        self.private_key = private_key
        self.sandbox_create = sandbox_create
        self.sandbox_from_id = sandbox_from_id
        self.clock = clock
        self.sleep = sleep
        self._sessions: dict[str, _SandboxSession] = {}
        self._canceled: set[str] = set()

    @_fail_closed_sandbox_errors
    def submit(
        self,
        *,
        job_id: str,
        bundle: bytes,
        entrypoint: str,
        limits: CompileLimits | None = None,
    ) -> CompilerStatus:
        envelope, submission = _submission(
            job_id=job_id,
            bundle=bundle,
            entrypoint=entrypoint,
            limits=limits,
            private_key=self.private_key,
            clock=self.clock,
        )
        if job_id in self._sessions:
            return self.status(job_id)
        session = self._create_session(envelope)
        try:
            response = _require_success(
                self._request(
                    session.sandbox,
                    "POST",
                    "/v1/jobs",
                    submission.model_dump_json().encode(),
                )
            )
            status = _status(response, job_id)
        except (ModalError, OSError, RuntimeError, ValueError):
            self._release(job_id, session)
            raise
        self._sessions[job_id] = session
        return status.model_copy(update={"provider_job_id": session.sandbox.object_id})

    @_fail_closed_sandbox_errors
    def resume(
        self,
        *,
        job_id: str,
        provider_job_id: str,
        bundle: bytes,
        entrypoint: str,
        limits: CompileLimits | None = None,
    ) -> CompilerStatus:
        envelope, _ = _submission(
            job_id=job_id,
            bundle=bundle,
            entrypoint=entrypoint,
            limits=limits,
            private_key=self.private_key,
            clock=self.clock,
        )
        if job_id not in self._sessions:
            sandbox = self.sandbox_from_id(provider_job_id)
            try:
                session = self._session_after_health(sandbox, envelope)
            except (ModalError, OSError, RuntimeError, ValueError):
                sandbox.terminate()
                raise
            self._sessions[job_id] = session
        return self.status(job_id)

    @_fail_closed_sandbox_errors
    def status(self, job_id: str) -> CompilerStatus:
        session = self._session(job_id)
        try:
            response = _require_success(
                self._request(session.sandbox, "GET", f"/v1/jobs/{job_id}")
            )
            return _status(response, job_id).model_copy(
                update={"provider_job_id": session.sandbox.object_id}
            )
        except ValueError:
            self._release(job_id, session)
            raise

    @_fail_closed_sandbox_errors
    def result(self, job_id: str) -> CompilerResult:
        session = self._session(job_id)
        try:
            response = _require_success(
                self._request(session.sandbox, "GET", f"/v1/jobs/{job_id}/result")
            )
            result = CompilerResult.model_validate_json(response.content)
            validate_result(result, expected=session.envelope)
            if result.compiler_image != self.image:
                raise EnvelopeError(
                    "Compiler result does not match the qualified Sandbox image"
                )
            return result
        finally:
            self._release(job_id, session)

    @_fail_closed_sandbox_errors
    def cancel(self, job_id: str) -> CompilerStatus:
        if job_id in self._canceled:
            return CompilerStatus(job_id=job_id, state=CompilerJobState.CANCELED)
        session = self._session(job_id)
        try:
            response = _require_success(
                self._request(session.sandbox, "DELETE", f"/v1/jobs/{job_id}")
            )
            result = _status(response, job_id).model_copy(
                update={"provider_job_id": session.sandbox.object_id}
            )
            self._canceled.add(job_id)
            return result
        finally:
            self._release(job_id, session)

    @_fail_closed_sandbox_errors
    def cancel_provider_job(self, provider_job_id: str) -> None:
        """Terminate a detached sandbox by its durable provider handle only."""

        self.sandbox_from_id(provider_job_id).terminate()
        logger.info("latex_compiler_event event=sandbox_provider_job_canceled")

    @_fail_closed_sandbox_errors
    def health(self, job_id: str) -> dict[str, object]:
        """Read the content-free in-sandbox operational snapshot."""
        session = self._session(job_id)
        try:
            response = _require_success(
                self._request(session.sandbox, "GET", "/health")
            )
            return self._qualified_health_snapshot(response.json())
        except (RuntimeError, ValueError):
            self._release(job_id, session)
            raise

    @_fail_closed_sandbox_errors
    def metrics(self, job_id: str) -> dict[str, object]:
        session = self._session(job_id)
        return _require_success(
            self._request(session.sandbox, "GET", "/metrics")
        ).json()

    @_fail_closed_sandbox_errors
    def isolation(self, job_id: str) -> dict[str, object]:
        """Return the non-secret sandbox isolation contract for qualification."""
        snapshot = self.health(job_id)
        return {
            "image": snapshot["qualified_image"],
            "block_network": True,
            "secrets": False,
            "volumes": False,
            "network_isolation": snapshot["network_isolation"],
            "workspace_isolation": snapshot["workspace_isolation"],
            "workspace_limit_bytes": snapshot["workspace_limit_bytes"],
        }

    @_fail_closed_sandbox_errors
    def reconnect_after_restart(
        self,
        *,
        job_id: str,
        provider_job_id: str,
        bundle: bytes,
        entrypoint: str,
        limits: CompileLimits | None = None,
    ) -> CompilerStatus:
        """Detach local state and exercise the normal durable-job reattachment path."""
        if self._sessions.pop(job_id, None) is None:
            raise RuntimeError("LaTeX Sandbox job is not attached")
        return self.resume(
            job_id=job_id,
            provider_job_id=provider_job_id,
            bundle=bundle,
            entrypoint=entrypoint,
            limits=limits,
        )

    def _create_session(self, envelope: CompilerEnvelope) -> _SandboxSession:
        public_key = base64.urlsafe_b64encode(
            self.private_key.public_key().public_bytes_raw()
        ).decode("ascii")
        sandbox = self.sandbox_create(
            block_network=True,
            cpu=1.0,
            memory=2048,
            timeout=_SANDBOX_LIFETIME_SECONDS,
            env={
                "PWC_LATEX_COMPILER_PUBLIC_KEY": public_key,
                "PWC_LATEX_COMPILER_QUALIFIED_IMAGE": self.image,
                "PWC_LATEX_COMPILER_NETWORK_ISOLATION_REQUIRED": "true",
            },
            secrets=[],
            volumes={},
        )
        try:
            # Modal blocks all sandbox networking; the preflight also proves
            # each compile gets a fresh user/network/PID namespace with no route.
            preflight = sandbox.exec(
                *_AS_COMPILER,
                _COMPILER_PYTHON,
                "-m",
                "latex_compiler_space.preflight",
                workdir="/app",
                timeout=15,
            )
            preflight.wait()
            if preflight.returncode != 0:
                raise RuntimeError("LaTeX Sandbox isolation preflight failed")
            sandbox.exec(
                *_AS_COMPILER,
                _COMPILER_PYTHON,
                "-m",
                "uvicorn",
                "latex_compiler_space.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                "7860",
                "--no-access-log",
                workdir="/app",
                stdout=StreamType.DEVNULL,
                stderr=StreamType.DEVNULL,
            )
            return self._session_after_health(sandbox, envelope)
        except (ModalError, OSError, RuntimeError, ValueError):
            self._release(envelope.job_id, _SandboxSession(sandbox, envelope))
            raise RuntimeError("LaTeX Sandbox isolation preflight failed") from None

    def _session_after_health(
        self, sandbox: Any, envelope: CompilerEnvelope
    ) -> _SandboxSession:
        for _ in range(30):
            response = self._request(sandbox, "GET", "/health")
            if response.status_code == 200:
                snapshot = self._qualified_health_snapshot(response.json())
                if snapshot.get("status") != "ready":
                    raise RuntimeError("LaTeX Sandbox compiler is not ready")
                logger.info("latex_compiler_event event=sandbox_ready")
                return _SandboxSession(sandbox=sandbox, envelope=envelope)
            self.sleep(0.5)
        raise RuntimeError("LaTeX Sandbox compiler did not become ready")

    def _request(
        self, sandbox: Any, method: str, path: str, body: bytes = b""
    ) -> _LoopbackResponse:
        """Call the in-sandbox compiler API through its loopback client."""
        process = sandbox.exec(
            *_AS_COMPILER,
            _COMPILER_PYTHON,
            "-m",
            "latex_compiler_space.local_client",
            method,
            path,
            workdir="/app",
            timeout=30,
            text=False,
        )
        if body:
            process.stdin.write(body)
        process.stdin.write_eof()
        process.stdin.drain()
        output = process.stdout.read()
        process.wait()
        reply = json.loads(output)
        if not isinstance(reply, dict) or not isinstance(reply.get("status"), int):
            raise ValueError("LaTeX compiler loopback reply is invalid")
        return _LoopbackResponse(reply["status"], str(reply.get("body", "")).encode())

    def _qualified_health_snapshot(self, snapshot: object) -> dict[str, object]:
        if not isinstance(snapshot, dict):
            raise RuntimeError("LaTeX Sandbox compiler health response is invalid")
        if snapshot.get("qualified_image") != self.image:
            raise RuntimeError(
                "LaTeX Sandbox compiler image does not match the requested image"
            )
        if snapshot.get("network_isolation") != _SANDBOX_EGRESS_ATTESTATION:
            raise RuntimeError("LaTeX Sandbox compiler network isolation is unattested")
        if (
            snapshot.get("workspace_isolation")
            != SANDBOX_WORKSPACE_ISOLATION_ATTESTATION
            or snapshot.get("workspace_limit_bytes") != SANDBOX_WORKSPACE_LIMIT_BYTES
        ):
            raise RuntimeError("LaTeX Sandbox compiler workspace quota is unattested")
        return snapshot

    def _session(self, job_id: str) -> _SandboxSession:
        session = self._sessions.get(job_id)
        if session is None:
            raise RuntimeError("LaTeX Sandbox job is not attached")
        return session

    def _release(self, job_id: str, session: _SandboxSession) -> None:
        self._sessions.pop(job_id, None)
        session.sandbox.terminate()
        logger.info("latex_compiler_event event=sandbox_released")


def compiler_transport_from_settings(settings: Settings) -> LatexCompilerTransport:
    """Build the only application transport: an attested, per-job sandbox."""
    if settings.environment != "staging":
        raise RuntimeError("LaTeX Sandbox transport is staging-only")
    if not settings.chat_latex_compiler_modal_image_id:
        raise RuntimeError("LaTeX Sandbox image is not configured")
    try:
        image = validate_staging_compiler_identity(
            settings.chat_latex_compiler_modal_image_id,
            settings.chat_latex_compiler_modal_environment,
        )
    except EnvelopeError as error:
        raise RuntimeError(
            "LaTeX Sandbox must use an immutable image in the staging environment"
        ) from error
    return ModalSandboxLatexCompilerTransport(
        image_id=image,
        environment=settings.chat_latex_compiler_modal_environment,
        private_key=_private_key_from_settings(settings),
    )


def _private_key_from_settings(settings: Settings) -> Ed25519PrivateKey:
    key = settings.chat_latex_compiler_signing_private_key
    if not key:
        raise RuntimeError("LaTeX compiler signing key is not configured")
    try:
        raw = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
        return Ed25519PrivateKey.from_private_bytes(raw)
    except ValueError as error:
        raise RuntimeError("LaTeX compiler signing key is invalid") from error


def _require_success(response: _LoopbackResponse) -> _LoopbackResponse:
    if response.status_code == 0:
        raise RuntimeError("LaTeX Sandbox compiler is unavailable")
    if response.status_code >= 400:
        raise CompilerRequestRejected(response.status_code)
    return response


def _status(response: _LoopbackResponse, expected_job_id: str) -> CompilerStatus:
    status = CompilerStatus.model_validate_json(response.content)
    if status.job_id != expected_job_id:
        raise EnvelopeError("Compiler response does not match the requested job")
    return status
