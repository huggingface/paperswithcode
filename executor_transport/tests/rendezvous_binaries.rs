use std::process::Command;

const ROUTE: &str = "/v1/environment";

#[test]
fn environment_accepts_only_the_exact_tls_hostname_and_route() {
    let binary = env!("CARGO_BIN_EXE_environment");
    for url in [
        "wss://chat-executor.paperswithcode.co/v1/environment",
        "wss://chat-executor.staging.paperswithcode.co/v1/environment",
    ] {
        assert!(
            Command::new(binary)
                .args(["--validate-url", url])
                .status()
                .unwrap()
                .success()
        );
    }
    for url in [
        "ws://chat-executor.paperswithcode.co/v1/environment",
        "wss://paperswithcode.co/v1/environment",
        "wss://chat-executor.paperswithcode.co/wrong",
        "wss://chat-executor.paperswithcode.co:8443/v1/environment",
    ] {
        assert!(
            !Command::new(binary)
                .args(["--validate-url", url])
                .status()
                .unwrap()
                .success()
        );
    }
}

#[test]
fn environment_self_test_exposes_only_public_identity_metadata() {
    let output = Command::new(env!("CARGO_BIN_EXE_environment"))
        .arg("--self-test")
        .output()
        .unwrap();
    assert!(output.status.success());
    let report = String::from_utf8(output.stdout).unwrap();
    assert!(report.contains("public_noise_key_id"));
    assert!(report.contains("Noise_hybridIK"));
    assert!(!report.contains("private"));
    assert!(!report.contains("secret"));
}

#[test]
fn rendezvous_self_test_declares_unix_only_bounded_contract() {
    let output = Command::new(env!("CARGO_BIN_EXE_rendezvous"))
        .arg("--self-test")
        .output()
        .unwrap();
    assert!(output.status.success());
    let report: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["listener"], "unix");
    assert_eq!(report["route"], ROUTE);
    assert_eq!(report["preauth_frame_bytes"], 2_048);
    assert_eq!(report["preauth_deadline_ms"], 2_000);
    assert_eq!(report["heartbeat_ms"], 5_000);
    assert_eq!(report["suspect_ms"], 15_000);
    assert!(report.get("tcp_listener").is_none());
}
