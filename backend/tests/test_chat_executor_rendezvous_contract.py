from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.chat_sandbox_worker.executor_release_manifest import (
    signed_release_manifest,
)
from backend.chat_sandbox_worker import publish_image
from backend.scripts.rollback_chat_executor_image import run as rollback_image
from backend.services.chat_executor_admission import (
    AdmissionSigningKey,
    sign_admission,
)
from backend.services.chat_sandbox_provider import ExecutorLaunchBundle, SandboxError

REPOSITORY = Path(__file__).resolve().parents[2]


def test_python_admission_rejects_identifiers_rust_would_reject() -> None:
    key = AdmissionSigningKey(
        key_id="invalid/key",
        private_key=Ed25519PrivateKey.from_private_bytes(b"\x18" * 32),
        not_before_ms=0,
        not_after_ms=2,
    )
    with pytest.raises(ValueError, match="identifier"):
        sign_admission({"issued_at_ms": 0, "expires_at_ms": 1}, signing_key=key)


def test_launch_bundle_is_bounded_and_contains_no_plaintext_in_tags() -> None:
    admission = b"signed-once"
    assert (
        base64.urlsafe_b64decode(ExecutorLaunchBundle(admission).encoded_admission())
        == admission
    )
    for invalid in (b"", b"x" * 2_049):
        with pytest.raises(SandboxError) as exc_info:
            ExecutorLaunchBundle(invalid).encoded_admission()
        assert exc_info.value.code == "sandbox_executor_admission_invalid"


def test_publishing_builds_locked_binary_and_sandbox_start_has_no_installs() -> None:
    publisher = (
        REPOSITORY / "backend/chat_sandbox_worker/publish_image.py"
    ).read_text()
    provider = (REPOSITORY / "backend/services/chat_sandbox_provider.py").read_text()
    environment = (REPOSITORY / "executor_transport/src/bin/environment.rs").read_text()
    assert '"build",\n            "--locked",\n            "--release"' in publisher
    assert "with_executor_binary(image, environment_binary)" in publisher
    assert '"/usr/local/bin/pwc-executor-environment"' in provider
    start = provider[provider.index("command = (") : provider.index("cpu_limit = (")]
    for forbidden in (
        "git clone",
        "pip install",
        "apt install",
        "curl ",
        "self-update",
    ):
        assert forbidden not in start
        assert forbidden not in environment


def test_publishing_requires_manifest_identity_before_external_work(
    monkeypatch,
) -> None:
    monkeypatch.delenv("PWC_CHAT_EXECUTOR_MANIFEST_SIGNING_KEY_FILE", raising=False)
    monkeypatch.delenv("PWC_CHAT_EXECUTOR_RELEASE_ID", raising=False)
    monkeypatch.setattr(
        publish_image.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("build started before validation"),
    )
    with pytest.raises(RuntimeError, match="signing configuration"):
        publish_image.main()


def test_release_manifest_signs_every_immutable_component(
    tmp_path, monkeypatch
) -> None:
    key = Ed25519PrivateKey.from_private_bytes(b"\x17" * 32)
    key_file = tmp_path / "signing.key"
    key_file.write_bytes(b"\x17" * 32)
    binary = tmp_path / "environment"
    binary.write_bytes(b"pinned-rust-binary")
    monkeypatch.setattr(
        "backend.chat_sandbox_worker.executor_release_manifest.subprocess.run",
        lambda *_args, **_kwargs: type("Result", (), {"stdout": "a" * 40})(),
    )

    manifest = signed_release_manifest(
        image_id="im-immutable",
        environment_binary=binary,
        signing_key_file=key_file,
        release_id="release-78",
    )

    payload = manifest["payload"]
    assert isinstance(payload, dict)
    for field in (
        "image_digest",
        "environment_binary_digest",
        "daemon_digest",
        "protocol_digest",
        "schema_digest",
        "source_commit_digest",
        "manifest_digest",
    ):
        assert len(str(payload[field])) == 64
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    key.public_key().verify(base64.urlsafe_b64decode(manifest["signature"]), canonical)


def test_rendezvous_has_no_tcp_listener_and_nginx_uses_exact_unix_route() -> None:
    rendezvous = (REPOSITORY / "executor_transport/src/bin/rendezvous.rs").read_text()
    assert "UnixListener" in rendezvous
    assert "TcpListener" not in rendezvous
    for environment in ("production", "staging"):
        nginx = (
            REPOSITORY
            / "deploy/nginx"
            / (
                "paperswithcode.co.conf"
                if environment == "production"
                else "staging.paperswithcode.co.conf"
            )
        ).read_text()
        assert "location = /v1/environment" in nginx
        assert "proxy_read_timeout 20s" in nginx
        assert "proxy_set_header X-PWC-Network-Source $remote_addr" in nginx
        assert "chat-executor-rendezvous.sock" in nginx
    unit = (
        REPOSITORY / "deploy/systemd/paperswithcode-chat-executor@.service"
    ).read_text()
    assert "LoadCredential=database-url:" in unit
    assert "LoadCredential=signing-key:" in unit
    assert "RuntimeDirectoryMode=0750" in unit
    assert "--database-url-file ${CREDENTIALS_DIRECTORY}/database-url" in unit
    assert "--signing-key-file ${CREDENTIALS_DIRECTORY}/signing-key" in unit


def test_image_rollback_cli_is_root_only_and_requires_exact_confirmation() -> None:
    arguments = [
        "--cell",
        "cell-v1",
        "--target-digest",
        "a" * 64,
        "--reason-class",
        "image_regression",
        "--qualification-evidence-ref",
        "qualification/previous.json",
        "--actor",
        "operator@example.test",
        "--request-id",
        "00000000-0000-0000-0000-000000000001",
        "--confirm",
        f"ROLLBACK {'b' * 64}",
    ]
    with pytest.raises(PermissionError):
        rollback_image(arguments, effective_uid=1000)
    with pytest.raises(ValueError, match="confirmation"):
        rollback_image(arguments, effective_uid=0)

    source = (
        REPOSITORY / "backend/scripts/rollback_chat_executor_image.py"
    ).read_text()
    assert "ChatExecutorRegistry" in source
    assert "FastAPI" not in source
