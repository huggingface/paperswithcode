//! PostgreSQL-backed nonce consumption and registration transitions.

use serde_json::Value;
use tokio_postgres::{Client, NoTls};
use uuid::Uuid;

use crate::admission::{AdmissionPurpose, VerifiedAdmission};
use crate::registry::{MAX_PUBLIC_NOISE_KEY_BYTES, RegistrationRequest};

pub struct PostgresRegistry {
    client: Client,
    shard_database_id: Uuid,
}

impl PostgresRegistry {
    pub async fn connect(
        database_url: &str,
        shard_database_id: Uuid,
    ) -> Result<Self, DurableRegistryError> {
        let (client, connection) = tokio_postgres::connect(database_url, NoTls).await?;
        tokio::spawn(async move {
            if connection.await.is_err() {
                eprintln!("executor registry connection closed");
            }
        });
        Ok(Self {
            client,
            shard_database_id,
        })
    }

    pub async fn consume_and_register(
        &mut self,
        request: &RegistrationRequest,
        admission: &VerifiedAdmission,
    ) -> Result<Uuid, DurableRegistryError> {
        let claims = admission.claims();
        if claims.environment_id != request.environment_id
            || claims.environment_generation != request.environment_generation
            || claims.cell_id != request.cell_id
            || claims.shard_id != request.shard_id
            || claims.shard_generation != request.shard_generation
            || (claims.public_noise_key_id != request.public_noise_key_id
                && !(claims.purpose == AdmissionPurpose::Registration
                    && claims.public_noise_key_id == "pending"))
            || claims.protocol_version != request.manifest.protocol_version
            || claims.schema_digest != request.manifest.schema_digest
            || claims.manifest_digest != request.manifest.manifest_digest
            || claims.image_digest != request.manifest.image_digest
            || claims.environment_binary_digest != request.manifest.environment_binary_digest
            || claims.daemon_digest != request.manifest.daemon_digest
            || claims.source_commit != request.manifest.source_commit
            || claims.release_id != request.manifest.release_id
            || claims.remaining_lifetime_ms != request.remaining_lifetime_ms
            || claims.compatibility_expires_at_ms != request.manifest.compatibility_expires_at_ms
        {
            return Err(DurableRegistryError::Rejected);
        }
        if request.public_noise_key.is_empty()
            || request.public_noise_key.len() > MAX_PUBLIC_NOISE_KEY_BYTES
            || !(240_000..=86_400_000).contains(&request.remaining_lifetime_ms)
        {
            return Err(DurableRegistryError::Rejected);
        }
        let public_noise_key: Value = serde_json::from_slice(&request.public_noise_key)
            .map_err(|_| DurableRegistryError::Rejected)?;
        if !public_noise_key.is_object() {
            return Err(DurableRegistryError::Rejected);
        }

        let transaction = self.client.transaction().await?;
        let nonce = transaction
            .query_opt(
                r#"
                UPDATE chat_executor_nonces
                SET consumed_at = current_timestamp
                WHERE nonce_digest = $1
                  AND purpose = $2
                  AND environment_id = $3
                  AND environment_generation = $4
                  AND shard_id = $5
                  AND shard_generation = $6
                  AND key_epoch = $7
                  AND consumed_at IS NULL
                  AND invalidated_at IS NULL
                  AND expires_at >= current_timestamp
                RETURNING nonce_digest
                "#,
                &[
                    &admission.nonce_digest(),
                    &claims.purpose.database_name(),
                    &claims.environment_id,
                    &(claims.environment_generation as i64),
                    &self.shard_database_id,
                    &(claims.shard_generation as i64),
                    &(claims.key_epoch as i64),
                ],
            )
            .await?;
        if nonce.is_none() {
            return Err(DurableRegistryError::Rejected);
        }

        let manifest_digest = hex_lower(&request.manifest.manifest_digest);
        let route = transaction
            .query_opt(
                r#"
                SELECT c.selected_manifest_digest, c.key_epoch, c.circuit_state,
                       c.active_shard_id, s.generation, s.state,
                       m.image_digest, m.environment_binary_digest, m.daemon_digest,
                       m.source_commit, m.protocol_version, m.schema_digest, m.release_id,
                       CASE WHEN m.compatibility_expires_at IS NULL THEN NULL
                            ELSE floor(extract(epoch FROM m.compatibility_expires_at) * 1000)::bigint
                       END,
                       (m.qualification_status='qualified'
                        AND m.compatibility_state<>'incompatible'
                        AND m.revoked_at IS NULL
                        AND (m.compatibility_expires_at IS NULL
                             OR m.compatibility_expires_at >= current_timestamp)) AS eligible
                FROM chat_executor_cells c
                JOIN chat_executor_shards s ON s.id = $2 AND s.cell_id = c.cell_id
                JOIN chat_executor_manifests m ON m.digest = c.selected_manifest_digest
                WHERE c.cell_id = $1
                FOR UPDATE OF c, s
                "#,
                &[&request.cell_id, &self.shard_database_id],
            )
            .await?
            .ok_or(DurableRegistryError::Rejected)?;
        let selected_manifest: Option<String> = route.get(0);
        let key_epoch: i64 = route.get(1);
        let circuit_state: String = route.get(2);
        let active_shard_id: Option<Uuid> = route.get(3);
        let shard_generation: i64 = route.get(4);
        let shard_state: String = route.get(5);
        let image_digest: String = route.get(6);
        let environment_binary_digest: String = route.get(7);
        let daemon_digest: String = route.get(8);
        let source_commit: String = route.get(9);
        let protocol_version: i32 = route.get(10);
        let schema_digest: String = route.get(11);
        let release_id: String = route.get(12);
        let compatibility_expires_at_ms: Option<i64> = route.get(13);
        let eligible: bool = route.get(14);
        if selected_manifest.as_deref() != Some(&manifest_digest)
            || key_epoch != claims.key_epoch as i64
            || circuit_state != "closed"
            || active_shard_id != Some(self.shard_database_id)
            || shard_generation != request.shard_generation as i64
            || shard_state != "ready"
            || image_digest != hex_lower(&request.manifest.image_digest)
            || environment_binary_digest != hex_lower(&request.manifest.environment_binary_digest)
            || daemon_digest != hex_lower(&request.manifest.daemon_digest)
            || source_commit != hex_lower(&request.manifest.source_commit)
            || protocol_version != request.manifest.protocol_version as i32
            || schema_digest != hex_lower(&request.manifest.schema_digest)
            || release_id != request.manifest.release_id
            || compatibility_expires_at_ms.map(|value| value as u64)
                != request.manifest.compatibility_expires_at_ms
            || !eligible
        {
            return Err(DurableRegistryError::Rejected);
        }

        let latest = transaction
            .query_opt(
                r#"
                SELECT id, environment_generation, public_key_id, public_noise_key, state
                FROM chat_executor_registrations
                WHERE environment_id = $1
                ORDER BY environment_generation DESC
                LIMIT 1
                FOR UPDATE
                "#,
                &[&request.environment_id],
            )
            .await?;
        let registration_id = if let Some(latest) = latest {
            let latest_id: Uuid = latest.get(0);
            let latest_generation: i64 = latest.get(1);
            let latest_key_id: String = latest.get(2);
            let latest_public_key: Value = latest.get(3);
            let latest_state: String = latest.get(4);
            if request.environment_generation as i64 == latest_generation {
                if claims.purpose != AdmissionPurpose::Reconnect
                    || latest_state != "suspect"
                    || latest_key_id != request.public_noise_key_id
                    || latest_public_key != public_noise_key
                {
                    return Err(DurableRegistryError::Rejected);
                }
                transaction
                    .execute(
                        r#"
                        UPDATE chat_executor_registrations
                        SET state='ready', last_seen_at=current_timestamp,
                            updated_at=current_timestamp
                        WHERE id=$1
                        "#,
                        &[&latest_id],
                    )
                    .await?;
                latest_id
            } else {
                if claims.purpose != AdmissionPurpose::Registration
                    || request.environment_generation as i64 <= latest_generation
                    || latest_key_id == request.public_noise_key_id
                {
                    return Err(DurableRegistryError::Rejected);
                }
                transaction
                    .execute(
                        r#"
                        UPDATE chat_executor_registrations
                        SET state='draining', updated_at=current_timestamp
                        WHERE id=$1 AND state IN ('ready','assigned_idle')
                        "#,
                        &[&latest_id],
                    )
                    .await?;
                Self::insert_registration(
                    &transaction,
                    self.shard_database_id,
                    request,
                    admission,
                    &public_noise_key,
                    &manifest_digest,
                )
                .await?
            }
        } else {
            if claims.purpose != AdmissionPurpose::Registration {
                return Err(DurableRegistryError::Rejected);
            }
            Self::insert_registration(
                &transaction,
                self.shard_database_id,
                request,
                admission,
                &public_noise_key,
                &manifest_digest,
            )
            .await?
        };

        transaction
            .execute(
                r#"
                UPDATE chat_executor_shards
                SET ready_capacity = (
                        SELECT count(*) FROM chat_executor_registrations
                        WHERE shard_id=$1 AND state='ready'
                    ), updated_at=current_timestamp
                WHERE id=$1
                "#,
                &[&self.shard_database_id],
            )
            .await?;
        transaction
            .execute(
                r#"
                UPDATE chat_executor_manifests
                SET ready_capacity = (
                    SELECT count(*) FROM chat_executor_registrations
                    WHERE manifest_digest=$1 AND state='ready'
                )
                WHERE digest=$1
                "#,
                &[&manifest_digest],
            )
            .await?;
        transaction.commit().await?;
        Ok(registration_id)
    }

    pub async fn invalidate_ready_on_startup(&mut self) -> Result<u64, DurableRegistryError> {
        let transaction = self.client.transaction().await?;
        let changed = transaction
            .execute(
                r#"
                UPDATE chat_executor_registrations
                SET state='suspect', updated_at=current_timestamp
                WHERE shard_id=$1 AND state IN ('ready','assigned_idle','claimed')
                "#,
                &[&self.shard_database_id],
            )
            .await?;
        transaction
            .execute(
                r#"
                UPDATE chat_executor_claims c
                SET state='invalidated', settled_at=current_timestamp,
                    terminal_code='rendezvous_restart'
                FROM chat_executor_registrations r
                WHERE c.registration_id=r.id AND r.shard_id=$1 AND c.state='active'
                "#,
                &[&self.shard_database_id],
            )
            .await?;
        transaction
            .execute(
                "UPDATE chat_executor_shards SET ready_capacity=0, updated_at=current_timestamp WHERE id=$1",
                &[&self.shard_database_id],
            )
            .await?;
        transaction
            .execute(
                r#"
                UPDATE chat_executor_manifests m SET ready_capacity=(
                    SELECT count(*) FROM chat_executor_registrations r
                    WHERE r.manifest_digest=m.digest AND r.state='ready'
                )
                WHERE EXISTS (
                    SELECT 1 FROM chat_executor_registrations r
                    WHERE r.manifest_digest=m.digest AND r.shard_id=$1
                )
                "#,
                &[&self.shard_database_id],
            )
            .await?;
        transaction.commit().await?;
        Ok(changed)
    }

    pub async fn persist_nonce(
        &self,
        admission: &VerifiedAdmission,
    ) -> Result<(), DurableRegistryError> {
        let claims = admission.claims();
        let ttl_seconds = match claims.purpose {
            AdmissionPurpose::Registration => 60_i64,
            AdmissionPurpose::Reconnect => 45_i64,
            AdmissionPurpose::ClaimLiveness => 2_i64,
        };
        self.client
            .execute(
                r#"
                INSERT INTO chat_executor_nonces (
                    nonce_digest, purpose, environment_id, environment_generation,
                    shard_id, shard_generation, key_epoch, expires_at,
                    retention_expires_at, created_at
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,
                    current_timestamp + ($8::bigint * interval '1 second'),
                    current_timestamp + interval '24 hours', current_timestamp
                )
                "#,
                &[
                    &admission.nonce_digest(),
                    &claims.purpose.database_name(),
                    &claims.environment_id,
                    &(claims.environment_generation as i64),
                    &self.shard_database_id,
                    &(claims.shard_generation as i64),
                    &(claims.key_epoch as i64),
                    &ttl_seconds,
                ],
            )
            .await?;
        Ok(())
    }

    async fn insert_registration(
        transaction: &tokio_postgres::Transaction<'_>,
        shard_database_id: Uuid,
        request: &RegistrationRequest,
        admission: &VerifiedAdmission,
        public_noise_key: &Value,
        manifest_digest: &str,
    ) -> Result<Uuid, DurableRegistryError> {
        let registration_id = Uuid::new_v4();
        let claims = admission.claims();
        transaction
            .execute(
                r#"
                INSERT INTO chat_executor_registrations (
                    id, environment_id, environment_generation, cell_id,
                    shard_id, shard_generation, public_key_id, public_noise_key,
                    authorization_key_id, key_epoch, manifest_digest, state,
                    last_seen_at, expires_at, created_at, updated_at
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'ready',
                    current_timestamp,
                    current_timestamp + ($12::bigint * interval '1 millisecond'),
                    current_timestamp,current_timestamp
                )
                "#,
                &[
                    &registration_id,
                    &request.environment_id,
                    &(request.environment_generation as i64),
                    &request.cell_id,
                    &shard_database_id,
                    &(request.shard_generation as i64),
                    &request.public_noise_key_id,
                    public_noise_key,
                    &admission.signer_key_id(),
                    &(claims.key_epoch as i64),
                    &manifest_digest,
                    &(request.remaining_lifetime_ms as i64),
                ],
            )
            .await?;
        Ok(registration_id)
    }

    pub async fn mark_suspect(
        &mut self,
        registration_id: Uuid,
    ) -> Result<(), DurableRegistryError> {
        let transaction = self.client.transaction().await?;
        let row = transaction
            .query_opt(
                r#"
                UPDATE chat_executor_registrations r
                SET state=CASE
                        WHEN r.expires_at <= current_timestamp
                          OR EXISTS (
                            SELECT 1 FROM chat_executor_manifests m
                            WHERE m.digest=r.manifest_digest
                              AND (m.revoked_at IS NOT NULL
                                   OR m.compatibility_state='incompatible'
                                   OR (m.compatibility_expires_at IS NOT NULL
                                       AND m.compatibility_expires_at <= current_timestamp))
                          ) THEN 'fenced'
                        ELSE 'suspect'
                    END,
                    updated_at=current_timestamp
                WHERE r.id=$1 AND r.state IN ('ready','assigned_idle','claimed')
                RETURNING shard_id, manifest_digest
                "#,
                &[&registration_id],
            )
            .await?;
        if let Some(row) = row {
            let shard_id: Uuid = row.get(0);
            let manifest_digest: String = row.get(1);
            transaction
                .execute(
                    r#"
                    UPDATE chat_executor_claims
                    SET state='invalidated', settled_at=current_timestamp,
                        terminal_code='registration_suspect'
                    WHERE registration_id=$1 AND state='active'
                    "#,
                    &[&registration_id],
                )
                .await?;
            transaction
                .execute(
                    r#"
                    UPDATE chat_executor_shards SET ready_capacity=(
                        SELECT count(*) FROM chat_executor_registrations
                        WHERE shard_id=$1 AND state='ready'
                    ), updated_at=current_timestamp WHERE id=$1
                    "#,
                    &[&shard_id],
                )
                .await?;
            transaction
                .execute(
                    r#"
                    UPDATE chat_executor_manifests SET ready_capacity=(
                        SELECT count(*) FROM chat_executor_registrations
                        WHERE manifest_digest=$1 AND state='ready'
                    ) WHERE digest=$1
                    "#,
                    &[&manifest_digest],
                )
                .await?;
        }
        transaction.commit().await?;
        Ok(())
    }

    pub async fn checkpoint_seen(
        &self,
        registration_ids: &[Uuid],
    ) -> Result<u64, DurableRegistryError> {
        Ok(self
            .client
            .execute(
                r#"
                UPDATE chat_executor_registrations
                SET last_seen_at=current_timestamp, updated_at=current_timestamp
                WHERE id = ANY($1)
                  AND (last_seen_at IS NULL
                       OR last_seen_at <= current_timestamp - interval '30 seconds')
                "#,
                &[&registration_ids],
            )
            .await?)
    }
}

fn hex_lower(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut value = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        value.push(DIGITS[(byte >> 4) as usize] as char);
        value.push(DIGITS[(byte & 0x0f) as usize] as char);
    }
    value
}

#[derive(Debug, thiserror::Error)]
pub enum DurableRegistryError {
    #[error("executor registry rejected")]
    Rejected,
    #[error("executor registry unavailable")]
    Database(#[from] tokio_postgres::Error),
}
