//! Hybrid IK channel for the persistent-executor feasibility probe.
//!
//! Adapted from Apache-2.0 `codex-rs/exec-server/src/noise_channel.rs` at
//! `c62d191c4c8c0cab7045fca6efc399197334bb6c`. See `PROVENANCE.md`.

use base64::Engine;
use base64::engine::general_purpose::STANDARD;
use clatter::bytearray::ByteArray;
use clatter::constants::MAX_MESSAGE_LEN;
use clatter::crypto::cipher::AesGcm;
use clatter::crypto::dh::X25519;
use clatter::crypto::hash::Sha256;
use clatter::crypto::kem::rust_crypto_ml_kem::MlKem768;
use clatter::handshakepattern::noise_hybrid_ik;
use clatter::traits::{Cipher, Dh, Handshaker, Kem};
use clatter::transportstate::TransportState;
use clatter::{HybridHandshake, HybridHandshakeParams, KeyPair};
use serde::{Deserialize, Serialize};

pub const SUITE: &str = "Noise_hybridIK_X25519+MLKEM768_AESGCM_SHA256";
const PROLOGUE_DOMAIN: &[u8] = b"pwc-persistent-executor-noise/v1";

type Handshake = HybridHandshake<X25519, MlKem768, MlKem768, AesGcm, Sha256>;
type Transport = TransportState<AesGcm, Sha256>;
type DhKeyPair = KeyPair<<X25519 as Dh>::PubKey, <X25519 as Dh>::PrivateKey>;
type KemKeyPair = KeyPair<<MlKem768 as Kem>::PubKey, <MlKem768 as Kem>::SecretKey>;
type KemPublicKey = <MlKem768 as Kem>::PubKey;

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NoisePublicKey {
    suite: String,
    x25519_public_key: String,
    mlkem768_public_key: String,
}

impl NoisePublicKey {
    fn decode(&self) -> Result<(<X25519 as Dh>::PubKey, KemPublicKey), NoiseError> {
        if self.suite != SUITE {
            return Err(NoiseError::InvalidPublicKey("unsupported suite"));
        }
        let dh = STANDARD
            .decode(&self.x25519_public_key)
            .map_err(|_| NoiseError::InvalidPublicKey("invalid X25519 key"))?;
        let dh = dh
            .try_into()
            .map_err(|_| NoiseError::InvalidPublicKey("invalid X25519 key length"))?;
        let kem = STANDARD
            .decode(&self.mlkem768_public_key)
            .map_err(|_| NoiseError::InvalidPublicKey("invalid ML-KEM-768 key"))?;
        if kem.len() != KemPublicKey::LENGTH {
            return Err(NoiseError::InvalidPublicKey(
                "invalid ML-KEM-768 key length",
            ));
        }
        Ok((dh, KemPublicKey::from_slice(&kem)))
    }
}

#[derive(Clone)]
pub struct NoiseIdentity {
    dh: DhKeyPair,
    kem: KemKeyPair,
}

impl NoiseIdentity {
    pub fn generate() -> Result<Self, NoiseError> {
        let dh = X25519::genkey().map_err(|error| NoiseError::KeyGeneration(error.to_string()))?;
        let kem =
            MlKem768::genkey().map_err(|error| NoiseError::KeyGeneration(error.to_string()))?;
        Ok(Self { dh, kem })
    }

    pub fn public_key(&self) -> NoisePublicKey {
        NoisePublicKey {
            suite: SUITE.to_owned(),
            x25519_public_key: STANDARD.encode(self.dh.public),
            mlkem768_public_key: STANDARD.encode(self.kem.public.as_slice()),
        }
    }
}

pub struct InitiatorHandshake {
    handshake: Handshake,
}

impl InitiatorHandshake {
    pub fn start(
        identity: &NoiseIdentity,
        responder_public_key: &NoisePublicKey,
        transcript: &[u8],
        authorization: &[u8],
    ) -> Result<(Self, Vec<u8>), NoiseError> {
        let (responder_dh, responder_kem) = responder_public_key.decode()?;
        let params = HybridHandshakeParams::new(noise_hybrid_ik(), true)
            .with_prologue(transcript)
            .with_s(identity.dh.clone())
            .with_s_kem(identity.kem.clone())
            .with_rs(responder_dh)
            .with_rs_kem(responder_kem);
        let mut handshake = Handshake::new(params)?;
        let overhead = handshake.get_next_message_overhead()?;
        if authorization.len() > MAX_MESSAGE_LEN - overhead {
            return Err(NoiseError::InvalidMessage("authorization is too large"));
        }
        let mut output = vec![0; authorization.len() + overhead];
        let output_len = handshake.write_message(authorization, &mut output)?;
        output.truncate(output_len);
        Ok((Self { handshake }, output))
    }

    pub fn finish(mut self, response: &[u8]) -> Result<NoiseTransport, NoiseError> {
        ensure_frame_len(response.len(), "handshake response is too large")?;
        let overhead = self.handshake.get_next_message_overhead()?;
        let mut payload = vec![0; response.len().saturating_sub(overhead)];
        if self.handshake.read_message(response, &mut payload)? != 0 {
            return Err(NoiseError::InvalidMessage(
                "handshake response payload must be empty",
            ));
        }
        Ok(NoiseTransport(self.handshake.finalize()?))
    }
}

pub struct PendingResponderHandshake {
    handshake: Handshake,
    initiator_public_key: NoisePublicKey,
    authorization: Vec<u8>,
}

impl PendingResponderHandshake {
    pub fn read_request(
        identity: &NoiseIdentity,
        transcript: &[u8],
        request: &[u8],
    ) -> Result<Self, NoiseError> {
        ensure_frame_len(request.len(), "handshake request is too large")?;
        let params = HybridHandshakeParams::new(noise_hybrid_ik(), false)
            .with_prologue(transcript)
            .with_s(identity.dh.clone())
            .with_s_kem(identity.kem.clone());
        let mut handshake = Handshake::new(params)?;
        let overhead = handshake.get_next_message_overhead()?;
        let mut authorization = vec![0; request.len().saturating_sub(overhead)];
        let payload_len = handshake.read_message(request, &mut authorization)?;
        let remote = handshake
            .get_remote_static()
            .ok_or(NoiseError::InvalidMessage("missing initiator static key"))?;
        authorization.truncate(payload_len);
        Ok(Self {
            handshake,
            initiator_public_key: NoisePublicKey {
                suite: SUITE.to_owned(),
                x25519_public_key: STANDARD.encode(remote.dh()),
                mlkem768_public_key: STANDARD.encode(remote.kem().as_slice()),
            },
            authorization,
        })
    }

    pub fn initiator_public_key(&self) -> &NoisePublicKey {
        &self.initiator_public_key
    }

    pub fn authorization(&self) -> &[u8] {
        &self.authorization
    }

    pub fn complete(mut self) -> Result<(NoiseTransport, Vec<u8>), NoiseError> {
        let overhead = self.handshake.get_next_message_overhead()?;
        let mut response = vec![0; overhead];
        let response_len = self.handshake.write_message(&[], &mut response)?;
        response.truncate(response_len);
        Ok((NoiseTransport(self.handshake.finalize()?), response))
    }
}

pub struct NoiseTransport(Transport);

impl NoiseTransport {
    pub fn encrypt(&mut self, plaintext: &[u8]) -> Result<Vec<u8>, NoiseError> {
        let frame_len =
            plaintext
                .len()
                .checked_add(AesGcm::tag_len())
                .ok_or(NoiseError::InvalidMessage(
                    "transport plaintext is too large",
                ))?;
        ensure_frame_len(frame_len, "transport plaintext is too large")?;
        Ok(self.0.send_vec(plaintext)?)
    }

    pub fn decrypt(&mut self, ciphertext: &[u8]) -> Result<Vec<u8>, NoiseError> {
        if ciphertext.len() < AesGcm::tag_len() {
            return Err(NoiseError::InvalidMessage(
                "transport ciphertext is too short",
            ));
        }
        ensure_frame_len(ciphertext.len(), "transport ciphertext is too large")?;
        Ok(self.0.receive_vec(ciphertext)?)
    }
}

pub fn prologue(environment_id: &str, registration_id: &str, stream_id: &str) -> Vec<u8> {
    let mut value = Vec::new();
    for part in [
        PROLOGUE_DOMAIN,
        environment_id.as_bytes(),
        registration_id.as_bytes(),
        stream_id.as_bytes(),
    ] {
        value.extend_from_slice(&(part.len() as u64).to_be_bytes());
        value.extend_from_slice(part);
    }
    value
}

fn ensure_frame_len(frame_len: usize, message: &'static str) -> Result<(), NoiseError> {
    if frame_len > MAX_MESSAGE_LEN {
        return Err(NoiseError::InvalidMessage(message));
    }
    Ok(())
}

#[derive(Debug, thiserror::Error)]
pub enum NoiseError {
    #[error("Noise key generation failed: {0}")]
    KeyGeneration(String),
    #[error("invalid Noise public key: {0}")]
    InvalidPublicKey(&'static str),
    #[error("invalid Noise message: {0}")]
    InvalidMessage(&'static str),
    #[error("Noise handshake failed: {0}")]
    Handshake(String),
    #[error("Noise transport failed: {0}")]
    Transport(String),
}

impl From<clatter::error::HandshakeError> for NoiseError {
    fn from(error: clatter::error::HandshakeError) -> Self {
        Self::Handshake(error.to_string())
    }
}

impl From<clatter::error::TransportError> for NoiseError {
    fn from(error: clatter::error::TransportError) -> Self {
        Self::Transport(error.to_string())
    }
}
