use std::time::Duration;

use pwc_persistent_executor_transport::postgres_registry::PostgresRegistry;
use tokio_postgres::NoTls;
use uuid::Uuid;

/// A terminated registry backend must not leave the daemon failing every call
/// until restart (staging rendezvous ran 33 hours that way).
#[tokio::test]
async fn registry_reconnects_after_postgres_closes_its_connection() {
    let Ok(database_url) = std::env::var("PWC_EXECUTOR_RUST_TEST_DATABASE_URL") else {
        return;
    };
    let (admin, connection) = tokio_postgres::connect(&database_url, NoTls).await.unwrap();
    tokio::spawn(async move { connection.await.unwrap() });
    let present: Option<String> = admin
        .query_one(
            "SELECT to_regclass('chat_executor_registrations')::text",
            &[],
        )
        .await
        .unwrap()
        .get(0);
    if present.is_none() {
        admin
            .batch_execute(include_str!(
                "../../backend/database/migrations/add_chat_executor_registrations.sql"
            ))
            .await
            .unwrap();
    }

    let mut registry = PostgresRegistry::connect(&database_url, Uuid::new_v4())
        .await
        .unwrap();
    registry.expire_suspect_recoveries().await.unwrap();

    // Simulate a server-side disconnect of every other session.
    admin
        .execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity \
             WHERE datname = current_database() AND pid <> pg_backend_pid()",
            &[],
        )
        .await
        .unwrap();
    tokio::time::sleep(Duration::from_millis(200)).await;

    let mut recovered = false;
    for _ in 0..3 {
        if registry.expire_suspect_recoveries().await.is_ok() {
            recovered = true;
            break;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    assert!(
        recovered,
        "registry never reconnected after its backend was terminated"
    );
}
