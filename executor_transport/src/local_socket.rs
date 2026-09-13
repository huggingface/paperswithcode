//! Bounded framing and authorization for the trusted VPS harness socket.

use std::collections::HashSet;
use std::fs::File;
use std::io::Read;
use std::os::unix::fs::{FileTypeExt, PermissionsExt};
use std::path::Path;

use serde::{Deserialize, Serialize};
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt};
use tokio::net::UnixStream;

use crate::noise::{NoiseIdentity, NoisePublicKey};
use crate::protocol::{
    AuthorizationClaims, AuthorizationSigner, ContentFreeError, HandshakeBinding,
    SignedAuthorization,
};

pub const MAX_LOCAL_FRAME_BYTES: usize = 2 * 1024 * 1024;
pub const MAX_ATTACH_LIFETIME_SECONDS: u64 = 2;

#[derive(Debug, thiserror::Error)]
pub enum LocalSocketError {
    #[error("local socket rejected")]
    SocketRejected,
    #[error("private credential rejected")]
    CredentialRejected,
    #[error("local frame rejected")]
    FrameRejected,
    #[error("peer rejected")]
    PeerRejected,
    #[error("attachment rejected")]
    AttachmentRejected,
    #[error("local I/O failed")]
    Io(#[from] std::io::Error),
    #[error("authorization rejected")]
    Authorization(#[from] ContentFreeError),
}

pub async fn read_frame<R: AsyncRead + Unpin>(stream: &mut R) -> Result<Vec<u8>, LocalSocketError> {
    let length = stream.read_u32().await? as usize;
    if length == 0 || length > MAX_LOCAL_FRAME_BYTES {
        return Err(LocalSocketError::FrameRejected);
    }
    let mut frame = vec![0; length];
    stream.read_exact(&mut frame).await?;
    Ok(frame)
}

pub async fn write_frame<W: AsyncWrite + Unpin>(
    stream: &mut W,
    frame: &[u8],
) -> Result<(), LocalSocketError> {
    if frame.is_empty() || frame.len() > MAX_LOCAL_FRAME_BYTES {
        return Err(LocalSocketError::FrameRejected);
    }
    stream
        .write_u32(
            frame
                .len()
                .try_into()
                .map_err(|_| LocalSocketError::FrameRejected)?,
        )
        .await?;
    stream.write_all(frame).await?;
    stream.flush().await?;
    Ok(())
}

pub fn validate_socket_path(path: &Path) -> Result<(), LocalSocketError> {
    let metadata = std::fs::symlink_metadata(path).map_err(LocalSocketError::Io)?;
    let parent = path.parent().ok_or(LocalSocketError::SocketRejected)?;
    let parent_metadata =
        std::fs::metadata(parent).map_err(|_| LocalSocketError::SocketRejected)?;
    if !metadata.file_type().is_socket()
        || metadata.permissions().mode() & 0o007 != 0
        || parent_metadata.permissions().mode() & 0o022 != 0
    {
        return Err(LocalSocketError::SocketRejected);
    }
    Ok(())
}

pub fn validate_peer(stream: &UnixStream, expected_uid: u32) -> Result<(), LocalSocketError> {
    let credential = stream
        .peer_cred()
        .map_err(|_| LocalSocketError::PeerRejected)?;
    if credential.uid() != expected_uid {
        return Err(LocalSocketError::PeerRejected);
    }
    Ok(())
}

pub fn read_private_seed(path: &Path) -> Result<[u8; 32], LocalSocketError> {
    let metadata = std::fs::symlink_metadata(path).map_err(LocalSocketError::Io)?;
    if !metadata.file_type().is_file()
        || metadata.file_type().is_symlink()
        || metadata.permissions().mode() & 0o077 != 0
        || metadata.len() != 32
    {
        return Err(LocalSocketError::CredentialRejected);
    }
    let mut file = File::open(path)?;
    let mut seed = [0; 32];
    file.read_exact(&mut seed)?;
    let mut excess = [0; 1];
    if file.read(&mut excess)? != 0 {
        return Err(LocalSocketError::CredentialRejected);
    }
    Ok(seed)
}

pub fn prepare_listener_path(path: &Path) -> Result<(), LocalSocketError> {
    let parent = path.parent().ok_or(LocalSocketError::SocketRejected)?;
    let metadata = std::fs::metadata(parent).map_err(LocalSocketError::Io)?;
    if metadata.permissions().mode() & 0o022 != 0 {
        return Err(LocalSocketError::SocketRejected);
    }
    if let Ok(existing) = std::fs::symlink_metadata(path) {
        if !existing.file_type().is_socket() {
            return Err(LocalSocketError::SocketRejected);
        }
        std::fs::remove_file(path)?;
    }
    Ok(())
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AttachmentRequest {
    pub request_id: String,
    pub environment_id: String,
    pub environment_generation: u64,
    pub registration_id: String,
    pub shard_generation: u64,
    pub stream_id: String,
    pub protocol_version: u32,
    pub schema_digest: String,
    pub authorization_id: String,
    pub expires_at: u64,
    pub harness_key_id: String,
    pub authorization_key_id: String,
    pub environment_noise_key_id: String,
    pub environment_public_key: NoisePublicKey,
}

#[derive(Clone, Debug, Serialize)]
pub struct AttachmentGrant {
    pub binding: HandshakeBinding,
    pub authorization: SignedAuthorization,
}

pub struct AttachmentGate {
    harness: NoiseIdentity,
    signer: AuthorizationSigner,
    protocol_version: u32,
    schema_digest: [u8; 32],
    used: HashSet<[u8; 16]>,
}

impl AttachmentGate {
    pub fn new(
        harness: NoiseIdentity,
        signer: AuthorizationSigner,
        protocol_version: u32,
        schema_digest: [u8; 32],
    ) -> Result<Self, LocalSocketError> {
        if protocol_version == 0 {
            return Err(LocalSocketError::AttachmentRejected);
        }
        Ok(Self {
            harness,
            signer,
            protocol_version,
            schema_digest,
            used: HashSet::new(),
        })
    }

    pub fn harness(&self) -> &NoiseIdentity {
        &self.harness
    }

    pub fn authorization_key_id(&self) -> &str {
        self.signer.key_id()
    }

    pub fn authorize(
        &mut self,
        request: &AttachmentRequest,
        now: u64,
    ) -> Result<AttachmentGrant, LocalSocketError> {
        let schema_digest = decode_hex::<32>(&request.schema_digest)?;
        let authorization_id = decode_hex::<16>(&request.authorization_id)?;
        let stream_id = decode_hex::<16>(&request.stream_id)?;
        if request.environment_generation == 0
            || request.shard_generation == 0
            || request.protocol_version != self.protocol_version
            || schema_digest != self.schema_digest
            || request.expires_at <= now
            || request.expires_at - now > MAX_ATTACH_LIFETIME_SECONDS
            || request.harness_key_id != self.harness.key_id()
            || request.authorization_key_id != self.signer.key_id()
            || request.environment_noise_key_id != request.environment_public_key.key_id()
            || self.used.contains(&authorization_id)
            || request.environment_public_key.key_id() != request.environment_noise_key_id
        {
            return Err(LocalSocketError::AttachmentRejected);
        }
        let binding = HandshakeBinding {
            environment_id: request.environment_id.clone(),
            registration_id: request.registration_id.clone(),
            stream_id: request.stream_id.clone(),
            protocol_version: self.protocol_version,
            schema_digest: self.schema_digest,
            authorization_key_id: self.signer.key_id().into(),
            harness_noise_key_id: self.harness.key_id(),
            environment_noise_key_id: request.environment_noise_key_id.clone(),
        };
        binding.encode_prologue()?;
        let authorization = self.signer.sign(AuthorizationClaims {
            authorization_id,
            environment_id: request.environment_id.clone(),
            environment_generation: request.environment_generation,
            shard_generation: request.shard_generation,
            stream_id,
            harness_key_id: self.harness.key_id(),
            protocol_version: self.protocol_version,
            schema_digest: self.schema_digest,
            issued_at: now,
            expires_at: request.expires_at,
        })?;
        self.used.insert(authorization_id);
        Ok(AttachmentGrant {
            binding,
            authorization,
        })
    }
}

fn decode_hex<const N: usize>(value: &str) -> Result<[u8; N], LocalSocketError> {
    if value.len() != N * 2 {
        return Err(LocalSocketError::AttachmentRejected);
    }
    let mut output = [0; N];
    for (index, pair) in value.as_bytes().chunks_exact(2).enumerate() {
        output[index] = (hex_digit(pair[0])? << 4) | hex_digit(pair[1])?;
    }
    Ok(output)
}

fn hex_digit(value: u8) -> Result<u8, LocalSocketError> {
    match value {
        b'0'..=b'9' => Ok(value - b'0'),
        b'a'..=b'f' => Ok(value - b'a' + 10),
        _ => Err(LocalSocketError::AttachmentRejected),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn framing_rejects_zero_and_oversized_before_allocation() {
        let (mut client, mut server) = tokio::io::duplex(64);
        tokio::spawn(async move {
            client.write_u32(0).await.unwrap();
        });
        assert!(matches!(
            read_frame(&mut server).await,
            Err(LocalSocketError::FrameRejected)
        ));

        let (mut client, mut server) = tokio::io::duplex(64);
        tokio::spawn(async move {
            client
                .write_u32((MAX_LOCAL_FRAME_BYTES + 1) as u32)
                .await
                .unwrap();
        });
        assert!(matches!(
            read_frame(&mut server).await,
            Err(LocalSocketError::FrameRejected)
        ));
    }

    #[test]
    fn attachment_is_exact_and_single_use() {
        let harness = NoiseIdentity::from_seed([3; 32]).unwrap();
        let environment = NoiseIdentity::from_seed([4; 32]).unwrap();
        let signer = AuthorizationSigner::from_seed("authorization-v1", [5; 32], 0, 100).unwrap();
        let mut gate = AttachmentGate::new(harness, signer, 1, [7; 32]).unwrap();
        let request = AttachmentRequest {
            request_id: "request-v1".into(),
            environment_id: "environment-v1".into(),
            environment_generation: 3,
            registration_id: "registration-v1".into(),
            shard_generation: 5,
            stream_id: "11".repeat(16),
            protocol_version: 1,
            schema_digest: "07".repeat(32),
            authorization_id: "22".repeat(16),
            expires_at: 12,
            harness_key_id: gate.harness.key_id(),
            authorization_key_id: "authorization-v1".into(),
            environment_noise_key_id: environment.key_id(),
            environment_public_key: environment.public_key(),
        };
        let mut downgrade = request.clone();
        downgrade.protocol_version = 0;
        assert!(matches!(
            gate.authorize(&downgrade, 10),
            Err(LocalSocketError::AttachmentRejected)
        ));
        let mut wrong_harness = request.clone();
        wrong_harness.harness_key_id = "wrong-harness".into();
        assert!(matches!(
            gate.authorize(&wrong_harness, 10),
            Err(LocalSocketError::AttachmentRejected)
        ));
        let grant = gate.authorize(&request, 10).unwrap();
        assert_eq!(grant.binding.protocol_version, 1);
        assert_eq!(grant.binding.schema_digest, [7; 32]);
        assert_eq!(grant.authorization.claims.environment_generation, 3);
        assert!(matches!(
            gate.authorize(&request, 10),
            Err(LocalSocketError::AttachmentRejected)
        ));
    }

    #[test]
    fn private_seed_requires_an_exact_private_regular_file() {
        let path = std::env::temp_dir().join(format!("pwc-harness-seed-{}", std::process::id()));
        std::fs::write(&path, [9; 32]).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o640)).unwrap();
        assert!(matches!(
            read_private_seed(&path),
            Err(LocalSocketError::CredentialRejected)
        ));
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o400)).unwrap();
        assert_eq!(read_private_seed(&path).unwrap(), [9; 32]);
        std::fs::write(&path, [9; 31]).unwrap();
        assert!(matches!(
            read_private_seed(&path),
            Err(LocalSocketError::CredentialRejected)
        ));
        std::fs::remove_file(path).unwrap();
    }
}
