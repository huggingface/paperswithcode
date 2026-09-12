use std::path::PathBuf;
use std::time::{Duration, Instant};

use base64::Engine;
use base64::engine::general_purpose::URL_SAFE;
use futures_util::{SinkExt, StreamExt};
use pwc_persistent_executor_transport::noise::{
    InitiatorHandshake, NoiseIdentity, NoisePublicKey, prologue,
};
use pwc_persistent_executor_transport::scheduler::ReconnectBackoff;
use serde::Deserialize;
use serde_json::{Value, json};
use tokio::process::Command;
use tokio::time::{interval, timeout};
use tokio_tungstenite::connect_async;
use tokio_tungstenite::tungstenite::Message;
use url::Url;
use uuid::Uuid;

const ROUTE: &str = "/v1/environment";
const PRODUCTION_HOST: &str = "chat-executor.paperswithcode.co";
const STAGING_HOST: &str = "chat-executor.staging.paperswithcode.co";
const HEARTBEAT: Duration = Duration::from_secs(5);
const RESPONSE_DEADLINE: Duration = Duration::from_secs(15);

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RegistrationResponse {
    registration_id: String,
    environment_id: String,
    responder_public_key: NoisePublicKey,
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
        [flag, url, admission_flag, admission_path]
            if flag == "--connect" && admission_flag == "--admission-file" =>
        {
            launch(url, AdmissionSource::File(PathBuf::from(admission_path))).await
        }
        [flag, url, admission_flag, admission_name]
            if flag == "--connect"
                && admission_flag == "--admission-env"
                && admission_name == "PWC_CHAT_EXECUTOR_ADMISSION" =>
        {
            launch(url, AdmissionSource::Environment).await
        }
        _ => Err("usage: environment --self-test | --validate-url URL | --connect URL (--admission-file PATH | --admission-env PWC_CHAT_EXECUTOR_ADMISSION)".into()),
    }
}

fn validate_url(value: &str) -> Result<Url, &'static str> {
    let url = Url::parse(value).map_err(|_| "rendezvous URL rejected")?;
    if url.scheme() != "wss"
        || !matches!(url.host_str(), Some(PRODUCTION_HOST) | Some(STAGING_HOST))
        || url.port().is_some()
        || url.path() != ROUTE
        || url.query().is_some()
        || url.fragment().is_some()
        || !url.username().is_empty()
        || url.password().is_some()
    {
        return Err("rendezvous URL rejected");
    }
    Ok(url)
}

enum AdmissionSource {
    File(PathBuf),
    Environment,
}

async fn launch(url: &str, source: AdmissionSource) -> Result<(), Box<dyn std::error::Error>> {
    let admission = match source {
        AdmissionSource::File(path) => tokio::fs::read(path).await?,
        AdmissionSource::Environment => {
            URL_SAFE.decode(std::env::var("PWC_CHAT_EXECUTOR_ADMISSION")?)?
        }
    };
    if admission.is_empty() || admission.len() > 2_048 {
        return Err("admission frame rejected".into());
    }
    let mut daemon = Command::new("python")
        .args(["-m", "backend.chat_sandbox_worker.executor_daemon"])
        .env_remove("PWC_CHAT_EXECUTOR_ADMISSION")
        .kill_on_drop(true)
        .spawn()?;
    let identity = NoiseIdentity::generate()?;
    let connection = maintain_connection(url, admission, &identity);
    let result = tokio::select! {
        result = connection => result,
        status = daemon.wait() => Err(format!("executor daemon exited: {}", status?).into()),
    };
    let _ = daemon.kill().await;
    result
}

async fn maintain_connection(
    url: &str,
    admission: Vec<u8>,
    identity: &NoiseIdentity,
) -> Result<(), Box<dyn std::error::Error>> {
    let mut next_admission = admission;
    let mut backoff = ReconnectBackoff::new();
    loop {
        let connected_at = Instant::now();
        match connect(url, next_admission, identity).await {
            Ok(reconnect) => {
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
            Err(error) => return Err(error),
        }
    }
}

async fn connect(
    url: &str,
    admission: Vec<u8>,
    identity: &NoiseIdentity,
) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
    let url = validate_url(url)?;
    let (mut socket, _) = connect_async(url.as_str()).await?;
    socket.send(Message::Binary(admission.into())).await?;
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
    match timeout(RESPONSE_DEADLINE, socket.next()).await {
        Ok(Some(Ok(Message::Binary(ciphertext)))) => {
            let acknowledgement: Value = serde_json::from_slice(&transport.decrypt(&ciphertext)?)?;
            if acknowledgement
                .get("registration_id")
                .and_then(Value::as_str)
                .is_none()
            {
                return Err("rendezvous registration rejected".into());
            }
        }
        _ => return Err("rendezvous registration rejected".into()),
    }

    let mut heartbeats = interval(HEARTBEAT);
    heartbeats.tick().await;
    let mut sequence = 0_u64;
    let mut reconnect_admission = None;
    loop {
        heartbeats.tick().await;
        sequence = sequence
            .checked_add(1)
            .ok_or("heartbeat sequence exhausted")?;
        let send_result = socket
            .send(Message::Binary(
                transport
                    .encrypt(&serde_json::to_vec(&json!({"sequence": sequence}))?)?
                    .into(),
            ))
            .await;
        if let Err(error) = send_result {
            return reconnect_admission.ok_or_else(|| error.into());
        }
        match timeout(RESPONSE_DEADLINE, socket.next()).await {
            Ok(Some(Ok(Message::Binary(ciphertext)))) => {
                let acknowledgement: Value =
                    serde_json::from_slice(&transport.decrypt(&ciphertext)?)?;
                let Some(token) = acknowledgement
                    .get("reconnect_token")
                    .and_then(Value::as_str)
                else {
                    return Err("rendezvous heartbeat rejected".into());
                };
                reconnect_admission = Some(URL_SAFE.decode(token)?);
            }
            Ok(Some(Ok(Message::Close(_))) | None) => {
                return reconnect_admission
                    .ok_or_else(|| "rendezvous closed before reconnect authorization".into());
            }
            Ok(Some(Ok(_))) => {}
            Ok(Some(Err(error))) => {
                return reconnect_admission.ok_or_else(|| error.into());
            }
            Err(_) => {
                return reconnect_admission.ok_or_else(|| "rendezvous heartbeat expired".into());
            }
        }
    }
}
