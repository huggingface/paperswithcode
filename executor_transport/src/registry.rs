//! Content-blind rendezvous registration and liveness state.

use std::collections::{HashMap, HashSet};

use crate::admission::{
    AdmissionPurpose, LifecycleClass, RECONNECT_TOKEN_TTL_MS, VerifiedAdmission,
};

pub const HEARTBEAT_INTERVAL_MS: u64 = 5_000;
pub const HEARTBEAT_SUSPECT_MS: u64 = 15_000;
pub const LAST_SEEN_CHECKPOINT_MS: u64 = 30_000;
pub const MIN_READY_LIFETIME_MS: u64 = 240_000;
pub const MAX_ENVIRONMENT_LIFETIME_MS: u64 = 24 * 60 * 60 * 1_000;
pub const REPLACE_BEFORE_DRAIN_MS: u64 = 60 * 60 * 1_000;
pub const MAX_PUBLIC_NOISE_KEY_BYTES: usize = 4_096;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ManifestPin {
    pub manifest_digest: [u8; 32],
    pub image_digest: [u8; 32],
    pub environment_binary_digest: [u8; 32],
    pub daemon_digest: [u8; 32],
    pub source_commit: [u8; 32],
    pub protocol_version: u32,
    pub schema_digest: [u8; 32],
    pub release_id: String,
    pub compatibility_expires_at_ms: Option<u64>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RegistrationRequest {
    pub environment_id: String,
    pub environment_generation: u64,
    pub cell_id: String,
    pub shard_id: String,
    pub shard_generation: u64,
    pub public_noise_key_id: String,
    pub public_noise_key: Vec<u8>,
    pub manifest: ManifestPin,
    pub remaining_lifetime_ms: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum EnvironmentState {
    Ready,
    Claimed,
    Suspect,
    Draining,
    Fenced,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RegisteredEnvironment {
    pub environment_id: String,
    pub environment_generation: u64,
    pub shard_generation: u64,
    pub public_noise_key_id: String,
    pub public_noise_key: Vec<u8>,
    pub authorization_key_id: String,
    pub manifest_digest: [u8; 32],
    pub lifecycle_class: LifecycleClass,
    pub state: EnvironmentState,
    pub last_heartbeat_at_ms: u64,
    pub last_checkpoint_at_ms: u64,
    pub expires_at_ms: u64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AuthenticatedPeer {
    session_id: [u8; 16],
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RegistrationAcceptance {
    pub environment: RegisteredEnvironment,
    pub peer: AuthenticatedPeer,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ReconnectTokenRequest {
    pub environment_id: String,
    pub environment_generation: u64,
    pub cell_id: String,
    pub shard_id: String,
    pub shard_generation: u64,
    pub public_noise_key_id: String,
    pub key_epoch: u64,
    pub protocol_version: u32,
    pub schema_digest: [u8; 32],
    pub lifecycle_class: LifecycleClass,
    pub issued_at_ms: u64,
    pub expires_at_ms: u64,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HeartbeatAck {
    pub checkpoint_due: bool,
    pub reconnect: ReconnectTokenRequest,
}

#[derive(Clone, Debug)]
struct PeerState {
    environment_id: String,
    environment_generation: u64,
    public_noise_key_id: String,
    key_epoch: u64,
    lifecycle_class: LifecycleClass,
    last_sequence: Option<u64>,
}

#[derive(Debug)]
pub struct RendezvousRegistry {
    cell_id: String,
    shard_id: String,
    shard_generation: u64,
    key_epoch: u64,
    manifest: ManifestPin,
    environments: HashMap<(String, u64), RegisteredEnvironment>,
    latest_generation: HashMap<String, u64>,
    consumed_authorizations: HashSet<[u8; 16]>,
    peers: HashMap<[u8; 16], PeerState>,
}

impl RendezvousRegistry {
    pub fn new(
        cell_id: &str,
        shard_id: &str,
        shard_generation: u64,
        key_epoch: u64,
        manifest: ManifestPin,
    ) -> Result<Self, RegistryError> {
        validate_identifier(cell_id)?;
        validate_identifier(shard_id)?;
        validate_identifier(&manifest.release_id)?;
        if shard_generation == 0 || key_epoch == 0 || manifest.protocol_version == 0 {
            return Err(RegistryError::RegistrationRejected);
        }
        Ok(Self {
            cell_id: cell_id.into(),
            shard_id: shard_id.into(),
            shard_generation,
            key_epoch,
            manifest,
            environments: HashMap::new(),
            latest_generation: HashMap::new(),
            consumed_authorizations: HashSet::new(),
            peers: HashMap::new(),
        })
    }

    pub fn register(
        &mut self,
        request: RegistrationRequest,
        admission: VerifiedAdmission,
        now_ms: u64,
    ) -> Result<RegistrationAcceptance, RegistryError> {
        self.validate_registration(&request, &admission, AdmissionPurpose::Registration)?;
        if self
            .latest_generation
            .get(&request.environment_id)
            .is_some_and(|generation| request.environment_generation <= *generation)
        {
            return Err(RegistryError::GenerationRejected);
        }
        if self
            .environments
            .values()
            .any(|row| row.public_noise_key_id == request.public_noise_key_id)
        {
            return Err(RegistryError::IdentityRejected);
        }
        self.consume_authorization(admission.claims().nonce)?;

        if let Some(previous_generation) =
            self.latest_generation.get(&request.environment_id).copied()
            && let Some(previous) = self
                .environments
                .get_mut(&(request.environment_id.clone(), previous_generation))
        {
            previous.state = EnvironmentState::Draining;
        }
        let row = RegisteredEnvironment {
            environment_id: request.environment_id.clone(),
            environment_generation: request.environment_generation,
            shard_generation: request.shard_generation,
            public_noise_key_id: request.public_noise_key_id,
            public_noise_key: request.public_noise_key,
            authorization_key_id: admission.signer_key_id().into(),
            manifest_digest: request.manifest.manifest_digest,
            lifecycle_class: admission.claims().lifecycle_class,
            state: EnvironmentState::Ready,
            last_heartbeat_at_ms: now_ms,
            last_checkpoint_at_ms: now_ms,
            expires_at_ms: now_ms + request.remaining_lifetime_ms,
        };
        self.latest_generation.insert(
            request.environment_id.clone(),
            request.environment_generation,
        );
        self.environments.insert(
            (request.environment_id, request.environment_generation),
            row.clone(),
        );
        Ok(self.accept(row, admission.claims().nonce))
    }

    pub fn reconnect(
        &mut self,
        request: RegistrationRequest,
        admission: VerifiedAdmission,
        now_ms: u64,
    ) -> Result<RegistrationAcceptance, RegistryError> {
        self.validate_registration(&request, &admission, AdmissionPurpose::Reconnect)?;
        if self.latest_generation.get(&request.environment_id)
            != Some(&request.environment_generation)
        {
            return Err(RegistryError::GenerationRejected);
        }
        let key = (
            request.environment_id.clone(),
            request.environment_generation,
        );
        let existing = self
            .environments
            .get(&key)
            .ok_or(RegistryError::RegistrationRejected)?;
        if existing.state != EnvironmentState::Suspect
            || existing.public_noise_key_id != request.public_noise_key_id
            || existing.public_noise_key != request.public_noise_key
        {
            return Err(RegistryError::IdentityRejected);
        }
        self.consume_authorization(admission.claims().nonce)?;
        let row = self
            .environments
            .get_mut(&key)
            .ok_or(RegistryError::RegistrationRejected)?;
        row.state = EnvironmentState::Ready;
        row.last_heartbeat_at_ms = now_ms;
        row.last_checkpoint_at_ms = now_ms;
        let row = row.clone();
        Ok(self.accept(row, admission.claims().nonce))
    }

    pub fn heartbeat(
        &mut self,
        peer: &AuthenticatedPeer,
        sequence: u64,
        now_ms: u64,
    ) -> Result<HeartbeatAck, RegistryError> {
        let peer_state = self
            .peers
            .get_mut(&peer.session_id)
            .ok_or(RegistryError::AuthorizationRejected)?;
        if peer_state.key_epoch != self.key_epoch
            || peer_state
                .last_sequence
                .is_some_and(|previous| sequence <= previous)
        {
            return Err(RegistryError::AuthorizationRejected);
        }
        let key = (
            peer_state.environment_id.clone(),
            peer_state.environment_generation,
        );
        let row = self
            .environments
            .get(&key)
            .ok_or(RegistryError::GenerationRejected)?;
        if row.public_noise_key_id != peer_state.public_noise_key_id
            || row.state != EnvironmentState::Ready
        {
            return Err(RegistryError::IdentityRejected);
        }
        peer_state.last_sequence = Some(sequence);
        let row = self
            .environments
            .get_mut(&key)
            .ok_or(RegistryError::GenerationRejected)?;
        row.last_heartbeat_at_ms = now_ms;
        let checkpoint_due =
            now_ms.saturating_sub(row.last_checkpoint_at_ms) >= LAST_SEEN_CHECKPOINT_MS;
        if checkpoint_due {
            row.last_checkpoint_at_ms = now_ms;
        }
        Ok(HeartbeatAck {
            checkpoint_due,
            reconnect: ReconnectTokenRequest {
                environment_id: row.environment_id.clone(),
                environment_generation: row.environment_generation,
                cell_id: self.cell_id.clone(),
                shard_id: self.shard_id.clone(),
                shard_generation: row.shard_generation,
                public_noise_key_id: row.public_noise_key_id.clone(),
                key_epoch: self.key_epoch,
                protocol_version: self.manifest.protocol_version,
                schema_digest: self.manifest.schema_digest,
                lifecycle_class: peer_state.lifecycle_class,
                issued_at_ms: now_ms,
                expires_at_ms: now_ms + RECONNECT_TOKEN_TTL_MS,
            },
        })
    }

    pub fn expire_heartbeats(&mut self, now_ms: u64) {
        for row in self.environments.values_mut() {
            if row.state == EnvironmentState::Ready
                && now_ms.saturating_sub(row.last_heartbeat_at_ms) >= HEARTBEAT_SUSPECT_MS
            {
                row.state = EnvironmentState::Suspect;
            }
        }
        self.peers.retain(|_, peer| {
            self.environments
                .get(&(peer.environment_id.clone(), peer.environment_generation))
                .is_some_and(|row| row.state == EnvironmentState::Ready)
        });
    }

    pub fn fence_expired(&mut self, now_ms: u64) {
        for row in self.environments.values_mut() {
            if now_ms >= row.expires_at_ms
                || self
                    .manifest
                    .compatibility_expires_at_ms
                    .is_some_and(|expires| now_ms >= expires)
            {
                row.state = EnvironmentState::Fenced;
            }
        }
        self.peers.retain(|_, peer| {
            self.environments
                .get(&(peer.environment_id.clone(), peer.environment_generation))
                .is_some_and(|row| row.state != EnvironmentState::Fenced)
        });
    }

    pub fn rotation_due(&self, environment_id: &str, now_ms: u64) -> bool {
        self.environment(environment_id).is_some_and(|row| {
            row.state == EnvironmentState::Ready
                && row.expires_at_ms.saturating_sub(now_ms) <= REPLACE_BEFORE_DRAIN_MS
        })
    }

    pub fn close(
        &mut self,
        environment_id: &str,
        environment_generation: u64,
    ) -> Result<(), RegistryError> {
        let row = self
            .environments
            .get_mut(&(environment_id.into(), environment_generation))
            .ok_or(RegistryError::GenerationRejected)?;
        if row.state == EnvironmentState::Ready {
            row.state = EnvironmentState::Suspect;
        }
        Ok(())
    }

    pub fn restart(&mut self, _now_ms: u64) {
        for row in self.environments.values_mut() {
            if row.state == EnvironmentState::Ready {
                row.state = EnvironmentState::Suspect;
            }
        }
        self.peers.clear();
    }

    pub fn revoke_key_epoch(&mut self, new_epoch: u64, _now_ms: u64) {
        if new_epoch <= self.key_epoch {
            return;
        }
        self.key_epoch = new_epoch;
        for row in self.environments.values_mut() {
            if matches!(
                row.state,
                EnvironmentState::Ready | EnvironmentState::Suspect
            ) {
                row.state = EnvironmentState::Fenced;
            }
        }
    }

    pub fn ready_capacity(&self) -> usize {
        self.environments
            .values()
            .filter(|row| row.state == EnvironmentState::Ready)
            .count()
    }

    pub fn environment(&self, environment_id: &str) -> Option<&RegisteredEnvironment> {
        let generation = self.latest_generation.get(environment_id)?;
        self.environment_generation(environment_id, *generation)
    }

    pub fn environment_generation(
        &self,
        environment_id: &str,
        environment_generation: u64,
    ) -> Option<&RegisteredEnvironment> {
        self.environments
            .get(&(environment_id.into(), environment_generation))
    }

    fn validate_registration(
        &self,
        request: &RegistrationRequest,
        admission: &VerifiedAdmission,
        purpose: AdmissionPurpose,
    ) -> Result<(), RegistryError> {
        let claims = admission.claims();
        validate_identifier(&request.environment_id)?;
        validate_identifier(&request.cell_id)?;
        validate_identifier(&request.shard_id)?;
        validate_identifier(&request.public_noise_key_id)?;
        validate_identifier(admission.signer_key_id())?;
        if claims.purpose != purpose
            || request.environment_generation == 0
            || request.environment_id != claims.environment_id
            || request.environment_generation != claims.environment_generation
            || request.shard_generation != claims.shard_generation
            || (request.public_noise_key_id != claims.public_noise_key_id
                && !(purpose == AdmissionPurpose::Registration
                    && claims.public_noise_key_id == "pending"))
            || request.cell_id != self.cell_id
            || request.cell_id != claims.cell_id
            || request.shard_id != self.shard_id
            || request.shard_id != claims.shard_id
            || request.shard_generation != self.shard_generation
            || claims.key_epoch != self.key_epoch
            || request.manifest != self.manifest
            || claims.protocol_version != self.manifest.protocol_version
            || claims.schema_digest != self.manifest.schema_digest
            || claims.manifest_digest != request.manifest.manifest_digest
            || claims.image_digest != request.manifest.image_digest
            || claims.environment_binary_digest != request.manifest.environment_binary_digest
            || claims.daemon_digest != request.manifest.daemon_digest
            || claims.source_commit != request.manifest.source_commit
            || claims.release_id != request.manifest.release_id
            || claims.remaining_lifetime_ms != request.remaining_lifetime_ms
            || claims.compatibility_expires_at_ms != request.manifest.compatibility_expires_at_ms
            || request.public_noise_key.is_empty()
            || request.public_noise_key.len() > MAX_PUBLIC_NOISE_KEY_BYTES
            || !(MIN_READY_LIFETIME_MS..=MAX_ENVIRONMENT_LIFETIME_MS)
                .contains(&request.remaining_lifetime_ms)
        {
            return Err(RegistryError::RegistrationRejected);
        }
        Ok(())
    }

    fn consume_authorization(&mut self, authorization_id: [u8; 16]) -> Result<(), RegistryError> {
        if !self.consumed_authorizations.insert(authorization_id) {
            return Err(RegistryError::AuthorizationRejected);
        }
        Ok(())
    }

    fn accept(
        &mut self,
        environment: RegisteredEnvironment,
        session_id: [u8; 16],
    ) -> RegistrationAcceptance {
        self.peers.insert(
            session_id,
            PeerState {
                environment_id: environment.environment_id.clone(),
                environment_generation: environment.environment_generation,
                public_noise_key_id: environment.public_noise_key_id.clone(),
                key_epoch: self.key_epoch,
                lifecycle_class: environment.lifecycle_class,
                last_sequence: None,
            },
        );
        RegistrationAcceptance {
            environment,
            peer: AuthenticatedPeer { session_id },
        }
    }
}

fn validate_identifier(value: &str) -> Result<(), RegistryError> {
    if value.is_empty()
        || value.len() > 128
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
    {
        return Err(RegistryError::RegistrationRejected);
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, thiserror::Error)]
pub enum RegistryError {
    #[error("executor registration rejected")]
    RegistrationRejected,
    #[error("executor authorization rejected")]
    AuthorizationRejected,
    #[error("executor generation rejected")]
    GenerationRejected,
    #[error("executor identity rejected")]
    IdentityRejected,
}
