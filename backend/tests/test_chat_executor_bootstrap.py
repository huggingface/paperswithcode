from __future__ import annotations

import base64
import json
import threading
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.services.chat_executor_bootstrap import (
    ATTEMPT_RETENTION_SECONDS,
    LAUNCH_CREDENTIAL_TTL_SECONDS,
    LIVE_CLAIM_RECOVERY_SECONDS,
    RECONNECT_TOKEN_TTL_SECONDS,
    BootstrapRejected,
    ExecutorBootstrapStateMachine,
    recovery_proof_message,
    registration_proof_message,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def _public(private: Ed25519PrivateKey) -> bytes:
    return private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _machine(clock: Clock) -> ExecutorBootstrapStateMachine:
    counter = iter(range(1, 100))
    return ExecutorBootstrapStateMachine(
        issuer_private_key=Ed25519PrivateKey.from_private_bytes(b"\x09" * 32),
        clock=clock,
        random_bytes=lambda size: bytes([next(counter)]) * size,
    )


def _register(
    machine: ExecutorBootstrapStateMachine,
    identity: Ed25519PrivateKey,
    *,
    environment_id: str = "env-1",
    generation: int = 1,
    credential: str = "single-use-launch",
):
    public = _public(identity)
    machine.provision(environment_id, generation, credential)
    signature = identity.sign(
        registration_proof_message(environment_id, generation, credential, public)
    )
    return machine.redeem_launch(
        environment_id=environment_id,
        generation=generation,
        launch_credential=credential,
        identity_public_key=public,
        signature=signature,
    )


def test_first_registration_binds_identity_and_consumes_launch_credential() -> None:
    clock = Clock()
    machine = _machine(clock)
    identity = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)

    authorization = _register(machine, identity)

    assert authorization.identity_public_key == _public(identity)
    with pytest.raises(BootstrapRejected):
        machine.redeem_launch(
            environment_id="env-1",
            generation=1,
            launch_credential="single-use-launch",
            identity_public_key=_public(identity),
            signature=identity.sign(
                registration_proof_message(
                    "env-1", 1, "single-use-launch", _public(identity)
                )
            ),
        )


@pytest.mark.parametrize("failure", ["expired", "mismatched", "wrong_identity"])
def test_first_registration_rejects_invalid_launch_or_possession(failure: str) -> None:
    clock = Clock()
    machine = _machine(clock)
    identity = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    wrong = Ed25519PrivateKey.from_private_bytes(b"\x02" * 32)
    public = _public(identity)
    machine.provision("env-1", 1, "single-use-launch")
    credential = "wrong" if failure == "mismatched" else "single-use-launch"
    signer = wrong if failure == "wrong_identity" else identity
    if failure == "expired":
        clock.now += LAUNCH_CREDENTIAL_TTL_SECONDS

    with pytest.raises(BootstrapRejected):
        machine.redeem_launch(
            environment_id="env-1",
            generation=1,
            launch_credential=credential,
            identity_public_key=public,
            signature=signer.sign(
                registration_proof_message("env-1", 1, credential, public)
            ),
        )


def test_lost_first_registration_response_recovers_with_bound_identity() -> None:
    clock = Clock()
    machine = _machine(clock)
    identity = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    authorization = _register(machine, identity)

    challenge = machine.issue_recovery_challenge("env-1", 1, authorization.attempt_id)
    recovered = machine.recover(
        environment_id="env-1",
        generation=1,
        attempt_id=authorization.attempt_id,
        challenge=challenge,
        signature=identity.sign(
            recovery_proof_message("env-1", 1, challenge, _public(identity))
        ),
    )

    assert recovered.attempt_id == authorization.attempt_id


def test_recovery_rejects_wrong_identity_and_expired_attempt() -> None:
    clock = Clock()
    machine = _machine(clock)
    identity = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    wrong = Ed25519PrivateKey.from_private_bytes(b"\x02" * 32)
    authorization = _register(machine, identity)
    challenge = machine.issue_recovery_challenge("env-1", 1, authorization.attempt_id)

    with pytest.raises(BootstrapRejected):
        machine.recover(
            environment_id="env-1",
            generation=1,
            attempt_id=authorization.attempt_id,
            challenge=challenge,
            signature=wrong.sign(
                recovery_proof_message("env-1", 1, challenge, _public(identity))
            ),
        )

    clock.now += ATTEMPT_RETENTION_SECONDS
    with pytest.raises(BootstrapRejected):
        machine.issue_recovery_challenge("env-1", 1, authorization.attempt_id)


def test_scheduler_saturation_preserves_reconnect_nonce_then_consumes_once() -> None:
    clock = Clock()
    machine = _machine(clock)
    identity = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    _register(machine, identity)
    token = machine.issue_reconnect_token(
        "env-1",
        1,
        shard_id="staging-1",
        shard_generation=7,
        lifecycle_class="active_claim",
    )

    retry = machine.admit_reconnect(
        token.encoded,
        expected_shard_id="staging-1",
        expected_shard_generation=7,
        scheduler_slot_acquired=False,
    )
    admitted = machine.admit_reconnect(
        token.encoded,
        expected_shard_id="staging-1",
        expected_shard_generation=7,
        scheduler_slot_acquired=True,
    )

    assert not retry.admitted
    assert admitted.admitted
    with pytest.raises(BootstrapRejected):
        machine.admit_reconnect(
            token.encoded,
            expected_shard_id="staging-1",
            expected_shard_generation=7,
            scheduler_slot_acquired=True,
        )


def test_simultaneous_reconnect_has_exactly_one_winner() -> None:
    clock = Clock()
    machine = _machine(clock)
    identity = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    _register(machine, identity)
    token = machine.issue_reconnect_token(
        "env-1",
        1,
        shard_id="staging-1",
        shard_generation=7,
        lifecycle_class="active_claim",
    )
    outcomes: list[str] = []
    barrier = threading.Barrier(3)

    def redeem() -> None:
        barrier.wait()
        try:
            machine.admit_reconnect(
                token.encoded,
                expected_shard_id="staging-1",
                expected_shard_generation=7,
                scheduler_slot_acquired=True,
            )
            outcomes.append("admitted")
        except BootstrapRejected:
            outcomes.append("rejected")

    threads = [threading.Thread(target=redeem) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["admitted", "rejected"]


def test_consumed_token_handshake_failure_uses_bounded_identity_recovery() -> None:
    clock = Clock()
    machine = _machine(clock)
    identity = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    _register(machine, identity)
    clock.now += ATTEMPT_RETENTION_SECONDS
    token = machine.issue_reconnect_token(
        "env-1",
        1,
        shard_id="staging-1",
        shard_generation=7,
        lifecycle_class="active_claim",
    )
    admission = machine.admit_reconnect(
        token.encoded,
        expected_shard_id="staging-1",
        expected_shard_generation=7,
        scheduler_slot_acquired=True,
    )
    assert admission.attempt_id is not None

    challenge = machine.issue_recovery_challenge("env-1", 1, admission.attempt_id)
    recovered = machine.recover(
        environment_id="env-1",
        generation=1,
        attempt_id=admission.attempt_id,
        challenge=challenge,
        signature=identity.sign(
            recovery_proof_message("env-1", 1, challenge, _public(identity))
        ),
    )

    assert recovered.attempt_id == admission.attempt_id


def test_consumed_token_recovery_cannot_extend_live_claim_window() -> None:
    clock = Clock()
    machine = _machine(clock)
    identity = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    _register(machine, identity)
    clock.now += ATTEMPT_RETENTION_SECONDS
    token = machine.issue_reconnect_token(
        "env-1",
        1,
        shard_id="staging-1",
        shard_generation=7,
        lifecycle_class="active_claim",
    )
    admission = machine.admit_reconnect(
        token.encoded,
        expected_shard_id="staging-1",
        expected_shard_generation=7,
        scheduler_slot_acquired=True,
    )
    assert admission.attempt_id is not None
    clock.now += LIVE_CLAIM_RECOVERY_SECONDS

    with pytest.raises(BootstrapRejected):
        machine.issue_recovery_challenge("env-1", 1, admission.attempt_id)


def test_lost_heartbeat_token_can_be_replaced_without_reusing_a_nonce() -> None:
    clock = Clock()
    machine = _machine(clock)
    identity = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    _register(machine, identity)
    first = machine.issue_reconnect_token(
        "env-1",
        1,
        shard_id="staging-1",
        shard_generation=7,
        lifecycle_class="assigned_idle",
    )
    second = machine.issue_reconnect_token(
        "env-1",
        1,
        shard_id="staging-1",
        shard_generation=7,
        lifecycle_class="assigned_idle",
    )

    assert first.nonce != second.nonce
    assert first.expires_at == second.expires_at


def test_reconnect_rejects_expiry_revocation_and_wrong_shard_generation() -> None:
    clock = Clock()
    machine = _machine(clock)
    identity = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    _register(machine, identity)
    token = machine.issue_reconnect_token(
        "env-1",
        1,
        shard_id="staging-1",
        shard_generation=7,
        lifecycle_class="blank",
    )

    with pytest.raises(BootstrapRejected):
        machine.admit_reconnect(
            token.encoded,
            expected_shard_id="staging-1",
            expected_shard_generation=8,
            scheduler_slot_acquired=True,
        )
    clock.now += RECONNECT_TOKEN_TTL_SECONDS
    with pytest.raises(BootstrapRejected):
        machine.admit_reconnect(
            token.encoded,
            expected_shard_id="staging-1",
            expected_shard_generation=7,
            scheduler_slot_acquired=True,
        )

    clock = Clock()
    machine = _machine(clock)
    _register(machine, identity)
    token = machine.issue_reconnect_token(
        "env-1",
        1,
        shard_id="staging-1",
        shard_generation=7,
        lifecycle_class="blank",
    )
    machine.revoke("env-1", 1)
    with pytest.raises(BootstrapRejected):
        machine.admit_reconnect(
            token.encoded,
            expected_shard_id="staging-1",
            expected_shard_generation=7,
            scheduler_slot_acquired=True,
        )


def test_issuer_authorized_generation_transition_fences_old_tokens() -> None:
    clock = Clock()
    machine = _machine(clock)
    identity = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    _register(machine, identity)
    old = machine.issue_reconnect_token(
        "env-1",
        1,
        shard_id="staging-1",
        shard_generation=7,
        lifecycle_class="blank",
    )

    machine.authorize_generation_transition(
        environment_id="env-1",
        old_generation=1,
        new_generation=2,
        issuer_authorized=True,
    )

    with pytest.raises(BootstrapRejected):
        machine.admit_reconnect(
            old.encoded,
            expected_shard_id="staging-1",
            expected_shard_generation=7,
            scheduler_slot_acquired=True,
        )
    current = machine.issue_reconnect_token(
        "env-1",
        2,
        shard_id="staging-2",
        shard_generation=1,
        lifecycle_class="blank",
    )
    assert current.nonce != old.nonce


def test_generation_transition_requires_issuer_authorization() -> None:
    clock = Clock()
    machine = _machine(clock)
    identity = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    _register(machine, identity)

    with pytest.raises(BootstrapRejected):
        machine.authorize_generation_transition(
            environment_id="env-1",
            old_generation=1,
            new_generation=2,
            issuer_authorized=False,
        )


def test_generation_transition_cannot_replace_existing_generation() -> None:
    clock = Clock()
    machine = _machine(clock)
    first = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
    second = Ed25519PrivateKey.from_private_bytes(b"\x02" * 32)
    _register(machine, first, generation=1)
    _register(
        machine,
        second,
        generation=2,
        credential="second-generation-launch",
    )

    with pytest.raises(BootstrapRejected):
        machine.authorize_generation_transition(
            environment_id="env-1",
            old_generation=1,
            new_generation=2,
            issuer_authorized=True,
        )


def test_public_interoperability_vector_matches_protocol_messages() -> None:
    root = Path(__file__).parents[2]
    vector = json.loads(
        (root / "executor_transport/vectors/bootstrap_v1.json").read_text()
    )
    public_key = _decode(vector["identity_public_key_base64url"])
    registration_message = _decode(vector["registration_message_base64url"])
    recovery_message = _decode(vector["recovery_message_base64url"])
    challenge = _decode(vector["recovery_challenge_base64url"])

    assert registration_message == registration_proof_message(
        vector["environment_id"],
        vector["environment_generation"],
        "launch-vector",
        public_key,
    )
    assert recovery_message == recovery_proof_message(
        vector["environment_id"],
        vector["environment_generation"],
        challenge,
        public_key,
    )
    identity = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32).public_key()
    identity.verify(
        _decode(vector["registration_signature_base64url"]), registration_message
    )
    identity.verify(_decode(vector["recovery_signature_base64url"]), recovery_message)
