use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use base64::Engine;
use base64::engine::general_purpose::{STANDARD, URL_SAFE};
use futures_util::{SinkExt, StreamExt};
use pwc_persistent_executor_transport::local_socket::{
    LocalSocketError, PeerMessageDecoder, encode_peer_message,
};
use pwc_persistent_executor_transport::noise::{
    InitiatorHandshake, NoiseIdentity, NoisePublicKey, NoiseTransport, PendingResponderHandshake,
    prologue,
};
use pwc_persistent_executor_transport::protocol::{
    FrameKind, HandshakeBinding, KeyRing, RelayFrame, ReplayBuffer, SequenceReceiver,
    SignedAuthorization, VerificationKey,
};
use pwc_persistent_executor_transport::scheduler::ReconnectBackoff;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::UnixStream;
use tokio::net::unix::OwnedWriteHalf;
use tokio::process::Command;
use tokio::sync::mpsc;
use tokio::time::{interval, timeout};
use tokio_tungstenite::connect_async_with_config;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::tungstenite::protocol::WebSocketConfig;
use url::Url;
use uuid::Uuid;

const ROUTE_PREFIX: &str = "/v1/generations/";
const ROUTE_SUFFIX: &str = "/environment";
const PRODUCTION_HOST: &str = "chat-executor.paperswithcode.co";
const STAGING_HOST: &str = "chat-executor-staging.paperswithcode.co";
const HEARTBEAT: Duration = Duration::from_secs(5);
const RESPONSE_DEADLINE: Duration = Duration::from_secs(15);
const EXECUTOR_SOCKET: &str = "/run/pwc-chat-executor/executor.sock";
const MAX_OUTER_MESSAGE_BYTES: usize = 128 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RegistrationResponse {
    registration_id: String,
    environment_id: String,
    responder_public_key: NoisePublicKey,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AuthorizationKeyConfig {
    key_id: String,
    public_key: String,
    not_before: u64,
    not_after: u64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AuthorizationKeysConfig {
    current: AuthorizationKeyConfig,
    previous: Option<AuthorizationKeyConfig>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PeerAttach {
    kind: String,
    environment_id: String,
    environment_generation: u64,
    registration_id: String,
    stream_id: String,
    binding: HandshakeBinding,
    harness_public_key: NoisePublicKey,
    handshake: String,
}

#[derive(Serialize)]
struct PeerAttached<'a> {
    kind: &'static str,
    stream_id: &'a str,
    connection_id: Uuid,
    handshake: String,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct PeerResume {
    kind: String,
    environment_id: String,
    environment_generation: u64,
    registration_id: String,
    stream_id: String,
    connection_id: Uuid,
    receiver_next: u64,
    harness_public_key: NoisePublicKey,
    handshake: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
struct PeerResumeClaims {
    kind: String,
    connection_id: Uuid,
    stream_id: String,
    receiver_next: u64,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct PeerResumed {
    kind: String,
    stream_id: String,
    connection_id: Uuid,
    receiver_next: u64,
    handshake: String,
}

struct PeerEndpoint {
    connection_id: Uuid,
    environment_generation: u64,
    binding: HandshakeBinding,
    harness_public_key: NoisePublicKey,
    transport: NoiseTransport,
    send_message_id: u64,
    replay: ReplayBuffer,
    receiver: SequenceReceiver,
    decoder: PeerMessageDecoder,
    last_ack_sent: u64,
    streams: HashMap<String, OwnedWriteHalf>,
    daemon_events: mpsc::Sender<DaemonEvent>,
    daemon_path: PathBuf,
}

struct DaemonEvent {
    connection_id: Uuid,
    stream_id: String,
    payload: Vec<u8>,
    closed: bool,
}

struct EnvironmentPeerState {
    endpoint: Option<PeerEndpoint>,
    daemon_events: mpsc::Sender<DaemonEvent>,
    daemon_receiver: mpsc::Receiver<DaemonEvent>,
}

impl EnvironmentPeerState {
    fn new() -> Self {
        let (daemon_events, daemon_receiver) = mpsc::channel(4);
        Self {
            endpoint: None,
            daemon_events,
            daemon_receiver,
        }
    }
}

#[tokio::main]
async fn main() {
    if let Err(error) = run().await {
        eprintln!("environment failed: {error}");
        std::process::exit(1);
    }
}

async fn run() -> Result<(), Box<dyn std::error::Error>> {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    match arguments.as_slice() {
        [flag] if flag == "--self-test" => {
            // Exercise the same default-provider selection as the WSS connector.
            let _tls_config = rustls::ClientConfig::builder()
                .with_root_certificates(rustls::RootCertStore::empty())
                .with_no_client_auth();
            let identity = NoiseIdentity::generate()?;
            println!(
                "{}",
                json!({
                    "protocol": "Noise_hybridIK_X25519+MLKEM768_AESGCM_SHA256",
                    "public_noise_key_id": identity.key_id(),
                })
            );
            Ok(())
        }
        [flag, value] if flag == "--validate-url" => {
            validate_url(value)?;
            Ok(())
        }
        [flag, url, admission_flag, admission_path, authorization_flag, authorization_name]
            if flag == "--connect"
                && admission_flag == "--admission-file"
                && authorization_flag == "--authorization-env" =>
        {
            launch(
                url,
                AdmissionSource::File(PathBuf::from(admission_path)),
                authorization_name,
            )
            .await
        }
        [flag, url, admission_flag, admission_name, authorization_flag, authorization_name]
            if flag == "--connect"
                && admission_flag == "--admission-env"
                && admission_name == "PWC_CHAT_EXECUTOR_ADMISSION"
                && authorization_flag == "--authorization-env" =>
        {
            launch(url, AdmissionSource::Environment, authorization_name).await
        }
        _ => Err("usage: environment --self-test | --validate-url URL | --connect URL (--admission-file PATH | --admission-env PWC_CHAT_EXECUTOR_ADMISSION) --authorization-env NAME".into()),
    }
}

fn validate_url(value: &str) -> Result<Url, &'static str> {
    let url = Url::parse(value).map_err(|_| "rendezvous URL rejected")?;
    if url.scheme() != "wss"
        || !matches!(url.host_str(), Some(PRODUCTION_HOST) | Some(STAGING_HOST))
        || url.port().is_some()
        || !valid_generation_route(url.path())
        || url.query().is_some()
        || url.fragment().is_some()
        || !url.username().is_empty()
        || url.password().is_some()
    {
        return Err("rendezvous URL rejected");
    }
    Ok(url)
}

fn valid_generation_route(path: &str) -> bool {
    path.strip_prefix(ROUTE_PREFIX)
        .and_then(|value| value.strip_suffix(ROUTE_SUFFIX))
        .is_some_and(|generation| {
            !generation.is_empty()
                && generation.len() <= 20
                && generation.bytes().all(|byte| byte.is_ascii_digit())
                && generation != "0"
                && !generation.starts_with('0')
        })
}

enum AdmissionSource {
    File(PathBuf),
    Environment,
}

async fn launch(
    url: &str,
    source: AdmissionSource,
    authorization_name: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let admission = match source {
        AdmissionSource::File(path) => tokio::fs::read(path).await?,
        AdmissionSource::Environment => {
            URL_SAFE.decode(std::env::var("PWC_CHAT_EXECUTOR_ADMISSION")?)?
        }
    };
    let authorization_keys = authorization_keys(authorization_name)?;
    if admission.is_empty() || admission.len() > 2_048 {
        return Err("admission frame rejected".into());
    }
    let mut daemon = Command::new("python")
        .args(["-m", "backend.chat_sandbox_worker.executor_daemon"])
        .env_remove("PWC_CHAT_EXECUTOR_ADMISSION")
        .env_remove(authorization_name)
        .env("PWC_CHAT_EXECUTOR_REMOTE_MODE", "1")
        .kill_on_drop(true)
        .spawn()?;
    let identity = NoiseIdentity::generate()?;
    let mut peer_state = EnvironmentPeerState::new();
    let connection = async {
        wait_for_daemon_socket(Path::new(EXECUTOR_SOCKET)).await?;
        maintain_connection(
            url,
            admission,
            &identity,
            &authorization_keys,
            &mut peer_state,
        )
        .await
    };
    let result = tokio::select! {
        result = connection => result,
        status = daemon.wait() => Err(format!("executor daemon exited: {}", status?).into()),
    };
    let _ = daemon.kill().await;
    result
}

async fn wait_for_daemon_socket(path: &Path) -> Result<(), Box<dyn std::error::Error>> {
    timeout(Duration::from_secs(15), async {
        loop {
            match UnixStream::connect(path).await {
                Ok(stream) => {
                    drop(stream);
                    return Ok::<(), std::io::Error>(());
                }
                Err(error)
                    if matches!(
                        error.kind(),
                        std::io::ErrorKind::NotFound | std::io::ErrorKind::ConnectionRefused
                    ) =>
                {
                    tokio::time::sleep(Duration::from_millis(10)).await;
                }
                Err(error) => return Err(error),
            }
        }
    })
    .await
    .map_err(|_| "executor daemon readiness timed out")??;
    Ok(())
}

async fn maintain_connection(
    url: &str,
    admission: Vec<u8>,
    identity: &NoiseIdentity,
    authorization_keys: &KeyRing,
    peer_state: &mut EnvironmentPeerState,
) -> Result<(), Box<dyn std::error::Error>> {
    let mut next_admission = admission;
    let mut backoff = ReconnectBackoff::new();
    let mut recovery_attempts = 0_u8;
    loop {
        let connected_at = Instant::now();
        match connect(
            url,
            &next_admission,
            identity,
            authorization_keys,
            peer_state,
        )
        .await
        {
            Ok(reconnect) => {
                recovery_attempts = 0;
                backoff.connected(0);
                backoff.disconnected(connected_at.elapsed().as_millis() as u64);
                next_admission = reconnect;
                let entropy = u64::from_be_bytes(
                    *Uuid::new_v4()
                        .as_bytes()
                        .first_chunk()
                        .expect("UUID is 16 bytes"),
                );
                tokio::time::sleep(Duration::from_millis(backoff.next_delay_ms(entropy))).await;
            }
            Err(error) => {
                recovery_attempts += 1;
                if recovery_attempts > 3 {
                    return Err(error);
                }
                let entropy = u64::from_be_bytes(
                    *Uuid::new_v4()
                        .as_bytes()
                        .first_chunk()
                        .expect("UUID is 16 bytes"),
                );
                tokio::time::sleep(Duration::from_millis(backoff.next_delay_ms(entropy))).await;
            }
        }
    }
}

async fn connect(
    url: &str,
    admission: &[u8],
    identity: &NoiseIdentity,
    authorization_keys: &KeyRing,
    peer_state: &mut EnvironmentPeerState,
) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
    let url = validate_url(url)?;
    let (mut socket, _) =
        connect_async_with_config(url.as_str(), Some(websocket_config()), false).await?;
    socket
        .send(Message::Binary(admission.to_vec().into()))
        .await?;
    socket
        .send(Message::Text(
            serde_json::to_string(&identity.public_key())?.into(),
        ))
        .await?;
    let registration: RegistrationResponse = match timeout(RESPONSE_DEADLINE, socket.next()).await {
        Ok(Some(Ok(Message::Text(response)))) => serde_json::from_str(&response)?,
        _ => return Err("rendezvous registration rejected".into()),
    };
    let transcript = prologue(
        &registration.environment_id,
        &registration.registration_id,
        "environment",
    );
    let (pending, request) = InitiatorHandshake::start(
        identity,
        &registration.responder_public_key,
        &transcript,
        &[],
    )?;
    socket.send(Message::Binary(request.into())).await?;
    let response = match timeout(RESPONSE_DEADLINE, socket.next()).await {
        Ok(Some(Ok(Message::Binary(response)))) => response,
        _ => return Err("rendezvous handshake rejected".into()),
    };
    let mut transport = pending.finish(&response)?;
    let (durable_registration_id, environment_generation, shard_generation) =
        match timeout(RESPONSE_DEADLINE, socket.next()).await {
            Ok(Some(Ok(Message::Binary(ciphertext)))) => {
                let acknowledgement: Value =
                    serde_json::from_slice(&transport.decrypt(&ciphertext)?)?;
                let registration_id = acknowledgement
                    .get("registration_id")
                    .and_then(Value::as_str)
                    .ok_or("rendezvous registration rejected")?
                    .to_owned();
                let environment_generation = acknowledgement
                    .get("environment_generation")
                    .and_then(Value::as_u64)
                    .filter(|value| *value > 0)
                    .ok_or("rendezvous registration rejected")?;
                let shard_generation = acknowledgement
                    .get("shard_generation")
                    .and_then(Value::as_u64)
                    .filter(|value| *value > 0)
                    .ok_or("rendezvous registration rejected")?;
                (registration_id, environment_generation, shard_generation)
            }
            _ => return Err("rendezvous registration rejected".into()),
        };

    let mut heartbeats = interval(HEARTBEAT);
    heartbeats.tick().await;
    let mut sequence = 0_u64;
    let mut reconnect_admission = None;
    loop {
        tokio::select! {
            _ = heartbeats.tick() => {
                sequence = sequence.checked_add(1).ok_or("heartbeat sequence exhausted")?;
                let message = serde_json::to_vec(&json!({
                    "kind": "heartbeat",
                    "sequence": sequence,
                }))?;
                if let Err(error) = socket.send(Message::Binary(transport.encrypt(&message)?.into())).await {
                    return reconnect_admission.ok_or_else(|| error.into());
                }
            }
            message = socket.next() => {
                let ciphertext = match message {
                    Some(Ok(Message::Binary(ciphertext))) => ciphertext,
                    Some(Ok(Message::Close(_))) | None => {
                        return reconnect_admission.ok_or_else(||
                            "rendezvous closed before reconnect authorization".into());
                    }
                    Some(Ok(_)) => continue,
                    Some(Err(error)) => return reconnect_admission.ok_or_else(|| error.into()),
                };
                let message: Value = serde_json::from_slice(&transport.decrypt(&ciphertext)?)?;
                match message.get("kind").and_then(Value::as_str) {
                    Some("heartbeat_ack") => {
                        let token = message.get("reconnect_token").and_then(Value::as_str)
                            .ok_or("rendezvous heartbeat rejected")?;
                        reconnect_admission = Some(URL_SAFE.decode(token)?);
                    }
                    Some("peer") => {
                        let connection_id = parse_connection_id(&message)?;
                        let frame = decode_outer_payload(&message)?;
                        match peer_state.endpoint.as_mut() {
                            None => {
                                let (endpoint, response) = PeerEndpoint::attach(
                                    connection_id,
                                    &frame,
                                    identity,
                                    authorization_keys,
                                    &registration.environment_id,
                                    &durable_registration_id,
                                    environment_generation,
                                    shard_generation,
                                    peer_state.daemon_events.clone(),
                                    PathBuf::from(EXECUTOR_SOCKET),
                                )?;
                                peer_state.endpoint = Some(endpoint);
                                send_outer_peer(&mut socket, &mut transport, connection_id, &response).await?;
                            }
                            Some(active) if active.connection_id == connection_id => {
                                let responses = if serde_json::from_slice::<Value>(&frame)
                                    .ok()
                                    .and_then(|value| value.get("kind").and_then(Value::as_str).map(str::to_owned))
                                    .as_deref()
                                    == Some("peer_resume")
                                {
                                    active.resume(&frame, identity)?
                                } else {
                                    active.receive(&frame).await?
                                };
                                for response in responses {
                                    send_outer_peer(&mut socket, &mut transport, connection_id, &response).await?;
                                }
                            }
                            Some(_) => {}
                        }
                    }
                    Some("peer_close") => {
                        let connection_id = parse_connection_id(&message)?;
                        if peer_state.endpoint.as_ref().is_some_and(|active| active.connection_id == connection_id) {
                            peer_state.endpoint = None;
                        }
                    }
                    _ => return Err("rendezvous message rejected".into()),
                }
            }
            event = peer_state.daemon_receiver.recv() => {
                let Some(event) = event else { continue };
                if let Some(active) = peer_state.endpoint.as_mut()
                    && active.connection_id == event.connection_id
                {
                    for response in active.daemon_event(event)? {
                        send_outer_peer(&mut socket, &mut transport, active.connection_id, &response).await?;
                    }
                }
            }
        }
    }
}

fn websocket_config() -> WebSocketConfig {
    WebSocketConfig::default()
        .read_buffer_size(4 * 1024)
        .write_buffer_size(64 * 1024)
        .max_write_buffer_size(256 * 1024)
        .max_message_size(Some(MAX_OUTER_MESSAGE_BYTES))
        .max_frame_size(Some(MAX_OUTER_MESSAGE_BYTES))
}

fn parse_connection_id(message: &Value) -> Result<Uuid, Box<dyn std::error::Error>> {
    Ok(message
        .get("connection_id")
        .and_then(Value::as_str)
        .ok_or("rendezvous peer identity rejected")?
        .parse()?)
}

fn decode_outer_payload(message: &Value) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
    Ok(STANDARD.decode(
        message
            .get("payload")
            .and_then(Value::as_str)
            .ok_or("rendezvous peer payload rejected")?,
    )?)
}

async fn send_outer_peer<S>(
    socket: &mut tokio_tungstenite::WebSocketStream<S>,
    transport: &mut NoiseTransport,
    connection_id: Uuid,
    frame: &[u8],
) -> Result<(), Box<dyn std::error::Error>>
where
    S: tokio::io::AsyncRead + tokio::io::AsyncWrite + Unpin,
{
    let message = serde_json::to_vec(&json!({
        "kind": "peer",
        "connection_id": connection_id,
        "payload": STANDARD.encode(frame),
    }))?;
    socket
        .send(Message::Binary(transport.encrypt(&message)?.into()))
        .await?;
    Ok(())
}

impl PeerEndpoint {
    #[allow(clippy::too_many_arguments)]
    fn attach(
        connection_id: Uuid,
        frame: &[u8],
        identity: &NoiseIdentity,
        keys: &KeyRing,
        environment_id: &str,
        registration_id: &str,
        environment_generation: u64,
        shard_generation: u64,
        daemon_events: mpsc::Sender<DaemonEvent>,
        daemon_path: PathBuf,
    ) -> Result<(Self, Vec<u8>), Box<dyn std::error::Error>> {
        let attach: PeerAttach = serde_json::from_slice(frame)?;
        if attach.kind != "peer_attach"
            || attach.environment_id != environment_id
            || attach.registration_id != registration_id
            || attach.environment_generation != environment_generation
            || attach.binding.environment_id != environment_id
            || attach.binding.registration_id != registration_id
            || attach.binding.stream_id != attach.stream_id
            || attach.binding.environment_noise_key_id != identity.key_id()
            || attach.binding.harness_noise_key_id != attach.harness_public_key.key_id()
        {
            return Err("executor peer attachment rejected".into());
        }
        let handshake = STANDARD.decode(&attach.handshake)?;
        let pending = PendingResponderHandshake::read_request(
            identity,
            &attach.binding.encode_prologue()?,
            &handshake,
        )?;
        if pending.initiator_public_key() != &attach.harness_public_key {
            return Err("executor peer identity rejected".into());
        }
        let authorization: SignedAuthorization = serde_json::from_slice(pending.authorization())?;
        keys.verify(&authorization, unix_seconds()?)?;
        let claims = &authorization.claims;
        if claims.environment_id != environment_id
            || claims.environment_generation != environment_generation
            || claims.shard_generation != shard_generation
            || claims.stream_id != decode_hex::<16>(&attach.stream_id)?
            || claims.harness_key_id != attach.binding.harness_noise_key_id
            || claims.protocol_version != attach.binding.protocol_version
            || claims.schema_digest != attach.binding.schema_digest
            || authorization.signer_key_id() != attach.binding.authorization_key_id
        {
            return Err("executor peer authorization rejected".into());
        }
        let (transport, response) = pending.complete()?;
        let attached = serde_json::to_vec(&PeerAttached {
            kind: "peer_attached",
            stream_id: &attach.stream_id,
            connection_id,
            handshake: STANDARD.encode(response),
        })?;
        Ok((
            Self {
                connection_id,
                environment_generation,
                binding: attach.binding,
                harness_public_key: attach.harness_public_key,
                transport,
                send_message_id: 1,
                replay: ReplayBuffer::new(),
                receiver: SequenceReceiver::new(),
                decoder: PeerMessageDecoder::new(),
                last_ack_sent: 0,
                streams: HashMap::new(),
                daemon_events,
                daemon_path,
            },
            attached,
        ))
    }

    async fn receive(
        &mut self,
        ciphertext: &[u8],
    ) -> Result<Vec<Vec<u8>>, Box<dyn std::error::Error>> {
        let frame = RelayFrame::decode(&self.transport.decrypt(ciphertext)?)?;
        if !matches!(frame.kind(), FrameKind::Data | FrameKind::Ack)
            || frame.stream_id() != 1
            || frame.operation_id() != 0
        {
            return Err(LocalSocketError::FrameRejected.into());
        }
        self.replay.acknowledge(frame.ack_next())?;
        if frame.kind() == FrameKind::Ack {
            return Ok(Vec::new());
        }
        let mut responses = Vec::new();
        for ordered in self.receiver.push(frame)? {
            if ordered.kind() == FrameKind::Data
                && let Some(message) = self.decoder.push(ordered.payload())?
            {
                let response = self.handle_message(&message).await?;
                if !response.is_empty() {
                    responses.extend(self.encrypt_message(&response)?);
                }
            }
        }
        responses.extend(self.encrypt_acknowledgement()?);
        Ok(responses)
    }

    fn resume(
        &mut self,
        frame: &[u8],
        identity: &NoiseIdentity,
    ) -> Result<Vec<Vec<u8>>, Box<dyn std::error::Error>> {
        let request: PeerResume = serde_json::from_slice(frame)?;
        if request.kind != "peer_resume"
            || request.environment_id != self.binding.environment_id
            || request.environment_generation != self.environment_generation
            || request.registration_id != self.binding.registration_id
            || request.stream_id != self.binding.stream_id
            || request.connection_id != self.connection_id
            || request.harness_public_key != self.harness_public_key
        {
            return Err("executor peer resume rejected".into());
        }
        let pending = PendingResponderHandshake::read_request(
            identity,
            &self.binding.encode_prologue()?,
            &STANDARD.decode(&request.handshake)?,
        )?;
        if pending.initiator_public_key() != &self.harness_public_key {
            return Err("executor peer resume identity rejected".into());
        }
        let claims: PeerResumeClaims = serde_json::from_slice(pending.authorization())?;
        let expected = PeerResumeClaims {
            kind: "resume".into(),
            connection_id: self.connection_id,
            stream_id: self.binding.stream_id.clone(),
            receiver_next: request.receiver_next,
        };
        if claims != expected {
            return Err("executor peer resume binding rejected".into());
        }
        self.replay.acknowledge(request.receiver_next)?;
        let (transport, handshake) = pending.complete()?;
        self.transport = transport;
        let receiver_next = self.receiver.next_sequence();
        let response = serde_json::to_vec(&PeerResumed {
            kind: "peer_resumed".into(),
            stream_id: self.binding.stream_id.clone(),
            connection_id: self.connection_id,
            receiver_next,
            handshake: STANDARD.encode(handshake),
        })?;
        let frames = self
            .replay
            .frames_from(request.receiver_next)?
            .into_iter()
            .cloned()
            .collect::<Vec<_>>();
        let mut output = vec![response];
        for replay in frames {
            output.push(self.transport.encrypt(&replay.encode())?);
        }
        Ok(output)
    }

    async fn handle_message(
        &mut self,
        message: &[u8],
    ) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
        let value: Value = serde_json::from_slice(message)?;
        let stream_id = value
            .get("stream_id")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty() && value.len() <= 128)
            .ok_or(LocalSocketError::FrameRejected)?
            .to_owned();
        match value.get("kind").and_then(Value::as_str) {
            Some("open") if !self.streams.contains_key(&stream_id) && self.streams.len() < 4 => {
                let daemon = UnixStream::connect(&self.daemon_path).await?;
                let (mut reader, writer) = daemon.into_split();
                self.streams.insert(stream_id.clone(), writer);
                let events = self.daemon_events.clone();
                let connection_id = self.connection_id;
                let reader_stream = stream_id.clone();
                tokio::spawn(async move {
                    let mut buffer = vec![0_u8; 60 * 1024];
                    loop {
                        match reader.read(&mut buffer).await {
                            Ok(0) | Err(_) => {
                                let _ = events
                                    .send(DaemonEvent {
                                        connection_id,
                                        stream_id: reader_stream,
                                        payload: Vec::new(),
                                        closed: true,
                                    })
                                    .await;
                                break;
                            }
                            Ok(length) => {
                                if events
                                    .send(DaemonEvent {
                                        connection_id,
                                        stream_id: reader_stream.clone(),
                                        payload: buffer[..length].to_vec(),
                                        closed: false,
                                    })
                                    .await
                                    .is_err()
                                {
                                    break;
                                }
                            }
                        }
                    }
                });
                Ok(serde_json::to_vec(&json!({
                    "kind": "opened",
                    "stream_id": stream_id,
                }))?)
            }
            Some("data") => {
                let payload = STANDARD.decode(
                    value
                        .get("payload")
                        .and_then(Value::as_str)
                        .ok_or(LocalSocketError::FrameRejected)?,
                )?;
                if payload.is_empty()
                    || payload.len()
                        > pwc_persistent_executor_transport::local_socket::MAX_LOCAL_FRAME_BYTES
                {
                    return Err(LocalSocketError::FrameRejected.into());
                }
                let writer = self
                    .streams
                    .get_mut(&stream_id)
                    .ok_or(LocalSocketError::FrameRejected)?;
                writer.write_all(&payload).await?;
                if value.get("eof").and_then(Value::as_bool) == Some(true) {
                    writer.shutdown().await?;
                }
                Ok(Vec::new())
            }
            Some("close") if self.streams.remove(&stream_id).is_some() => {
                Ok(serde_json::to_vec(&json!({
                    "kind": "closed",
                    "stream_id": stream_id,
                }))?)
            }
            _ => Err(LocalSocketError::FrameRejected.into()),
        }
    }

    fn daemon_event(
        &mut self,
        event: DaemonEvent,
    ) -> Result<Vec<Vec<u8>>, Box<dyn std::error::Error>> {
        let message = if event.closed {
            if self.streams.remove(&event.stream_id).is_none() {
                return Ok(Vec::new());
            }
            json!({"kind": "closed", "stream_id": event.stream_id})
        } else {
            json!({
                "kind": "data",
                "stream_id": event.stream_id,
                "payload": STANDARD.encode(event.payload),
            })
        };
        self.encrypt_message(&serde_json::to_vec(&message)?)
    }

    fn encrypt_message(
        &mut self,
        message: &[u8],
    ) -> Result<Vec<Vec<u8>>, Box<dyn std::error::Error>> {
        let message_id = self.send_message_id;
        self.send_message_id = self
            .send_message_id
            .checked_add(1)
            .ok_or("executor peer message identity exhausted")?;
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

    fn encrypt_acknowledgement(&mut self) -> Result<Vec<Vec<u8>>, Box<dyn std::error::Error>> {
        let ack_next = self.receiver.next_sequence();
        if ack_next == self.last_ack_sent {
            return Ok(Vec::new());
        }
        let frame = RelayFrame::new(FrameKind::Ack, 1, 0, 0, ack_next, Vec::new())?;
        self.last_ack_sent = ack_next;
        Ok(vec![self.transport.encrypt(&frame.encode())?])
    }
}

fn decode_hex<const N: usize>(value: &str) -> Result<[u8; N], LocalSocketError> {
    if value.len() != N * 2 {
        return Err(LocalSocketError::AttachmentRejected);
    }
    let mut output = [0_u8; N];
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

fn unix_seconds() -> Result<u64, Box<dyn std::error::Error>> {
    Ok(std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_secs())
}

fn authorization_keys(name: &str) -> Result<KeyRing, Box<dyn std::error::Error>> {
    if name != "PWC_CHAT_EXECUTOR_AUTHORIZATION_KEYS" {
        return Err("executor authorization configuration rejected".into());
    }
    let encoded = std::env::var(name)?;
    if encoded.len() > 4_096 {
        return Err("executor authorization configuration rejected".into());
    }
    let config: AuthorizationKeysConfig = serde_json::from_str(&encoded)?;
    KeyRing::new(
        verification_key(config.current)?,
        config.previous.map(verification_key).transpose()?,
    )
    .map_err(Into::into)
}

fn verification_key(
    config: AuthorizationKeyConfig,
) -> Result<VerificationKey, Box<dyn std::error::Error>> {
    let public_key: [u8; 32] = STANDARD
        .decode(config.public_key)?
        .try_into()
        .map_err(|_| "executor authorization public key rejected")?;
    Ok(VerificationKey::new(
        &config.key_id,
        public_key,
        config.not_before,
        config.not_after,
    )?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use pwc_persistent_executor_transport::protocol::{AuthorizationClaims, AuthorizationSigner};

    #[tokio::test]
    async fn registration_readiness_waits_for_the_local_daemon_listener() {
        let path = std::env::temp_dir().join(format!("pwc-daemon-ready-{}", Uuid::new_v4()));
        let readiness = wait_for_daemon_socket(&path);
        tokio::pin!(readiness);
        assert!(
            timeout(Duration::from_millis(20), &mut readiness)
                .await
                .is_err()
        );
        let listener = tokio::net::UnixListener::bind(&path).unwrap();
        timeout(Duration::from_secs(1), &mut readiness)
            .await
            .unwrap()
            .unwrap();
        drop(listener);
        std::fs::remove_file(&path).unwrap();
    }

    struct AttachedFixture {
        endpoint: PeerEndpoint,
        transport: NoiseTransport,
        environment: NoiseIdentity,
        harness: NoiseIdentity,
        binding: HandshakeBinding,
    }

    fn attach_fixture(
        environment_generation: u64,
    ) -> Result<AttachedFixture, Box<dyn std::error::Error>> {
        let now = unix_seconds()?;
        let environment = NoiseIdentity::from_seed([4; 32])?;
        let harness = NoiseIdentity::from_seed([3; 32])?;
        let signer = AuthorizationSigner::from_seed("authorization-v1", [5; 32], 0, now + 60)?;
        let stream_id = "11".repeat(16);
        let binding = HandshakeBinding {
            environment_id: "environment-v1".into(),
            registration_id: "registration-v1".into(),
            stream_id: stream_id.clone(),
            protocol_version: 1,
            schema_digest: [7; 32],
            authorization_key_id: "authorization-v1".into(),
            harness_noise_key_id: harness.key_id(),
            environment_noise_key_id: environment.key_id(),
        };
        let authorization = signer.sign(AuthorizationClaims {
            authorization_id: [9; 16],
            environment_id: binding.environment_id.clone(),
            environment_generation,
            shard_generation: 5,
            stream_id: [0x11; 16],
            harness_key_id: harness.key_id(),
            protocol_version: 1,
            schema_digest: [7; 32],
            issued_at: now,
            expires_at: now + 2,
        })?;
        let (pending, handshake) = InitiatorHandshake::start(
            &harness,
            &environment.public_key(),
            &binding.encode_prologue()?,
            &serde_json::to_vec(&authorization)?,
        )?;
        let attach = serde_json::to_vec(&json!({
            "kind": "peer_attach",
            "environment_id": "environment-v1",
            "environment_generation": environment_generation,
            "registration_id": "registration-v1",
            "stream_id": stream_id,
            "binding": binding.clone(),
            "harness_public_key": harness.public_key(),
            "handshake": STANDARD.encode(handshake),
        }))?;
        let ring = KeyRing::new(signer.verification_key(), None)?;
        let (events, _receiver) = mpsc::channel(1);
        let (endpoint, response) = PeerEndpoint::attach(
            Uuid::new_v4(),
            &attach,
            &environment,
            &ring,
            "environment-v1",
            "registration-v1",
            3,
            5,
            events,
            PathBuf::from(EXECUTOR_SOCKET),
        )?;
        let response: Value = serde_json::from_slice(&response)?;
        let transport = pending.finish(
            &STANDARD.decode(
                response
                    .get("handshake")
                    .and_then(Value::as_str)
                    .ok_or("peer response rejected")?,
            )?,
        )?;
        Ok(AttachedFixture {
            endpoint,
            transport,
            environment,
            harness,
            binding,
        })
    }

    #[test]
    fn peer_attachment_is_exactly_generation_and_authorization_bound() {
        attach_fixture(3).expect("valid attachment");
        let error = match attach_fixture(4) {
            Ok(_) => panic!("stale generation must fail"),
            Err(error) => error,
        };
        assert!(error.to_string().contains("attachment rejected"));
    }

    #[test]
    fn peer_resume_rekeys_and_replays_only_unacknowledged_frames() {
        let AttachedFixture {
            mut endpoint,
            transport: mut harness_transport,
            environment,
            harness,
            binding,
        } = attach_fixture(3).expect("valid attachment");
        let original = endpoint
            .encrypt_message(br#"{"kind":"closed","stream_id":"operation-1"}"#)
            .expect("outbound frame");
        let first = RelayFrame::decode(
            &harness_transport
                .decrypt(&original[0])
                .expect("original decrypt"),
        )
        .expect("original relay frame");
        assert_eq!(first.sequence(), 0);

        let claims = PeerResumeClaims {
            kind: "resume".into(),
            connection_id: endpoint.connection_id,
            stream_id: binding.stream_id.clone(),
            receiver_next: 0,
        };
        let (pending, handshake) = InitiatorHandshake::start(
            &harness,
            &environment.public_key(),
            &binding.encode_prologue().expect("resume prologue"),
            &serde_json::to_vec(&claims).expect("resume claims"),
        )
        .expect("resume handshake");
        let request = serde_json::to_vec(&PeerResume {
            kind: "peer_resume".into(),
            environment_id: binding.environment_id.clone(),
            environment_generation: 3,
            registration_id: binding.registration_id.clone(),
            stream_id: binding.stream_id.clone(),
            connection_id: endpoint.connection_id,
            receiver_next: 0,
            harness_public_key: harness.public_key(),
            handshake: STANDARD.encode(handshake),
        })
        .expect("resume request");
        let resumed = endpoint
            .resume(&request, &environment)
            .expect("resume response");
        assert_eq!(resumed.len(), 2);
        let response: PeerResumed =
            serde_json::from_slice(&resumed[0]).expect("resume response frame");
        let mut resumed_transport = pending
            .finish(
                &STANDARD
                    .decode(response.handshake)
                    .expect("resume handshake response"),
            )
            .expect("resumed transport");
        let replay = RelayFrame::decode(
            &resumed_transport
                .decrypt(&resumed[1])
                .expect("replay decrypt"),
        )
        .expect("replay relay frame");
        assert_eq!(replay.sequence(), 0);
        assert_eq!(replay.payload(), first.payload());
    }
}
