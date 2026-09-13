use std::os::unix::fs::{FileTypeExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex as StandardMutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use base64::Engine;
use base64::engine::general_purpose::URL_SAFE;
use futures_util::{SinkExt, StreamExt};
use pwc_persistent_executor_transport::admission::{
    AdmissionClaims, AdmissionPurpose, AdmissionSigner, AdmissionVerificationKey,
    AdmissionVerifier, LifecycleClass, MAX_PREAUTH_FRAME_BYTES, PREAUTH_DEADLINE_MS,
};
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
use tokio::net::{UnixListener, UnixStream};
use tokio::sync::{Mutex, Semaphore};
use tokio::time::timeout;
use tokio_tungstenite::accept_hdr_async;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::tungstenite::handshake::server::{Request, Response};
use uuid::Uuid;

const ROUTE: &str = "/v1/environment";
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
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct RegistrationResponse {
    registration_id: String,
    environment_id: String,
    responder_public_key: NoisePublicKey,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Heartbeat {
    sequence: u64,
}

#[derive(Serialize)]
struct HeartbeatAck {
    reconnect_token: String,
    expires_at_ms: u64,
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
    });

    prepare_socket_path(&path)?;
    let listener = UnixListener::bind(&path)?;
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o660))?;
    loop {
        let (stream, _) = listener.accept().await?;
        let Ok(permit) = Arc::clone(&state.capacity).try_acquire_owned() else {
            continue;
        };
        let state = Arc::clone(&state);
        tokio::spawn(async move {
            let _permit = permit;
            let _ = handle(stream, state).await;
        });
    }
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
async fn handle(stream: UnixStream, state: Arc<State>) -> Result<(), ConnectionError> {
    let network_source = Arc::new(StandardMutex::new(String::from("nginx")));
    let captured_source = Arc::clone(&network_source);
    let mut socket = accept_hdr_async(stream, move |request: &Request, response: Response| {
        if let Some(value) = request
            .headers()
            .get("x-pwc-network-source")
            .and_then(|value| value.to_str().ok())
            .filter(|value| !value.is_empty() && value.len() <= 64)
        {
            *captured_source.lock().expect("network source lock") = value.into();
        }
        validate_upgrade(request, response)
    })
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
    let session_result: Result<(), ConnectionError> = async {
        socket
            .send(Message::Binary(
                transport
                    .encrypt(&serde_json::to_vec(&json!({
                        "registration_id": registration_id,
                    }))?)?
                    .into(),
            ))
            .await?;

        let mut last_sequence = None;
        let mut last_checkpoint_ms = now_ms;
        loop {
            let message =
                match timeout(Duration::from_millis(HEARTBEAT_SUSPECT_MS), socket.next()).await {
                    Ok(Some(Ok(Message::Binary(ciphertext)))) => ciphertext,
                    _ => break,
                };
            let heartbeat: Heartbeat = serde_json::from_slice(&transport.decrypt(&message)?)?;
            if last_sequence.is_some_and(|previous| heartbeat.sequence <= previous) {
                break;
            }
            last_sequence = Some(heartbeat.sequence);
            let heartbeat_now = unix_ms()?;
            if heartbeat_now >= claims.environment_expires_at_ms
                || claims
                    .compatibility_expires_at_ms
                    .is_some_and(|expires| heartbeat_now >= expires)
            {
                break;
            }
            if heartbeat_now.saturating_sub(last_checkpoint_ms) >= 30_000 {
                state
                    .database
                    .lock()
                    .await
                    .checkpoint_seen(&[registration_id])
                    .await?;
                last_checkpoint_ms = heartbeat_now;
            }
            let reconnect_claims = reconnect_claims(claims, &public_key_id, heartbeat_now);
            let reconnect_frame = state.signer.sign(reconnect_claims)?;
            let verified = state.verifier.verify(&reconnect_frame, 0, heartbeat_now)?;
            state.database.lock().await.persist_nonce(&verified).await?;
            let acknowledgement = serde_json::to_vec(&HeartbeatAck {
                reconnect_token: URL_SAFE.encode(reconnect_frame),
                expires_at_ms: heartbeat_now + 45_000,
            })?;
            socket
                .send(Message::Binary(transport.encrypt(&acknowledgement)?.into()))
                .await?;
        }
        Ok(())
    }
    .await;
    let fence_result = state
        .database
        .lock()
        .await
        .mark_suspect(registration_id)
        .await;
    session_result?;
    fence_result?;
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
