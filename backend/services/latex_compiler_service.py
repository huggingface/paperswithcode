"""Transport boundary for private, per-job LaTeX compilation."""

from __future__ import annotations

import base64
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, ParamSpec, Protocol, TypeVar

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from huggingface_hub.errors import SandboxError

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
    validate_staging_sandbox_compiler_identity,
)

logger = logging.getLogger(__name__)
_SANDBOX_PORT = 7860
_SANDBOX_EGRESS_ATTESTATION = "sandbox-netns-v1"
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
        except SandboxError:
            raise RuntimeError("LaTeX Sandbox provider operation failed") from None

    return guarded


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
    client: httpx.Client
    envelope: CompilerEnvelope


class HuggingFaceSandboxLatexCompilerTransport:
    """One disposable HF Sandbox VM per compile, with an in-VM egress barrier."""

    def __init__(
        self,
        *,
        image: str,
        namespace: str,
        token: str,
        private_key: Ed25519PrivateKey,
        flavor: str = "cpu-upgrade",
        idle_timeout_seconds: int = 180,
        sandbox_create: Callable[..., Any] | None = None,
        sandbox_connect: Callable[..., Any] | None = None,
        http_client_factory: Callable[[dict[str, str]], httpx.Client] | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if sandbox_create is None or sandbox_connect is None:
            from huggingface_hub import Sandbox

            sandbox_create = sandbox_create or Sandbox.create
            sandbox_connect = sandbox_connect or Sandbox.connect
        self.image = validate_staging_sandbox_compiler_identity(image, namespace)
        self.namespace = namespace
        self.token = token
        self.private_key = private_key
        self.flavor = flavor
        self.idle_timeout_seconds = idle_timeout_seconds
        self.sandbox_create = sandbox_create
        self.sandbox_connect = sandbox_connect
        self.http_client_factory = http_client_factory or (
            lambda headers: httpx.Client(headers=headers, timeout=15.0)
        )
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
            response = session.client.post(
                session.sandbox.proxy_url_for(_SANDBOX_PORT, "/v1/jobs"),
                json=submission.model_dump(mode="json"),
            )
            response.raise_for_status()
            status = _status(response, job_id)
        except (SandboxError, httpx.HTTPError, OSError, RuntimeError, ValueError):
            self._release(job_id, session)
            raise
        self._sessions[job_id] = session
        return status.model_copy(update={"provider_job_id": session.sandbox.id})

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
            sandbox = self.sandbox_connect(
                provider_job_id, namespace=self.namespace, token=self.token
            )
            try:
                session = self._session_after_health(sandbox, envelope)
            except (SandboxError, httpx.HTTPError, OSError, RuntimeError, ValueError):
                sandbox.kill()
                raise
            self._sessions[job_id] = session
        return self.status(job_id)

    @_fail_closed_sandbox_errors
    def status(self, job_id: str) -> CompilerStatus:
        session = self._session(job_id)
        try:
            response = session.client.get(
                session.sandbox.proxy_url_for(_SANDBOX_PORT, f"/v1/jobs/{job_id}")
            )
            response.raise_for_status()
            return _status(response, job_id).model_copy(
                update={"provider_job_id": session.sandbox.id}
            )
        except ValueError:
            self._release(job_id, session)
            raise

    @_fail_closed_sandbox_errors
    def result(self, job_id: str) -> CompilerResult:
        session = self._session(job_id)
        try:
            response = session.client.get(
                session.sandbox.proxy_url_for(
                    _SANDBOX_PORT, f"/v1/jobs/{job_id}/result"
                )
            )
            response.raise_for_status()
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
            response = session.client.delete(
                session.sandbox.proxy_url_for(_SANDBOX_PORT, f"/v1/jobs/{job_id}")
            )
            response.raise_for_status()
            result = _status(response, job_id).model_copy(
                update={"provider_job_id": session.sandbox.id}
            )
            self._canceled.add(job_id)
            return result
        finally:
            self._release(job_id, session)

    @_fail_closed_sandbox_errors
    def cancel_provider_job(self, provider_job_id: str) -> None:
        """Kill a detached Sandbox by its durable provider handle only."""

        sandbox = self.sandbox_connect(
            provider_job_id, namespace=self.namespace, token=self.token
        )
        sandbox.kill()
        logger.info("latex_compiler_event event=sandbox_provider_job_canceled")

    @_fail_closed_sandbox_errors
    def health(self, job_id: str) -> dict[str, object]:
        """Read the content-free in-sandbox operational snapshot."""
        session = self._session(job_id)
        try:
            response = session.client.get(
                session.sandbox.proxy_url_for(_SANDBOX_PORT, "/health")
            )
            response.raise_for_status()
            return self._qualified_health_snapshot(response.json())
        except (RuntimeError, ValueError):
            self._release(job_id, session)
            raise

    @_fail_closed_sandbox_errors
    def metrics(self, job_id: str) -> dict[str, object]:
        session = self._session(job_id)
        response = session.client.get(
            session.sandbox.proxy_url_for(_SANDBOX_PORT, "/metrics")
        )
        response.raise_for_status()
        return response.json()

    @_fail_closed_sandbox_errors
    def isolation(self, job_id: str) -> dict[str, object]:
        """Return the non-secret Sandbox isolation contract for qualification."""
        snapshot = self.health(job_id)
        return {
            "image": snapshot["qualified_image"],
            "forward_hf_token": False,
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
        session = self._sessions.pop(job_id, None)
        if session is None:
            raise RuntimeError("LaTeX Sandbox job is not attached")
        session.client.close()
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
            image=self.image,
            flavor=self.flavor,
            idle_timeout=self.idle_timeout_seconds,
            env={
                "PWC_LATEX_COMPILER_PUBLIC_KEY": public_key,
                "PWC_LATEX_COMPILER_QUALIFIED_IMAGE": self.image,
                "PWC_LATEX_COMPILER_NETWORK_ISOLATION_REQUIRED": "true",
            },
            secrets=None,
            volumes=None,
            namespace=self.namespace,
            forward_hf_token=False,
            token=self.token,
        )
        try:
            # The preflight itself starts an unprivileged user/network namespace
            # and refuses any default route before manuscript bytes are submitted.
            sandbox.run(["python3", "-m", "latex_compiler_space.preflight"], timeout=15)
            sandbox.run(
                [
                    "python3",
                    "-m",
                    "uvicorn",
                    "latex_compiler_space.app:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(_SANDBOX_PORT),
                    "--no-access-log",
                ],
                background=True,
            )
            return self._session_after_health(sandbox, envelope)
        except (SandboxError, httpx.HTTPError, OSError, RuntimeError, ValueError):
            self._release(
                envelope.job_id, _SandboxSession(sandbox, httpx.Client(), envelope)
            )
            raise RuntimeError("LaTeX Sandbox isolation preflight failed") from None

    def _session_after_health(
        self, sandbox: Any, envelope: CompilerEnvelope
    ) -> _SandboxSession:
        client = self.http_client_factory(sandbox.proxy_headers)
        session = _SandboxSession(sandbox=sandbox, client=client, envelope=envelope)
        ready = False
        try:
            for _ in range(30):
                try:
                    response = client.get(
                        sandbox.proxy_url_for(_SANDBOX_PORT, "/health")
                    )
                    if response.status_code == 200:
                        snapshot = self._qualified_health_snapshot(response.json())
                        if snapshot.get("status") != "ready":
                            raise RuntimeError("LaTeX Sandbox compiler is not ready")
                        logger.info("latex_compiler_event event=sandbox_ready")
                        ready = True
                        return session
                except httpx.HTTPError:
                    pass
                self.sleep(0.5)
            raise RuntimeError("LaTeX Sandbox compiler did not become ready")
        finally:
            if not ready:
                client.close()

    def _qualified_health_snapshot(self, snapshot: object) -> dict[str, object]:
        if not isinstance(snapshot, dict):
            raise RuntimeError("LaTeX Sandbox compiler health response is invalid")
        if snapshot.get("qualified_image") != self.image:
            raise RuntimeError(
                "LaTeX Sandbox compiler image does not match the requested digest"
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
        try:
            session.client.close()
        finally:
            session.sandbox.kill()
        logger.info("latex_compiler_event event=sandbox_released")


def compiler_transport_from_settings(settings: Settings) -> LatexCompilerTransport:
    """Build the only application transport: an attested, per-job Sandbox."""
    if settings.environment != "staging":
        raise RuntimeError("LaTeX Sandbox transport is staging-only")
    if not settings.chat_latex_compiler_hf_sandbox_image:
        raise RuntimeError("LaTeX Sandbox image is not configured")
    try:
        image = validate_staging_sandbox_compiler_identity(
            settings.chat_latex_compiler_hf_sandbox_image,
            settings.chat_latex_compiler_hf_sandbox_namespace,
        )
    except EnvelopeError as error:
        raise RuntimeError(
            "LaTeX Sandbox image must use a private immutable HF digest"
        ) from error
    private_key = _private_key_from_settings(settings)
    if not settings.chat_latex_compiler_hf_sandbox_token:
        raise RuntimeError("LaTeX Sandbox credential is not configured")
    if (
        settings.chat_latex_compiler_hf_sandbox_egress_policy_attestation
        != _SANDBOX_EGRESS_ATTESTATION
    ):
        raise RuntimeError("LaTeX Sandbox egress policy is not attested")
    return HuggingFaceSandboxLatexCompilerTransport(
        image=image,
        namespace=settings.chat_latex_compiler_hf_sandbox_namespace,
        token=settings.chat_latex_compiler_hf_sandbox_token,
        private_key=private_key,
        flavor=settings.chat_latex_compiler_hf_sandbox_flavor,
        idle_timeout_seconds=settings.chat_latex_compiler_hf_sandbox_idle_timeout_seconds,
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


def _status(response: httpx.Response, expected_job_id: str) -> CompilerStatus:
    status = CompilerStatus.model_validate_json(response.content)
    if status.job_id != expected_job_id:
        raise EnvelopeError("Compiler response does not match the requested job")
    return status
