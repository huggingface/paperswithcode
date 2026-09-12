use pwc_persistent_executor_transport::admission::{
    AdmissionClaims, AdmissionPurpose, AdmissionSigner, AdmissionVerifier, LifecycleClass,
};
use pwc_persistent_executor_transport::noise::NoiseIdentity;
use pwc_persistent_executor_transport::postgres_registry::PostgresRegistry;
use pwc_persistent_executor_transport::registry::{ManifestPin, RegistrationRequest};
use tokio_postgres::NoTls;
use uuid::Uuid;

fn digest(byte: u8) -> [u8; 32] {
    [byte; 32]
}

#[tokio::test]
async fn durable_registration_consumes_nonce_and_updates_capacity_atomically() {
    let Ok(database_url) = std::env::var("PWC_EXECUTOR_RUST_TEST_DATABASE_URL") else {
        return;
    };
    let (client, connection) = tokio_postgres::connect(&database_url, NoTls).await.unwrap();
    tokio::spawn(async move { connection.await.unwrap() });
    client
        .batch_execute(include_str!(
            "../../backend/database/migrations/add_chat_executor_registrations.sql"
        ))
        .await
        .unwrap();
    let shard_database_id = Uuid::new_v4();
    let manifest = ManifestPin {
        manifest_digest: digest(1),
        image_digest: digest(2),
        environment_binary_digest: digest(3),
        daemon_digest: digest(4),
        source_commit: digest(5),
        protocol_version: 7,
        schema_digest: digest(6),
        release_id: "release-v7".into(),
        compatibility_expires_at_ms: None,
    };
    client
        .execute(
            "INSERT INTO chat_executor_manifests (digest,image_digest,environment_binary_digest,daemon_digest,source_commit,release_id,protocol_version,schema_digest,qualification_status,compatibility_state,qualification_evidence_ref) VALUES ($1,$2,$3,$4,$5,$6,7,$7,'qualified','current','qualification/test')",
            &[&hex(&manifest.manifest_digest), &hex(&manifest.image_digest), &hex(&manifest.environment_binary_digest), &hex(&manifest.daemon_digest), &hex(&manifest.source_commit), &manifest.release_id, &hex(&manifest.schema_digest)],
        )
        .await
        .unwrap();
    client.execute(
        "INSERT INTO chat_executor_cells (cell_id,selected_manifest_digest,key_epoch) VALUES ('cell-v1',$1,11)",
        &[&hex(&manifest.manifest_digest)],
    ).await.unwrap();
    client.execute(
        "INSERT INTO chat_executor_shards (id,cell_id,shard_id,generation,state) VALUES ($1,'cell-v1','shard-v1',7,'ready')",
        &[&shard_database_id],
    ).await.unwrap();
    client
        .execute(
            "UPDATE chat_executor_cells SET active_shard_id=$1 WHERE cell_id='cell-v1'",
            &[&shard_database_id],
        )
        .await
        .unwrap();

    let identity = NoiseIdentity::generate().unwrap();
    let public_key = serde_json::to_vec(&identity.public_key()).unwrap();
    let request = RegistrationRequest {
        environment_id: "environment-v1".into(),
        environment_generation: 1,
        cell_id: "cell-v1".into(),
        shard_id: "shard-v1".into(),
        shard_generation: 7,
        public_noise_key_id: identity.key_id(),
        public_noise_key: public_key,
        manifest: manifest.clone(),
        remaining_lifetime_ms: 240_000,
    };
    let signer = AdmissionSigner::from_seed("issuer-v1", [9; 32], 0, 1_000_000).unwrap();
    let verifier = AdmissionVerifier::new(signer.verification_key(), None).unwrap();
    let token = signer
        .sign(AdmissionClaims {
            nonce: [8; 16],
            purpose: AdmissionPurpose::Registration,
            environment_id: request.environment_id.clone(),
            environment_generation: 1,
            cell_id: request.cell_id.clone(),
            shard_id: request.shard_id.clone(),
            shard_generation: 7,
            public_noise_key_id: "pending".into(),
            key_epoch: 11,
            protocol_version: 7,
            schema_digest: manifest.schema_digest,
            manifest_digest: manifest.manifest_digest,
            image_digest: manifest.image_digest,
            environment_binary_digest: manifest.environment_binary_digest,
            daemon_digest: manifest.daemon_digest,
            source_commit: manifest.source_commit,
            release_id: manifest.release_id.clone(),
            remaining_lifetime_ms: 240_000,
            environment_expires_at_ms: 241_000,
            compatibility_expires_at_ms: None,
            lifecycle_class: LifecycleClass::BlankPool,
            issued_at_ms: 1_000,
            expires_at_ms: 61_000,
        })
        .unwrap();
    let admission = verifier.verify(&token, 0, 1_000).unwrap();
    client.execute(
        "INSERT INTO chat_executor_nonces (nonce_digest,purpose,environment_id,environment_generation,shard_id,shard_generation,key_epoch,expires_at,retention_expires_at) VALUES ($1,'launch','environment-v1',1,$2,7,11,current_timestamp + interval '60 seconds',current_timestamp + interval '1 hour')",
        &[&admission.nonce_digest(), &shard_database_id],
    ).await.unwrap();

    let mut registry = PostgresRegistry::connect(&database_url, shard_database_id)
        .await
        .unwrap();
    registry
        .consume_and_register(&request, &admission)
        .await
        .unwrap();
    assert!(
        registry
            .consume_and_register(&request, &admission)
            .await
            .is_err()
    );
    let ready: i32 = client
        .query_one(
            "SELECT ready_capacity FROM chat_executor_shards WHERE id=$1",
            &[&shard_database_id],
        )
        .await
        .unwrap()
        .get(0);
    assert_eq!(ready, 1);
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}
