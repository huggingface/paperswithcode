use pwc_persistent_executor_transport::admission::{
    AdmissionClaims, AdmissionPurpose, AdmissionSigner, AdmissionVerifier, LifecycleClass,
    RECONNECT_TOKEN_TTL_MS, REGISTRATION_TOKEN_TTL_MS, VerifiedAdmission,
};
use pwc_persistent_executor_transport::registry::{
    EnvironmentState, HEARTBEAT_SUSPECT_MS, ManifestPin, RegistrationRequest, RendezvousRegistry,
};

fn digest(byte: u8) -> [u8; 32] {
    [byte; 32]
}

fn manifest() -> ManifestPin {
    ManifestPin {
        manifest_digest: digest(1),
        image_digest: digest(2),
        environment_binary_digest: digest(3),
        daemon_digest: digest(4),
        source_commit: digest(5),
        protocol_version: 7,
        schema_digest: digest(6),
        release_id: "release-v7".into(),
        compatibility_expires_at_ms: None,
    }
}

fn registration(generation: u64, shard_generation: u64) -> RegistrationRequest {
    RegistrationRequest {
        environment_id: "environment-v1".into(),
        environment_generation: generation,
        cell_id: "cell-v1".into(),
        shard_id: "shard-v1".into(),
        shard_generation,
        public_noise_key_id: "noise-v1".into(),
        public_noise_key: vec![7; 64],
        manifest: manifest(),
        remaining_lifetime_ms: 24 * 60 * 60 * 1_000,
    }
}

fn admission(
    nonce: u128,
    request: &RegistrationRequest,
    purpose: AdmissionPurpose,
    key_epoch: u64,
    now_ms: u64,
) -> VerifiedAdmission {
    let signer = AdmissionSigner::from_seed("issuer-v1", [3; 32], 0, 100_000_000).unwrap();
    let verifier = AdmissionVerifier::new(signer.verification_key(), None).unwrap();
    let ttl = match purpose {
        AdmissionPurpose::Registration => REGISTRATION_TOKEN_TTL_MS,
        AdmissionPurpose::Reconnect => RECONNECT_TOKEN_TTL_MS,
        AdmissionPurpose::ClaimLiveness => 2_000,
    };
    let frame = signer
        .sign(AdmissionClaims {
            nonce: nonce.to_be_bytes(),
            purpose,
            environment_id: request.environment_id.clone(),
            environment_generation: request.environment_generation,
            cell_id: request.cell_id.clone(),
            shard_id: request.shard_id.clone(),
            shard_generation: request.shard_generation,
            public_noise_key_id: request.public_noise_key_id.clone(),
            key_epoch,
            protocol_version: request.manifest.protocol_version,
            schema_digest: request.manifest.schema_digest,
            manifest_digest: request.manifest.manifest_digest,
            image_digest: request.manifest.image_digest,
            environment_binary_digest: request.manifest.environment_binary_digest,
            daemon_digest: request.manifest.daemon_digest,
            source_commit: request.manifest.source_commit,
            release_id: request.manifest.release_id.clone(),
            remaining_lifetime_ms: request.remaining_lifetime_ms,
            environment_expires_at_ms: now_ms + request.remaining_lifetime_ms,
            compatibility_expires_at_ms: request.manifest.compatibility_expires_at_ms,
            lifecycle_class: LifecycleClass::BlankPool,
            issued_at_ms: now_ms,
            expires_at_ms: now_ms + ttl,
        })
        .unwrap();
    verifier.verify(&frame, 0, now_ms).unwrap()
}

#[test]
fn registration_is_authenticated_generation_and_manifest_pinned() {
    let mut registry = RendezvousRegistry::new("cell-v1", "shard-v1", 7, 11, manifest()).unwrap();
    let request = registration(3, 7);
    let ready = registry
        .register(
            request.clone(),
            admission(1, &request, AdmissionPurpose::Registration, 11, 1_000),
            1_000,
        )
        .unwrap();
    assert_eq!(ready.environment.state, EnvironmentState::Ready);
    assert_eq!(registry.ready_capacity(), 1);

    for (nonce, rejected) in [(2, registration(3, 7)), (3, registration(2, 7))] {
        assert!(
            registry
                .register(
                    rejected.clone(),
                    admission(nonce, &rejected, AdmissionPurpose::Registration, 11, 1_001,),
                    1_001,
                )
                .is_err()
        );
    }
    let wrong_shard = registration(4, 6);
    assert!(
        registry
            .register(
                wrong_shard.clone(),
                admission(4, &wrong_shard, AdmissionPurpose::Registration, 11, 1_001,),
                1_001,
            )
            .is_err()
    );

    for field in 0..7 {
        let signed = registration(4, 7);
        let authorization = admission(
            5 + field,
            &signed,
            AdmissionPurpose::Registration,
            11,
            1_001,
        );
        let mut mismatch = signed;
        match field {
            0 => mismatch.manifest.manifest_digest = digest(9),
            1 => mismatch.manifest.image_digest = digest(9),
            2 => mismatch.manifest.environment_binary_digest = digest(9),
            3 => mismatch.manifest.daemon_digest = digest(9),
            4 => mismatch.manifest.source_commit = digest(9),
            5 => mismatch.manifest.schema_digest = digest(9),
            _ => mismatch.manifest.release_id = "release-wrong".into(),
        }
        assert!(registry.register(mismatch, authorization, 1_001).is_err());
    }
    assert_eq!(registry.ready_capacity(), 1);
}

#[test]
fn heartbeat_boundaries_replay_and_close_remove_ready_capacity_immediately() {
    let mut registry = RendezvousRegistry::new("cell-v1", "shard-v1", 7, 11, manifest()).unwrap();
    let request = registration(3, 7);
    let accepted = registry
        .register(
            request.clone(),
            admission(1, &request, AdmissionPurpose::Registration, 11, 1_000),
            1_000,
        )
        .unwrap();
    let ack = registry.heartbeat(&accepted.peer, 1, 6_000).unwrap();
    assert_eq!(ack.reconnect.expires_at_ms, 51_000);
    assert!(registry.heartbeat(&accepted.peer, 1, 6_001).is_err());

    registry.expire_heartbeats(6_000 + HEARTBEAT_SUSPECT_MS - 1);
    assert_eq!(registry.ready_capacity(), 1);
    registry.expire_heartbeats(6_000 + HEARTBEAT_SUSPECT_MS);
    assert_eq!(registry.ready_capacity(), 0);

    let reconnected = registry
        .reconnect(
            request.clone(),
            admission(3, &request, AdmissionPurpose::Reconnect, 11, 22_000),
            22_000,
        )
        .unwrap();
    assert_eq!(reconnected.environment.state, EnvironmentState::Ready);
    registry.close("environment-v1", 3).unwrap();
    assert_eq!(registry.ready_capacity(), 0);
}

#[test]
fn restart_and_key_epoch_fence_require_full_reauthentication() {
    let mut registry = RendezvousRegistry::new("cell-v1", "shard-v1", 7, 11, manifest()).unwrap();
    let request = registration(3, 7);
    let original = admission(1, &request, AdmissionPurpose::Registration, 11, 1_000);
    registry
        .register(request.clone(), original.clone(), 1_000)
        .unwrap();
    registry.restart(2_000);
    assert_eq!(registry.ready_capacity(), 0);
    assert!(
        registry
            .reconnect(request.clone(), original, 2_001)
            .is_err()
    );
    assert!(
        registry
            .reconnect(
                request.clone(),
                admission(2, &request, AdmissionPurpose::Reconnect, 10, 2_001),
                2_001,
            )
            .is_err()
    );
    registry
        .reconnect(
            request.clone(),
            admission(3, &request, AdmissionPurpose::Reconnect, 11, 2_001),
            2_001,
        )
        .unwrap();
    registry.revoke_key_epoch(12, 2_002);
    assert_eq!(registry.ready_capacity(), 0);
    assert_eq!(
        registry.environment("environment-v1").unwrap().state,
        EnvironmentState::Fenced
    );
}

#[test]
fn replacement_generation_gets_ready_before_old_generation_drains() {
    let mut registry = RendezvousRegistry::new("cell-v1", "shard-v1", 7, 11, manifest()).unwrap();
    let first = registration(3, 7);
    registry
        .register(
            first.clone(),
            admission(1, &first, AdmissionPurpose::Registration, 11, 1_000),
            1_000,
        )
        .unwrap();

    let mut replacement = registration(4, 7);
    replacement.public_noise_key_id = "noise-v2".into();
    replacement.public_noise_key = vec![8; 64];
    registry
        .register(
            replacement.clone(),
            admission(2, &replacement, AdmissionPurpose::Registration, 11, 2_000),
            2_000,
        )
        .unwrap();

    assert_eq!(registry.ready_capacity(), 1);
    assert_eq!(
        registry
            .environment_generation("environment-v1", 3)
            .unwrap()
            .state,
        EnvironmentState::Draining
    );
    assert_eq!(
        registry
            .environment("environment-v1")
            .unwrap()
            .environment_generation,
        4
    );
}

#[test]
fn lifetime_readiness_rotation_and_fencing_use_exact_boundaries() {
    let mut registry = RendezvousRegistry::new("cell-v1", "shard-v1", 7, 11, manifest()).unwrap();
    let mut too_short = registration(1, 7);
    too_short.remaining_lifetime_ms = 239_000;
    assert!(
        registry
            .register(
                too_short.clone(),
                admission(10, &too_short, AdmissionPurpose::Registration, 11, 1_000),
                1_000,
            )
            .is_err()
    );

    let mut exact = registration(1, 7);
    exact.remaining_lifetime_ms = 240_000;
    registry
        .register(
            exact.clone(),
            admission(11, &exact, AdmissionPurpose::Registration, 11, 1_000),
            1_000,
        )
        .unwrap();
    assert!(registry.rotation_due("environment-v1", 1_000));
    registry.fence_expired(240_999);
    assert_eq!(registry.ready_capacity(), 1);
    registry.fence_expired(241_000);
    assert_eq!(
        registry.environment("environment-v1").unwrap().state,
        EnvironmentState::Fenced
    );

    let mut rotation = registration(2, 7);
    rotation.public_noise_key_id = "noise-v2".into();
    rotation.remaining_lifetime_ms = 3_600_001;
    registry
        .register(
            rotation.clone(),
            admission(12, &rotation, AdmissionPurpose::Registration, 11, 300_000),
            300_000,
        )
        .unwrap();
    assert!(!registry.rotation_due("environment-v1", 300_000));
    assert!(registry.rotation_due("environment-v1", 300_001));
}
