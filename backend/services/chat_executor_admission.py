"""Issue bounded Rust-compatible executor admission frames."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.orm import Session

from backend.services.chat_executor_registry import ChatExecutorRegistry

MAX_ADMISSION_BYTES = 2_048
MAX_ENVIRONMENT_LIFETIME_MS = 24 * 60 * 60 * 1_000
MIN_READY_LIFETIME_MS = 240_000
REGISTRATION_TTL_MS = 60_000
SIGNATURE_DOMAIN = b"pwc-rendezvous-admission/v1"


@dataclass(frozen=True, slots=True)
class AdmissionManifest:
    manifest_digest: str
    image_digest: str
    environment_binary_digest: str
    daemon_digest: str
    source_commit: str
    protocol_version: int
    schema_digest: str
    release_id: str
    compatibility_expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AdmissionSigningKey:
    key_id: str
    private_key: Ed25519PrivateKey
    not_before_ms: int
    not_after_ms: int


def issue_launch_admission(
    db: Session,
    *,
    registry: ChatExecutorRegistry,
    signing_key: AdmissionSigningKey,
    environment_id: str,
    environment_generation: int,
    cell_id: str,
    shard_id: str,
    shard_database_id: uuid.UUID,
    shard_generation: int,
    key_epoch: int,
    lifecycle_class: str,
    manifest: AdmissionManifest,
    remaining_lifetime_ms: int,
) -> bytes:
    now = registry._database_now(db)
    issued_at_ms = int(now.timestamp() * 1000)
    if (
        not MIN_READY_LIFETIME_MS
        <= remaining_lifetime_ms
        <= MAX_ENVIRONMENT_LIFETIME_MS
    ):
        raise ValueError("Executor environment lifetime is invalid")
    nonce = secrets.token_bytes(16)
    claims: dict[str, object] = {
        "nonce": list(nonce),
        "purpose": "registration",
        "environment_id": environment_id,
        "environment_generation": environment_generation,
        "cell_id": cell_id,
        "shard_id": shard_id,
        "shard_generation": shard_generation,
        "public_noise_key_id": "pending",
        "key_epoch": key_epoch,
        "protocol_version": manifest.protocol_version,
        "schema_digest": _digest_bytes(manifest.schema_digest),
        "manifest_digest": _digest_bytes(manifest.manifest_digest),
        "image_digest": _digest_bytes(manifest.image_digest),
        "environment_binary_digest": _digest_bytes(manifest.environment_binary_digest),
        "daemon_digest": _digest_bytes(manifest.daemon_digest),
        "source_commit": _digest_bytes(manifest.source_commit),
        "release_id": manifest.release_id,
        "remaining_lifetime_ms": remaining_lifetime_ms,
        "environment_expires_at_ms": issued_at_ms + remaining_lifetime_ms,
        "compatibility_expires_at_ms": (
            int(manifest.compatibility_expires_at.timestamp() * 1000)
            if manifest.compatibility_expires_at is not None
            else None
        ),
        "lifecycle_class": lifecycle_class,
        "issued_at_ms": issued_at_ms,
        "expires_at_ms": issued_at_ms + REGISTRATION_TTL_MS,
    }
    frame = sign_admission(claims, signing_key=signing_key)
    registry.issue_nonce(
        db,
        nonce_digest=hashlib.sha256(nonce).hexdigest(),
        purpose="launch",
        environment_id=environment_id,
        environment_generation=environment_generation,
        shard_id=shard_database_id,
        shard_generation=shard_generation,
        key_epoch=key_epoch,
        ttl_seconds=60,
        retention_seconds=24 * 60 * 60,
    )
    return frame


def sign_admission(
    claims: dict[str, object], *, signing_key: AdmissionSigningKey
) -> bytes:
    canonical = canonical_claims(claims, signer_key_id=signing_key.key_id)
    issued_at_ms = _integer(claims, "issued_at_ms")
    expires_at_ms = _integer(claims, "expires_at_ms")
    if (
        issued_at_ms < signing_key.not_before_ms
        or expires_at_ms > signing_key.not_after_ms
    ):
        raise ValueError("Executor admission signing key is unavailable")
    envelope = {
        "claims": claims,
        "signer_key_id": signing_key.key_id,
        "signature": list(signing_key.private_key.sign(canonical)),
    }
    frame = json.dumps(envelope, separators=(",", ":")).encode()
    if len(frame) > MAX_ADMISSION_BYTES:
        raise ValueError("Executor admission frame is too large")
    return frame


def canonical_claims(claims: dict[str, object], *, signer_key_id: str) -> bytes:
    purpose = {"registration": 0, "reconnect": 1, "claim_liveness": 2}
    lifecycle = {"active_claim": 0, "assigned_idle": 1, "blank_pool": 2}
    encoded = bytearray(SIGNATURE_DOMAIN)
    _push(encoded, signer_key_id.encode())
    encoded.extend(bytes(_list(claims, "nonce", 16)))
    encoded.append(purpose[_string(claims, "purpose")])
    _push(encoded, _string(claims, "environment_id").encode())
    encoded.extend(_integer(claims, "environment_generation").to_bytes(8, "big"))
    _push(encoded, _string(claims, "cell_id").encode())
    _push(encoded, _string(claims, "shard_id").encode())
    encoded.extend(_integer(claims, "shard_generation").to_bytes(8, "big"))
    _push(encoded, _string(claims, "public_noise_key_id").encode())
    encoded.extend(_integer(claims, "key_epoch").to_bytes(8, "big"))
    encoded.extend(_integer(claims, "protocol_version").to_bytes(4, "big"))
    for field in (
        "schema_digest",
        "manifest_digest",
        "image_digest",
        "environment_binary_digest",
        "daemon_digest",
        "source_commit",
    ):
        encoded.extend(bytes(_list(claims, field, 32)))
    _push(encoded, _string(claims, "release_id").encode())
    encoded.extend(_integer(claims, "remaining_lifetime_ms").to_bytes(8, "big"))
    encoded.extend(_integer(claims, "environment_expires_at_ms").to_bytes(8, "big"))
    compatibility = claims.get("compatibility_expires_at_ms")
    if compatibility is None:
        encoded.append(0)
    elif isinstance(compatibility, int) and not isinstance(compatibility, bool):
        encoded.append(1)
        encoded.extend(compatibility.to_bytes(8, "big"))
    else:
        raise ValueError("Executor compatibility expiry is invalid")
    encoded.append(lifecycle[_string(claims, "lifecycle_class")])
    encoded.extend(_integer(claims, "issued_at_ms").to_bytes(8, "big"))
    encoded.extend(_integer(claims, "expires_at_ms").to_bytes(8, "big"))
    return bytes(encoded)


def _push(target: bytearray, value: bytes) -> None:
    if (
        not value
        or len(value) > 128
        or any(
            not (
                byte in b"-_."
                or ord("0") <= byte <= ord("9")
                or ord("A") <= byte <= ord("Z")
                or ord("a") <= byte <= ord("z")
            )
            for byte in value
        )
    ):
        raise ValueError("Executor admission identifier is invalid")
    target.extend(len(value).to_bytes(2, "big"))
    target.extend(value)


def _integer(claims: dict[str, object], field: str) -> int:
    value = claims.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"Executor admission {field} is invalid")
    return value


def _string(claims: dict[str, object], field: str) -> str:
    value = claims.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Executor admission {field} is invalid")
    return value


def _list(claims: dict[str, object], field: str, length: int) -> list[int]:
    value = claims.get(field)
    if (
        not isinstance(value, list)
        or len(value) != length
        or any(
            not isinstance(item, int) or isinstance(item, bool) or not 0 <= item <= 255
            for item in value
        )
    ):
        raise ValueError(f"Executor admission {field} is invalid")
    return value


def _digest_bytes(value: str) -> list[int]:
    if len(value) != 64:
        raise ValueError("Executor admission digest is invalid")
    try:
        return list(bytes.fromhex(value))
    except ValueError as error:
        raise ValueError("Executor admission digest is invalid") from error
