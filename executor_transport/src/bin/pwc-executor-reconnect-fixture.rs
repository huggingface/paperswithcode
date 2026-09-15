use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::time::Instant;

use pwc_persistent_executor_transport::noise::{
    InitiatorHandshake, NoiseIdentity, NoiseTransport, PendingResponderHandshake, prologue,
};
use serde_json::json;

const ADDRESS: &str = "0.0.0.0:8787";
const MAX_FRAME: usize = 64 * 1024;

fn main() {
    let arguments = std::env::args().skip(1).collect::<Vec<_>>();
    let result = match arguments.as_slice() {
        [mode] if mode == "server" => server(),
        [mode, host, port, token] if mode == "client" => client(host, port, token),
        _ => {
            eprintln!("usage: pwc-executor-reconnect-fixture server|client HOST PORT TOKEN");
            std::process::exit(2);
        }
    };
    if let Err(error) = result {
        eprintln!("reconnect fixture failed: {error}");
        std::process::exit(1);
    }
}

fn server() -> Result<(), Box<dyn std::error::Error>> {
    let identity = NoiseIdentity::generate()?;
    let listener = TcpListener::bind(ADDRESS)?;
    let (mut transport, authorization) = loop {
        let (mut stream, _) = listener.accept()?;
        stream.set_nodelay(true)?;
        match first_server_connection(&identity, &mut stream) {
            Ok(value) => break value,
            Err(_) => continue,
        }
    };
    loop {
        let (mut stream, _) = listener.accept()?;
        stream.set_nodelay(true)?;
        let token = match read_frame(&mut stream) {
            Ok(value) => value,
            Err(_) => continue,
        };
        if token != authorization {
            continue;
        }
        let command = transport.decrypt(&read_frame(&mut stream)?)?;
        if command != b"resume" {
            return Err("resume command mismatch".into());
        }
        write_frame(&mut stream, &transport.encrypt(b"resumed")?)?;
        return Ok(());
    }
}

fn first_server_connection(
    identity: &NoiseIdentity,
    stream: &mut TcpStream,
) -> Result<(NoiseTransport, Vec<u8>), Box<dyn std::error::Error>> {
    write_frame(stream, &serde_json::to_vec(&identity.public_key())?)?;
    let transcript = prologue("modal-reconnect", "task0", "shared-stream");
    let pending =
        PendingResponderHandshake::read_request(identity, &transcript, &read_frame(stream)?)?;
    let authorization = pending.authorization().to_vec();
    if authorization.is_empty() {
        return Err("authorization is empty".into());
    }
    let (mut transport, response) = pending.complete()?;
    write_frame(stream, &response)?;
    let command = transport.decrypt(&read_frame(stream)?)?;
    if command != b"initial" {
        return Err("initial command mismatch".into());
    }
    write_frame(stream, &transport.encrypt(b"ready")?)?;
    Ok((transport, authorization))
}

fn client(host: &str, port: &str, token: &str) -> Result<(), Box<dyn std::error::Error>> {
    let address = format!("{host}:{port}");
    let mut first = TcpStream::connect(&address)?;
    first.set_nodelay(true)?;
    let remote = serde_json::from_slice(&read_frame(&mut first)?)?;
    let identity = NoiseIdentity::generate()?;
    let transcript = prologue("modal-reconnect", "task0", "shared-stream");
    let (initiator, request) =
        InitiatorHandshake::start(&identity, &remote, &transcript, token.as_bytes())?;
    write_frame(&mut first, &request)?;
    let mut transport = initiator.finish(&read_frame(&mut first)?)?;
    write_frame(&mut first, &transport.encrypt(b"initial")?)?;
    if transport.decrypt(&read_frame(&mut first)?)? != b"ready" {
        return Err("initial response mismatch".into());
    }
    drop(first);

    let reconnect_started = Instant::now();
    let mut second = TcpStream::connect(&address)?;
    second.set_nodelay(true)?;
    write_frame(&mut second, token.as_bytes())?;
    write_frame(&mut second, &transport.encrypt(b"resume")?)?;
    if transport.decrypt(&read_frame(&mut second)?)? != b"resumed" {
        return Err("resumed response mismatch".into());
    }
    println!(
        "{}",
        json!({
            "reconnect_ms": reconnect_started.elapsed().as_secs_f64() * 1000.0,
            "same_noise_transport": true,
            "authorization_bound": true,
        })
    );
    Ok(())
}

fn write_frame(stream: &mut TcpStream, value: &[u8]) -> std::io::Result<()> {
    if value.len() > MAX_FRAME {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "frame is too large",
        ));
    }
    stream.write_all(&(value.len() as u32).to_be_bytes())?;
    stream.write_all(value)
}

fn read_frame(stream: &mut TcpStream) -> std::io::Result<Vec<u8>> {
    let mut length = [0; 4];
    stream.read_exact(&mut length)?;
    let length = u32::from_be_bytes(length) as usize;
    if length > MAX_FRAME {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "frame is too large",
        ));
    }
    let mut value = vec![0; length];
    stream.read_exact(&mut value)?;
    Ok(value)
}
