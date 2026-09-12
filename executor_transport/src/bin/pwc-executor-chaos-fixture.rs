use std::io::{self, Write};
use std::process::Command;
use std::thread;
use std::time::Duration;

use pwc_persistent_executor_transport::noise::{
    InitiatorHandshake, NoiseIdentity, PendingResponderHandshake, prologue,
};
use serde_json::json;

const ACTORS: [&str; 4] = ["peer", "rendezvous", "harness", "worker"];
const BOUNDARIES: [&str; 4] = [
    "before_delivery",
    "after_acceptance",
    "during_execution",
    "after_terminal_before_delivery",
];

fn main() {
    let arguments = std::env::args().skip(1).collect::<Vec<_>>();
    if arguments.len() != 3 || arguments[0] != "--hold" {
        eprintln!("usage: pwc-executor-chaos-fixture --hold ACTOR BOUNDARY");
        std::process::exit(2);
    }
    if !ACTORS.contains(&arguments[1].as_str()) || !BOUNDARIES.contains(&arguments[2].as_str()) {
        eprintln!("actor or delivery boundary is invalid");
        std::process::exit(2);
    }
    if let Err(error) = hold(&arguments[1], &arguments[2]) {
        eprintln!("chaos fixture failed: {error}");
        std::process::exit(1);
    }
}

fn hold(actor: &str, boundary: &str) -> Result<(), Box<dyn std::error::Error>> {
    let harness = NoiseIdentity::generate()?;
    let environment = NoiseIdentity::generate()?;
    let transcript = prologue("chaos-environment", "chaos-registration", "chaos-stream");
    let (initiator, request) = InitiatorHandshake::start(
        &harness,
        &environment.public_key(),
        &transcript,
        b"chaos-authorization",
    )?;
    let responder = PendingResponderHandshake::read_request(&environment, &transcript, &request)?;
    let (mut environment_transport, response) = responder.complete()?;
    let mut harness_transport = initiator.finish(&response)?;

    let mut command_starts = 0;
    let mut child_pid = None;
    let mut terminal_ciphertext_buffered = false;
    if boundary != "before_delivery" {
        let ciphertext = harness_transport.encrypt(b"sleep 230")?;
        let command = environment_transport.decrypt(&ciphertext)?;
        if command != b"sleep 230" {
            return Err("encrypted command mismatch".into());
        }
    }
    if matches!(
        boundary,
        "during_execution" | "after_terminal_before_delivery"
    ) {
        command_starts = 1;
    }
    if boundary == "during_execution" {
        let child = Command::new("sleep").arg("230").spawn()?;
        child_pid = Some(child.id());
        std::mem::forget(child);
    }
    if boundary == "after_terminal_before_delivery" {
        let result = environment_transport.encrypt(b"terminal-result")?;
        terminal_ciphertext_buffered = true;
        if result.is_empty() {
            return Err("terminal ciphertext is empty".into());
        }
    }
    println!(
        "{}",
        json!({
            "actor": actor,
            "boundary": boundary,
            "noise_handshake_complete": true,
            "encrypted_stream_active": true,
            "command_starts": command_starts,
            "child_pid": child_pid,
            "terminal_ciphertext_buffered": terminal_ciphertext_buffered,
        })
    );
    io::stdout().flush()?;
    loop {
        thread::sleep(Duration::from_secs(60));
    }
}
