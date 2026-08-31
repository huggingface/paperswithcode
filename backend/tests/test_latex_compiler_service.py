from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from huggingface_hub.errors import SandboxError

from backend.config import Settings
from backend.services.latex_compiler_service import (
    HuggingFaceSandboxLatexCompilerTransport,
    LatexCompilerClient,
    compiler_transport_from_settings,
)
from latex_compiler_contract import (
    CompileLimits,
    CompilerEnvelope,
    CompilerResult,
    EnvelopeError,
    SANDBOX_WORKSPACE_ISOLATION_ATTESTATION,
    SANDBOX_WORKSPACE_LIMIT_BYTES,
)


def test_client_signs_submits_polls_cancels_and_reads_result() -> None:
    private_key = Ed25519PrivateKey.generate()
    source = b"zip bytes"
    observed: list[httpx.Request] = []
    job_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        if request.method == "POST":
            payload = json.loads(request.content)
            assert (
                payload["envelope"]["source_digest"]
                == hashlib.sha256(source).hexdigest()
            )
            assert payload["bundle_base64"] == base64.b64encode(source).decode()
            return httpx.Response(202, json={"job_id": job_id, "state": "queued"})
        if request.method == "DELETE":
            return httpx.Response(200, json={"job_id": job_id, "state": "canceled"})
        if request.url.path.endswith("/result"):
            result = CompilerResult.succeeded(
                CompilerEnvelope(
                    job_id=job_id,
                    source_digest=hashlib.sha256(source).hexdigest(),
                    source_bytes=len(source),
                    entrypoint="main.tex",
                    limits=CompileLimits(),
                    expires_at=int(time.time()) + 60,
                ),
                pdf=b"%PDF-test",
                log_tail="",
                compiler_image="test-image",
                engine_version="pdfTeX test",
            )
            return httpx.Response(200, json=result.model_dump(mode="json"))
        return httpx.Response(200, json={"job_id": job_id, "state": "compiling"})

    client = LatexCompilerClient(
        "https://compiler.example.invalid",
        private_key=private_key,
        hf_token="space-token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    submission = client.submit(job_id=job_id, bundle=source, entrypoint="main.tex")
    assert submission.job_id == job_id
    assert client.status(job_id).state == "compiling"
    assert client.cancel(job_id).state == "canceled"
    assert client.result(job_id).pdf == b"%PDF-test"
    assert observed[0].headers["authorization"] == "Bearer space-token"


def test_client_rejects_a_response_for_another_job() -> None:
    private_key = Ed25519PrivateKey.generate()
    client = LatexCompilerClient(
        "https://compiler.example.invalid",
        private_key=private_key,
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    202, json={"job_id": str(uuid.uuid4()), "state": "queued"}
                )
            )
        ),
    )

    with pytest.raises(EnvelopeError, match="requested job"):
        client.submit(job_id=str(uuid.uuid4()), bundle=b"source", entrypoint="main.tex")


def test_sandbox_transport_uses_a_dedicated_tokenless_job_and_reconnects() -> None:
    """A backend restart can reattach without creating a second Sandbox job."""

    private_key = Ed25519PrivateKey.generate()
    source = b"zip bytes"
    job_id = str(uuid.uuid4())
    image = (
        "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:" + "a" * 64
    )

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
                    "qualified_image": image,
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
        image=image,
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
    assert created[0][1]["env"]["PWC_LATEX_COMPILER_QUALIFIED_IMAGE"] == image
    assert created[0][1]["namespace"] == "nielsr"
    assert created[0][1]["token"] == "sandbox-token"
    assert any(command[0][0] == "python3" for command in sandbox.commands)
    assert transport.cancel(job_id).state.value == "canceled"
    assert sandbox.killed

    restarted = HuggingFaceSandboxLatexCompilerTransport(
        image=image,
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


def test_sandbox_transport_fails_closed_when_result_image_is_not_the_pinned_image() -> (
    None
):
    private_key = Ed25519PrivateKey.generate()
    source = b"zip bytes"
    job_id = str(uuid.uuid4())
    image = (
        "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:" + "a" * 64
    )
    mismatched_image = (
        "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:" + "b" * 64
    )
    submitted: CompilerEnvelope | None = None

    class FakeSandbox:
        id = "sandbox-job-id"

        def __init__(self) -> None:
            self.proxy_headers = {"X-Sandbox-Token": "ephemeral"}
            self.killed = False

        def run(self, *_: object, **__: object) -> None:
            return None

        def proxy_url_for(self, _port: int, path: str = "/") -> str:
            return f"https://sandbox.example.invalid{path}"

        def kill(self) -> None:
            self.killed = True

    sandbox = FakeSandbox()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submitted
        if request.url.path == "/health":
            return httpx.Response(
                200,
                json={
                    "status": "ready",
                    "qualified_image": image,
                    "network_isolation": "sandbox-netns-v1",
                    "workspace_isolation": SANDBOX_WORKSPACE_ISOLATION_ATTESTATION,
                    "workspace_limit_bytes": SANDBOX_WORKSPACE_LIMIT_BYTES,
                },
            )
        if request.method == "POST":
            submitted = CompilerEnvelope.model_validate(
                json.loads(request.content)["envelope"]
            )
            return httpx.Response(202, json={"job_id": job_id, "state": "queued"})
        assert submitted is not None
        result = CompilerResult.succeeded(
            submitted,
            pdf=b"%PDF-test",
            log_tail="",
            compiler_image=mismatched_image,
            engine_version="pdfTeX test",
        )
        return httpx.Response(200, json=result.model_dump(mode="json"))

    transport = HuggingFaceSandboxLatexCompilerTransport(
        image=image,
        namespace="nielsr",
        token="sandbox-token",
        private_key=private_key,
        sandbox_create=lambda **_: sandbox,
        sandbox_connect=lambda *_args, **_kwargs: sandbox,
        http_client_factory=lambda headers: httpx.Client(
            headers=headers, transport=httpx.MockTransport(handler)
        ),
    )

    transport.submit(job_id=job_id, bundle=source, entrypoint="main.tex")

    with pytest.raises(EnvelopeError, match="qualified Sandbox image"):
        transport.result(job_id)

    assert sandbox.killed


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
        image=(
            "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:"
            + "a" * 64
        ),
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


@pytest.mark.parametrize(
    ("image", "namespace"),
    [
        (
            "registry.hf.space/other-pwc-latex-compiler-sandbox-staging@sha256:"
            + "a" * 64,
            "other",
        ),
        (
            "registry.hf.space/nielsr-pwc-chat-artifacts-staging@sha256:" + "a" * 64,
            "nielsr",
        ),
        (
            "registry.hf.space/nielsr-pwc-latex-compiler-production-staging@sha256:"
            + "a" * 64,
            "nielsr",
        ),
    ],
)
def test_sandbox_transport_refuses_a_nonapproved_staging_compiler_identity(
    image: str, namespace: str
) -> None:
    """Runtime settings cannot redirect manuscripts to another HF image or owner."""

    with pytest.raises(EnvelopeError, match="approved staging"):
        HuggingFaceSandboxLatexCompilerTransport(
            image=image,
            namespace=namespace,
            token="sandbox-token",
            private_key=Ed25519PrivateKey.generate(),
            sandbox_create=lambda **_: None,
            sandbox_connect=lambda *_args, **_kwargs: None,
        )


def test_sandbox_transport_kills_a_job_when_preflight_raises_sandbox_error() -> None:
    """A provider-side preflight failure cannot leave a live compiler VM behind."""

    class FakeSandbox:
        id = "failed-sandbox-job"

        def __init__(self) -> None:
            self.killed = False

        def run(self, *_: object, **__: object) -> None:
            raise SandboxError("preflight unavailable")

        def kill(self) -> None:
            self.killed = True

    sandbox = FakeSandbox()
    transport = HuggingFaceSandboxLatexCompilerTransport(
        image=(
            "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:"
            + "a" * 64
        ),
        namespace="nielsr",
        token="sandbox-token",
        private_key=Ed25519PrivateKey.generate(),
        sandbox_create=lambda **_: sandbox,
        sandbox_connect=lambda *_args, **_kwargs: sandbox,
    )

    with pytest.raises(RuntimeError, match="isolation preflight failed"):
        transport.submit(
            job_id=str(uuid.uuid4()), bundle=b"zip bytes", entrypoint="main.tex"
        )

    assert sandbox.killed


def test_sandbox_transport_normalizes_provider_creation_errors() -> None:
    """Provider details must not escape the compiler service boundary."""

    transport = HuggingFaceSandboxLatexCompilerTransport(
        image=(
            "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:"
            + "a" * 64
        ),
        namespace="nielsr",
        token="sandbox-token",
        private_key=Ed25519PrivateKey.generate(),
        sandbox_create=lambda **_kwargs: (_ for _ in ()).throw(
            SandboxError("untrusted-provider-detail")
        ),
        sandbox_connect=lambda *_args, **_kwargs: None,
    )

    with pytest.raises(
        RuntimeError, match="Sandbox provider operation failed"
    ) as error:
        transport.submit(
            job_id=str(uuid.uuid4()), bundle=b"zip bytes", entrypoint="main.tex"
        )

    assert "untrusted-provider-detail" not in str(error.value)


def test_sandbox_transport_normalizes_provider_reconnect_errors() -> None:
    """Reattachment must not expose a provider response after process restart."""

    transport = HuggingFaceSandboxLatexCompilerTransport(
        image=(
            "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:"
            + "a" * 64
        ),
        namespace="nielsr",
        token="sandbox-token",
        private_key=Ed25519PrivateKey.generate(),
        sandbox_create=lambda **_kwargs: None,
        sandbox_connect=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            SandboxError("untrusted-provider-detail")
        ),
    )

    with pytest.raises(
        RuntimeError, match="Sandbox provider operation failed"
    ) as error:
        transport.resume(
            job_id=str(uuid.uuid4()),
            provider_job_id="provider-job",
            bundle=b"zip bytes",
            entrypoint="main.tex",
        )

    assert "untrusted-provider-detail" not in str(error.value)


def test_sandbox_transport_cancels_a_detached_provider_job_without_submission() -> None:
    """Deletion can terminate a durable Sandbox handle without source bytes."""

    class FakeSandbox:
        def __init__(self) -> None:
            self.killed = False

        def kill(self) -> None:
            self.killed = True

    sandbox = FakeSandbox()
    connected: list[tuple[str, str, str]] = []
    transport = HuggingFaceSandboxLatexCompilerTransport(
        image=(
            "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:"
            + "a" * 64
        ),
        namespace="nielsr",
        token="sandbox-token",
        private_key=Ed25519PrivateKey.generate(),
        sandbox_create=lambda **_kwargs: pytest.fail(
            "provider-handle cancellation must not submit a compiler job"
        ),
        sandbox_connect=lambda provider_job_id, *, namespace, token: (
            connected.append((provider_job_id, namespace, token)) or sandbox
        ),
    )

    transport.cancel_provider_job("opaque-sandbox-job")

    assert connected == [("opaque-sandbox-job", "nielsr", "sandbox-token")]
    assert sandbox.killed
    assert transport._sessions == {}


def test_sandbox_transport_cleans_up_a_malformed_health_payload() -> None:
    """Invalid readiness JSON cannot leave the newly-created Sandbox alive."""

    image = (
        "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:" + "a" * 64
    )

    class FakeSandbox:
        id = "malformed-health-sandbox"

        def __init__(self) -> None:
            self.proxy_headers = {"X-Sandbox-Token": "ephemeral"}
            self.killed = False

        def run(self, *_args: object, **_kwargs: object) -> None:
            return None

        def proxy_url_for(self, _port: int, path: str = "/") -> str:
            return f"https://sandbox.example.invalid{path}"

        def kill(self) -> None:
            self.killed = True

    sandbox = FakeSandbox()
    clients: list[httpx.Client] = []

    def make_client(headers: dict[str, str]) -> httpx.Client:
        client = httpx.Client(
            headers=headers,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, content=b"not-json")
            ),
        )
        clients.append(client)
        return client

    transport = HuggingFaceSandboxLatexCompilerTransport(
        image=image,
        namespace="nielsr",
        token="sandbox-token",
        private_key=Ed25519PrivateKey.generate(),
        sandbox_create=lambda **_kwargs: sandbox,
        sandbox_connect=lambda *_args, **_kwargs: sandbox,
        http_client_factory=make_client,
    )

    with pytest.raises(RuntimeError, match="isolation preflight failed"):
        transport.submit(
            job_id=str(uuid.uuid4()), bundle=b"zip bytes", entrypoint="main.tex"
        )

    assert sandbox.killed
    assert clients[0].is_closed


def test_sandbox_transport_cleans_up_an_attached_job_with_malformed_status() -> None:
    """Pydantic status validation failures must release the per-job Sandbox."""

    image = (
        "registry.hf.space/nielsr-pwc-latex-compiler-sandbox-staging@sha256:" + "a" * 64
    )
    job_id = str(uuid.uuid4())

    class FakeSandbox:
        id = "malformed-status-sandbox"

        def __init__(self) -> None:
            self.proxy_headers = {"X-Sandbox-Token": "ephemeral"}
            self.killed = False

        def run(self, *_args: object, **_kwargs: object) -> None:
            return None

        def proxy_url_for(self, _port: int, path: str = "/") -> str:
            return f"https://sandbox.example.invalid{path}"

        def kill(self) -> None:
            self.killed = True

    sandbox = FakeSandbox()
    clients: list[httpx.Client] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(
                200,
                json={
                    "status": "ready",
                    "qualified_image": image,
                    "network_isolation": "sandbox-netns-v1",
                    "workspace_isolation": SANDBOX_WORKSPACE_ISOLATION_ATTESTATION,
                    "workspace_limit_bytes": SANDBOX_WORKSPACE_LIMIT_BYTES,
                },
            )
        if request.method == "POST":
            return httpx.Response(202, json={"job_id": job_id, "state": "queued"})
        return httpx.Response(200, json={"job_id": job_id})

    def make_client(headers: dict[str, str]) -> httpx.Client:
        client = httpx.Client(headers=headers, transport=httpx.MockTransport(handler))
        clients.append(client)
        return client

    transport = HuggingFaceSandboxLatexCompilerTransport(
        image=image,
        namespace="nielsr",
        token="sandbox-token",
        private_key=Ed25519PrivateKey.generate(),
        sandbox_create=lambda **_kwargs: sandbox,
        sandbox_connect=lambda *_args, **_kwargs: sandbox,
        http_client_factory=make_client,
    )
    transport.submit(job_id=job_id, bundle=b"zip bytes", entrypoint="main.tex")

    with pytest.raises(ValueError):
        transport.status(job_id)

    assert sandbox.killed
    assert clients[0].is_closed


def test_compiler_transport_refuses_non_staging_configuration() -> None:
    with pytest.raises(RuntimeError, match="staging-only"):
        compiler_transport_from_settings(
            Settings(
                environment="production",
                chat_latex_compiler_hf_sandbox_image=(
                    "registry.hf.space/pwc-test-latex-compiler-staging@sha256:"
                    + "a" * 64
                ),
            )
        )
