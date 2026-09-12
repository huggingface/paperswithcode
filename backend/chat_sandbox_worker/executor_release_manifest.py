"""Signed immutable release manifest for the remote executor image."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPOSITORY = Path(__file__).resolve().parents[2]
MANIFEST_VERSION = 1


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _schema_digest(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(REPOSITORY).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def signed_release_manifest(
    *,
    image_id: str,
    environment_binary: Path,
    signing_key_file: Path,
    release_id: str,
) -> dict[str, object]:
    if (
        not image_id.startswith("im-")
        or not release_id
        or len(release_id) > 128
        or any(
            not (character.isascii() and (character.isalnum() or character in "-_."))
            for character in release_id
        )
    ):
        raise ValueError("Executor release identity is invalid")
    key_bytes = signing_key_file.read_bytes()
    if len(key_bytes) != 32:
        raise ValueError("Executor manifest signing key is invalid")
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    daemon = REPOSITORY / "backend/chat_sandbox_worker/executor_daemon.py"
    python_protocol = REPOSITORY / "backend/chat_sandbox_worker/executor_protocol.py"
    transport_protocol = REPOSITORY / "executor_transport/src/protocol.rs"
    payload: dict[str, object] = {
        "version": MANIFEST_VERSION,
        "release_id": release_id,
        "image_id": image_id,
        "image_digest": hashlib.sha256(image_id.encode()).hexdigest(),
        "environment_binary_digest": _digest(environment_binary),
        "daemon_digest": _digest(daemon),
        "protocol_version": 1,
        "protocol_digest": _digest(transport_protocol),
        "schema_digest": _schema_digest((python_protocol, transport_protocol)),
        "source_commit": source_commit,
        "source_commit_digest": hashlib.sha256(source_commit.encode()).hexdigest(),
    }
    payload["manifest_digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    private_key = Ed25519PrivateKey.from_private_bytes(key_bytes)
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return {
        "payload": payload,
        "signing_key_id": hashlib.sha256(public_key).hexdigest(),
        "signature": base64.urlsafe_b64encode(private_key.sign(canonical)).decode(),
    }
