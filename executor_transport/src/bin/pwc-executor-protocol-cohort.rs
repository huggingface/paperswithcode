use std::thread;
use std::time::{Duration, Instant};

use pwc_persistent_executor_transport::noise::{
    InitiatorHandshake, NoiseIdentity, PendingResponderHandshake, prologue,
};
use serde_json::json;

fn main() {
    let arguments = std::env::args().skip(1).collect::<Vec<_>>();
    if arguments.as_slice() != ["--run", "1000", "250"] {
        eprintln!("usage: pwc-executor-protocol-cohort --run 1000 250");
        std::process::exit(2);
    }
    match run() {
        Ok(report) => println!("{report}"),
        Err(error) => {
            eprintln!("protocol cohort failed: {error}");
            std::process::exit(1);
        }
    }
}

fn run() -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    let harness = NoiseIdentity::generate()?;
    let environment = NoiseIdentity::generate()?;
    let started = Instant::now();
    let mut ready_ms = Vec::with_capacity(1000);
    let mut handshake_ms = Vec::with_capacity(1000);
    for index in 0..1000 {
        let scheduled = Duration::from_secs_f64((index + 1) as f64 / 250.0);
        if let Some(delay) = scheduled.checked_sub(started.elapsed()) {
            thread::sleep(delay);
        }
        let handshake_started = Instant::now();
        let transcript = prologue("protocol-cohort", &format!("peer-{index:04}"), "stream");
        let (initiator, request) = InitiatorHandshake::start(
            &harness,
            &environment.public_key(),
            &transcript,
            format!("admitted-token-{index:04}").as_bytes(),
        )?;
        let responder =
            PendingResponderHandshake::read_request(&environment, &transcript, &request)?;
        let (mut environment_transport, response) = responder.complete()?;
        let mut harness_transport = initiator.finish(&response)?;
        let ciphertext = harness_transport.encrypt(b"ready")?;
        if environment_transport.decrypt(&ciphertext)? != b"ready" {
            return Err("transport readiness mismatch".into());
        }
        handshake_ms.push(handshake_started.elapsed().as_secs_f64() * 1000.0);
        ready_ms.push(started.elapsed().as_secs_f64() * 1000.0);
    }
    let p95 = percentile(&ready_ms, 0.95);
    let p99 = percentile(&ready_ms, 0.99);
    Ok(json!({
        "observations": ready_ms.len(),
        "starts_per_second_max": 250,
        "ready_p95_ms": p95,
        "ready_p99_ms": p99,
        "ready_max_ms": ready_ms.iter().copied().fold(0.0_f64, f64::max),
        "handshake_p95_ms": percentile(&handshake_ms, 0.95),
        "handshake_p99_ms": percentile(&handshake_ms, 0.99),
        "ready_ms": ready_ms,
    }))
}

fn percentile(values: &[f64], percentile: f64) -> f64 {
    let mut ordered = values.to_vec();
    ordered.sort_by(f64::total_cmp);
    ordered[((ordered.len() as f64 * percentile).ceil() as usize) - 1]
}
