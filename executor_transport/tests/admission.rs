use pwc_persistent_executor_transport::admission::{
    AdmissionClaims, AdmissionError, AdmissionPurpose, AdmissionSigner, AdmissionVerifier,
    LifecycleClass, MAX_PREAUTH_FRAME_BYTES, PREAUTH_DEADLINE_MS, RECONNECT_TOKEN_TTL_MS,
};

fn claims(now_ms: u64) -> AdmissionClaims {
    AdmissionClaims {
        nonce: [7; 16],
        purpose: AdmissionPurpose::Reconnect,
        environment_id: "environment-v1".into(),
        environment_generation: 3,
        cell_id: "cell-v1".into(),
        shard_id: "shard-v1".into(),
        shard_generation: 7,
        public_noise_key_id: "noise-v1".into(),
        key_epoch: 11,
        protocol_version: 7,
        schema_digest: [9; 32],
        manifest_digest: [1; 32],
        image_digest: [2; 32],
        environment_binary_digest: [3; 32],
        daemon_digest: [4; 32],
        source_commit: [5; 32],
        release_id: "release-v7".into(),
        remaining_lifetime_ms: 240_000,
        environment_expires_at_ms: now_ms + 240_000,
        compatibility_expires_at_ms: None,
        lifecycle_class: LifecycleClass::ActiveClaim,
        issued_at_ms: now_ms,
        expires_at_ms: now_ms + RECONNECT_TOKEN_TTL_MS,
    }
}

#[test]
fn signed_frame_binds_every_server_verified_routing_field() {
    let signer = AdmissionSigner::from_seed("issuer-v1", [3; 32], 1_000, 100_000).unwrap();
    let verifier = AdmissionVerifier::new(signer.verification_key(), None).unwrap();
    let frame = signer.sign(claims(1_000)).unwrap();
    let verified = verifier.verify(&frame, 1_999, 46_000).unwrap();
    assert_eq!(verified.claims(), &claims(1_000));

    let mut tampered = frame;
    let position = tampered
        .windows("shard-v1".len())
        .position(|window| window == b"shard-v1")
        .unwrap();
    tampered[position] = b'X';
    assert_eq!(
        verifier.verify(&tampered, 1_999, 46_000),
        Err(AdmissionError::Signature)
    );
}

#[test]
fn exact_expiry_frame_and_read_deadline_boundaries_are_enforced() {
    let signer = AdmissionSigner::from_seed("issuer-v1", [3; 32], 1_000, 100_000).unwrap();
    let verifier = AdmissionVerifier::new(signer.verification_key(), None).unwrap();
    let frame = signer.sign(claims(1_000)).unwrap();
    assert!(frame.len() <= MAX_PREAUTH_FRAME_BYTES);
    assert!(
        verifier
            .verify(&frame, PREAUTH_DEADLINE_MS - 1, 46_000)
            .is_ok()
    );
    assert_eq!(
        verifier.verify(&frame, PREAUTH_DEADLINE_MS, 46_000),
        Err(AdmissionError::Deadline)
    );
    assert_eq!(
        verifier.verify(&frame, 0, 46_001),
        Err(AdmissionError::Expired)
    );
    assert_eq!(
        verifier.verify(&vec![0; MAX_PREAUTH_FRAME_BYTES + 1], 0, 1_000),
        Err(AdmissionError::Oversized)
    );
}

#[test]
fn revocation_overrides_current_or_previous_key_overlap() {
    let previous = AdmissionSigner::from_seed("issuer-old", [2; 32], 1_000, 86_401_000).unwrap();
    let current = AdmissionSigner::from_seed("issuer-v1", [3; 32], 1_000, 100_000).unwrap();
    let mut verifier = AdmissionVerifier::new(
        current.verification_key(),
        Some(previous.verification_key()),
    )
    .unwrap();
    let frame = current.sign(claims(1_000)).unwrap();
    verifier.revoke("issuer-v1");
    assert_eq!(
        verifier.verify(&frame, 0, 1_000),
        Err(AdmissionError::Revoked)
    );
}

#[test]
fn malformed_or_wrong_ttl_claims_never_produce_a_signed_frame() {
    let signer = AdmissionSigner::from_seed("issuer-v1", [3; 32], 1_000, 100_000).unwrap();
    let mut invalid = claims(1_000);
    invalid.expires_at_ms -= 1;
    assert_eq!(signer.sign(invalid), Err(AdmissionError::ClaimsRejected));
}

#[test]
fn python_issuer_golden_matches_the_rust_frame() {
    use sha2::{Digest, Sha256};

    let signer = AdmissionSigner::from_seed("issuer-v1", [9; 32], 0, 1_000_000).unwrap();
    let mut golden = claims(1_000);
    golden.nonce = [8; 16];
    golden.purpose = AdmissionPurpose::Registration;
    golden.environment_generation = 1;
    golden.public_noise_key_id = "pending".into();
    golden.schema_digest = [6; 32];
    golden.lifecycle_class = LifecycleClass::BlankPool;
    golden.expires_at_ms = 61_000;
    let frame = signer.sign(golden).unwrap();
    assert_eq!(frame.len(), 1_249);
    assert_eq!(
        format!("{:x}", Sha256::digest(frame)),
        "852fca65c84707ce31924269e572360d2c4469902420d30c8c68f533d2fb052c"
    );
}
