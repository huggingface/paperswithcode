from __future__ import annotations

import json
import uuid
from collections.abc import Callable

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.services.latex_compiler_service import (
    CompilerRequestRejected,
    ModalSandboxLatexCompilerTransport,
)
from latex_compiler_contract import (
    SANDBOX_WORKSPACE_ISOLATION_ATTESTATION,
    SANDBOX_WORKSPACE_LIMIT_BYTES,
    EnvelopeError,
)


IMAGE = "im-" + "A1b2C3d4E5f6G7h8I9j0K1"
ENVIRONMENT = "pwc-latex-staging"
HEALTH = {
    "status": "ready",
    "qualified_image": IMAGE,
    "network_isolation": "sandbox-netns-v1",
    "workspace_isolation": SANDBOX_WORKSPACE_ISOLATION_ATTESTATION,
    "workspace_limit_bytes": SANDBOX_WORKSPACE_LIMIT_BYTES,
}


class _Stream:
    def __init__(self, data: bytes = b"") -> None:
        self.data = data
        self.written = b""

    def read(self) -> bytes:
        return self.data

    def write(self, data: bytes) -> None:
        self.written += data

    def write_eof(self) -> None:
        pass

    def drain(self) -> None:
        pass


class _Process:
    def __init__(self, stdout: bytes = b"", returncode: int = 0) -> None:
        self.stdin = _Stream()
        self.stdout = _Stream(stdout)
        self.returncode = returncode

    def wait(self) -> int:
        return self.returncode


class FakeSandbox:
    """Answers loopback-client calls with the handler's (status, body)."""

    object_id = "sb-compile-job"

    def __init__(self, handler: Callable[[str, str], tuple[int, object]]) -> None:
        self.handler = handler
        self.commands: list[tuple[str, ...]] = []
        self.terminated = False

    def exec(self, *command: str, **_: object) -> _Process:
        self.commands.append(command)
        if "latex_compiler_space.local_client" in command:
            method, path = command[-2], command[-1]
            status, body = self.handler(method, path)
            reply = {"status": status, "body": json.dumps(body)}
            return _Process(json.dumps(reply).encode())
        return _Process()

    def terminate(self) -> None:
        self.terminated = True


def _transport(sandbox: FakeSandbox, **overrides: object):
    created: list[dict[str, object]] = []
    reattached: list[str] = []

    def create(**options: object) -> FakeSandbox:
        created.append(options)
        return sandbox

    def from_id(sandbox_id: str) -> FakeSandbox:
        reattached.append(sandbox_id)
        return sandbox

    transport = ModalSandboxLatexCompilerTransport(
        image_id=IMAGE,
        environment=ENVIRONMENT,
        private_key=Ed25519PrivateKey.generate(),
        sandbox_create=create,
        sandbox_from_id=from_id,
        sleep=lambda _: None,
        **overrides,
    )
    return transport, created, reattached


def test_sandbox_transport_uses_a_network_blocked_credentialless_sandbox() -> None:
    """A backend restart can reattach without creating a second sandbox."""

    job_id = str(uuid.uuid4())

    def handler(method: str, path: str) -> tuple[int, object]:
        if path == "/health":
            return 200, HEALTH
        if method == "POST":
            return 202, {"job_id": job_id, "state": "queued"}
        if method == "DELETE":
            return 200, {"job_id": job_id, "state": "canceled"}
        return 200, {"job_id": job_id, "state": "compiling"}

    sandbox = FakeSandbox(handler)
    transport, created, reattached = _transport(sandbox)

    status = transport.submit(job_id=job_id, bundle=b"zip bytes", entrypoint="main.tex")

    assert status.provider_job_id == "sb-compile-job"
    assert created[0]["block_network"] is True
    assert created[0]["secrets"] == []
    assert created[0]["volumes"] == {}
    environment = created[0]["env"]
    assert isinstance(environment, dict)
    assert set(environment) == {
        "PWC_LATEX_COMPILER_PUBLIC_KEY",
        "PWC_LATEX_COMPILER_QUALIFIED_IMAGE",
        "PWC_LATEX_COMPILER_NETWORK_ISOLATION_REQUIRED",
    }
    # Every in-sandbox process runs as the unprivileged compiler account.
    assert all(
        command[:2] == ("setpriv", "--reuid=10001") for command in sandbox.commands
    )
    assert any(
        "latex_compiler_space.preflight" in command for command in sandbox.commands
    )
    assert transport.cancel(job_id).state.value == "canceled"
    assert sandbox.terminated

    restarted, restarted_created, restarted_reattached = _transport(sandbox)
    resumed = restarted.resume(
        job_id=job_id,
        provider_job_id="sb-compile-job",
        bundle=b"zip bytes",
        entrypoint="main.tex",
    )
    assert resumed.provider_job_id == "sb-compile-job"
    assert restarted_reattached == ["sb-compile-job"]
    assert restarted_created == []
    assert reattached == []


def test_sandbox_transport_cleans_up_an_unhealthy_reconnected_job() -> None:
    sandbox = FakeSandbox(lambda _method, _path: (503, {}))
    transport, _, _ = _transport(sandbox)

    with pytest.raises(RuntimeError, match="did not become ready"):
        transport.resume(
            job_id=str(uuid.uuid4()),
            provider_job_id="sb-stale",
            bundle=b"zip bytes",
            entrypoint="main.tex",
        )

    assert sandbox.terminated


def test_sandbox_transport_reports_a_rejected_submission_status() -> None:
    def handler(method: str, path: str) -> tuple[int, object]:
        if path == "/health":
            return 200, HEALTH
        return 422, {"detail": "Invalid compiler bundle"}

    sandbox = FakeSandbox(handler)
    transport, _, _ = _transport(sandbox)

    with pytest.raises(CompilerRequestRejected) as rejected:
        transport.submit(job_id=str(uuid.uuid4()), bundle=b"bad", entrypoint="main.tex")

    assert rejected.value.status_code == 422
    assert sandbox.terminated


def test_sandbox_transport_fails_closed_on_a_failed_isolation_preflight() -> None:
    class PreflightFails(FakeSandbox):
        def exec(self, *command: str, **options: object) -> _Process:
            if "latex_compiler_space.preflight" in command:
                self.commands.append(command)
                return _Process(returncode=1)
            return super().exec(*command, **options)

    sandbox = PreflightFails(lambda _method, _path: (200, HEALTH))
    transport, _, _ = _transport(sandbox)

    with pytest.raises(RuntimeError, match="isolation preflight failed"):
        transport.submit(job_id=str(uuid.uuid4()), bundle=b"zip", entrypoint="main.tex")

    assert sandbox.terminated
    assert not any("uvicorn" in command for command in sandbox.commands)


@pytest.mark.parametrize(
    ("image", "environment"),
    [
        ("registry.hf.space/x@sha256:" + "a" * 64, ENVIRONMENT),
        (IMAGE, "pwc-chat-staging"),
        (IMAGE, "pwc-latex-production"),
    ],
)
def test_sandbox_transport_requires_the_staging_compiler_identity(
    image: str, environment: str
) -> None:
    with pytest.raises(EnvelopeError):
        ModalSandboxLatexCompilerTransport(
            image_id=image,
            environment=environment,
            private_key=Ed25519PrivateKey.generate(),
            sandbox_create=lambda **_: None,
            sandbox_from_id=lambda _: None,
        )
