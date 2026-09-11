"""Authentication state machine for persistent executor registration.

This module contains no HTTP adapter and no transport payload handling.  The
repository that backs it must provide the same atomic transitions when this
contract is moved from deterministic feasibility tests to PostgreSQL.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

LAUNCH_CREDENTIAL_TTL_SECONDS = 60
RECOVERY_CHALLENGE_TTL_SECONDS = 10
ATTEMPT_RETENTION_SECONDS = 60
RECONNECT_TOKEN_TTL_SECONDS = 45
LIVE_CLAIM_RECOVERY_SECONDS = 30
MAX_RECOVERY_CHALLENGES_PER_ATTEMPT = 3
_PROTOCOL = b"pwc-executor-bootstrap-v1"


class BootstrapRejected(RuntimeError):
    """A bounded authentication transition was rejected without secret detail."""


@dataclass(frozen=True, slots=True)
class ProvisionedEnvironment:
    environment_id: str
    generation: int
    launch_credential_digest: bytes
    launch_expires_at: float
    identity_public_key: bytes | None = None
    launch_consumed_at: float | None = None
    key_epoch: int = 1
    revoked: bool = False


@dataclass(frozen=True, slots=True)
class AuthenticationAttempt:
    attempt_id: str
    environment_id: str
    generation: int
    kind: str
    created_at: float
    recovery_expires_at: float
    stream_recovery_expires_at: float | None = None
    challenge_digest: bytes | None = None
    challenge_expires_at: float | None = None
    challenges_issued: int = 0
    completed: bool = False


@dataclass(frozen=True, slots=True)
class RegistrationAuthorization:
    environment_id: str
    generation: int
    attempt_id: str
    identity_public_key: bytes
    key_epoch: int


@dataclass(frozen=True, slots=True)
class ReconnectToken:
    encoded: str
    nonce: str
    expires_at: float


@dataclass(frozen=True, slots=True)
class ReconnectAdmission:
    admitted: bool
    retry_after_seconds: float | None = None
    attempt_id: str | None = None


def _credential_digest(credential: str) -> bytes:
    return hashlib.sha256(credential.encode("utf-8")).digest()


def _proof_message(
    purpose: bytes,
    environment_id: str,
    generation: int,
    challenge: bytes,
    public_key: bytes,
) -> bytes:
    return b"\0".join(
        (
            _PROTOCOL,
            purpose,
            environment_id.encode("utf-8"),
            str(generation).encode("ascii"),
            challenge,
            public_key,
        )
    )


def registration_proof_message(
    environment_id: str,
    generation: int,
    launch_credential: str,
    public_key: bytes,
) -> bytes:
    """Return the exact first-registration proof message for test/client parity."""
    return _proof_message(
        b"first-registration",
        environment_id,
        generation,
        _credential_digest(launch_credential),
        public_key,
    )


def recovery_proof_message(
    environment_id: str,
    generation: int,
    challenge: bytes,
    public_key: bytes,
) -> bytes:
    """Return the exact pre-stream recovery proof message."""
    return _proof_message(
        b"bounded-recovery", environment_id, generation, challenge, public_key
    )


class ExecutorBootstrapStateMachine:
    """Thread-safe reference state machine for Task 0 authentication vectors."""

    def __init__(
        self,
        *,
        issuer_private_key: Ed25519PrivateKey,
        clock: Callable[[], float],
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        self._issuer = issuer_private_key
        self._clock = clock
        self._random_bytes = random_bytes
        self._lock = threading.Lock()
        self._environments: dict[tuple[str, int], ProvisionedEnvironment] = {}
        self._attempts: dict[str, AuthenticationAttempt] = {}
        self._consumed_nonces: dict[str, float] = {}
        self._active_attempt_by_environment: dict[tuple[str, int], str] = {}

    def provision(
        self, environment_id: str, generation: int, launch_credential: str
    ) -> None:
        now = self._clock()
        key = (environment_id, generation)
        record = ProvisionedEnvironment(
            environment_id=environment_id,
            generation=generation,
            launch_credential_digest=_credential_digest(launch_credential),
            launch_expires_at=now + LAUNCH_CREDENTIAL_TTL_SECONDS,
        )
        with self._lock:
            if key in self._environments:
                raise BootstrapRejected("environment already provisioned")
            self._environments[key] = record

    def redeem_launch(
        self,
        *,
        environment_id: str,
        generation: int,
        launch_credential: str,
        identity_public_key: bytes,
        signature: bytes,
    ) -> RegistrationAuthorization:
        key = (environment_id, generation)
        now = self._clock()
        with self._lock:
            record = self._current_environment(key, now)
            if (
                record.identity_public_key is not None
                or record.launch_consumed_at is not None
            ):
                raise BootstrapRejected("launch credential is unavailable")
            if not secrets.compare_digest(
                record.launch_credential_digest,
                _credential_digest(launch_credential),
            ):
                raise BootstrapRejected("launch credential is unavailable")
            self._verify(
                identity_public_key,
                signature,
                registration_proof_message(
                    environment_id,
                    generation,
                    launch_credential,
                    identity_public_key,
                ),
            )
            attempt = self._new_attempt(key, "first_registration", now)
            record = replace(
                record,
                identity_public_key=identity_public_key,
                launch_consumed_at=now,
            )
            self._environments[key] = record
            return self._authorization(record, attempt)

    def issue_recovery_challenge(
        self, environment_id: str, generation: int, attempt_id: str
    ) -> bytes:
        key = (environment_id, generation)
        now = self._clock()
        with self._lock:
            record = self._registered_environment(key, now)
            attempt = self._recoverable_attempt(key, attempt_id, now)
            if attempt.completed or (
                attempt.challenges_issued >= MAX_RECOVERY_CHALLENGES_PER_ATTEMPT
            ):
                raise BootstrapRejected("recovery attempt is unavailable")
            challenge = self._random_bytes(32)
            self._attempts[attempt_id] = replace(
                attempt,
                challenge_digest=hashlib.sha256(challenge).digest(),
                challenge_expires_at=now + RECOVERY_CHALLENGE_TTL_SECONDS,
                challenges_issued=attempt.challenges_issued + 1,
            )
            assert record.identity_public_key is not None
            return challenge

    def recover(
        self,
        *,
        environment_id: str,
        generation: int,
        attempt_id: str,
        challenge: bytes,
        signature: bytes,
    ) -> RegistrationAuthorization:
        key = (environment_id, generation)
        now = self._clock()
        with self._lock:
            record = self._registered_environment(key, now)
            attempt = self._recoverable_attempt(key, attempt_id, now)
            if (
                attempt.challenge_digest is None
                or attempt.challenge_expires_at is None
                or now >= attempt.challenge_expires_at
                or not secrets.compare_digest(
                    attempt.challenge_digest, hashlib.sha256(challenge).digest()
                )
            ):
                raise BootstrapRejected("recovery challenge is unavailable")
            assert record.identity_public_key is not None
            self._verify(
                record.identity_public_key,
                signature,
                recovery_proof_message(
                    environment_id,
                    generation,
                    challenge,
                    record.identity_public_key,
                ),
            )
            self._attempts[attempt_id] = replace(
                attempt,
                challenge_digest=None,
                challenge_expires_at=None,
                completed=True,
            )
            return self._authorization(record, attempt)

    def issue_reconnect_token(
        self,
        environment_id: str,
        generation: int,
        *,
        shard_id: str,
        shard_generation: int,
        lifecycle_class: str,
    ) -> ReconnectToken:
        now = self._clock()
        key = (environment_id, generation)
        with self._lock:
            record = self._registered_environment(key, now)
            # A heartbeat can be authenticated only after the registration
            # response was accepted by the bound identity. It closes the
            # response-loss recovery window before creating reconnect state.
            active = self._active_attempt_by_environment.pop(key, None)
            if active is not None:
                previous = self._attempts.get(active)
                if previous is not None:
                    self._attempts[active] = replace(previous, completed=True)
            nonce = self._token(self._random_bytes(24))
            expires_at = now + RECONNECT_TOKEN_TTL_SECONDS
            payload = {
                "environment_id": environment_id,
                "environment_generation": generation,
                "expires_at_ms": int(expires_at * 1000),
                "key_epoch": record.key_epoch,
                "lifecycle_class": lifecycle_class,
                "nonce": nonce,
                "shard_generation": shard_generation,
                "shard_id": shard_id,
            }
            body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            encoded = f"{self._token(body)}.{self._token(self._issuer.sign(body))}"
            return ReconnectToken(encoded=encoded, nonce=nonce, expires_at=expires_at)

    def admit_reconnect(
        self,
        token: str,
        *,
        expected_shard_id: str,
        expected_shard_generation: int,
        scheduler_slot_acquired: bool,
        retry_after_seconds: float = 0.05,
    ) -> ReconnectAdmission:
        now = self._clock()
        payload = self._decode_token(token)
        key = (
            str(payload["environment_id"]),
            int(payload["environment_generation"]),
        )
        with self._lock:
            record = self._registered_environment(key, now)
            if (
                payload["shard_id"] != expected_shard_id
                or payload["shard_generation"] != expected_shard_generation
                or payload["key_epoch"] != record.key_epoch
                or now * 1000 >= payload["expires_at_ms"]
            ):
                raise BootstrapRejected("reconnect authorization is unavailable")
            nonce = str(payload["nonce"])
            if nonce in self._consumed_nonces:
                raise BootstrapRejected("reconnect authorization is unavailable")
            if not scheduler_slot_acquired:
                return ReconnectAdmission(
                    admitted=False, retry_after_seconds=retry_after_seconds
                )
            self._consumed_nonces[nonce] = now
            attempt = self._new_attempt(key, "reconnect", now)
            return ReconnectAdmission(admitted=True, attempt_id=attempt.attempt_id)

    def authorize_generation_transition(
        self,
        *,
        environment_id: str,
        old_generation: int,
        new_generation: int,
        issuer_authorized: bool,
    ) -> None:
        now = self._clock()
        old_key = (environment_id, old_generation)
        new_key = (environment_id, new_generation)
        with self._lock:
            old = self._registered_environment(old_key, now)
            if (
                not issuer_authorized
                or new_generation <= old_generation
                or new_key in self._environments
            ):
                raise BootstrapRejected("generation transition is unavailable")
            assert old.identity_public_key is not None
            self._environments[new_key] = ProvisionedEnvironment(
                environment_id=environment_id,
                generation=new_generation,
                launch_credential_digest=b"",
                launch_expires_at=now,
                identity_public_key=old.identity_public_key,
                launch_consumed_at=now,
                key_epoch=old.key_epoch,
            )
            self._environments[old_key] = replace(old, revoked=True)

    def revoke(self, environment_id: str, generation: int) -> None:
        key = (environment_id, generation)
        with self._lock:
            record = self._environments[key]
            self._environments[key] = replace(
                record, revoked=True, key_epoch=record.key_epoch + 1
            )

    def _current_environment(
        self, key: tuple[str, int], now: float
    ) -> ProvisionedEnvironment:
        record = self._environments.get(key)
        if record is None or record.revoked or now >= record.launch_expires_at:
            raise BootstrapRejected("environment authorization is unavailable")
        return record

    def _registered_environment(
        self, key: tuple[str, int], now: float
    ) -> ProvisionedEnvironment:
        record = self._environments.get(key)
        if (
            record is None
            or record.revoked
            or record.identity_public_key is None
            or record.launch_consumed_at is None
        ):
            raise BootstrapRejected("environment authorization is unavailable")
        self._prune(now)
        return record

    def _new_attempt(
        self, key: tuple[str, int], kind: str, now: float
    ) -> AuthenticationAttempt:
        active = self._active_attempt_by_environment.get(key)
        if active is not None:
            previous = self._attempts.get(active)
            if previous is not None and now < previous.recovery_expires_at:
                raise BootstrapRejected("an authentication attempt is already active")
        attempt_id = self._token(self._random_bytes(18))
        attempt = AuthenticationAttempt(
            attempt_id=attempt_id,
            environment_id=key[0],
            generation=key[1],
            kind=kind,
            created_at=now,
            recovery_expires_at=now + ATTEMPT_RETENTION_SECONDS,
            stream_recovery_expires_at=(
                now + LIVE_CLAIM_RECOVERY_SECONDS if kind == "reconnect" else None
            ),
        )
        self._attempts[attempt_id] = attempt
        self._active_attempt_by_environment[key] = attempt_id
        return attempt

    def _recoverable_attempt(
        self, key: tuple[str, int], attempt_id: str, now: float
    ) -> AuthenticationAttempt:
        attempt = self._attempts.get(attempt_id)
        if (
            attempt is None
            or (attempt.environment_id, attempt.generation) != key
            or now >= attempt.recovery_expires_at
            or (
                attempt.stream_recovery_expires_at is not None
                and now >= attempt.stream_recovery_expires_at
            )
        ):
            raise BootstrapRejected("recovery attempt is unavailable")
        return attempt

    def _prune(self, now: float) -> None:
        expired_attempts = [
            attempt_id
            for attempt_id, attempt in self._attempts.items()
            if now >= attempt.recovery_expires_at
        ]
        for attempt_id in expired_attempts:
            attempt = self._attempts.pop(attempt_id)
            key = (attempt.environment_id, attempt.generation)
            if self._active_attempt_by_environment.get(key) == attempt_id:
                self._active_attempt_by_environment.pop(key, None)
        consumed_before = now - RECONNECT_TOKEN_TTL_SECONDS
        self._consumed_nonces = {
            nonce: consumed_at
            for nonce, consumed_at in self._consumed_nonces.items()
            if consumed_at >= consumed_before
        }

    @staticmethod
    def _verify(public_key: bytes, signature: bytes, message: bytes) -> None:
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
        except (InvalidSignature, ValueError):
            raise BootstrapRejected("identity proof is unavailable") from None

    @staticmethod
    def _authorization(
        record: ProvisionedEnvironment, attempt: AuthenticationAttempt
    ) -> RegistrationAuthorization:
        assert record.identity_public_key is not None
        return RegistrationAuthorization(
            environment_id=record.environment_id,
            generation=record.generation,
            attempt_id=attempt.attempt_id,
            identity_public_key=record.identity_public_key,
            key_epoch=record.key_epoch,
        )

    def _decode_token(self, value: str) -> dict[str, object]:
        try:
            encoded_body, encoded_signature = value.split(".", 1)
            body = self._untoken(encoded_body)
            signature = self._untoken(encoded_signature)
            self._issuer.public_key().verify(signature, body)
            payload = json.loads(body)
        except (ValueError, InvalidSignature, json.JSONDecodeError, UnicodeDecodeError):
            raise BootstrapRejected("reconnect authorization is unavailable") from None
        required = {
            "environment_id",
            "environment_generation",
            "expires_at_ms",
            "key_epoch",
            "lifecycle_class",
            "nonce",
            "shard_generation",
            "shard_id",
        }
        if not isinstance(payload, dict) or set(payload) != required:
            raise BootstrapRejected("reconnect authorization is unavailable")
        return payload

    @staticmethod
    def _token(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _untoken(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
