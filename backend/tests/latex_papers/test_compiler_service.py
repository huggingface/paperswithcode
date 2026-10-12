from __future__ import annotations

import uuid

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.services.latex_compiler_service import (
    HuggingFaceSandboxLatexCompilerTransport,
)
from latex_compiler_contract import (
    SANDBOX_WORKSPACE_ISOLATION_ATTESTATION,
    SANDBOX_WORKSPACE_LIMIT_BYTES,
)


IMAGE = (
    "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-netns-v1-staging@sha256:"
    + "a" * 64
)


def test_sandbox_transport_uses_a_dedicated_tokenless_job_and_reconnects() -> None:
    """A backend restart can reattach without creating a second Sandbox job."""

    private_key = Ed25519PrivateKey.generate()
    source = b"zip bytes"
    job_id = str(uuid.uuid4())

    class FakeSandbox:
        id = "sandbox-job-id"

        def __init__(self) -> None:
            self.proxy_headers = {"X-Sandbox-Token": "ephemeral"}
            self.commands: list[tuple[list[str], bool]] = []
            self.killed = False

        def run(
            self, command: list[str], *, background: bool = False, **_: object
        ) -> None:
            self.commands.append((command, background))

        def proxy_url_for(self, port: int, path: str = "/") -> str:
            assert port == 7860
            return f"https://sandbox.example.invalid{path}"

        def kill(self) -> None:
            self.killed = True

    created: list[tuple[FakeSandbox, dict[str, object]]] = []
    sandbox = FakeSandbox()
    connected: list[str] = []

    def create(**kwargs: object) -> FakeSandbox:
        created.append((sandbox, kwargs))
        return sandbox

    def connect(provider_job_id: str, **_: object) -> FakeSandbox:
        connected.append(provider_job_id)
        return sandbox

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(
                200,
                json={
                    "status": "ready",
                    "qualified_image": IMAGE,
                    "network_isolation": "sandbox-netns-v1",
                    "workspace_isolation": SANDBOX_WORKSPACE_ISOLATION_ATTESTATION,
                    "workspace_limit_bytes": SANDBOX_WORKSPACE_LIMIT_BYTES,
                },
            )
        if request.method == "POST":
            return httpx.Response(202, json={"job_id": job_id, "state": "queued"})
        if request.method == "DELETE":
            return httpx.Response(200, json={"job_id": job_id, "state": "canceled"})
        return httpx.Response(200, json={"job_id": job_id, "state": "compiling"})

    transport = HuggingFaceSandboxLatexCompilerTransport(
        image=IMAGE,
        namespace="nielsr",
        token="sandbox-token",
        private_key=private_key,
        sandbox_create=create,
        sandbox_connect=connect,
        http_client_factory=lambda headers: httpx.Client(
            headers=headers, transport=httpx.MockTransport(handler)
        ),
    )

    status = transport.submit(job_id=job_id, bundle=source, entrypoint="main.tex")
    assert status.provider_job_id == "sandbox-job-id"
    assert created[0][1]["forward_hf_token"] is False
    assert created[0][1]["secrets"] is None
    assert created[0][1]["volumes"] is None
    assert created[0][1]["namespace"] == "nielsr"
    assert created[0][1]["token"] == "sandbox-token"
    assert any(command[0][0] == "python3" for command in sandbox.commands)
    assert transport.cancel(job_id).state.value == "canceled"
    assert sandbox.killed

    restarted = HuggingFaceSandboxLatexCompilerTransport(
        image=IMAGE,
        namespace="nielsr",
        token="sandbox-token",
        private_key=private_key,
        sandbox_create=create,
        sandbox_connect=connect,
        http_client_factory=lambda headers: httpx.Client(
            headers=headers, transport=httpx.MockTransport(handler)
        ),
    )
    resumed = restarted.resume(
        job_id=job_id,
        provider_job_id="sandbox-job-id",
        bundle=source,
        entrypoint="main.tex",
    )
    assert resumed.provider_job_id == "sandbox-job-id"
    assert connected == ["sandbox-job-id"]
    assert len(created) == 1


def test_sandbox_transport_cleans_up_an_unhealthy_reconnected_job() -> None:
    class FakeSandbox:
        id = "stale-sandbox-job"

        def __init__(self) -> None:
            self.proxy_headers = {"X-Sandbox-Token": "ephemeral"}
            self.killed = False

        def proxy_url_for(self, _port: int, path: str = "/") -> str:
            return f"https://sandbox.example.invalid{path}"

        def kill(self) -> None:
            self.killed = True

    private_key = Ed25519PrivateKey.generate()
    sandbox = FakeSandbox()
    transport = HuggingFaceSandboxLatexCompilerTransport(
        image=IMAGE,
        namespace="nielsr",
        token="sandbox-token",
        private_key=private_key,
        sandbox_create=lambda **_: sandbox,
        sandbox_connect=lambda *_args, **_kwargs: sandbox,
        http_client_factory=lambda headers: httpx.Client(
            headers=headers,
            transport=httpx.MockTransport(lambda _: httpx.Response(503)),
        ),
        sleep=lambda _: None,
    )

    with pytest.raises(RuntimeError, match="did not become ready"):
        transport.resume(
            job_id=str(uuid.uuid4()),
            provider_job_id="stale-sandbox-job",
            bundle=b"zip bytes",
            entrypoint="main.tex",
        )

    assert sandbox.killed
