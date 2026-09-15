use std::process::Command;

#[test]
fn self_test_runs_hybrid_ik_before_pwd() {
    let output = Command::new(std::env::var("CARGO_BIN_EXE_pwc-executor-environment").unwrap())
        .arg("--self-test")
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let report: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();

    assert_eq!(report["protocol"], "noise_hybrid_ik_v1");
    assert_eq!(report["command"], "pwd");
    assert_eq!(report["exit_code"], 0);
    assert!(report["noise_attach_us"].as_u64().unwrap() > 0);
    assert!(report["command_us"].as_u64().unwrap() > 0);
}
