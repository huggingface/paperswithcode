use std::collections::HashSet;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use base64::Engine;
use base64::engine::general_purpose::STANDARD;
use pwc_persistent_executor_transport::local_socket::{
    AttachmentGate, AttachmentRequest, LocalSocketError, PeerMessageDecoder, encode_peer_message,
    prepare_listener_path, read_frame, read_private_seed, validate_peer, validate_socket_path,
    write_frame,
};
use pwc_persistent_executor_transport::noise::{InitiatorHandshake, NoiseIdentity, NoiseTransport};
use pwc_persistent_executor_transport::protocol::{
    AuthorizationSigner, FrameKind, HandshakeBinding, RelayFrame, ReplayBuffer, SequenceReceiver,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use tokio::net::{UnixListener, UnixStream};
use tokio::sync::Mutex;
use uuid::Uuid;
use zeroize::Zeroizing;

type ProxyError = Box<dyn std::error::Error + Send + Sync>;
const SERVICE_DRAIN_SECONDS: u64 = 240;

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
    connection_id: Uuid,
    handshake: String,
}

#[derive(Serialize)]
struct PeerResume<'a> {
    kind: &'static str,
    environment_id: &'a str,
    environment_generation: u64,
    registration_id: &'a str,
    stream_id: &'a str,
    connection_id: Uuid,
    receiver_next: u64,
    harness_public_key: pwc_persistent_executor_transport::noise::NoisePublicKey,
    handshake: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PeerResumed {
    kind: String,
    stream_id: String,
    connection_id: Uuid,
    receiver_next: u64,
    handshake: String,
}

#[derive(Serialize)]
struct PeerResumeClaims<'a> {
    kind: &'static str,
    connection_id: Uuid,
    stream_id: &'a str,
    receiver_next: u64,
}

#[derive(Serialize)]
struct PeerDetach<'a> {
    kind: &'static str,
    environment_id: &'a str,
    environment_generation: u64,
    registration_id: &'a str,
    connection_id: Uuid,
}

struct EncryptedPeer {
    transport: NoiseTransport,
    send_message_id: u64,
    replay: ReplayBuffer,
    receiver: SequenceReceiver,
    decoder: PeerMessageDecoder,
    last_ack_sent: u64,
}

struct PeerDelivery {
    plaintexts: Vec<Vec<u8>>,
    acknowledgements: Vec<Vec<u8>>,
}

impl EncryptedPeer {
    fn new(transport: NoiseTransport) -> Self {
        Self {
            transport,
            send_message_id: 1,
            replay: ReplayBuffer::new(),
            receiver: SequenceReceiver::new(),
            decoder: PeerMessageDecoder::new(),
            last_ack_sent: 0,
        }
    }

    fn encode_message(&mut self, message: &[u8]) -> Result<Vec<Vec<u8>>, ProxyError> {
        let message_id = self.send_message_id;
        self.send_message_id = self
            .send_message_id
            .checked_add(1)
            .ok_or("peer message identity exhausted")?;
        let mut output = Vec::new();
        for record in encode_peer_message(message_id, message)? {
            let frame = RelayFrame::new(
                FrameKind::Data,
                1,
                0,
                self.replay.next_sequence(),
                self.receiver.next_sequence(),
                record,
            )?;
            self.replay.record(frame.clone())?;
            output.push(self.transport.encrypt(&frame.encode())?);
        }
        Ok(output)
    }

    fn receive(&mut self, ciphertext: &[u8]) -> Result<PeerDelivery, ProxyError> {
        let frame = RelayFrame::decode(&self.transport.decrypt(ciphertext)?)?;
        if !matches!(frame.kind(), FrameKind::Data | FrameKind::Ack)
            || frame.stream_id() != 1
            || frame.operation_id() != 0
        {
            return Err(LocalSocketError::FrameRejected.into());
        }
        self.replay.acknowledge(frame.ack_next())?;
        if frame.kind() == FrameKind::Ack {
            return Ok(PeerDelivery {
                plaintexts: Vec::new(),
                acknowledgements: Vec::new(),
            });
        }
        let mut messages = Vec::new();
        for ordered in self.receiver.push(frame)? {
            if ordered.kind() == FrameKind::Data
                && let Some(message) = self.decoder.push(ordered.payload())?
            {
                messages.push(message)
            }
        }
        let acknowledgements = self.encode_acknowledgement()?;
        Ok(PeerDelivery {
            plaintexts: messages,
            acknowledgements,
        })
    }

    fn encode_acknowledgement(&mut self) -> Result<Vec<Vec<u8>>, ProxyError> {
        let ack_next = self.receiver.next_sequence();
        if ack_next == self.last_ack_sent {
            return Ok(Vec::new());
        }
        let frame = RelayFrame::new(FrameKind::Ack, 1, 0, 0, ack_next, Vec::new())?;
        self.last_ack_sent = ack_next;
        Ok(vec![self.transport.encrypt(&frame.encode())?])
    }

    fn receiver_next(&self) -> u64 {
        self.receiver.next_sequence()
    }

    fn resume(
        &mut self,
        transport: NoiseTransport,
        peer_receiver_next: u64,
    ) -> Result<Vec<Vec<u8>>, ProxyError> {
        self.replay.acknowledge(peer_receiver_next)?;
        self.transport = transport;
        let frames = self
            .replay
            .frames_from(peer_receiver_next)?
            .into_iter()
            .cloned()
            .collect::<Vec<_>>();
        frames
            .into_iter()
            .map(|frame| self.transport.encrypt(&frame.encode()).map_err(Into::into))
            .collect()
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
    let mut terminate = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    loop {
        let accepted = tokio::select! {
            accepted = listener.accept() => accepted,
            _ = terminate.recv() => break,
        };
        let (stream, _) = accepted?;
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
    drop(listener);
    std::fs::remove_file(&socket_path).ok();
    tokio::time::sleep(std::time::Duration::from_secs(SERVICE_DRAIN_SECONDS)).await;
    Ok(())
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
    let binding = grant.binding.clone();
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

    let mut peer = UnixStream::connect(&peer_path).await?;
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
    let connection_id = response.connection_id;
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
                let frame = match frame {
                    Ok(frame) => frame,
                    Err(_) => {
                        let _ = detach_peer(
                            &peer_path,
                            expected_rendezvous_uid,
                            &binding,
                            attachment.environment_generation,
                            connection_id,
                        ).await;
                        break;
                    }
                };
                validate_local_relay_frame(&frame, &mut open_streams)?;
                let ciphertexts = encrypted_peer.encode_message(&frame)?;
                for ciphertext in ciphertexts {
                    if write_frame(&mut peer, &ciphertext).await.is_err() {
                        peer = resume_peer(
                            &peer_path,
                            expected_rendezvous_uid,
                            &gate,
                            &binding,
                            &attachment.environment_public_key,
                            attachment.environment_generation,
                            connection_id,
                            &mut encrypted_peer,
                        ).await?;
                        break;
                    }
                }
            }
            frame = read_frame(&mut peer) => {
                let frame = match frame {
                    Ok(frame) => frame,
                    Err(_) => {
                        peer = resume_peer(
                            &peer_path,
                            expected_rendezvous_uid,
                            &gate,
                            &binding,
                            &attachment.environment_public_key,
                            attachment.environment_generation,
                            connection_id,
                            &mut encrypted_peer,
                        ).await?;
                        continue;
                    }
                };
                let delivery = encrypted_peer.receive(&frame)?;
                for plaintext in delivery.plaintexts {
                    validate_peer_relay_frame(&plaintext, &mut open_streams)?;
                    write_frame(&mut local, &plaintext).await?;
                }
                for acknowledgement in delivery.acknowledgements {
                    if write_frame(&mut peer, &acknowledgement).await.is_err() {
                        peer = resume_peer(
                            &peer_path,
                            expected_rendezvous_uid,
                            &gate,
                            &binding,
                            &attachment.environment_public_key,
                            attachment.environment_generation,
                            connection_id,
                            &mut encrypted_peer,
                        ).await?;
                        break;
                    }
                }
            }
        }
    }
    Ok(())
}

async fn detach_peer(
    peer_path: &Path,
    expected_rendezvous_uid: u32,
    binding: &HandshakeBinding,
    environment_generation: u64,
    connection_id: Uuid,
) -> Result<(), ProxyError> {
    let mut peer = UnixStream::connect(peer_path).await?;
    validate_peer(&peer, expected_rendezvous_uid)?;
    write_frame(
        &mut peer,
        &serde_json::to_vec(&PeerDetach {
            kind: "peer_detach",
            environment_id: &binding.environment_id,
            environment_generation,
            registration_id: &binding.registration_id,
            connection_id,
        })?,
    )
    .await?;
    Ok(())
}

#[allow(clippy::too_many_arguments)]
async fn resume_peer(
    peer_path: &Path,
    expected_rendezvous_uid: u32,
    gate: &Arc<Mutex<AttachmentGate>>,
    binding: &HandshakeBinding,
    environment_public_key: &pwc_persistent_executor_transport::noise::NoisePublicKey,
    environment_generation: u64,
    connection_id: Uuid,
    encrypted_peer: &mut EncryptedPeer,
) -> Result<UnixStream, ProxyError> {
    let deadline = Instant::now() + Duration::from_secs(30);
    let mut delay = Duration::from_millis(50);
    loop {
        if Instant::now() >= deadline {
            return Err("executor peer resume expired".into());
        }
        let receiver_next = encrypted_peer.receiver_next();
        let claims = serde_json::to_vec(&PeerResumeClaims {
            kind: "resume",
            connection_id,
            stream_id: &binding.stream_id,
            receiver_next,
        })?;
        let locked_gate = gate.lock().await;
        let (pending, handshake) = InitiatorHandshake::start(
            locked_gate.harness(),
            environment_public_key,
            &binding.encode_prologue()?,
            &claims,
        )?;
        let harness_public_key = locked_gate.harness().public_key();
        drop(locked_gate);
        let attempt = async {
            let mut peer = UnixStream::connect(peer_path).await?;
            validate_peer(&peer, expected_rendezvous_uid)?;
            write_frame(
                &mut peer,
                &serde_json::to_vec(&PeerResume {
                    kind: "peer_resume",
                    environment_id: &binding.environment_id,
                    environment_generation,
                    registration_id: &binding.registration_id,
                    stream_id: &binding.stream_id,
                    connection_id,
                    receiver_next,
                    harness_public_key,
                    handshake: STANDARD.encode(handshake),
                })?,
            )
            .await?;
            let response: PeerResumed = serde_json::from_slice(&read_frame(&mut peer).await?)?;
            if response.kind != "peer_resumed"
                || response.stream_id != binding.stream_id
                || response.connection_id != connection_id
            {
                return Err(LocalSocketError::AttachmentRejected.into());
            }
            let transport = pending.finish(&STANDARD.decode(response.handshake)?)?;
            let replay = encrypted_peer.resume(transport, response.receiver_next)?;
            for ciphertext in replay {
                write_frame(&mut peer, &ciphertext).await?;
            }
            Ok::<UnixStream, ProxyError>(peer)
        };
        if let Ok(Ok(peer)) = tokio::time::timeout(Duration::from_secs(2), attempt).await {
            return Ok(peer);
        }
        tokio::time::sleep(delay).await;
        delay = (delay * 2).min(Duration::from_secs(2));
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

#[cfg(test)]
mod tests {
    use super::*;
    use pwc_persistent_executor_transport::noise::{PendingResponderHandshake, prologue};

    #[test]
    fn harness_resume_rekeys_and_replays_unacknowledged_frames() {
        let harness = NoiseIdentity::from_seed([3; 32]).expect("harness identity");
        let environment = NoiseIdentity::from_seed([4; 32]).expect("environment identity");
        let transcript = prologue("environment-v1", "registration-v1", "peer-v1");
        let (pending, request) = InitiatorHandshake::start(
            &harness,
            &environment.public_key(),
            &transcript,
            b"authorization",
        )
        .expect("initial request");
        let responder =
            PendingResponderHandshake::read_request(&environment, &transcript, &request)
                .expect("initial response");
        let (mut environment_transport, response) =
            responder.complete().expect("initial completion");
        let mut peer = EncryptedPeer::new(pending.finish(&response).expect("initial transport"));
        let original = peer
            .encode_message(br#"{"kind":"open","stream_id":"operation-1"}"#)
            .expect("original frame");
        let original = RelayFrame::decode(
            &environment_transport
                .decrypt(&original[0])
                .expect("original decrypt"),
        )
        .expect("original relay frame");
        assert_eq!(original.sequence(), 0);
        let acknowledgement =
            RelayFrame::new(FrameKind::Ack, 1, 0, 0, 1, Vec::new()).expect("acknowledgement frame");
        let acknowledgement = environment_transport
            .encrypt(&acknowledgement.encode())
            .expect("encrypted acknowledgement");
        let delivered = peer
            .receive(&acknowledgement)
            .expect("acknowledgement accepted");
        assert!(delivered.plaintexts.is_empty());
        assert!(delivered.acknowledgements.is_empty());
        assert!(
            peer.replay
                .frames_from(1)
                .expect("acknowledged replay position")
                .is_empty()
        );

        let original = peer
            .encode_message(br#"{"kind":"open","stream_id":"operation-2"}"#)
            .expect("second original frame");
        let original = RelayFrame::decode(
            &environment_transport
                .decrypt(&original[0])
                .expect("second original decrypt"),
        )
        .expect("second original relay frame");

        let (pending, request) =
            InitiatorHandshake::start(&harness, &environment.public_key(), &transcript, b"resume")
                .expect("resume request");
        let responder =
            PendingResponderHandshake::read_request(&environment, &transcript, &request)
                .expect("resume response");
        let (mut resumed_environment, response) = responder.complete().expect("resume completion");
        let replay = peer
            .resume(pending.finish(&response).expect("resumed transport"), 1)
            .expect("replay");
        assert_eq!(replay.len(), 1);
        let replay = RelayFrame::decode(
            &resumed_environment
                .decrypt(&replay[0])
                .expect("replay decrypt"),
        )
        .expect("replay relay frame");
        assert_eq!(replay.sequence(), 1);
        assert_eq!(replay.payload(), original.payload());
    }
}
