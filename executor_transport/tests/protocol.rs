use pwc_persistent_executor_transport::noise::{
    InitiatorHandshake, NoiseIdentity, PendingResponderHandshake, bound_prologue,
};
use pwc_persistent_executor_transport::protocol::{
    AuthorizationClaims, AuthorizationSigner, AuthorizationState, ConnectionCredits,
    ContentFreeError, FrameKind, HandshakeBinding, KeyRing, MAX_BASH_TIMEOUT_MS, MAX_COMMAND_BYTES,
    MAX_CONNECTION_CREDIT, MAX_CONTROL_PAYLOAD, MAX_OPERATION_CREDIT, MAX_PATH_BYTES,
    MAX_READ_BYTES, MAX_RELAY_PAYLOAD, MAX_STREAM_CREDIT, MessageDecoder, ProtocolRelease,
    RESUME_WINDOW_MS, RegistrationKind, RelayFrame, ReleasePolicy, ReplayBuffer, SequenceReceiver,
    SignedAuthorization, frame_message, frame_records, validate_bash, validate_read,
};
use sha2::{Digest, Sha256};

const NOW: u64 = 1_800_000_000;
const DAY: u64 = 24 * 60 * 60;

fn digest(byte: u8) -> [u8; 32] {
    [byte; 32]
}

fn claims(version: u32, schema_digest: [u8; 32], harness_key_id: &str) -> AuthorizationClaims {
    AuthorizationClaims {
        authorization_id: [7; 16],
        environment_id: "env-7".into(),
        environment_generation: 11,
        shard_generation: 13,
        stream_id: [17; 16],
        harness_key_id: harness_key_id.into(),
        protocol_version: version,
        schema_digest,
        issued_at: NOW,
        expires_at: NOW + 60,
    }
}

fn signer(seed: u8, key_id: &str, not_before: u64, not_after: u64) -> AuthorizationSigner {
    AuthorizationSigner::from_seed(key_id, [seed; 32], not_before, not_after).unwrap()
}

fn signed_current() -> (AuthorizationSigner, SignedAuthorization) {
    let signer = signer(3, "issuer-current", NOW - DAY, NOW + DAY);
    let signed = signer
        .sign(claims(7, digest(7), "harness-current"))
        .unwrap();
    (signer, signed)
}

#[test]
fn frame_golden_vector_and_content_free_errors() {
    let frame = RelayFrame::new(FrameKind::Data, 5, 9, 2, 1, b"pwd".to_vec()).unwrap();
    assert_eq!(
        frame.encode(),
        [
            b'P', b'W', b'C', b'1', 0, 0, 0, 0, 5, 0, 0, 0, 9, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 0,
            0, 0, 0, 1, 0, 0, 0, 3, b'p', b'w', b'd',
        ]
    );
    assert_eq!(RelayFrame::decode(&frame.encode()).unwrap(), frame);
    assert_eq!(
        ContentFreeError::FrameTooLarge.to_string(),
        "relay frame rejected"
    );
    assert!(!ContentFreeError::FrameTooLarge.to_string().contains("pwd"));
}

#[test]
fn bounded_records_reassemble_exact_command_and_read_boundaries() {
    for payload in [vec![b'c'; MAX_COMMAND_BYTES], vec![b'r'; MAX_READ_BYTES]] {
        let records = frame_records(&payload).unwrap();
        assert!(
            records
                .iter()
                .all(|record| record.len() <= MAX_RELAY_PAYLOAD)
        );
        let mut decoder = MessageDecoder::new();
        let mut decoded = Vec::new();
        for record in records {
            decoded.extend(decoder.push(&record).unwrap());
        }
        assert_eq!(decoded, vec![payload]);
    }
    assert_eq!(
        frame_message(&vec![0; MAX_READ_BYTES + 1]),
        Err(ContentFreeError::MessageTooLarge)
    );
}

#[test]
fn message_decoder_rejects_zero_oversized_and_overlong_records_before_buffering() {
    let mut decoder = MessageDecoder::new();
    assert_eq!(
        decoder.push(&0_u32.to_be_bytes()),
        Err(ContentFreeError::MalformedFrame)
    );
    let mut decoder = MessageDecoder::new();
    assert_eq!(
        decoder.push(&((MAX_READ_BYTES + 1) as u32).to_be_bytes()),
        Err(ContentFreeError::MessageTooLarge)
    );
    let mut decoder = MessageDecoder::new();
    assert_eq!(
        decoder.push(&vec![0; MAX_RELAY_PAYLOAD + 1]),
        Err(ContentFreeError::FrameTooLarge)
    );
}

#[test]
fn frames_reject_replay_reorder_excess_and_malformed_lengths() {
    let frame0 = RelayFrame::new(FrameKind::Data, 1, 1, 0, 0, vec![0]).unwrap();
    let frame1 = RelayFrame::new(FrameKind::Data, 1, 1, 1, 0, vec![1]).unwrap();
    let mut receiver = SequenceReceiver::new();

    assert!(receiver.push(frame1.clone()).unwrap().is_empty());
    assert_eq!(
        receiver.push(frame0.clone()).unwrap(),
        vec![frame0, frame1.clone()]
    );
    assert!(
        receiver
            .push(RelayFrame::new(FrameKind::Data, 1, 1, 1, 0, vec![1]).unwrap())
            .unwrap()
            .is_empty()
    );

    let too_far = RelayFrame::new(FrameKind::Data, 1, 1, 67, 0, vec![1]).unwrap();
    assert_eq!(
        receiver.push(too_far),
        Err(ContentFreeError::SequenceViolation)
    );
    assert_eq!(
        RelayFrame::new(FrameKind::Data, 1, 1, 3, 0, vec![0; MAX_RELAY_PAYLOAD + 1]),
        Err(ContentFreeError::FrameTooLarge)
    );

    let mut malformed = frame1.encode();
    malformed[29..33].copy_from_slice(&4_u32.to_be_bytes());
    assert_eq!(
        RelayFrame::decode(&malformed),
        Err(ContentFreeError::MalformedFrame)
    );
}

#[test]
fn acknowledgements_are_monotonic_bounded_and_trim_replay() {
    let mut replay = ReplayBuffer::new();
    for sequence in 0..3 {
        replay
            .record(
                RelayFrame::new(FrameKind::Data, 1, 1, sequence, 0, vec![sequence as u8]).unwrap(),
            )
            .unwrap();
    }
    assert_eq!(replay.acknowledge(2).unwrap(), 2);
    assert_eq!(replay.frames_from(2).unwrap().len(), 1);
    assert_eq!(replay.acknowledge(2).unwrap(), 0);
    assert_eq!(replay.acknowledge(1), Err(ContentFreeError::AckViolation));
    assert_eq!(replay.acknowledge(4), Err(ContentFreeError::AckViolation));
}

#[test]
fn reconnect_is_valid_only_while_sequence_state_and_claim_window_survive() {
    let mut replay = ReplayBuffer::new();
    replay
        .record(RelayFrame::new(FrameKind::Data, 1, 1, 0, 0, b"once".to_vec()).unwrap())
        .unwrap();
    replay.detach(10_000);
    assert!(replay.resume(10_000 + RESUME_WINDOW_MS).is_ok());
    replay.detach(20_000);
    assert_eq!(
        replay.resume(20_000 + RESUME_WINDOW_MS + 1),
        Err(ContentFreeError::ResumeExpired)
    );
    assert_eq!(replay.frames_from(0).unwrap().len(), 1);

    replay.detach_until(50_000, 50_100);
    assert_eq!(replay.resume(50_101), Err(ContentFreeError::ResumeExpired));
}

#[test]
fn replay_memory_is_bounded_and_ack_releases_capacity() {
    let mut replay = ReplayBuffer::new();
    let sizes = [
        MAX_RELAY_PAYLOAD,
        MAX_RELAY_PAYLOAD,
        MAX_RELAY_PAYLOAD,
        MAX_RELAY_PAYLOAD,
        MAX_STREAM_CREDIT - 4 * MAX_RELAY_PAYLOAD,
    ];
    for (sequence, size) in sizes.into_iter().enumerate() {
        replay
            .record(
                RelayFrame::new(FrameKind::Data, 1, 1, sequence as u64, 0, vec![0; size]).unwrap(),
            )
            .unwrap();
    }
    assert_eq!(
        replay.record(RelayFrame::new(FrameKind::Data, 1, 1, 5, 0, vec![0]).unwrap()),
        Err(ContentFreeError::CreditViolation)
    );
    replay.acknowledge(5).unwrap();
    replay
        .record(RelayFrame::new(FrameKind::Data, 1, 1, 5, 0, vec![0]).unwrap())
        .unwrap();
}

#[test]
fn noise_identity_and_selected_contract_are_bound_to_the_prologue() {
    let harness = NoiseIdentity::generate().unwrap();
    let environment = NoiseIdentity::generate().unwrap();
    assert_ne!(harness.key_id(), environment.key_id());

    let binding = HandshakeBinding {
        environment_id: "env-7".into(),
        registration_id: "registration-11".into(),
        stream_id: "stream-13".into(),
        protocol_version: 7,
        schema_digest: digest(7),
        authorization_key_id: "issuer-current".into(),
        harness_noise_key_id: harness.key_id(),
        environment_noise_key_id: environment.key_id(),
    };
    let transcript = bound_prologue(&binding).unwrap();
    assert_eq!(transcript.len(), 251);
    let (initiator, request) = InitiatorHandshake::start(
        &harness,
        &environment.public_key(),
        &transcript,
        b"authorization",
    )
    .unwrap();

    let mut downgrade = binding.clone();
    downgrade.protocol_version = 6;
    assert!(
        PendingResponderHandshake::read_request(
            &environment,
            &bound_prologue(&downgrade).unwrap(),
            &request,
        )
        .is_err()
    );

    let responder =
        PendingResponderHandshake::read_request(&environment, &transcript, &request).unwrap();
    let (_, response) = responder.complete().unwrap();
    initiator.finish(&response).unwrap();
}

#[test]
fn bound_prologue_has_a_stable_golden_digest() {
    let binding = HandshakeBinding {
        environment_id: "env-vector".into(),
        registration_id: "registration-vector".into(),
        stream_id: "stream-vector".into(),
        protocol_version: 7,
        schema_digest: digest(7),
        authorization_key_id: "issuer-vector".into(),
        harness_noise_key_id: "harness-vector".into(),
        environment_noise_key_id: "environment-vector".into(),
    };
    let transcript = bound_prologue(&binding).unwrap();
    assert_eq!(
        Sha256::digest(&transcript).as_slice(),
        &[
            28, 214, 19, 160, 99, 101, 115, 117, 148, 169, 124, 240, 234, 81, 64, 108, 161, 118,
            86, 206, 148, 236, 89, 215, 179, 213, 87, 102, 184, 183, 113, 77,
        ]
    );
}

#[test]
fn identity_mismatch_fails_the_hybrid_ik_handshake() {
    let harness = NoiseIdentity::generate().unwrap();
    let expected_environment = NoiseIdentity::generate().unwrap();
    let wrong_environment = NoiseIdentity::generate().unwrap();
    let binding = HandshakeBinding::test_fixture(
        harness.key_id(),
        expected_environment.key_id(),
        7,
        digest(7),
    );
    let transcript = bound_prologue(&binding).unwrap();
    let (_, request) = InitiatorHandshake::start(
        &harness,
        &expected_environment.public_key(),
        &transcript,
        b"authorization",
    )
    .unwrap();
    assert!(
        PendingResponderHandshake::read_request(&wrong_environment, &transcript, &request).is_err()
    );
}

#[test]
fn private_key_api_exposes_only_public_material_and_stable_identifiers() {
    let identity = NoiseIdentity::generate().unwrap();
    let public = serde_json::to_value(identity.public_key()).unwrap();
    assert_eq!(identity.key_id().len(), 64);
    assert_eq!(public.as_object().unwrap().len(), 3);
    assert!(public.get("private_key").is_none());
    assert!(public.get("secret_key").is_none());
}

#[test]
fn signed_authorization_has_a_stable_vector_and_rejects_mutation() {
    let (signer, signed) = signed_current();
    assert_eq!(signed.canonical_claims().unwrap().len(), 169);
    assert_eq!(
        signed.signature(),
        &[
            136, 138, 167, 146, 38, 155, 113, 236, 231, 211, 168, 46, 118, 48, 219, 74, 76, 64, 71,
            10, 84, 38, 75, 107, 55, 11, 120, 28, 195, 152, 152, 218, 246, 133, 252, 163, 21, 24,
            144, 156, 107, 166, 5, 123, 145, 186, 120, 182, 135, 132, 132, 178, 165, 237, 227, 136,
            205, 130, 114, 143, 216, 113, 38, 4,
        ]
    );
    let key = signer.verification_key();
    let ring = KeyRing::new(key, None).unwrap();
    ring.verify(&signed, NOW + 1).unwrap();
    assert_eq!(
        ring.verify(&signed, NOW + 61),
        Err(ContentFreeError::AuthorizationExpired)
    );

    let mut changed = signed.clone();
    changed.claims.protocol_version = 6;
    assert_eq!(
        ring.verify(&changed, NOW + 1),
        Err(ContentFreeError::AuthorizationRejected)
    );
}

#[test]
fn key_windows_accept_only_current_or_previous_and_honor_immediate_revocation() {
    let current = signer(3, "issuer-current", NOW, NOW + DAY);
    let previous = signer(2, "issuer-previous", NOW - DAY, NOW + 30);
    let older = signer(1, "issuer-older", NOW - DAY, NOW + 30);
    let current_auth = current
        .sign(claims(7, digest(7), "harness-current"))
        .unwrap();
    let mut previous_claims = claims(6, digest(6), "harness-previous");
    previous_claims.expires_at = NOW + 30;
    let previous_auth = previous.sign(previous_claims).unwrap();
    let mut older_claims = claims(5, digest(5), "harness-older");
    older_claims.expires_at = NOW + 30;
    let older_auth = older.sign(older_claims).unwrap();
    let mut ring = KeyRing::new(
        current.verification_key(),
        Some(previous.verification_key()),
    )
    .unwrap();

    ring.verify(&current_auth, NOW + 1).unwrap();
    ring.verify(&previous_auth, NOW + 1).unwrap();
    assert_eq!(
        ring.verify(&older_auth, NOW + 1),
        Err(ContentFreeError::UnknownKey)
    );
    assert_eq!(
        ring.verify(&previous_auth, NOW + 31),
        Err(ContentFreeError::KeyExpired)
    );

    ring.revoke("issuer-current");
    for state in [
        AuthorizationState::Fresh,
        AuthorizationState::Cached,
        AuthorizationState::Detached,
        AuthorizationState::Acknowledged,
    ] {
        assert_eq!(
            ring.verify_for_state(&current_auth, NOW + 1, state),
            Err(ContentFreeError::SecurityRevoked)
        );
    }
    ring.verify(&previous_auth, NOW + 1).unwrap();
}

#[test]
fn key_ring_rejects_more_than_one_previous_key_or_excess_overlap() {
    let current = signer(3, "current", NOW, NOW + DAY);
    let previous = signer(2, "previous", NOW - DAY, NOW + DAY + 1).verification_key();
    assert_eq!(
        KeyRing::new(current.verification_key(), Some(previous)),
        Err(ContentFreeError::KeyWindowRejected)
    );
}

#[test]
fn version_negotiation_is_exact_signed_and_current_only_for_new_environments() {
    let current = ProtocolRelease::new(7, digest(7), NOW, None);
    let previous = ProtocolRelease::new(6, digest(6), NOW - DAY, Some(NOW + DAY));
    let policy = ReleasePolicy::compatible(current.clone(), previous.clone()).unwrap();
    let current_claims = claims(7, digest(7), "harness-current");
    let previous_claims = claims(6, digest(6), "harness-previous");

    assert_eq!(
        policy
            .negotiate(
                RegistrationKind::New,
                &[current.clone(), previous.clone()],
                &current_claims,
                NOW
            )
            .unwrap(),
        current
    );
    assert_eq!(
        policy
            .negotiate(
                RegistrationKind::Existing,
                std::slice::from_ref(&previous),
                &previous_claims,
                NOW
            )
            .unwrap(),
        previous
    );
    assert_eq!(
        policy.negotiate(
            RegistrationKind::New,
            std::slice::from_ref(&previous),
            &previous_claims,
            NOW
        ),
        Err(ContentFreeError::ProtocolVersionRejected)
    );
    assert_eq!(
        policy.negotiate(
            RegistrationKind::Existing,
            &[ProtocolRelease::new(6, digest(8), NOW, None)],
            &previous_claims,
            NOW
        ),
        Err(ContentFreeError::SchemaDigestRejected)
    );
    assert_eq!(
        policy.negotiate(
            RegistrationKind::Existing,
            &[ProtocolRelease::new(5, digest(5), NOW, None)],
            &claims(5, digest(5), "harness"),
            NOW
        ),
        Err(ContentFreeError::ProtocolVersionRejected)
    );
}

#[test]
fn previous_version_expires_at_24_hours_and_incompatible_release_has_no_window() {
    let current = ProtocolRelease::new(7, digest(7), NOW, None);
    let previous = ProtocolRelease::new(6, digest(6), NOW - DAY, Some(NOW + DAY));
    let claims = claims(6, digest(6), "harness-previous");
    let policy = ReleasePolicy::compatible(current.clone(), previous.clone()).unwrap();
    assert!(
        policy
            .negotiate(
                RegistrationKind::Existing,
                std::slice::from_ref(&previous),
                &claims,
                NOW + DAY
            )
            .is_ok()
    );
    assert_eq!(
        policy.negotiate(
            RegistrationKind::Existing,
            std::slice::from_ref(&previous),
            &claims,
            NOW + DAY + 1
        ),
        Err(ContentFreeError::ProtocolVersionRejected)
    );

    let incompatible = ReleasePolicy::incompatible(current).unwrap();
    assert_eq!(
        incompatible.negotiate(RegistrationKind::Existing, &[previous], &claims, NOW),
        Err(ContentFreeError::ProtocolVersionRejected)
    );
}

#[test]
fn release_policy_rejects_non_adjacent_or_overlong_compatibility() {
    let current = ProtocolRelease::new(7, digest(7), NOW, None);
    assert_eq!(
        ReleasePolicy::compatible(
            current.clone(),
            ProtocolRelease::new(5, digest(5), NOW, Some(NOW + DAY)),
        ),
        Err(ContentFreeError::ProtocolVersionRejected)
    );
    assert_eq!(
        ReleasePolicy::compatible(
            current,
            ProtocolRelease::new(6, digest(6), NOW, Some(NOW + DAY + 1)),
        ),
        Err(ContentFreeError::ProtocolVersionRejected)
    );
}

#[test]
fn bash_and_read_boundaries_are_checked_before_delivery() {
    assert!(validate_bash(&vec![b'x'; MAX_COMMAND_BYTES], MAX_BASH_TIMEOUT_MS as i64).is_ok());
    assert_eq!(
        validate_bash(
            &vec![b'x'; MAX_COMMAND_BYTES + 1],
            MAX_BASH_TIMEOUT_MS as i64
        ),
        Err(ContentFreeError::CommandRejected)
    );
    assert_eq!(
        validate_bash(b"pwd", MAX_BASH_TIMEOUT_MS as i64 + 1),
        Err(ContentFreeError::TimeoutRejected)
    );
    assert_eq!(
        validate_bash(&[0xff], 1),
        Err(ContentFreeError::InvalidUtf8)
    );

    assert!(validate_read(&vec![b'p'; MAX_PATH_BYTES], 0, MAX_READ_BYTES as u128).is_ok());
    assert_eq!(
        validate_read(&vec![b'p'; MAX_PATH_BYTES + 1], 0, 1),
        Err(ContentFreeError::PathRejected)
    );
    assert_eq!(
        validate_read(&[0xff], 0, 1),
        Err(ContentFreeError::InvalidUtf8)
    );
    assert_eq!(
        validate_read(b"file", -1, 1),
        Err(ContentFreeError::OffsetRejected)
    );
    assert_eq!(
        validate_read(b"file", 0, MAX_READ_BYTES as u128 + 1),
        Err(ContentFreeError::ReadSizeRejected)
    );
    assert_eq!(
        validate_read(b"file", u64::MAX as i128, 2),
        Err(ContentFreeError::IntegerOverflow)
    );
}

#[test]
fn data_credit_is_exact_at_operation_stream_and_connection_caps() {
    let mut credits = ConnectionCredits::new();
    credits.reserve_data(1, 1, MAX_OPERATION_CREDIT).unwrap();
    assert_eq!(credits.operation_bytes(1, 1), MAX_OPERATION_CREDIT);
    assert_eq!(
        credits.reserve_data(1, 1, 1),
        Err(ContentFreeError::CreditViolation)
    );
    assert_eq!(
        credits.reserve_data(1, 2, 1),
        Err(ContentFreeError::CreditViolation)
    );
    credits.reserve_control(FrameKind::Terminal, 1).unwrap();

    let mut credits = ConnectionCredits::new();
    for operation in 0..4 {
        credits
            .reserve_data(1, operation, MAX_OPERATION_CREDIT)
            .unwrap();
    }
    assert_eq!(credits.stream_bytes(1), MAX_STREAM_CREDIT);
    assert_eq!(
        credits.reserve_data(1, 5, 1),
        Err(ContentFreeError::CreditViolation)
    );

    let mut credits = ConnectionCredits::new();
    for stream in 0..2 {
        for operation in 0..4 {
            credits
                .reserve_data(stream, operation, MAX_OPERATION_CREDIT)
                .unwrap();
        }
    }
    assert_eq!(credits.connection_bytes(), MAX_CONNECTION_CREDIT);
    assert_eq!(
        credits.reserve_data(3, 1, 1),
        Err(ContentFreeError::CreditViolation)
    );
}

#[test]
fn full_data_windows_never_consume_reserved_control_capacity() {
    let mut credits = ConnectionCredits::new();
    for stream in 0..2 {
        for operation in 0..4 {
            credits
                .reserve_data(stream, operation, MAX_OPERATION_CREDIT)
                .unwrap();
        }
    }
    for kind in [FrameKind::Ack, FrameKind::Cancel, FrameKind::Terminal] {
        assert!(credits.reserve_control(kind, MAX_CONTROL_PAYLOAD).is_ok());
    }
    assert_eq!(
        credits.reserve_control(FrameKind::Data, 1),
        Err(ContentFreeError::FrameKindRejected)
    );
    assert_eq!(
        credits.reserve_control(FrameKind::Ack, MAX_CONTROL_PAYLOAD + 1),
        Err(ContentFreeError::FrameTooLarge)
    );
    credits
        .reserve_control(FrameKind::Ack, MAX_CONTROL_PAYLOAD)
        .unwrap();
    assert_eq!(
        credits.reserve_control(FrameKind::Terminal, 1),
        Err(ContentFreeError::CreditViolation)
    );
    credits.release_control(MAX_CONTROL_PAYLOAD).unwrap();
    credits.reserve_control(FrameKind::Terminal, 1).unwrap();
}
