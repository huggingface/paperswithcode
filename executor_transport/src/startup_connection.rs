//! Prepare TCP/TLS during local startup without opening an unready WebSocket.

use std::future::Future;
use std::sync::Arc;
use std::time::{Duration, Instant};

use tokio::net::TcpStream;
use tokio::time::timeout;
use tokio_tungstenite::tungstenite::protocol::WebSocketConfig;
use tokio_tungstenite::{MaybeTlsStream, WebSocketStream, client_async_with_config};
use url::Url;

type Error = Box<dyn std::error::Error>;
type Socket = MaybeTlsStream<TcpStream>;

/// The caller validates the destination and bounds its readiness future.
/// Only TCP/TLS may precede readiness: upgrading starts the server's short
/// preauthentication deadline, and registration makes the executor claimable.
/// The network budget covers preparation plus upgrade, excluding daemon wait.
pub async fn connect_when_ready<F>(
    url: &str,
    config: WebSocketConfig,
    network_budget: Duration,
    ready: F,
) -> Result<WebSocketStream<Socket>, Error>
where
    F: Future<Output = Result<(), Error>>,
{
    let prepare = async {
        let started = Instant::now();
        let socket = timeout(network_budget, prepare_socket(url))
            .await
            .map_err(|_| "rendezvous connection timed out")??;
        Ok::<_, Error>((socket, network_budget.saturating_sub(started.elapsed())))
    };
    let ((socket, remaining), ()) = tokio::try_join!(prepare, ready)?;
    if remaining.is_zero() {
        return Err("rendezvous connection timed out".into());
    }
    let (socket, _) = timeout(
        remaining,
        client_async_with_config(url, socket, Some(config)),
    )
    .await
    .map_err(|_| "rendezvous connection timed out")??;
    Ok(socket)
}

async fn prepare_socket(address: &str) -> Result<Socket, Error> {
    let url = Url::parse(address)?;
    if !matches!(url.scheme(), "ws" | "wss") {
        return Err("rendezvous URL rejected".into());
    }
    let host = url.host_str().ok_or("rendezvous host missing")?;
    let port = url
        .port_or_known_default()
        .ok_or("rendezvous port missing")?;
    let socket = TcpStream::connect((host, port)).await?;
    socket.set_nodelay(true)?;
    if url.scheme() == "ws" {
        return Ok(MaybeTlsStream::Plain(socket));
    }
    // Match tokio-tungstenite's existing webpki root and hostname checks.
    let roots = rustls::RootCertStore::from_iter(webpki_roots::TLS_SERVER_ROOTS.iter().cloned());
    let config = rustls::ClientConfig::builder()
        .with_root_certificates(roots)
        .with_no_client_auth();
    let name = rustls::pki_types::ServerName::try_from(host.to_owned())?;
    let socket = tokio_rustls::TlsConnector::from(Arc::new(config))
        .connect(name, socket)
        .await?;
    Ok(MaybeTlsStream::Rustls(socket))
}
