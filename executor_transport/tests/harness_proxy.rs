use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::path::Path;
use std::process::Stdio;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use base64::Engine;
use base64::engine::general_purpose::STANDARD;
use pwc_persistent_executor_transport::local_socket::{read_frame, write_frame};
use pwc_persistent_executor_transport::noise::{
    NoiseIdentity, NoisePublicKey, PendingResponderHandshake,
};
use pwc_persistent_executor_transport::protocol::{
    AuthorizationSigner, FrameKind, HandshakeBinding, KeyRing, MessageDecoder, RelayFrame,
    SequenceReceiver, SignedAuthorization, frame_records,
};
use serde_json::{Value, json};
use tokio::net::{UnixListener, UnixStream};
use tokio::process::Command;

#[tokio::test]
async fn harness_uses_one_bound_noise_stream_and_consumes_authorization_once() {
    let root = std::env::temp_dir().join(format!("pwc-harness-proxy-{}", std::process::id()));
    if root.exists() {
        std::fs::remove_dir_all(&root).unwrap();
    }
    std::fs::create_dir(&root).unwrap();
    std::fs::set_permissions(&root, std::fs::Permissions::from_mode(0o700)).unwrap();
    let local_path = root.join("harness.sock");
    let peer_path = root.join("rendezvous.sock");
    let listener = UnixListener::bind(&peer_path).unwrap();
    std::fs::set_permissions(&peer_path, std::fs::Permissions::from_mode(0o660)).unwrap();
    let uid = std::fs::metadata(&root).unwrap().uid();
    let now = unix_seconds();
    let harness_key = root.join("harness.key");
    let authorization_key = root.join("authorization.key");
    write_private(&harness_key, &[3; 32]);
    write_private(&authorization_key, &[5; 32]);
    let config = root.join("config.json");
    std::fs::write(
        &config,
        serde_json::to_vec(&json!({
            "allowed_backend_uid": uid,
            "expected_rendezvous_uid": uid,
            "protocol_version": 1,
            "schema_digest": "07".repeat(32),
            "authorization_key_id": "authorization-v1",
            "authorization_not_before": now.saturating_sub(1),
            "authorization_not_after": now + 60,
        }))
        .unwrap(),
    )
    .unwrap();

    let environment = NoiseIdentity::from_seed([4; 32]).unwrap();
    let environment_public = environment.public_key();
    let harness_key_id = NoiseIdentity::from_seed([3; 32]).unwrap().key_id();
    let verification_key =
        AuthorizationSigner::from_seed("authorization-v1", [5; 32], now - 1, now + 60)
            .unwrap()
            .verification_key();
    let command = vec![b'x'; 64 * 1024];
    let peer_command = command.clone();
    let peer = tokio::spawn(async move {
        let (mut stream, _) = listener.accept().await.unwrap();
        let attach: Value =
            serde_json::from_slice(&read_frame(&mut stream).await.unwrap()).unwrap();
        assert_eq!(attach["kind"], "peer_attach");
        let binding: HandshakeBinding = serde_json::from_value(attach["binding"].clone()).unwrap();
        let harness_public: NoisePublicKey =
            serde_json::from_value(attach["harness_public_key"].clone()).unwrap();
        assert_eq!(binding.harness_noise_key_id, harness_public.key_id());
        assert_eq!(binding.environment_noise_key_id, environment.key_id());
        let handshake = STANDARD
            .decode(attach["handshake"].as_str().unwrap())
            .unwrap();
        let pending = PendingResponderHandshake::read_request(
            &environment,
            &binding.encode_prologue().unwrap(),
            &handshake,
        )
        .unwrap();
        assert_eq!(pending.initiator_public_key(), &harness_public);
        let authorization: SignedAuthorization =
            serde_json::from_slice(pending.authorization()).unwrap();
        let ring = KeyRing::new(verification_key, None).unwrap();
        ring.verify(&authorization, unix_seconds()).unwrap();
        assert_eq!(authorization.claims.environment_generation, 3);
        assert_eq!(authorization.claims.shard_generation, 5);
        assert_eq!(authorization.claims.protocol_version, 1);
        assert_eq!(authorization.claims.schema_digest, [7; 32]);
        let (mut transport, response) = pending.complete().unwrap();
        write_frame(
            &mut stream,
            &serde_json::to_vec(&json!({
                "kind": "peer_attached",
                "stream_id": binding.stream_id,
                "handshake": STANDARD.encode(response),
            }))
            .unwrap(),
        )
        .await
        .unwrap();

        let mut receiver = SequenceReceiver::new();
        let mut decoder = MessageDecoder::new();
        let mut send_sequence = 0;
        let open =
            receive_noise_message(&mut stream, &mut transport, &mut receiver, &mut decoder).await;
        assert_eq!(
            serde_json::from_slice::<Value>(&open).unwrap()["kind"],
            "open"
        );
        send_noise_message(
            &mut stream,
            &mut transport,
            &mut send_sequence,
            &serde_json::to_vec(&json!({
                "kind": "opened",
                "stream_id": "operation-1",
            }))
            .unwrap(),
        )
        .await;

        let data =
            receive_noise_message(&mut stream, &mut transport, &mut receiver, &mut decoder).await;
        let data: Value = serde_json::from_slice(&data).unwrap();
        assert_eq!(data["kind"], "data");
        assert_eq!(
            STANDARD.decode(data["payload"].as_str().unwrap()).unwrap(),
            peer_command
        );
        send_noise_message(
            &mut stream,
            &mut transport,
            &mut send_sequence,
            &serde_json::to_vec(&json!({
                "kind": "data",
                "stream_id": "operation-1",
                "payload": STANDARD.encode(b"secret-output"),
            }))
            .unwrap(),
        )
        .await;
    });

    let mut child = Command::new(env!("CARGO_BIN_EXE_harness_proxy"))
        .args([
            "--unix-socket",
            local_path.to_str().unwrap(),
            "--rendezvous-socket",
            peer_path.to_str().unwrap(),
            "--config",
            config.to_str().unwrap(),
            "--harness-key-file",
            harness_key.to_str().unwrap(),
            "--authorization-key-file",
            authorization_key.to_str().unwrap(),
        ])
        .stdout(Stdio::null())
        .stderr(Stdio::inherit())
        .env("CREDENTIALS_DIRECTORY", &root)
        .kill_on_drop(true)
        .spawn()
        .unwrap();
    wait_for_socket(&local_path).await;

    let attach = json!({
        "kind": "attach",
        "request_id": "request-v1",
        "environment_id": "environment-v1",
        "environment_generation": 3,
        "registration_id": "registration-v1",
        "shard_generation": 5,
        "stream_id": "11".repeat(16),
        "protocol_version": 1,
        "schema_digest": "07".repeat(32),
        "authorization_id": "22".repeat(16),
        "expires_at": now + 2,
        "harness_key_id": harness_key_id,
        "authorization_key_id": "authorization-v1",
        "environment_noise_key_id": environment_public.key_id(),
        "environment_public_key": environment_public,
    });
    let mut local = UnixStream::connect(&local_path).await.unwrap();
    write_frame(&mut local, &serde_json::to_vec(&attach).unwrap())
        .await
        .unwrap();
    let attached: Value = serde_json::from_slice(&read_frame(&mut local).await.unwrap()).unwrap();
    assert_eq!(attached["kind"], "attached");
    assert_eq!(attached["harness_key_id"].as_str().unwrap().len(), 64);
    assert_eq!(attached["authorization_key_id"], "authorization-v1");

    write_frame(
        &mut local,
        &serde_json::to_vec(&json!({"kind": "open", "stream_id": "operation-1"})).unwrap(),
    )
    .await
    .unwrap();
    let opened: Value = serde_json::from_slice(&read_frame(&mut local).await.unwrap()).unwrap();
    assert_eq!(opened["kind"], "opened");
    write_frame(
        &mut local,
        &serde_json::to_vec(&json!({
            "kind": "data",
            "stream_id": "operation-1",
            "payload": STANDARD.encode(command),
            "eof": true,
        }))
        .unwrap(),
    )
    .await
    .unwrap();
    let result: Value = serde_json::from_slice(&read_frame(&mut local).await.unwrap()).unwrap();
    assert_eq!(
        STANDARD
            .decode(result["payload"].as_str().unwrap())
            .unwrap(),
        b"secret-output"
    );
    peer.await.unwrap();

    let mut replay = UnixStream::connect(&local_path).await.unwrap();
    write_frame(&mut replay, &serde_json::to_vec(&attach).unwrap())
        .await
        .unwrap();
    assert!(
        tokio::time::timeout(Duration::from_secs(1), read_frame(&mut replay))
            .await
            .unwrap()
            .is_err()
    );

    child.kill().await.unwrap();
    let _ = child.wait().await;
    std::fs::remove_dir_all(root).unwrap();
}

fn write_private(path: &Path, value: &[u8; 32]) {
    std::fs::write(path, value).unwrap();
    std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o400)).unwrap();
}

async fn wait_for_socket(path: &Path) {
    for _ in 0..200 {
        if path.exists() {
            return;
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    panic!("harness socket did not become ready");
}

fn unix_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs()
}

async fn send_noise_message(
    stream: &mut UnixStream,
    transport: &mut pwc_persistent_executor_transport::noise::NoiseTransport,
    sequence: &mut u64,
    message: &[u8],
) {
    for record in frame_records(message).unwrap() {
        let frame = RelayFrame::new(FrameKind::Data, 1, 0, *sequence, 0, record).unwrap();
        *sequence += 1;
        let ciphertext = transport.encrypt(&frame.encode()).unwrap();
        assert!(!contains(&ciphertext, b"secret-output"));
        write_frame(stream, &ciphertext).await.unwrap();
    }
}

async fn receive_noise_message(
    stream: &mut UnixStream,
    transport: &mut pwc_persistent_executor_transport::noise::NoiseTransport,
    receiver: &mut SequenceReceiver,
    decoder: &mut MessageDecoder,
) -> Vec<u8> {
    loop {
        let ciphertext = read_frame(stream).await.unwrap();
        assert!(!contains(&ciphertext, &[b'x'; 64]));
        assert!(!contains(&ciphertext, b"eHh4eHh4eHh4eHh4"));
        let frame = RelayFrame::decode(&transport.decrypt(&ciphertext).unwrap()).unwrap();
        for ordered in receiver.push(frame).unwrap() {
            let messages = decoder.push(ordered.payload()).unwrap();
            if let Some(message) = messages.into_iter().next() {
                return message;
            }
        }
    }
}

fn contains(haystack: &[u8], needle: &[u8]) -> bool {
    haystack
        .windows(needle.len())
        .any(|window| window == needle)
}
