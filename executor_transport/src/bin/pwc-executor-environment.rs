use std::process::Command;
use std::time::Instant;

use pwc_persistent_executor_transport::noise::{
    InitiatorHandshake, NoiseIdentity, PendingResponderHandshake, prologue,
};
use serde_json::json;

fn main() {
    if std::env::args().skip(1).collect::<Vec<_>>() != ["--self-test"] {
        eprintln!("usage: pwc-executor-environment --self-test");
        std::process::exit(2);
    }
    match self_test() {
        Ok(report) => println!("{report}"),
        Err(error) => {
            eprintln!("self-test failed: {error}");
            std::process::exit(1);
        }
    }
}

fn self_test() -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let attach_started = Instant::now();
    let harness = NoiseIdentity::generate()?;
    let environment = NoiseIdentity::generate()?;
    let transcript = prologue("candidate-image", "self-test", "stream-0");
    let (initiator, request) = InitiatorHandshake::start(
        &harness,
        &environment.public_key(),
        &transcript,
        b"self-test-only",
    )?;
    let responder = PendingResponderHandshake::read_request(&environment, &transcript, &request)?;
    if responder.initiator_public_key() != &harness.public_key()
        || responder.authorization() != b"self-test-only"
    {
        return Err("Hybrid IK peer authorization mismatch".into());
    }
    let (mut environment_transport, response) = responder.complete()?;
    let mut harness_transport = initiator.finish(&response)?;
    let command_ciphertext = harness_transport.encrypt(b"pwd")?;
    let command = environment_transport.decrypt(&command_ciphertext)?;
    let noise_attach_us = attach_started.elapsed().as_micros() as u64;

    let command_started = Instant::now();
    let output = Command::new(std::str::from_utf8(&command)?).output()?;
    let command_us = command_started.elapsed().as_micros() as u64;
    let response_ciphertext = environment_transport.encrypt(&output.stdout)?;
    let response = harness_transport.decrypt(&response_ciphertext)?;
    if response != output.stdout {
        return Err("encrypted response mismatch".into());
    }

    Ok(json!({
        "protocol": "noise_hybrid_ik_v1",
        "command": "pwd",
        "exit_code": output.status.code(),
        "noise_attach_us": noise_attach_us,
        "command_us": command_us,
    }))
}
