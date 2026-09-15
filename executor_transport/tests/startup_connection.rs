use std::sync::Arc;
use std::time::Duration;

use pwc_persistent_executor_transport::startup_connection::connect_when_ready;
use tokio::net::TcpListener;
use tokio::sync::oneshot;
use tokio::time::{sleep, timeout};
use tokio_tungstenite::tungstenite::protocol::WebSocketConfig;

#[tokio::test]
async fn tcp_starts_early_but_upgrade_waits_even_past_preauth_deadline() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("ws://{}", listener.local_addr().unwrap());
    let (ready_tx, ready_rx) = oneshot::channel();
    let client = connect_when_ready(
        &url,
        WebSocketConfig::default(),
        Duration::from_secs(1),
        async {
            ready_rx.await?;
            Ok(())
        },
    );
    let server = async {
        // A sequential connector would deadlock waiting for ready_rx here.
        let (tcp, _) = timeout(Duration::from_secs(1), listener.accept())
            .await
            .unwrap()
            .unwrap();
        let mut byte = [0];
        assert!(
            timeout(Duration::from_millis(2100), tcp.peek(&mut byte))
                .await
                .is_err()
        );
        ready_tx.send(()).unwrap();
        tokio_tungstenite::accept_async(tcp).await.unwrap()
    };
    let (client, server) = tokio::join!(client, server);
    let client = client.unwrap();
    let tokio_tungstenite::MaybeTlsStream::Plain(tcp) = client.get_ref() else {
        panic!("expected test TCP connection");
    };
    assert!(tcp.nodelay().unwrap());
    drop((client, server));
}

#[tokio::test]
async fn readiness_failure_drops_prepared_socket_without_upgrading() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("ws://{}", listener.local_addr().unwrap());
    let (ready_tx, ready_rx) = oneshot::channel();
    let client = connect_when_ready(
        &url,
        WebSocketConfig::default(),
        Duration::from_secs(1),
        async {
            ready_rx.await?;
            Err("daemon exited".into())
        },
    );
    let server = async {
        let (tcp, _) = listener.accept().await.unwrap();
        ready_tx.send(()).unwrap();
        let mut byte = [0];
        assert_eq!(
            timeout(Duration::from_secs(1), tcp.peek(&mut byte))
                .await
                .unwrap()
                .unwrap(),
            0
        );
    };
    let (result, ()) = tokio::join!(client, server);
    assert_eq!(result.unwrap_err().to_string(), "daemon exited");
}

#[tokio::test]
async fn stalled_upgrade_is_still_bounded() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("ws://{}", listener.local_addr().unwrap());
    let client = connect_when_ready(
        &url,
        WebSocketConfig::default(),
        Duration::from_millis(30),
        async { Ok(()) },
    );
    let server = async {
        let (tcp, _) = listener.accept().await.unwrap();
        sleep(Duration::from_millis(100)).await;
        drop(tcp);
    };
    let (result, ()) = tokio::join!(client, server);
    assert_eq!(
        result.unwrap_err().to_string(),
        "rendezvous connection timed out"
    );
}

#[tokio::test]
async fn stalled_tls_does_not_wait_for_daemon_or_fall_back_to_plaintext() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("wss://{}", listener.local_addr().unwrap());
    let client = connect_when_ready(
        &url,
        WebSocketConfig::default(),
        Duration::from_millis(30),
        std::future::pending(),
    );
    let server = async {
        let (tcp, _) = listener.accept().await.unwrap();
        sleep(Duration::from_millis(100)).await;
        drop(tcp);
    };
    let (result, ()) = tokio::join!(client, server);
    assert_eq!(
        result.unwrap_err().to_string(),
        "rendezvous connection timed out"
    );
}

#[tokio::test]
async fn untrusted_tls_certificate_is_rejected_before_readiness() {
    // Deliberately public, self-signed test identity; never a deployed credential.
    let cert = rustls::pki_types::CertificateDer::from(
        include_bytes!("fixtures/untrusted-localhost.der").to_vec(),
    );
    let key = rustls::pki_types::PrivatePkcs8KeyDer::from(
        include_bytes!("fixtures/untrusted-localhost-key.der").to_vec(),
    );
    let config = rustls::ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(vec![cert], key.into())
        .unwrap();
    let acceptor = tokio_rustls::TlsAcceptor::from(Arc::new(config));
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("wss://localhost:{}", listener.local_addr().unwrap().port());
    let client = connect_when_ready(
        &url,
        WebSocketConfig::default(),
        Duration::from_secs(1),
        std::future::pending(),
    );
    let server = async {
        let (tcp, _) = listener.accept().await.unwrap();
        assert!(acceptor.accept(tcp).await.is_err());
    };
    let (result, ()) = tokio::join!(client, server);
    let error = result.unwrap_err().to_string();
    assert!(error.contains("UnknownIssuer"), "{error}");
}
