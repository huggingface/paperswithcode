//! Content-blind framing, authorization, compatibility, and flow control.
//!
//! Framing and ordered delivery are narrow adaptations of the bounded-prefix
//! and ordered-ciphertext rules in the pinned Codex modules recorded in
//! `PROVENANCE.md`. Product authorization and credit hierarchy are local.

use std::collections::{BTreeMap, HashMap, HashSet, VecDeque};

use ed25519_dalek::{Signature, Signer, SigningKey, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};

pub const MAX_RELAY_PAYLOAD: usize = 60 * 1024;
pub const MAX_CONTROL_PAYLOAD: usize = 4 * 1024;
pub const MAX_CONTROL_CREDIT: usize = 16 * 1024;
pub const MAX_REORDER_DISTANCE: u64 = 64;
pub const MAX_COMMAND_BYTES: usize = 64 * 1024;
pub const MAX_PATH_BYTES: usize = 4 * 1024;
pub const MAX_BASH_TIMEOUT_MS: u32 = 30_000;
pub const MAX_READ_BYTES: usize = 1024 * 1024;
pub const MAX_OPERATION_CREDIT: usize = 64 * 1024;
pub const MAX_STREAM_CREDIT: usize = 256 * 1024;
pub const MAX_CONNECTION_CREDIT: usize = 512 * 1024;
pub const RESUME_WINDOW_MS: u64 = 30_000;
pub const MAX_COMPATIBILITY_SECONDS: u64 = 24 * 60 * 60;

const FRAME_MAGIC: &[u8; 4] = b"PWC1";
const FRAME_HEADER_LEN: usize = 33;
const PROLOGUE_DOMAIN: &[u8] = b"pwc-persistent-executor-noise/v2";
const AUTHORIZATION_DOMAIN: &[u8] = b"pwc-executor-authorization/v1";

/// Prefix an opaque application message before splitting it into Noise-sized
/// records. The authenticated prefix is rejected before unbounded buffering.
pub fn frame_message(message: &[u8]) -> Result<Vec<u8>, ContentFreeError> {
    if message.is_empty() {
        return Err(ContentFreeError::MalformedFrame);
    }
    if message.len() > MAX_READ_BYTES {
        return Err(ContentFreeError::MessageTooLarge);
    }
    let length = u32::try_from(message.len()).map_err(|_| ContentFreeError::MessageTooLarge)?;
    let mut framed = Vec::with_capacity(4 + message.len());
    framed.extend_from_slice(&length.to_be_bytes());
    framed.extend_from_slice(message);
    Ok(framed)
}

fn split_records(framed: &[u8]) -> Vec<Vec<u8>> {
    framed
        .chunks(MAX_RELAY_PAYLOAD)
        .map(<[u8]>::to_vec)
        .collect()
}

pub fn frame_records(message: &[u8]) -> Result<Vec<Vec<u8>>, ContentFreeError> {
    Ok(split_records(&frame_message(message)?))
}

#[derive(Debug, Default)]
pub struct MessageDecoder {
    buffered: Vec<u8>,
}

impl MessageDecoder {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn push(&mut self, record: &[u8]) -> Result<Vec<Vec<u8>>, ContentFreeError> {
        if record.len() > MAX_RELAY_PAYLOAD {
            return Err(ContentFreeError::FrameTooLarge);
        }
        self.buffered.extend_from_slice(record);
        let mut messages = Vec::new();
        loop {
            if self.buffered.len() < 4 {
                break;
            }
            let message_len = u32::from_be_bytes(copy_array(&self.buffered[..4])) as usize;
            if message_len == 0 {
                return Err(ContentFreeError::MalformedFrame);
            }
            if message_len > MAX_READ_BYTES {
                return Err(ContentFreeError::MessageTooLarge);
            }
            let framed_len = 4_usize
                .checked_add(message_len)
                .ok_or(ContentFreeError::IntegerOverflow)?;
            if self.buffered.len() < framed_len {
                break;
            }
            let payload = self.buffered[4..framed_len].to_vec();
            self.buffered.drain(..framed_len);
            messages.push(payload);
        }
        if self.buffered.len() > MAX_READ_BYTES + 4 {
            return Err(ContentFreeError::MessageTooLarge);
        }
        Ok(messages)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
#[repr(u8)]
pub enum FrameKind {
    Data = 0,
    Ack = 1,
    Cancel = 2,
    Terminal = 3,
}

impl TryFrom<u8> for FrameKind {
    type Error = ContentFreeError;

    fn try_from(value: u8) -> Result<Self, Self::Error> {
        match value {
            0 => Ok(Self::Data),
            1 => Ok(Self::Ack),
            2 => Ok(Self::Cancel),
            3 => Ok(Self::Terminal),
            _ => Err(ContentFreeError::FrameKindRejected),
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RelayFrame {
    kind: FrameKind,
    stream_id: u32,
    operation_id: u32,
    sequence: u64,
    /// The next sequence the sender expects, acknowledging every lower value.
    ack_next: u64,
    payload: Vec<u8>,
}

impl RelayFrame {
    pub fn new(
        kind: FrameKind,
        stream_id: u32,
        operation_id: u32,
        sequence: u64,
        ack_next: u64,
        payload: Vec<u8>,
    ) -> Result<Self, ContentFreeError> {
        let payload_limit = if kind == FrameKind::Data {
            MAX_RELAY_PAYLOAD
        } else {
            MAX_CONTROL_PAYLOAD
        };
        if payload.len() > payload_limit {
            return Err(ContentFreeError::FrameTooLarge);
        }
        Ok(Self {
            kind,
            stream_id,
            operation_id,
            sequence,
            ack_next,
            payload,
        })
    }

    pub fn encode(&self) -> Vec<u8> {
        let mut encoded = Vec::with_capacity(FRAME_HEADER_LEN + self.payload.len());
        encoded.extend_from_slice(FRAME_MAGIC);
        encoded.push(self.kind as u8);
        encoded.extend_from_slice(&self.stream_id.to_be_bytes());
        encoded.extend_from_slice(&self.operation_id.to_be_bytes());
        encoded.extend_from_slice(&self.sequence.to_be_bytes());
        encoded.extend_from_slice(&self.ack_next.to_be_bytes());
        encoded.extend_from_slice(&(self.payload.len() as u32).to_be_bytes());
        encoded.extend_from_slice(&self.payload);
        encoded
    }

    pub fn decode(encoded: &[u8]) -> Result<Self, ContentFreeError> {
        if encoded.len() < FRAME_HEADER_LEN || &encoded[..4] != FRAME_MAGIC {
            return Err(ContentFreeError::MalformedFrame);
        }
        let kind = FrameKind::try_from(encoded[4])?;
        let stream_id = u32::from_be_bytes(copy_array(&encoded[5..9]));
        let operation_id = u32::from_be_bytes(copy_array(&encoded[9..13]));
        let sequence = u64::from_be_bytes(copy_array(&encoded[13..21]));
        let ack_next = u64::from_be_bytes(copy_array(&encoded[21..29]));
        let payload_len = u32::from_be_bytes(copy_array(&encoded[29..33])) as usize;
        let payload_limit = if kind == FrameKind::Data {
            MAX_RELAY_PAYLOAD
        } else {
            MAX_CONTROL_PAYLOAD
        };
        if payload_len > payload_limit {
            return Err(ContentFreeError::FrameTooLarge);
        }
        let expected_len = FRAME_HEADER_LEN
            .checked_add(payload_len)
            .ok_or(ContentFreeError::MalformedFrame)?;
        if encoded.len() != expected_len {
            return Err(ContentFreeError::MalformedFrame);
        }
        Self::new(
            kind,
            stream_id,
            operation_id,
            sequence,
            ack_next,
            encoded[33..].to_vec(),
        )
    }

    pub fn kind(&self) -> FrameKind {
        self.kind
    }

    pub fn stream_id(&self) -> u32 {
        self.stream_id
    }

    pub fn operation_id(&self) -> u32 {
        self.operation_id
    }

    pub fn sequence(&self) -> u64 {
        self.sequence
    }

    pub fn ack_next(&self) -> u64 {
        self.ack_next
    }

    pub fn payload(&self) -> &[u8] {
        &self.payload
    }
}

fn copy_array<const N: usize>(slice: &[u8]) -> [u8; N] {
    let mut value = [0; N];
    value.copy_from_slice(slice);
    value
}

#[derive(Debug, Default)]
pub struct SequenceReceiver {
    next_sequence: u64,
    pending: BTreeMap<u64, RelayFrame>,
    pending_bytes: usize,
}

impl SequenceReceiver {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn push(&mut self, frame: RelayFrame) -> Result<Vec<RelayFrame>, ContentFreeError> {
        if frame.sequence < self.next_sequence || self.pending.contains_key(&frame.sequence) {
            return Ok(Vec::new());
        }
        if frame.sequence > self.next_sequence {
            if frame.sequence - self.next_sequence > MAX_REORDER_DISTANCE {
                return Err(ContentFreeError::SequenceViolation);
            }
            let pending_bytes = self
                .pending_bytes
                .checked_add(frame.payload.len())
                .ok_or(ContentFreeError::IntegerOverflow)?;
            if pending_bytes > MAX_STREAM_CREDIT {
                return Err(ContentFreeError::CreditViolation);
            }
            self.pending_bytes = pending_bytes;
            self.pending.insert(frame.sequence, frame);
            return Ok(Vec::new());
        }

        let mut ready = vec![frame];
        self.next_sequence = self
            .next_sequence
            .checked_add(1)
            .ok_or(ContentFreeError::SequenceViolation)?;
        while let Some(frame) = self.pending.remove(&self.next_sequence) {
            self.pending_bytes -= frame.payload.len();
            ready.push(frame);
            self.next_sequence = self
                .next_sequence
                .checked_add(1)
                .ok_or(ContentFreeError::SequenceViolation)?;
        }
        Ok(ready)
    }
}

#[derive(Debug, Default)]
pub struct ReplayBuffer {
    next_sequence: u64,
    ack_next: u64,
    frames: VecDeque<RelayFrame>,
    detached_at_ms: Option<u64>,
    claim_expires_at_ms: Option<u64>,
    buffered_data_bytes: usize,
    buffered_control_bytes: usize,
}

impl ReplayBuffer {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn record(&mut self, frame: RelayFrame) -> Result<(), ContentFreeError> {
        if frame.sequence != self.next_sequence {
            return Err(ContentFreeError::SequenceViolation);
        }
        let data_bytes = if frame.kind == FrameKind::Data {
            frame.payload.len()
        } else {
            0
        };
        let control_bytes = if frame.kind == FrameKind::Data {
            0
        } else {
            frame.payload.len()
        };
        let buffered_data_bytes = self
            .buffered_data_bytes
            .checked_add(data_bytes)
            .ok_or(ContentFreeError::CreditViolation)?;
        if buffered_data_bytes > MAX_STREAM_CREDIT {
            return Err(ContentFreeError::CreditViolation);
        }
        let buffered_control_bytes = self
            .buffered_control_bytes
            .checked_add(control_bytes)
            .ok_or(ContentFreeError::CreditViolation)?;
        if buffered_control_bytes > MAX_CONTROL_CREDIT {
            return Err(ContentFreeError::CreditViolation);
        }
        self.next_sequence = self
            .next_sequence
            .checked_add(1)
            .ok_or(ContentFreeError::SequenceViolation)?;
        self.frames.push_back(frame);
        self.buffered_data_bytes = buffered_data_bytes;
        self.buffered_control_bytes = buffered_control_bytes;
        Ok(())
    }

    pub fn acknowledge(&mut self, ack_next: u64) -> Result<usize, ContentFreeError> {
        if ack_next < self.ack_next || ack_next > self.next_sequence {
            return Err(ContentFreeError::AckViolation);
        }
        let mut removed = 0;
        while self
            .frames
            .front()
            .is_some_and(|frame| frame.sequence < ack_next)
        {
            if let Some(frame) = self.frames.pop_front() {
                if frame.kind == FrameKind::Data {
                    self.buffered_data_bytes -= frame.payload.len();
                } else {
                    self.buffered_control_bytes -= frame.payload.len();
                }
            }
            removed += 1;
        }
        self.ack_next = ack_next;
        Ok(removed)
    }

    pub fn frames_from(&self, ack_next: u64) -> Result<Vec<&RelayFrame>, ContentFreeError> {
        if ack_next < self.ack_next || ack_next > self.next_sequence {
            return Err(ContentFreeError::AckViolation);
        }
        Ok(self
            .frames
            .iter()
            .filter(|frame| frame.sequence >= ack_next)
            .collect())
    }

    pub fn detach(&mut self, now_ms: u64) {
        self.detached_at_ms = Some(now_ms);
        self.claim_expires_at_ms = now_ms.checked_add(RESUME_WINDOW_MS);
    }

    pub fn detach_until(&mut self, now_ms: u64, claim_expires_at_ms: u64) {
        self.detached_at_ms = Some(now_ms);
        self.claim_expires_at_ms = Some(claim_expires_at_ms);
    }

    pub fn resume(&mut self, now_ms: u64) -> Result<(), ContentFreeError> {
        let detached_at = self.detached_at_ms.ok_or(ContentFreeError::ResumeExpired)?;
        let elapsed = now_ms
            .checked_sub(detached_at)
            .ok_or(ContentFreeError::ResumeExpired)?;
        if elapsed > RESUME_WINDOW_MS {
            return Err(ContentFreeError::ResumeExpired);
        }
        if self
            .claim_expires_at_ms
            .is_none_or(|expiry| now_ms > expiry)
        {
            return Err(ContentFreeError::ResumeExpired);
        }
        self.detached_at_ms = None;
        self.claim_expires_at_ms = None;
        Ok(())
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HandshakeBinding {
    pub environment_id: String,
    pub registration_id: String,
    pub stream_id: String,
    pub protocol_version: u32,
    pub schema_digest: [u8; 32],
    pub authorization_key_id: String,
    pub harness_noise_key_id: String,
    pub environment_noise_key_id: String,
}

impl HandshakeBinding {
    pub fn test_fixture(
        harness_noise_key_id: String,
        environment_noise_key_id: String,
        protocol_version: u32,
        schema_digest: [u8; 32],
    ) -> Self {
        Self {
            environment_id: "env-fixture".into(),
            registration_id: "registration-fixture".into(),
            stream_id: "stream-fixture".into(),
            protocol_version,
            schema_digest,
            authorization_key_id: "issuer-fixture".into(),
            harness_noise_key_id,
            environment_noise_key_id,
        }
    }

    pub fn encode_prologue(&self) -> Result<Vec<u8>, ContentFreeError> {
        validate_identifier(&self.authorization_key_id)?;
        validate_identifier(&self.harness_noise_key_id)?;
        validate_identifier(&self.environment_noise_key_id)?;
        let mut encoded = Vec::with_capacity(512);
        encoded.extend_from_slice(PROLOGUE_DOMAIN);
        push_bounded(&mut encoded, self.environment_id.as_bytes())?;
        push_bounded(&mut encoded, self.registration_id.as_bytes())?;
        push_bounded(&mut encoded, self.stream_id.as_bytes())?;
        encoded.extend_from_slice(&self.protocol_version.to_be_bytes());
        encoded.extend_from_slice(&self.schema_digest);
        push_bounded(&mut encoded, self.authorization_key_id.as_bytes())?;
        push_bounded(&mut encoded, self.harness_noise_key_id.as_bytes())?;
        push_bounded(&mut encoded, self.environment_noise_key_id.as_bytes())?;
        if encoded.len() > 2048 {
            return Err(ContentFreeError::AuthorizationRejected);
        }
        Ok(encoded)
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AuthorizationClaims {
    pub authorization_id: [u8; 16],
    pub environment_id: String,
    pub environment_generation: u64,
    pub shard_generation: u64,
    pub stream_id: [u8; 16],
    pub harness_key_id: String,
    pub protocol_version: u32,
    pub schema_digest: [u8; 32],
    pub issued_at: u64,
    pub expires_at: u64,
}

impl AuthorizationClaims {
    fn encode(&self, signer_key_id: &str) -> Result<Vec<u8>, ContentFreeError> {
        validate_identifier(signer_key_id)?;
        validate_identifier(&self.harness_key_id)?;
        if self.expires_at < self.issued_at
            || self.expires_at - self.issued_at > MAX_COMPATIBILITY_SECONDS
        {
            return Err(ContentFreeError::AuthorizationRejected);
        }
        let mut encoded = Vec::with_capacity(256);
        encoded.extend_from_slice(AUTHORIZATION_DOMAIN);
        push_bounded(&mut encoded, signer_key_id.as_bytes())?;
        encoded.extend_from_slice(&self.authorization_id);
        push_bounded(&mut encoded, self.environment_id.as_bytes())?;
        encoded.extend_from_slice(&self.environment_generation.to_be_bytes());
        encoded.extend_from_slice(&self.shard_generation.to_be_bytes());
        encoded.extend_from_slice(&self.stream_id);
        push_bounded(&mut encoded, self.harness_key_id.as_bytes())?;
        encoded.extend_from_slice(&self.protocol_version.to_be_bytes());
        encoded.extend_from_slice(&self.schema_digest);
        encoded.extend_from_slice(&self.issued_at.to_be_bytes());
        encoded.extend_from_slice(&self.expires_at.to_be_bytes());
        if encoded.len() > 2048 {
            return Err(ContentFreeError::AuthorizationRejected);
        }
        Ok(encoded)
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SignedAuthorization {
    pub claims: AuthorizationClaims,
    signer_key_id: String,
    signature: Vec<u8>,
}

impl SignedAuthorization {
    pub fn canonical_claims(&self) -> Result<Vec<u8>, ContentFreeError> {
        self.claims.encode(&self.signer_key_id)
    }

    pub fn signer_key_id(&self) -> &str {
        &self.signer_key_id
    }

    pub fn signature(&self) -> &[u8] {
        &self.signature
    }
}

pub struct AuthorizationSigner {
    key_id: String,
    signing_key: SigningKey,
    not_before: u64,
    not_after: u64,
}

impl AuthorizationSigner {
    pub fn from_seed(
        key_id: &str,
        seed: [u8; 32],
        not_before: u64,
        not_after: u64,
    ) -> Result<Self, ContentFreeError> {
        validate_identifier(key_id)?;
        if not_after < not_before {
            return Err(ContentFreeError::KeyWindowRejected);
        }
        Ok(Self {
            key_id: key_id.into(),
            signing_key: SigningKey::from_bytes(&seed),
            not_before,
            not_after,
        })
    }

    pub fn sign(
        &self,
        claims: AuthorizationClaims,
    ) -> Result<SignedAuthorization, ContentFreeError> {
        if claims.issued_at < self.not_before || claims.expires_at > self.not_after {
            return Err(ContentFreeError::KeyWindowRejected);
        }
        let canonical = claims.encode(&self.key_id)?;
        let signature = self.signing_key.sign(&canonical).to_bytes().to_vec();
        Ok(SignedAuthorization {
            claims,
            signer_key_id: self.key_id.clone(),
            signature,
        })
    }

    pub fn verification_key(&self) -> VerificationKey {
        VerificationKey {
            key_id: self.key_id.clone(),
            public_key: self.signing_key.verifying_key().to_bytes(),
            not_before: self.not_before,
            not_after: self.not_after,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct VerificationKey {
    key_id: String,
    public_key: [u8; 32],
    not_before: u64,
    not_after: u64,
}

impl VerificationKey {
    pub fn new(
        key_id: &str,
        public_key: [u8; 32],
        not_before: u64,
        not_after: u64,
    ) -> Result<Self, ContentFreeError> {
        validate_identifier(key_id)?;
        if not_after < not_before {
            return Err(ContentFreeError::KeyWindowRejected);
        }
        VerifyingKey::from_bytes(&public_key)
            .map_err(|_| ContentFreeError::AuthorizationRejected)?;
        Ok(Self {
            key_id: key_id.into(),
            public_key,
            not_before,
            not_after,
        })
    }
}

#[derive(Debug, Eq, PartialEq)]
pub struct KeyRing {
    current: VerificationKey,
    previous: Option<VerificationKey>,
    revoked: HashSet<String>,
}

impl KeyRing {
    pub fn new(
        current: VerificationKey,
        previous: Option<VerificationKey>,
    ) -> Result<Self, ContentFreeError> {
        validate_identifier(&current.key_id)?;
        if let Some(previous) = &previous {
            validate_identifier(&previous.key_id)?;
            if previous.key_id == current.key_id
                || previous.not_after
                    > current
                        .not_before
                        .checked_add(MAX_COMPATIBILITY_SECONDS)
                        .ok_or(ContentFreeError::IntegerOverflow)?
            {
                return Err(ContentFreeError::KeyWindowRejected);
            }
        }
        Ok(Self {
            current,
            previous,
            revoked: HashSet::new(),
        })
    }

    pub fn revoke(&mut self, key_id: &str) {
        self.revoked.insert(key_id.to_owned());
    }

    pub fn verify(
        &self,
        authorization: &SignedAuthorization,
        now: u64,
    ) -> Result<(), ContentFreeError> {
        if self.revoked.contains(authorization.signer_key_id()) {
            return Err(ContentFreeError::SecurityRevoked);
        }
        let key = if authorization.signer_key_id() == self.current.key_id {
            &self.current
        } else if self
            .previous
            .as_ref()
            .is_some_and(|key| authorization.signer_key_id() == key.key_id)
        {
            self.previous.as_ref().expect("previous key checked")
        } else {
            return Err(ContentFreeError::UnknownKey);
        };
        if now < key.not_before || now > key.not_after {
            return Err(ContentFreeError::KeyExpired);
        }
        if authorization.claims.issued_at < key.not_before
            || authorization.claims.expires_at > key.not_after
        {
            return Err(ContentFreeError::AuthorizationRejected);
        }
        if now < authorization.claims.issued_at || now > authorization.claims.expires_at {
            return Err(ContentFreeError::AuthorizationExpired);
        }
        let public_key = VerifyingKey::from_bytes(&key.public_key)
            .map_err(|_| ContentFreeError::AuthorizationRejected)?;
        let signature = Signature::from_slice(authorization.signature())
            .map_err(|_| ContentFreeError::AuthorizationRejected)?;
        public_key
            .verify(&authorization.canonical_claims()?, &signature)
            .map_err(|_| ContentFreeError::AuthorizationRejected)
    }

    pub fn verify_for_state(
        &self,
        authorization: &SignedAuthorization,
        now: u64,
        _state: AuthorizationState,
    ) -> Result<(), ContentFreeError> {
        // Every state transition rechecks the live ring; cached authorization,
        // detached sequence state, and ACK history never bypass revocation.
        self.verify(authorization, now)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AuthorizationState {
    Fresh,
    Cached,
    Detached,
    Acknowledged,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ProtocolRelease {
    pub version: u32,
    pub schema_digest: [u8; 32],
    pub activated_at: u64,
    pub expires_at: Option<u64>,
}

impl ProtocolRelease {
    pub fn new(
        version: u32,
        schema_digest: [u8; 32],
        activated_at: u64,
        expires_at: Option<u64>,
    ) -> Self {
        Self {
            version,
            schema_digest,
            activated_at,
            expires_at,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RegistrationKind {
    New,
    Existing,
}

#[derive(Debug, Eq, PartialEq)]
pub struct ReleasePolicy {
    current: ProtocolRelease,
    previous: Option<ProtocolRelease>,
}

impl ReleasePolicy {
    pub fn compatible(
        current: ProtocolRelease,
        previous: ProtocolRelease,
    ) -> Result<Self, ContentFreeError> {
        let expected_previous = current
            .version
            .checked_sub(1)
            .ok_or(ContentFreeError::ProtocolVersionRejected)?;
        let compatibility_ends = previous
            .expires_at
            .ok_or(ContentFreeError::ProtocolVersionRejected)?;
        let latest_allowed = current
            .activated_at
            .checked_add(MAX_COMPATIBILITY_SECONDS)
            .ok_or(ContentFreeError::IntegerOverflow)?;
        if current.expires_at.is_some()
            || previous.version != expected_previous
            || previous.activated_at > current.activated_at
            || compatibility_ends < current.activated_at
            || compatibility_ends > latest_allowed
        {
            return Err(ContentFreeError::ProtocolVersionRejected);
        }
        Ok(Self {
            current,
            previous: Some(previous),
        })
    }

    pub fn incompatible(current: ProtocolRelease) -> Result<Self, ContentFreeError> {
        if current.version == 0 || current.expires_at.is_some() {
            return Err(ContentFreeError::ProtocolVersionRejected);
        }
        Ok(Self {
            current,
            previous: None,
        })
    }

    pub fn negotiate(
        &self,
        registration: RegistrationKind,
        advertised: &[ProtocolRelease],
        claims: &AuthorizationClaims,
        now: u64,
    ) -> Result<ProtocolRelease, ContentFreeError> {
        let authorized = if claims.protocol_version == self.current.version {
            if now < self.current.activated_at {
                return Err(ContentFreeError::ProtocolVersionRejected);
            }
            &self.current
        } else if registration == RegistrationKind::Existing {
            self.previous
                .as_ref()
                .filter(|release| release.version == claims.protocol_version)
                .filter(|release| now >= release.activated_at)
                .filter(|release| release.expires_at.is_some_and(|expiry| now <= expiry))
                .ok_or(ContentFreeError::ProtocolVersionRejected)?
        } else {
            return Err(ContentFreeError::ProtocolVersionRejected);
        };
        if claims.schema_digest != authorized.schema_digest {
            return Err(ContentFreeError::SchemaDigestRejected);
        }
        let offered = advertised
            .iter()
            .find(|release| release.version == authorized.version)
            .ok_or(ContentFreeError::ProtocolVersionRejected)?;
        if offered.schema_digest != authorized.schema_digest {
            return Err(ContentFreeError::SchemaDigestRejected);
        }
        Ok(authorized.clone())
    }
}

#[derive(Debug, Default)]
pub struct ConnectionCredits {
    operation: HashMap<(u32, u32), usize>,
    stream: HashMap<u32, usize>,
    connection: usize,
    control: usize,
    failed: bool,
}

impl ConnectionCredits {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn reserve_data(
        &mut self,
        stream_id: u32,
        operation_id: u32,
        bytes: usize,
    ) -> Result<(), ContentFreeError> {
        if self.failed {
            return Err(ContentFreeError::CreditViolation);
        }
        let operation = self
            .operation
            .get(&(stream_id, operation_id))
            .copied()
            .unwrap_or(0);
        let stream = self.stream.get(&stream_id).copied().unwrap_or(0);
        let Some(next_operation) = operation.checked_add(bytes) else {
            self.failed = true;
            return Err(ContentFreeError::CreditViolation);
        };
        let Some(next_stream) = stream.checked_add(bytes) else {
            self.failed = true;
            return Err(ContentFreeError::CreditViolation);
        };
        let Some(next_connection) = self.connection.checked_add(bytes) else {
            self.failed = true;
            return Err(ContentFreeError::CreditViolation);
        };
        if next_operation > MAX_OPERATION_CREDIT
            || next_stream > MAX_STREAM_CREDIT
            || next_connection > MAX_CONNECTION_CREDIT
        {
            self.failed = true;
            return Err(ContentFreeError::CreditViolation);
        }
        self.operation
            .insert((stream_id, operation_id), next_operation);
        self.stream.insert(stream_id, next_stream);
        self.connection = next_connection;
        Ok(())
    }

    pub fn release_data(
        &mut self,
        stream_id: u32,
        operation_id: u32,
        bytes: usize,
    ) -> Result<(), ContentFreeError> {
        let operation = self
            .operation
            .get_mut(&(stream_id, operation_id))
            .ok_or(ContentFreeError::CreditViolation)?;
        if bytes > *operation {
            return Err(ContentFreeError::CreditViolation);
        }
        *operation -= bytes;
        let stream = self
            .stream
            .get_mut(&stream_id)
            .ok_or(ContentFreeError::CreditViolation)?;
        *stream -= bytes;
        self.connection -= bytes;
        Ok(())
    }

    pub fn reserve_control(
        &mut self,
        kind: FrameKind,
        bytes: usize,
    ) -> Result<(), ContentFreeError> {
        if kind == FrameKind::Data {
            return Err(ContentFreeError::FrameKindRejected);
        }
        if bytes > MAX_CONTROL_PAYLOAD {
            return Err(ContentFreeError::FrameTooLarge);
        }
        let next = self
            .control
            .checked_add(bytes)
            .ok_or(ContentFreeError::CreditViolation)?;
        if next > MAX_CONTROL_CREDIT {
            return Err(ContentFreeError::CreditViolation);
        }
        self.control = next;
        Ok(())
    }

    pub fn release_control(&mut self, bytes: usize) -> Result<(), ContentFreeError> {
        if bytes > self.control {
            return Err(ContentFreeError::CreditViolation);
        }
        self.control -= bytes;
        Ok(())
    }

    pub fn operation_bytes(&self, stream_id: u32, operation_id: u32) -> usize {
        self.operation
            .get(&(stream_id, operation_id))
            .copied()
            .unwrap_or(0)
    }

    pub fn stream_bytes(&self, stream_id: u32) -> usize {
        self.stream.get(&stream_id).copied().unwrap_or(0)
    }

    pub fn connection_bytes(&self) -> usize {
        self.connection
    }
}

pub fn validate_bash(command: &[u8], timeout_ms: i64) -> Result<&str, ContentFreeError> {
    let command = std::str::from_utf8(command).map_err(|_| ContentFreeError::InvalidUtf8)?;
    if command.len() > MAX_COMMAND_BYTES {
        return Err(ContentFreeError::CommandRejected);
    }
    if !(0..=MAX_BASH_TIMEOUT_MS as i64).contains(&timeout_ms) {
        return Err(ContentFreeError::TimeoutRejected);
    }
    Ok(command)
}

pub fn validate_read(path: &[u8], offset: i128, length: u128) -> Result<&str, ContentFreeError> {
    let path = std::str::from_utf8(path).map_err(|_| ContentFreeError::InvalidUtf8)?;
    if path.len() > MAX_PATH_BYTES {
        return Err(ContentFreeError::PathRejected);
    }
    let offset = u64::try_from(offset).map_err(|_| ContentFreeError::OffsetRejected)?;
    if length > MAX_READ_BYTES as u128 {
        return Err(ContentFreeError::ReadSizeRejected);
    }
    let length = u64::try_from(length).map_err(|_| ContentFreeError::IntegerOverflow)?;
    offset
        .checked_add(length)
        .ok_or(ContentFreeError::IntegerOverflow)?;
    Ok(path)
}

fn push_bounded(target: &mut Vec<u8>, value: &[u8]) -> Result<(), ContentFreeError> {
    let length = u16::try_from(value.len()).map_err(|_| ContentFreeError::AuthorizationRejected)?;
    target.extend_from_slice(&length.to_be_bytes());
    target.extend_from_slice(value);
    Ok(())
}

fn validate_identifier(identifier: &str) -> Result<(), ContentFreeError> {
    if identifier.is_empty()
        || identifier.len() > 128
        || !identifier
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
    {
        return Err(ContentFreeError::AuthorizationRejected);
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, thiserror::Error)]
pub enum ContentFreeError {
    #[error("relay frame rejected")]
    MalformedFrame,
    #[error("relay frame rejected")]
    FrameTooLarge,
    #[error("relay message rejected")]
    MessageTooLarge,
    #[error("relay frame rejected")]
    FrameKindRejected,
    #[error("relay sequence rejected")]
    SequenceViolation,
    #[error("relay acknowledgement rejected")]
    AckViolation,
    #[error("relay resumption rejected")]
    ResumeExpired,
    #[error("transport credit rejected")]
    CreditViolation,
    #[error("authorization rejected")]
    AuthorizationRejected,
    #[error("authorization expired")]
    AuthorizationExpired,
    #[error("verification key rejected")]
    UnknownKey,
    #[error("verification key expired")]
    KeyExpired,
    #[error("verification key window rejected")]
    KeyWindowRejected,
    #[error("security authorization revoked")]
    SecurityRevoked,
    #[error("protocol version rejected")]
    ProtocolVersionRejected,
    #[error("protocol schema rejected")]
    SchemaDigestRejected,
    #[error("command rejected")]
    CommandRejected,
    #[error("path rejected")]
    PathRejected,
    #[error("timeout rejected")]
    TimeoutRejected,
    #[error("read size rejected")]
    ReadSizeRejected,
    #[error("offset rejected")]
    OffsetRejected,
    #[error("UTF-8 rejected")]
    InvalidUtf8,
    #[error("integer range rejected")]
    IntegerOverflow,
}
