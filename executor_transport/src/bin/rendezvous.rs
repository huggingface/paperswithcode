use std::collections::HashMap;
use std::os::unix::fs::{FileTypeExt, PermissionsExt};
use std::os::unix::io::AsRawFd;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex as StandardMutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use base64::Engine;
use base64::engine::general_purpose::{STANDARD, URL_SAFE};
use futures_util::{SinkExt, StreamExt};
use pwc_persistent_executor_transport::admission::{
    AdmissionClaims, AdmissionPurpose, AdmissionSigner, AdmissionVerificationKey,
    AdmissionVerifier, LifecycleClass, MAX_PREAUTH_FRAME_BYTES, PREAUTH_DEADLINE_MS,
};
use pwc_persistent_executor_transport::local_socket::{FrameReader, validate_peer, write_frame};
use pwc_persistent_executor_transport::noise::{
    NoiseIdentity, NoisePublicKey, PendingResponderHandshake, prologue,
};
use pwc_persistent_executor_transport::postgres_registry::PostgresRegistry;
use pwc_persistent_executor_transport::registry::{
    HEARTBEAT_INTERVAL_MS, HEARTBEAT_SUSPECT_MS, ManifestPin, RegistrationRequest,
};
use pwc_persistent_executor_transport::scheduler::{
    Contender, InvalidAttemptGate, MAX_PREAUTH_SOCKETS, ReconnectClass, ReconnectScheduler,
    ScheduleDecision,
};
use serde::{Deserialize, Serialize};
use serde_json::json;
use tokio::io::AsyncReadExt;
use tokio::net::{UnixListener, UnixStream};
use tokio::sync::{Mutex, Semaphore, mpsc};
use tokio::time::{Instant as TokioInstant, interval, sleep_until, timeout};
use tokio_tungstenite::accept_hdr_async_with_config;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::tungstenite::handshake::server::{Request, Response};
use tokio_tungstenite::tungstenite::protocol::WebSocketConfig;
use uuid::Uuid;

const ROUTE: &str = "/v1/environment";
const SERVICE_DRAIN_SECONDS: u64 = 240;
const MAX_LOCAL_PREAUTH_FRAME_BYTES: usize = 16 * 1024;
const MAX_LOCAL_PEER_FRAME_BYTES: usize = 64 * 1024;
const MAX_OUTER_MESSAGE_BYTES: usize = 128 * 1024;
type ConnectionError = Box<dyn std::error::Error + Send + Sync>;

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
struct VerificationKeyConfig {
    key_id: String,
    public_key: String,
    not_before_ms: u64,
    not_after_ms: u64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RendezvousConfig {
    shard_database_id: Uuid,
    allowed_backend_uid: u32,
    allowed_harness_uid: u32,
    current_protocol_version: u32,
    current_key: VerificationKeyConfig,
    previous_key: Option<VerificationKeyConfig>,
}

struct State {
    current_protocol_version: u32,
    verifier: AdmissionVerifier,
    signer: AdmissionSigner,
    database: Mutex<PostgresRegistry>,
    scheduler: Mutex<ReconnectScheduler>,
    invalid_gate: Mutex<InvalidAttemptGate>,
    capacity: Arc<Semaphore>,
    live: Mutex<HashMap<Uuid, LiveRegistration>>,
}

struct LiveRegistration {
    connection_id: Uuid,
    claims: AdmissionClaims,
    peer_events: mpsc::Sender<PeerEvent>,
}

enum PeerEvent {
    Attach {
        connection_id: Uuid,
        frame: Vec<u8>,
        outbound: mpsc::Sender<Vec<u8>>,
    },
    Resume {
        connection_id: Uuid,
        frame: Vec<u8>,
        outbound: mpsc::Sender<Vec<u8>>,
    },
    Data {
        connection_id: Uuid,
        frame: Vec<u8>,
    },
    Closed {
        connection_id: Uuid,
    },
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct LivenessRequest {
    kind: String,
    registration_id: Uuid,
    environment_id: String,
    environment_generation: u64,
    shard_generation: u64,
    turn_id: Uuid,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct RegistrationResponse {
    registration_id: String,
    environment_id: String,
    responder_public_key: NoisePublicKey,
}

#[tokio::main]
async fn main() {
    if let Err(error) = run().await {
        eprintln!("rendezvous failed: {error}");
        std::process::exit(1);
    }
}

async fn run() -> Result<(), ConnectionError> {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    match arguments.as_slice() {
        [flag] if flag == "--self-test" => {
            println!(
                "{}",
                json!({
                    "listener": "unix",
                    "route": ROUTE,
                    "preauth_frame_bytes": MAX_PREAUTH_FRAME_BYTES,
                    "preauth_deadline_ms": PREAUTH_DEADLINE_MS,
                    "heartbeat_ms": HEARTBEAT_INTERVAL_MS,
                    "suspect_ms": HEARTBEAT_SUSPECT_MS,
                    "preauth_socket_cap": MAX_PREAUTH_SOCKETS,
                })
            );
            Ok(())
        }
        [socket_flag, socket, config_flag, config, database_flag, database, signing_flag, signing]
            if socket_flag == "--unix-socket"
                && config_flag == "--config"
                && database_flag == "--database-url-file"
                && signing_flag == "--signing-key-file" =>
        {
            serve(
                PathBuf::from(socket),
                PathBuf::from(config),
                PathBuf::from(database),
                PathBuf::from(signing),
            )
            .await
        }
        _ => Err("usage: rendezvous --self-test | --unix-socket PATH --config PATH --database-url-file PATH --signing-key-file PATH".into()),
    }
}

async fn serve(
    path: PathBuf,
    config_path: PathBuf,
    database_path: PathBuf,
    signing_path: PathBuf,
) -> Result<(), ConnectionError> {
    let config: RendezvousConfig = serde_json::from_slice(&tokio::fs::read(config_path).await?)?;
    if config.current_protocol_version == 0 {
        return Err("rendezvous protocol version rejected".into());
    }
    let now_ms = unix_ms()?;
    if now_ms < config.current_key.not_before_ms || now_ms > config.current_key.not_after_ms {
        return Err("rendezvous current key rejected".into());
    }
    let current = verification_key(&config.current_key)?;
    let previous = config
        .previous_key
        .as_ref()
        .map(verification_key)
        .transpose()?;
    let verifier = AdmissionVerifier::new(current, previous)?;
    let signing_key: [u8; 32] = tokio::fs::read(signing_path)
        .await?
        .try_into()
        .map_err(|_| "rendezvous signing key rejected")?;
    let signer = AdmissionSigner::from_seed(
        &config.current_key.key_id,
        signing_key,
        config.current_key.not_before_ms,
        config.current_key.not_after_ms,
    )?;
    if signer.verification_key() != verification_key(&config.current_key)? {
        return Err("rendezvous signing key rejected".into());
    }
    let database_url = String::from_utf8(tokio::fs::read(database_path).await?)?;
    let mut database =
        PostgresRegistry::connect(database_url.trim(), config.shard_database_id).await?;
    database.invalidate_ready_on_startup().await?;
    let state = Arc::new(State {
        current_protocol_version: config.current_protocol_version,
        verifier,
        signer,
        database: Mutex::new(database),
        scheduler: Mutex::new(ReconnectScheduler::new()),
        invalid_gate: Mutex::new(InvalidAttemptGate::new(unix_ms()?)),
        capacity: Arc::new(Semaphore::new(MAX_PREAUTH_SOCKETS)),
        live: Mutex::new(HashMap::new()),
    });
    let recovery_state = state.clone();
    tokio::spawn(async move {
        let mut cleanup = interval(Duration::from_secs(1));
        cleanup.tick().await;
        loop {
            cleanup.tick().await;
            if let Err(error) = recovery_state
                .database
                .lock()
                .await
                .expire_suspect_recoveries()
                .await
            {
                eprintln!("executor recovery reconciliation failed: {error}");
            }
        }
    });

    prepare_socket_path(&path)?;
    let listener = UnixListener::bind(&path)?;
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o660))?;
    let mut terminate = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    loop {
        let accepted = tokio::select! {
            accepted = listener.accept() => accepted,
            _ = terminate.recv() => break,
        };
        let (stream, _) = accepted?;
        let Ok(permit) = Arc::clone(&state.capacity).try_acquire_owned() else {
            continue;
        };
        let state = Arc::clone(&state);
        let allowed_backend_uid = config.allowed_backend_uid;
        let allowed_harness_uid = config.allowed_harness_uid;
        tokio::spawn(async move {
            let _permit = permit;
            if let Err(error) =
                dispatch(stream, state, allowed_backend_uid, allowed_harness_uid).await
            {
                eprintln!("executor connection failed: {error}");
            }
        });
    }
    drop(listener);
    std::fs::remove_file(&path).ok();
    tokio::time::sleep(Duration::from_secs(SERVICE_DRAIN_SECONDS)).await;
    Ok(())
}

async fn dispatch(
    stream: UnixStream,
    state: Arc<State>,
    allowed_backend_uid: u32,
    allowed_harness_uid: u32,
) -> Result<(), ConnectionError> {
    let mut prefix = [0_u8; 4];
    timeout(Duration::from_millis(PREAUTH_DEADLINE_MS), async {
        let result: Result<(), std::io::Error> = loop {
            stream.readable().await?;
            match stream.try_io(tokio::io::Interest::READABLE, || {
                let read = unsafe {
                    libc::recv(
                        stream.as_raw_fd(),
                        prefix.as_mut_ptr().cast(),
                        prefix.len(),
                        libc::MSG_PEEK,
                    )
                };
                if read < 0 {
                    Err(std::io::Error::last_os_error())
                } else if read < prefix.len() as isize {
                    Err(std::io::Error::from(std::io::ErrorKind::WouldBlock))
                } else {
                    Ok(())
                }
            }) {
                Ok(result) => break Ok(result),
                Err(_) => continue,
            }
        };
        result
    })
    .await??;
    if &prefix == b"GET " {
        handle_environment(stream, state).await
    } else {
        handle_local(stream, state, allowed_backend_uid, allowed_harness_uid).await
    }
}

async fn handle_local(
    mut stream: UnixStream,
    state: Arc<State>,
    allowed_backend_uid: u32,
    allowed_harness_uid: u32,
) -> Result<(), ConnectionError> {
    let peer_uid = stream.peer_cred()?.uid();
    if peer_uid != allowed_backend_uid && peer_uid != allowed_harness_uid {
        return Err("executor local peer rejected".into());
    }
    let frame = timeout(
        Duration::from_millis(PREAUTH_DEADLINE_MS),
        read_local_preauth(&mut stream),
    )
    .await??;
    let value: serde_json::Value = serde_json::from_slice(&frame)?;
    match value.get("kind").and_then(serde_json::Value::as_str) {
        Some("claim_liveness") => {
            validate_peer(&stream, allowed_backend_uid)?;
            handle_liveness(stream, state, value).await
        }
        Some("peer_attach" | "peer_resume") => {
            validate_peer(&stream, allowed_harness_uid)?;
            handle_peer(stream, state, value, frame).await
        }
        Some("peer_detach") => {
            validate_peer(&stream, allowed_harness_uid)?;
            handle_peer_detach(state, value).await
        }
        Some("route_health") => {
            validate_peer(&stream, allowed_backend_uid)?;
            handle_route_health(stream, state).await
        }
        _ => Ok(()),
    }
}

async fn read_local_preauth(stream: &mut UnixStream) -> Result<Vec<u8>, ConnectionError> {
    read_bounded_frame(stream, MAX_LOCAL_PREAUTH_FRAME_BYTES).await
}

async fn read_bounded_frame(
    stream: &mut UnixStream,
    maximum: usize,
) -> Result<Vec<u8>, ConnectionError> {
    let length = stream.read_u32().await? as usize;
    if length == 0 || length > maximum {
        return Err("executor local preauthentication rejected".into());
    }
    let mut frame = vec![0_u8; length];
    stream.read_exact(&mut frame).await?;
    Ok(frame)
}

async fn handle_route_health(
    mut stream: UnixStream,
    state: Arc<State>,
) -> Result<(), ConnectionError> {
    let live_environments = state.live.lock().await.len();
    write_frame(
        &mut stream,
        &serde_json::to_vec(&json!({
            "kind": "route_health",
            "age_ms": 0,
            "live_environments": live_environments,
        }))?,
    )
    .await?;
    Ok(())
}

async fn handle_liveness(
    mut stream: UnixStream,
    state: Arc<State>,
    value: serde_json::Value,
) -> Result<(), ConnectionError> {
    let request: LivenessRequest = serde_json::from_value(value)?;
    if request.kind != "claim_liveness" {
        return Err("executor liveness rejected".into());
    }
    let live = state.live.lock().await;
    let claims = live
        .get(&request.registration_id)
        .filter(|entry| {
            entry.claims.environment_id == request.environment_id
                && entry.claims.environment_generation == request.environment_generation
                && entry.claims.shard_generation == request.shard_generation
        })
        .map(|entry| entry.claims.clone())
        .ok_or("executor liveness rejected")?;
    drop(live);
    let now_ms = unix_ms()?;
    let mut assertion = claims;
    assertion.nonce = *Uuid::new_v4().as_bytes();
    assertion.purpose = AdmissionPurpose::ClaimLiveness;
    assertion.lifecycle_class = LifecycleClass::ActiveClaim;
    assertion.issued_at_ms = now_ms;
    assertion.expires_at_ms = now_ms + 2_000;
    assertion.remaining_lifetime_ms = assertion.environment_expires_at_ms.saturating_sub(now_ms);
    let frame = state.signer.sign(assertion)?;
    let verified = state.verifier.verify(&frame, 0, now_ms)?;
    state.database.lock().await.persist_nonce(&verified).await?;
    write_frame(
        &mut stream,
        &serde_json::to_vec(&json!({
            "kind": "claim_liveness",
            "turn_id": request.turn_id,
            "nonce_digest": verified.nonce_digest(),
        }))?,
    )
    .await?;
    Ok(())
}

async fn handle_peer_detach(
    state: Arc<State>,
    value: serde_json::Value,
) -> Result<(), ConnectionError> {
    let registration_id = value
        .get("registration_id")
        .and_then(serde_json::Value::as_str)
        .ok_or("executor peer detach rejected")?
        .parse::<Uuid>()?;
    let environment_id = value
        .get("environment_id")
        .and_then(serde_json::Value::as_str)
        .ok_or("executor peer detach rejected")?;
    let environment_generation = value
        .get("environment_generation")
        .and_then(serde_json::Value::as_u64)
        .ok_or("executor peer detach rejected")?;
    let connection_id = value
        .get("connection_id")
        .and_then(serde_json::Value::as_str)
        .ok_or("executor peer detach rejected")?
        .parse::<Uuid>()?;
    let events = {
        let live = state.live.lock().await;
        live.get(&registration_id)
            .filter(|entry| {
                entry.claims.environment_id == environment_id
                    && entry.claims.environment_generation == environment_generation
            })
            .map(|entry| entry.peer_events.clone())
            .ok_or("executor peer detach rejected")?
    };
    events.send(PeerEvent::Closed { connection_id }).await?;
    Ok(())
}

async fn handle_peer(
    mut stream: UnixStream,
    state: Arc<State>,
    value: serde_json::Value,
    initial: Vec<u8>,
) -> Result<(), ConnectionError> {
    let kind = value
        .get("kind")
        .and_then(serde_json::Value::as_str)
        .ok_or("executor peer kind rejected")?;
    if !matches!(kind, "peer_attach" | "peer_resume") {
        return Err("executor peer kind rejected".into());
    }
    let registration_id = value
        .get("registration_id")
        .and_then(serde_json::Value::as_str)
        .ok_or("executor peer registration rejected")?
        .parse::<Uuid>()?;
    let environment_id = value
        .get("environment_id")
        .and_then(serde_json::Value::as_str)
        .ok_or("executor peer environment rejected")?;
    let environment_generation = value
        .get("environment_generation")
        .and_then(serde_json::Value::as_u64)
        .ok_or("executor peer generation rejected")?;
    let (events, claims) = {
        let live = state.live.lock().await;
        let entry = live
            .get(&registration_id)
            .filter(|entry| {
                entry.claims.environment_id == environment_id
                    && entry.claims.environment_generation == environment_generation
            })
            .ok_or("executor peer route rejected")?;
        (entry.peer_events.clone(), entry.claims.clone())
    };
    if kind == "peer_attach" {
        let binding = value
            .get("binding")
            .and_then(serde_json::Value::as_object)
            .ok_or("executor peer binding rejected")?;
        if binding
            .get("registration_id")
            .and_then(serde_json::Value::as_str)
            != Some(
                value["registration_id"]
                    .as_str()
                    .expect("registration parsed"),
            )
            || value
                .get("binding")
                .and_then(|binding| binding.get("environment_id"))
                .and_then(serde_json::Value::as_str)
                != Some(claims.environment_id.as_str())
        {
            return Err("executor peer binding rejected".into());
        }
    }
    let connection_id = if kind == "peer_resume" {
        value
            .get("connection_id")
            .and_then(serde_json::Value::as_str)
            .ok_or("executor peer resume identity rejected")?
            .parse()?
    } else {
        Uuid::new_v4()
    };
    let (outbound, mut responses) = mpsc::channel(4);
    let event = if kind == "peer_resume" {
        PeerEvent::Resume {
            connection_id,
            frame: initial,
            outbound,
        }
    } else {
        PeerEvent::Attach {
            connection_id,
            frame: initial,
            outbound,
        }
    };
    timeout(
        Duration::from_millis(PREAUTH_DEADLINE_MS),
        events.send(event),
    )
    .await??;
    let mut reader = FrameReader::new(MAX_LOCAL_PEER_FRAME_BYTES);
    loop {
        tokio::select! {
            frame = reader.read(&mut stream) => {
                match frame {
                    Ok(frame) => events.send(PeerEvent::Data { connection_id, frame }).await?,
                    Err(_) => break,
                }
            }
            response = responses.recv() => {
                match response {
                    Some(response) => write_frame(&mut stream, &response).await?,
                    None => break,
                }
            }
        }
    }
    Ok(())
}

fn verification_key(
    config: &VerificationKeyConfig,
) -> Result<AdmissionVerificationKey, ConnectionError> {
    let bytes: [u8; 32] = URL_SAFE
        .decode(&config.public_key)?
        .try_into()
        .map_err(|_| "rendezvous verification key rejected")?;
    Ok(AdmissionVerificationKey::new(
        &config.key_id,
        bytes,
        config.not_before_ms,
        config.not_after_ms,
    )?)
}

fn prepare_socket_path(path: &Path) -> Result<(), ConnectionError> {
    if let Ok(metadata) = std::fs::symlink_metadata(path) {
        if !metadata.file_type().is_socket() {
            return Err("rendezvous socket path already exists and is not a socket".into());
        }
        std::fs::remove_file(path)?;
    }
    let parent = path.parent().ok_or("rendezvous socket requires a parent")?;
    let metadata = std::fs::metadata(parent)?;
    if metadata.permissions().mode() & 0o002 != 0 {
        return Err("rendezvous socket parent is world-writable".into());
    }
    Ok(())
}

#[allow(clippy::result_large_err)]
async fn handle_environment(stream: UnixStream, state: Arc<State>) -> Result<(), ConnectionError> {
    let network_source = Arc::new(StandardMutex::new(String::from("nginx")));
    let captured_source = Arc::clone(&network_source);
    let mut socket = accept_hdr_async_with_config(
        stream,
        move |request: &Request, response: Response| {
            if let Some(value) = request
                .headers()
                .get("x-pwc-network-source")
                .and_then(|value| value.to_str().ok())
                .filter(|value| !value.is_empty() && value.len() <= 64)
            {
                *captured_source.lock().expect("network source lock") = value.into();
            }
            validate_upgrade(request, response)
        },
        Some(websocket_config()),
    )
    .await?;
    let started = Instant::now();
    let frame = match timeout(Duration::from_millis(PREAUTH_DEADLINE_MS), socket.next()).await {
        Ok(Some(Ok(Message::Binary(frame))))
            if !frame.is_empty() && frame.len() <= MAX_PREAUTH_FRAME_BYTES =>
        {
            frame
        }
        _ => return Ok(()),
    };
    let now_ms = unix_ms()?;
    let admission =
        match state
            .verifier
            .verify(&frame, started.elapsed().as_millis() as u64, now_ms)
        {
            Ok(admission) => admission,
            Err(_) => {
                let source = network_source.lock().expect("network source lock").clone();
                state.invalid_gate.lock().await.invalid(&source, now_ms);
                return Ok(());
            }
        };
    let claims = admission.claims();
    if claims.purpose == AdmissionPurpose::Registration
        && claims.protocol_version != state.current_protocol_version
    {
        return Ok(());
    }
    let class = match claims.lifecycle_class {
        LifecycleClass::ActiveClaim => ReconnectClass::ActiveClaim,
        LifecycleClass::AssignedIdle => ReconnectClass::AssignedIdle,
        LifecycleClass::BlankPool => ReconnectClass::BlankPool,
    };
    let contender_id = u64::from_be_bytes(claims.nonce[..8].try_into()?);
    match state.scheduler.lock().await.try_start(
        [Contender::new(contender_id, class, claims.issued_at_ms)],
        now_ms,
        contender_id,
    ) {
        ScheduleDecision::Retry { after_ms } => {
            socket
                .send(Message::Text(
                    json!({"retry_after_ms": after_ms}).to_string().into(),
                ))
                .await?;
            return Ok(());
        }
        ScheduleDecision::Started(_) => {}
        ScheduleDecision::Empty => return Ok(()),
    }

    let public_frame =
        match timeout(Duration::from_millis(PREAUTH_DEADLINE_MS), socket.next()).await {
            Ok(Some(Ok(Message::Text(frame)))) if frame.len() <= 4_096 => frame,
            _ => return Ok(()),
        };
    let public_key: NoisePublicKey = serde_json::from_str(&public_frame)?;
    let public_key_id = public_key.key_id();
    if claims.public_noise_key_id != public_key_id
        && !(claims.purpose == AdmissionPurpose::Registration
            && claims.public_noise_key_id == "pending")
    {
        return Ok(());
    }
    let attempt_id = Uuid::new_v4();
    let responder = NoiseIdentity::generate()?;
    socket
        .send(Message::Text(
            serde_json::to_string(&RegistrationResponse {
                registration_id: attempt_id.to_string(),
                environment_id: claims.environment_id.clone(),
                responder_public_key: responder.public_key(),
            })?
            .into(),
        ))
        .await?;
    let handshake = match timeout(Duration::from_secs(2), socket.next()).await {
        Ok(Some(Ok(Message::Binary(frame)))) => frame,
        _ => return Ok(()),
    };
    let transcript = prologue(
        &claims.environment_id,
        &attempt_id.to_string(),
        "environment",
    );
    let pending = PendingResponderHandshake::read_request(&responder, &transcript, &handshake)?;
    if pending.initiator_public_key() != &public_key || !pending.authorization().is_empty() {
        return Ok(());
    }
    let (mut transport, response) = pending.complete()?;
    socket.send(Message::Binary(response.into())).await?;

    let request = request_from_claims(
        claims,
        public_key_id.clone(),
        public_frame.as_bytes().to_vec(),
    );
    let registration_id = state
        .database
        .lock()
        .await
        .consume_and_register(&request, &admission)
        .await?;
    let connection_id = Uuid::new_v4();
    let (peer_events, mut peer_receiver) = mpsc::channel(4);
    state.live.lock().await.insert(
        registration_id,
        LiveRegistration {
            connection_id,
            claims: claims.clone(),
            peer_events,
        },
    );
    let session_result: Result<(), ConnectionError> = async {
        socket
            .send(Message::Binary(
                transport
                    .encrypt(&serde_json::to_vec(&json!({
                        "registration_id": registration_id,
                        "environment_generation": claims.environment_generation,
                        "shard_generation": claims.shard_generation,
                    }))?)?
                    .into(),
            ))
            .await?;

        let mut last_sequence = None;
        let mut last_checkpoint_ms = now_ms;
        let mut active_peer: Option<(Uuid, mpsc::Sender<Vec<u8>>)> = None;
        let heartbeat_deadline = sleep_until(
            TokioInstant::now() + Duration::from_millis(HEARTBEAT_SUSPECT_MS),
        );
        tokio::pin!(heartbeat_deadline);
        loop {
            tokio::select! {
                _ = &mut heartbeat_deadline => break,
                message = socket.next() => {
                    let ciphertext = match message {
                        Some(Ok(Message::Binary(ciphertext))) => ciphertext,
                        _ => break,
                    };
                    let message: serde_json::Value =
                        serde_json::from_slice(&transport.decrypt(&ciphertext)?)?;
                    match message.get("kind").and_then(serde_json::Value::as_str) {
                        Some("heartbeat") => {
                            let sequence = message.get("sequence")
                                .and_then(serde_json::Value::as_u64)
                                .ok_or("executor heartbeat rejected")?;
                            if last_sequence.is_some_and(|previous| sequence <= previous) {
                                break;
                            }
                            last_sequence = Some(sequence);
                            heartbeat_deadline.as_mut().reset(
                                TokioInstant::now()
                                    + Duration::from_millis(HEARTBEAT_SUSPECT_MS),
                            );
                            let heartbeat_now = unix_ms()?;
                            if heartbeat_now >= claims.environment_expires_at_ms
                                || claims.compatibility_expires_at_ms
                                    .is_some_and(|expires| heartbeat_now >= expires)
                            {
                                break;
                            }
                            if heartbeat_now.saturating_sub(last_checkpoint_ms) >= 30_000 {
                                state.database.lock().await
                                    .checkpoint_seen(&[registration_id]).await?;
                                last_checkpoint_ms = heartbeat_now;
                            }
                            let reconnect_claims = reconnect_claims(claims, &public_key_id, heartbeat_now);
                            let reconnect_frame = state.signer.sign(reconnect_claims)?;
                            let verified = state.verifier.verify(&reconnect_frame, 0, heartbeat_now)?;
                            state.database.lock().await.persist_nonce(&verified).await?;
                            let acknowledgement = serde_json::to_vec(&json!({
                                "kind": "heartbeat_ack",
                                "reconnect_token": URL_SAFE.encode(reconnect_frame),
                                "expires_at_ms": heartbeat_now + 45_000,
                            }))?;
                            socket.send(Message::Binary(transport.encrypt(&acknowledgement)?.into())).await?;
                        }
                        Some("peer") => {
                            let peer_id = message.get("connection_id")
                                .and_then(serde_json::Value::as_str)
                                .and_then(|value| value.parse::<Uuid>().ok());
                            let payload = message.get("payload")
                                .and_then(serde_json::Value::as_str)
                                .map(|value| STANDARD.decode(value))
                                .transpose()?;
                            if let (Some((active_id, outbound)), Some(peer_id), Some(payload)) =
                                (&active_peer, peer_id, payload)
                                && *active_id == peer_id
                            {
                                outbound.send(payload).await?;
                            }
                        }
                        _ => break,
                    }
                }
                event = peer_receiver.recv() => {
                    match event {
                        Some(PeerEvent::Attach { connection_id: peer_id, frame, outbound })
                            if active_peer.is_none() => {
                                active_peer = Some((peer_id, outbound));
                                send_peer_frame(&mut socket, &mut transport, peer_id, &frame).await?;
                            }
                        Some(PeerEvent::Resume { connection_id: peer_id, frame, outbound })
                            if active_peer.as_ref().is_none_or(|(active, _)| *active == peer_id) => {
                                active_peer = Some((peer_id, outbound));
                                send_peer_frame(&mut socket, &mut transport, peer_id, &frame).await?;
                            }
                        Some(PeerEvent::Data { connection_id: peer_id, frame })
                            if active_peer.as_ref().is_some_and(|(active, _)| *active == peer_id) => {
                                send_peer_frame(&mut socket, &mut transport, peer_id, &frame).await?;
                            }
                        Some(PeerEvent::Closed { connection_id: peer_id })
                            if active_peer.as_ref().is_some_and(|(active, _)| *active == peer_id) => {
                                send_peer_close(&mut socket, &mut transport, peer_id).await?;
                                active_peer = None;
                            }
                        Some(PeerEvent::Attach { .. } | PeerEvent::Resume { .. } | PeerEvent::Data { .. } | PeerEvent::Closed { .. }) => {}
                        None => break,
                    }
                }
            }
        }
        Ok(())
    }
    .await;
    let mut live = state.live.lock().await;
    let owns_registration = live
        .get(&registration_id)
        .is_some_and(|entry| entry.connection_id == connection_id);
    if owns_registration {
        live.remove(&registration_id);
    }
    drop(live);
    let fence_result = if owns_registration {
        state
            .database
            .lock()
            .await
            .mark_suspect(registration_id)
            .await
    } else {
        Ok(())
    };
    session_result?;
    fence_result?;
    Ok(())
}

fn websocket_config() -> WebSocketConfig {
    WebSocketConfig::default()
        .read_buffer_size(4 * 1024)
        .write_buffer_size(64 * 1024)
        .max_write_buffer_size(256 * 1024)
        .max_message_size(Some(MAX_OUTER_MESSAGE_BYTES))
        .max_frame_size(Some(MAX_OUTER_MESSAGE_BYTES))
}

async fn send_peer_frame<S>(
    socket: &mut tokio_tungstenite::WebSocketStream<S>,
    transport: &mut pwc_persistent_executor_transport::noise::NoiseTransport,
    connection_id: Uuid,
    frame: &[u8],
) -> Result<(), ConnectionError>
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

async fn send_peer_close<S>(
    socket: &mut tokio_tungstenite::WebSocketStream<S>,
    transport: &mut pwc_persistent_executor_transport::noise::NoiseTransport,
    connection_id: Uuid,
) -> Result<(), ConnectionError>
where
    S: tokio::io::AsyncRead + tokio::io::AsyncWrite + Unpin,
{
    let message = serde_json::to_vec(&json!({
        "kind": "peer_close",
        "connection_id": connection_id,
    }))?;
    socket
        .send(Message::Binary(transport.encrypt(&message)?.into()))
        .await?;
    Ok(())
}

fn request_from_claims(
    claims: &AdmissionClaims,
    public_key_id: String,
    public_key: Vec<u8>,
) -> RegistrationRequest {
    RegistrationRequest {
        environment_id: claims.environment_id.clone(),
        environment_generation: claims.environment_generation,
        cell_id: claims.cell_id.clone(),
        shard_id: claims.shard_id.clone(),
        shard_generation: claims.shard_generation,
        public_noise_key_id: public_key_id,
        public_noise_key: public_key,
        manifest: ManifestPin {
            manifest_digest: claims.manifest_digest,
            image_digest: claims.image_digest,
            environment_binary_digest: claims.environment_binary_digest,
            daemon_digest: claims.daemon_digest,
            source_commit: claims.source_commit,
            protocol_version: claims.protocol_version,
            schema_digest: claims.schema_digest,
            release_id: claims.release_id.clone(),
            compatibility_expires_at_ms: claims.compatibility_expires_at_ms,
        },
        remaining_lifetime_ms: claims.remaining_lifetime_ms,
    }
}

fn reconnect_claims(claims: &AdmissionClaims, public_key_id: &str, now_ms: u64) -> AdmissionClaims {
    let mut reconnect = claims.clone();
    reconnect.nonce = *Uuid::new_v4().as_bytes();
    reconnect.purpose = AdmissionPurpose::Reconnect;
    reconnect.public_noise_key_id = public_key_id.into();
    reconnect.issued_at_ms = now_ms;
    reconnect.expires_at_ms = now_ms + 45_000;
    reconnect.remaining_lifetime_ms = reconnect.environment_expires_at_ms.saturating_sub(now_ms);
    reconnect
}

fn unix_ms() -> Result<u64, ConnectionError> {
    Ok(SystemTime::now()
        .duration_since(UNIX_EPOCH)?
        .as_millis()
        .try_into()?)
}

fn http_error() -> tokio_tungstenite::tungstenite::handshake::server::ErrorResponse {
    tokio_tungstenite::tungstenite::http::Response::builder()
        .status(tokio_tungstenite::tungstenite::http::StatusCode::NOT_FOUND)
        .body(Some("not found".into()))
        .expect("static response")
}

#[allow(clippy::result_large_err)]
fn validate_upgrade(
    request: &Request,
    response: Response,
) -> Result<Response, tokio_tungstenite::tungstenite::handshake::server::ErrorResponse> {
    if request.uri().path() == ROUTE && request.uri().query().is_none() {
        Ok(response)
    } else {
        Err(http_error())
    }
}
