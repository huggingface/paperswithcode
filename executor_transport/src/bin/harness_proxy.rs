use std::collections::HashSet;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use base64::Engine;
use base64::engine::general_purpose::STANDARD;
use pwc_persistent_executor_transport::local_socket::{
    AttachmentGate, AttachmentRequest, LocalSocketError, PeerMessageDecoder, encode_peer_message,
    prepare_listener_path, read_frame, read_private_seed, validate_peer, validate_socket_path,
    write_frame,
};
use pwc_persistent_executor_transport::noise::{InitiatorHandshake, NoiseIdentity, NoiseTransport};
use pwc_persistent_executor_transport::protocol::{
    AuthorizationSigner, FrameKind, RelayFrame, SequenceReceiver,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use tokio::net::{UnixListener, UnixStream};
use tokio::sync::Mutex;
use zeroize::Zeroizing;

type ProxyError = Box<dyn std::error::Error + Send + Sync>;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct HarnessConfig {
    allowed_backend_uid: u32,
    expected_rendezvous_uid: u32,
    protocol_version: u32,
    schema_digest: String,
    authorization_key_id: String,
    authorization_not_before: u64,
    authorization_not_after: u64,
}

#[derive(Serialize)]
struct PeerAttach<'a> {
    kind: &'static str,
    environment_id: &'a str,
    environment_generation: u64,
    registration_id: &'a str,
    stream_id: &'a str,
    binding: &'a pwc_persistent_executor_transport::protocol::HandshakeBinding,
    harness_public_key: pwc_persistent_executor_transport::noise::NoisePublicKey,
    handshake: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PeerAttached {
    kind: String,
    stream_id: String,
    handshake: String,
}

struct EncryptedPeer {
    transport: NoiseTransport,
    send_sequence: u64,
    send_message_id: u64,
    receiver: SequenceReceiver,
    decoder: PeerMessageDecoder,
}

impl EncryptedPeer {
    fn new(transport: NoiseTransport) -> Self {
        Self {
            transport,
            send_sequence: 0,
            send_message_id: 1,
            receiver: SequenceReceiver::new(),
            decoder: PeerMessageDecoder::new(),
        }
    }

    async fn send(&mut self, stream: &mut UnixStream, message: &[u8]) -> Result<(), ProxyError> {
        let message_id = self.send_message_id;
        self.send_message_id = self
            .send_message_id
            .checked_add(1)
            .ok_or("peer message identity exhausted")?;
        for record in encode_peer_message(message_id, message)? {
            let frame = RelayFrame::new(FrameKind::Data, 1, 0, self.send_sequence, 0, record)?;
            self.send_sequence = self
                .send_sequence
                .checked_add(1)
                .ok_or("harness sequence exhausted")?;
            write_frame(stream, &self.transport.encrypt(&frame.encode())?).await?;
        }
        Ok(())
    }

    fn receive(&mut self, ciphertext: &[u8]) -> Result<Vec<Vec<u8>>, ProxyError> {
        let frame = RelayFrame::decode(&self.transport.decrypt(ciphertext)?)?;
        if frame.kind() != FrameKind::Data || frame.stream_id() != 1 || frame.operation_id() != 0 {
            return Err(LocalSocketError::FrameRejected.into());
        }
        let mut messages = Vec::new();
        for ordered in self.receiver.push(frame)? {
            if let Some(message) = self.decoder.push(ordered.payload())? {
                messages.push(message);
            }
        }
        Ok(messages)
    }
}

#[tokio::main]
async fn main() {
    if let Err(error) = run().await {
        eprintln!("harness proxy failed: {error}");
        std::process::exit(1);
    }
}

async fn run() -> Result<(), ProxyError> {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    match arguments.as_slice() {
        [flag] if flag == "--self-test" => {
            println!(
                "{}",
                json!({
                    "listener": "unix",
                    "peer": "unix",
                    "plaintext_scope": "protected_local_socket",
                    "authorization": "single_use_generation_bound",
                    "private_keys": ["harness_noise", "authorization_signing"],
                })
            );
            Ok(())
        }
        [socket_flag, socket, peer_flag, peer, config_flag, config, harness_flag, harness, authorization_flag, authorization]
            if socket_flag == "--unix-socket"
                && peer_flag == "--rendezvous-socket"
                && config_flag == "--config"
                && harness_flag == "--harness-key-file"
                && authorization_flag == "--authorization-key-file" =>
        {
            serve(
                PathBuf::from(socket),
                PathBuf::from(peer),
                PathBuf::from(config),
                PathBuf::from(harness),
                PathBuf::from(authorization),
            )
            .await
        }
        _ => Err("usage: harness_proxy --self-test | --unix-socket PATH --rendezvous-socket PATH --config PATH --harness-key-file PATH --authorization-key-file PATH".into()),
    }
}

async fn serve(
    socket_path: PathBuf,
    peer_path: PathBuf,
    config_path: PathBuf,
    harness_key_path: PathBuf,
    authorization_key_path: PathBuf,
) -> Result<(), ProxyError> {
    require_systemd_credential(&harness_key_path)?;
    require_systemd_credential(&authorization_key_path)?;
    let config: HarnessConfig = serde_json::from_slice(&tokio::fs::read(config_path).await?)?;
    let schema_digest = decode_digest(&config.schema_digest)?;
    let harness_seed = Zeroizing::new(read_private_seed(&harness_key_path)?);
    let authorization_seed = Zeroizing::new(read_private_seed(&authorization_key_path)?);
    if harness_seed == authorization_seed {
        return Err(LocalSocketError::CredentialRejected.into());
    }
    let signer = AuthorizationSigner::from_seed(
        &config.authorization_key_id,
        *authorization_seed,
        config.authorization_not_before,
        config.authorization_not_after,
    )?;
    let harness = NoiseIdentity::from_seed(*harness_seed)?;
    let gate = Arc::new(Mutex::new(AttachmentGate::new(
        harness,
        signer,
        config.protocol_version,
        schema_digest,
    )?));
    validate_socket_path(&peer_path)?;
    prepare_listener_path(&socket_path)?;
    let listener = UnixListener::bind(&socket_path)?;
    std::fs::set_permissions(&socket_path, std::fs::Permissions::from_mode(0o660))?;
    loop {
        let (stream, _) = listener.accept().await?;
        if validate_peer(&stream, config.allowed_backend_uid).is_err() {
            continue;
        }
        let peer_path = peer_path.clone();
        let gate = Arc::clone(&gate);
        let expected_rendezvous_uid = config.expected_rendezvous_uid;
        tokio::spawn(async move {
            if let Err(error) = handle(stream, peer_path, expected_rendezvous_uid, gate).await {
                eprintln!("harness proxy connection failed: {error}");
            }
        });
    }
}

fn require_systemd_credential(path: &Path) -> Result<(), LocalSocketError> {
    let directory = std::env::var_os("CREDENTIALS_DIRECTORY")
        .map(PathBuf::from)
        .ok_or(LocalSocketError::CredentialRejected)?;
    let directory =
        std::fs::canonicalize(directory).map_err(|_| LocalSocketError::CredentialRejected)?;
    let parent = path
        .parent()
        .and_then(|value| std::fs::canonicalize(value).ok())
        .ok_or(LocalSocketError::CredentialRejected)?;
    if parent != directory {
        return Err(LocalSocketError::CredentialRejected);
    }
    Ok(())
}

async fn handle(
    mut local: UnixStream,
    peer_path: PathBuf,
    expected_rendezvous_uid: u32,
    gate: Arc<Mutex<AttachmentGate>>,
) -> Result<(), ProxyError> {
    let attachment_frame = read_frame(&mut local).await?;
    let attachment = parse_attachment(&attachment_frame)?;
    let now = unix_seconds()?;
    let mut locked_gate = gate.lock().await;
    let grant = locked_gate.authorize(&attachment, now)?;
    let prologue = grant.binding.encode_prologue()?;
    let authorization = serde_json::to_vec(&grant.authorization)?;
    let (pending, handshake) = InitiatorHandshake::start(
        locked_gate.harness(),
        &attachment.environment_public_key,
        &prologue,
        &authorization,
    )?;
    let harness_public_key = locked_gate.harness().public_key();
    let harness_key_id = locked_gate.harness().key_id();
    let authorization_key_id = locked_gate.authorization_key_id().to_owned();
    drop(locked_gate);

    let mut peer = UnixStream::connect(peer_path).await?;
    validate_peer(&peer, expected_rendezvous_uid)?;
    write_frame(
        &mut peer,
        &serde_json::to_vec(&PeerAttach {
            kind: "peer_attach",
            environment_id: &attachment.environment_id,
            environment_generation: attachment.environment_generation,
            registration_id: &attachment.registration_id,
            stream_id: &attachment.stream_id,
            binding: &grant.binding,
            harness_public_key,
            handshake: STANDARD.encode(handshake),
        })?,
    )
    .await?;
    let response: PeerAttached = serde_json::from_slice(&read_frame(&mut peer).await?)?;
    if response.kind != "peer_attached" || response.stream_id != attachment.stream_id {
        return Err(LocalSocketError::AttachmentRejected.into());
    }
    let transport = pending.finish(&STANDARD.decode(response.handshake)?)?;
    let mut encrypted_peer = EncryptedPeer::new(transport);
    write_frame(
        &mut local,
        &serde_json::to_vec(&json!({
            "kind": "attached",
            "request_id": attachment.request_id,
            "stream_id": attachment.stream_id,
            "harness_key_id": harness_key_id,
            "authorization_key_id": authorization_key_id,
        }))?,
    )
    .await?;

    let mut open_streams = HashSet::new();
    loop {
        tokio::select! {
            frame = read_frame(&mut local) => {
                let frame = frame?;
                validate_local_relay_frame(&frame, &mut open_streams)?;
                encrypted_peer.send(&mut peer, &frame).await?;
            }
            frame = read_frame(&mut peer) => {
                for plaintext in encrypted_peer.receive(&frame?)? {
                    validate_peer_relay_frame(&plaintext, &mut open_streams)?;
                    write_frame(&mut local, &plaintext).await?;
                }
            }
        }
    }
}

fn parse_attachment(frame: &[u8]) -> Result<AttachmentRequest, ProxyError> {
    let mut value: Value = serde_json::from_slice(frame)?;
    let object = value
        .as_object_mut()
        .ok_or(LocalSocketError::AttachmentRejected)?;
    if object.remove("kind") != Some(Value::String("attach".into())) {
        return Err(LocalSocketError::AttachmentRejected.into());
    }
    Ok(serde_json::from_value(value)?)
}

fn validate_local_relay_frame(
    frame: &[u8],
    open_streams: &mut HashSet<String>,
) -> Result<(), ProxyError> {
    let value: Value = serde_json::from_slice(frame)?;
    let kind = value.get("kind").and_then(Value::as_str);
    let stream_id = value
        .get("stream_id")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty() && value.len() <= 128)
        .ok_or(LocalSocketError::FrameRejected)?;
    match kind {
        Some("open") if open_streams.insert(stream_id.into()) => Ok(()),
        Some("data") if open_streams.contains(stream_id) => {
            let payload = value
                .get("payload")
                .and_then(Value::as_str)
                .ok_or(LocalSocketError::FrameRejected)?;
            let decoded = STANDARD.decode(payload)?;
            if decoded.is_empty()
                || decoded.len()
                    > pwc_persistent_executor_transport::local_socket::MAX_LOCAL_FRAME_BYTES
            {
                return Err(LocalSocketError::FrameRejected.into());
            }
            Ok(())
        }
        Some("close") if open_streams.remove(stream_id) => Ok(()),
        _ => Err(LocalSocketError::FrameRejected.into()),
    }
}

fn validate_peer_relay_frame(
    frame: &[u8],
    open_streams: &mut HashSet<String>,
) -> Result<(), ProxyError> {
    let value: Value = serde_json::from_slice(frame)?;
    let stream_id = value
        .get("stream_id")
        .and_then(Value::as_str)
        .ok_or(LocalSocketError::FrameRejected)?;
    match value.get("kind").and_then(Value::as_str) {
        Some("opened") if open_streams.contains(stream_id) => Ok(()),
        Some("data") if open_streams.contains(stream_id) => Ok(()),
        Some("closed") if open_streams.remove(stream_id) => Ok(()),
        _ => Err(LocalSocketError::FrameRejected.into()),
    }
}

fn decode_digest(value: &str) -> Result<[u8; 32], LocalSocketError> {
    if value.len() != 64 {
        return Err(LocalSocketError::AttachmentRejected);
    }
    let mut digest = [0; 32];
    for (index, pair) in value.as_bytes().chunks_exact(2).enumerate() {
        digest[index] = (hex(pair[0])? << 4) | hex(pair[1])?;
    }
    Ok(digest)
}

fn hex(value: u8) -> Result<u8, LocalSocketError> {
    match value {
        b'0'..=b'9' => Ok(value - b'0'),
        b'a'..=b'f' => Ok(value - b'a' + 10),
        _ => Err(LocalSocketError::AttachmentRejected),
    }
}

fn unix_seconds() -> Result<u64, ProxyError> {
    Ok(SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs())
}

#[allow(dead_code)]
fn _path_is_protected(path: &Path) -> bool {
    validate_socket_path(path).is_ok()
}
