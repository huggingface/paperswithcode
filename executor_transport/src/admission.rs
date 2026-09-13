//! Bounded, signed pre-authentication tokens for rendezvous admission.

use std::collections::HashSet;

use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};

pub const MAX_PREAUTH_FRAME_BYTES: usize = 2_048;
pub const PREAUTH_DEADLINE_MS: u64 = 2_000;
pub const RECONNECT_TOKEN_TTL_MS: u64 = 45_000;
pub const REGISTRATION_TOKEN_TTL_MS: u64 = 60_000;
pub const LIVENESS_TOKEN_TTL_MS: u64 = 2_000;
pub const MAX_PREVIOUS_KEY_OVERLAP_MS: u64 = 24 * 60 * 60 * 1_000;
pub const MAX_KEY_LIFETIME_MS: u64 = 30 * 24 * 60 * 60 * 1_000;

const SIGNATURE_DOMAIN: &[u8] = b"pwc-rendezvous-admission/v1";

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
#[repr(u8)]
pub enum AdmissionPurpose {
    Registration,
    Reconnect,
    ClaimLiveness,
}

impl AdmissionPurpose {
    fn ttl_ms(self) -> u64 {
        match self {
            Self::Registration => REGISTRATION_TOKEN_TTL_MS,
            Self::Reconnect => RECONNECT_TOKEN_TTL_MS,
            Self::ClaimLiveness => LIVENESS_TOKEN_TTL_MS,
        }
    }

    pub fn database_name(self) -> &'static str {
        match self {
            Self::Registration => "launch",
            Self::Reconnect => "reconnect",
            Self::ClaimLiveness => "liveness",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
#[repr(u8)]
pub enum LifecycleClass {
    ActiveClaim,
    AssignedIdle,
    BlankPool,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AdmissionClaims {
    pub nonce: [u8; 16],
    pub purpose: AdmissionPurpose,
    pub environment_id: String,
    pub environment_generation: u64,
    pub cell_id: String,
    pub shard_id: String,
    pub shard_generation: u64,
    pub public_noise_key_id: String,
    pub key_epoch: u64,
    pub protocol_version: u32,
    pub schema_digest: [u8; 32],
    pub manifest_digest: [u8; 32],
    pub image_digest: [u8; 32],
    pub environment_binary_digest: [u8; 32],
    pub daemon_digest: [u8; 32],
    pub source_commit: [u8; 32],
    pub release_id: String,
    pub remaining_lifetime_ms: u64,
    pub environment_expires_at_ms: u64,
    pub compatibility_expires_at_ms: Option<u64>,
    pub lifecycle_class: LifecycleClass,
    pub issued_at_ms: u64,
    pub expires_at_ms: u64,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct AdmissionEnvelope {
    claims: AdmissionClaims,
    signer_key_id: String,
    signature: Vec<u8>,
}

pub struct AdmissionSigner {
    key_id: String,
    signing_key: SigningKey,
    not_before_ms: u64,
    not_after_ms: u64,
}

impl AdmissionSigner {
    pub fn from_seed(
        key_id: &str,
        seed: [u8; 32],
        not_before_ms: u64,
        not_after_ms: u64,
    ) -> Result<Self, AdmissionError> {
        validate_identifier(key_id)?;
        if not_after_ms < not_before_ms || not_after_ms - not_before_ms > MAX_KEY_LIFETIME_MS {
            return Err(AdmissionError::KeyRejected);
        }
        Ok(Self {
            key_id: key_id.into(),
            signing_key: SigningKey::from_bytes(&seed),
            not_before_ms,
            not_after_ms,
        })
    }

    pub fn sign(&self, claims: AdmissionClaims) -> Result<Vec<u8>, AdmissionError> {
        validate_claims(&claims)?;
        if claims.issued_at_ms < self.not_before_ms || claims.expires_at_ms > self.not_after_ms {
            return Err(AdmissionError::KeyRejected);
        }
        let canonical = canonical_claims(&claims, &self.key_id)?;
        let envelope = AdmissionEnvelope {
            claims,
            signer_key_id: self.key_id.clone(),
            signature: self.signing_key.sign(&canonical).to_bytes().to_vec(),
        };
        let encoded = serde_json::to_vec(&envelope).map_err(|_| AdmissionError::Malformed)?;
        if encoded.len() > MAX_PREAUTH_FRAME_BYTES {
            return Err(AdmissionError::Oversized);
        }
        Ok(encoded)
    }

    pub fn verification_key(&self) -> AdmissionVerificationKey {
        AdmissionVerificationKey {
            key_id: self.key_id.clone(),
            public_key: self.signing_key.verifying_key().to_bytes(),
            not_before_ms: self.not_before_ms,
            not_after_ms: self.not_after_ms,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AdmissionVerificationKey {
    key_id: String,
    public_key: [u8; 32],
    not_before_ms: u64,
    not_after_ms: u64,
}

impl AdmissionVerificationKey {
    pub fn new(
        key_id: &str,
        public_key: [u8; 32],
        not_before_ms: u64,
        not_after_ms: u64,
    ) -> Result<Self, AdmissionError> {
        validate_identifier(key_id)?;
        VerifyingKey::from_bytes(&public_key).map_err(|_| AdmissionError::KeyRejected)?;
        if not_after_ms < not_before_ms || not_after_ms - not_before_ms > MAX_KEY_LIFETIME_MS {
            return Err(AdmissionError::KeyRejected);
        }
        Ok(Self {
            key_id: key_id.into(),
            public_key,
            not_before_ms,
            not_after_ms,
        })
    }
}

pub struct AdmissionVerifier {
    current: AdmissionVerificationKey,
    previous: Option<AdmissionVerificationKey>,
    revoked: HashSet<String>,
}

impl AdmissionVerifier {
    pub fn new(
        current: AdmissionVerificationKey,
        previous: Option<AdmissionVerificationKey>,
    ) -> Result<Self, AdmissionError> {
        if let Some(previous) = &previous
            && (previous.key_id == current.key_id
                || previous.not_after_ms
                    > current
                        .not_before_ms
                        .checked_add(MAX_PREVIOUS_KEY_OVERLAP_MS)
                        .ok_or(AdmissionError::KeyRejected)?)
        {
            return Err(AdmissionError::KeyRejected);
        }
        Ok(Self {
            current,
            previous,
            revoked: HashSet::new(),
        })
    }

    pub fn revoke(&mut self, key_id: &str) {
        self.revoked.insert(key_id.into());
    }

    pub fn verify(
        &self,
        frame: &[u8],
        elapsed_read_ms: u64,
        now_ms: u64,
    ) -> Result<VerifiedAdmission, AdmissionError> {
        if frame.len() > MAX_PREAUTH_FRAME_BYTES {
            return Err(AdmissionError::Oversized);
        }
        if elapsed_read_ms >= PREAUTH_DEADLINE_MS {
            return Err(AdmissionError::Deadline);
        }
        let envelope: AdmissionEnvelope =
            serde_json::from_slice(frame).map_err(|_| AdmissionError::Malformed)?;
        if self.revoked.contains(&envelope.signer_key_id) {
            return Err(AdmissionError::Revoked);
        }
        let key = if envelope.signer_key_id == self.current.key_id {
            &self.current
        } else if self
            .previous
            .as_ref()
            .is_some_and(|key| envelope.signer_key_id == key.key_id)
        {
            self.previous.as_ref().expect("previous key checked")
        } else {
            return Err(AdmissionError::KeyRejected);
        };
        validate_claims(&envelope.claims)?;
        if now_ms < key.not_before_ms
            || now_ms > key.not_after_ms
            || envelope.claims.issued_at_ms < key.not_before_ms
            || envelope.claims.expires_at_ms > key.not_after_ms
        {
            return Err(AdmissionError::KeyRejected);
        }
        if now_ms < envelope.claims.issued_at_ms || now_ms > envelope.claims.expires_at_ms {
            return Err(AdmissionError::Expired);
        }
        let signature =
            Signature::from_slice(&envelope.signature).map_err(|_| AdmissionError::Signature)?;
        let public_key =
            VerifyingKey::from_bytes(&key.public_key).map_err(|_| AdmissionError::Signature)?;
        public_key
            .verify(
                &canonical_claims(&envelope.claims, &envelope.signer_key_id)?,
                &signature,
            )
            .map_err(|_| AdmissionError::Signature)?;
        Ok(VerifiedAdmission {
            claims: envelope.claims,
            signer_key_id: envelope.signer_key_id,
        })
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VerifiedAdmission {
    claims: AdmissionClaims,
    signer_key_id: String,
}

impl VerifiedAdmission {
    pub fn claims(&self) -> &AdmissionClaims {
        &self.claims
    }

    pub fn signer_key_id(&self) -> &str {
        &self.signer_key_id
    }

    pub fn nonce_digest(&self) -> String {
        use sha2::{Digest, Sha256};

        let digest = Sha256::digest(self.claims.nonce);
        hex_lower(&digest)
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

fn validate_claims(claims: &AdmissionClaims) -> Result<(), AdmissionError> {
    for identifier in [
        &claims.environment_id,
        &claims.cell_id,
        &claims.shard_id,
        &claims.public_noise_key_id,
        &claims.release_id,
    ] {
        validate_identifier(identifier)?;
    }
    if claims.environment_generation == 0
        || claims.shard_generation == 0
        || claims.key_epoch == 0
        || claims.protocol_version == 0
        || claims.remaining_lifetime_ms == 0
        || claims.environment_expires_at_ms <= claims.issued_at_ms
        || claims.environment_expires_at_ms - claims.issued_at_ms != claims.remaining_lifetime_ms
        || claims.remaining_lifetime_ms > 86_400_000
        || claims.compatibility_expires_at_ms.is_some_and(|expires| {
            expires <= claims.issued_at_ms
                || expires - claims.issued_at_ms > MAX_PREVIOUS_KEY_OVERLAP_MS
        })
        || claims.expires_at_ms < claims.issued_at_ms
        || claims.expires_at_ms - claims.issued_at_ms != claims.purpose.ttl_ms()
    {
        return Err(AdmissionError::ClaimsRejected);
    }
    Ok(())
}

fn canonical_claims(
    claims: &AdmissionClaims,
    signer_key_id: &str,
) -> Result<Vec<u8>, AdmissionError> {
    validate_identifier(signer_key_id)?;
    let mut encoded = Vec::with_capacity(512);
    encoded.extend_from_slice(SIGNATURE_DOMAIN);
    push(&mut encoded, signer_key_id.as_bytes())?;
    encoded.extend_from_slice(&claims.nonce);
    encoded.push(claims.purpose as u8);
    push(&mut encoded, claims.environment_id.as_bytes())?;
    encoded.extend_from_slice(&claims.environment_generation.to_be_bytes());
    push(&mut encoded, claims.cell_id.as_bytes())?;
    push(&mut encoded, claims.shard_id.as_bytes())?;
    encoded.extend_from_slice(&claims.shard_generation.to_be_bytes());
    push(&mut encoded, claims.public_noise_key_id.as_bytes())?;
    encoded.extend_from_slice(&claims.key_epoch.to_be_bytes());
    encoded.extend_from_slice(&claims.protocol_version.to_be_bytes());
    encoded.extend_from_slice(&claims.schema_digest);
    encoded.extend_from_slice(&claims.manifest_digest);
    encoded.extend_from_slice(&claims.image_digest);
    encoded.extend_from_slice(&claims.environment_binary_digest);
    encoded.extend_from_slice(&claims.daemon_digest);
    encoded.extend_from_slice(&claims.source_commit);
    push(&mut encoded, claims.release_id.as_bytes())?;
    encoded.extend_from_slice(&claims.remaining_lifetime_ms.to_be_bytes());
    encoded.extend_from_slice(&claims.environment_expires_at_ms.to_be_bytes());
    match claims.compatibility_expires_at_ms {
        Some(expires) => {
            encoded.push(1);
            encoded.extend_from_slice(&expires.to_be_bytes());
        }
        None => encoded.push(0),
    }
    encoded.push(claims.lifecycle_class as u8);
    encoded.extend_from_slice(&claims.issued_at_ms.to_be_bytes());
    encoded.extend_from_slice(&claims.expires_at_ms.to_be_bytes());
    Ok(encoded)
}

fn push(target: &mut Vec<u8>, value: &[u8]) -> Result<(), AdmissionError> {
    let length = u16::try_from(value.len()).map_err(|_| AdmissionError::ClaimsRejected)?;
    target.extend_from_slice(&length.to_be_bytes());
    target.extend_from_slice(value);
    Ok(())
}

fn validate_identifier(value: &str) -> Result<(), AdmissionError> {
    if value.is_empty()
        || value.len() > 128
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
    {
        return Err(AdmissionError::ClaimsRejected);
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, thiserror::Error)]
pub enum AdmissionError {
    #[error("pre-authentication frame rejected")]
    Malformed,
    #[error("pre-authentication frame rejected")]
    Oversized,
    #[error("pre-authentication deadline exceeded")]
    Deadline,
    #[error("admission claims rejected")]
    ClaimsRejected,
    #[error("admission signature rejected")]
    Signature,
    #[error("admission key rejected")]
    KeyRejected,
    #[error("admission key revoked")]
    Revoked,
    #[error("admission token expired")]
    Expired,
}
