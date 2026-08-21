mod common;

use std::time::Duration;
use token_service_client::{Token16, TokenServiceClient, TokenServiceError, VerificationResult};

use crate::common::simulate_service_reconnect;

#[tokio::test]
async fn test_local_in_memory_cache_hit() {
    let toxiproxy_api = common::ToxiproxyApi::new();
    let api_base = "http://127.0.0.1:8474";
    let server_url = common::server_url();

    let guard = toxiproxy_api
        .create_proxy(
            api_base,
            "test_local_in_memory_cache_hit",
            "tokenservice",
            50051,
            common::toxiproxy_grpc_listen_port(),
        )
        .await
        .unwrap();

    let mut client =
        TokenServiceClient::<Token16, common::UserUuid>::new(&server_url, Duration::from_secs(5))
            .with_local_cache_ttl(Duration::from_secs(60));
    client.connect().await.unwrap();

    let user_id = common::test_user_id();
    let token = client.issue_token(&user_id).await.unwrap();
    let res1 = client.verify_token(&token).await.unwrap();
    assert_eq!(res1, VerificationResult::Valid(user_id.clone()));

    // Simulate stopping server process by deleting the proxy
    drop(guard);

    let res2 = client.verify_token(&token).await.unwrap();
    assert_eq!(res2, VerificationResult::ValidDegraded(user_id));
}

#[tokio::test]
async fn test_stream_outage_and_safety_ttl_eviction() {
    let toxiproxy_api = common::ToxiproxyApi::new();
    let api_base = "http://127.0.0.1:8474";
    let server_url = common::server_url();

    let guard = toxiproxy_api
        .create_proxy(
            api_base,
            "test_stream_outage_and_safety_ttl_eviction",
            "tokenservice",
            50051,
            common::toxiproxy_grpc_listen_port(),
        )
        .await
        .unwrap();

    let mut client =
        TokenServiceClient::<Token16, common::UserUuid>::new(&server_url, Duration::from_secs(5))
            .with_local_cache_ttl(Duration::from_secs(1));
    client.connect().await.unwrap();

    let user_id = common::test_user_id();
    let token = client.issue_token(&user_id).await.unwrap();
    let res1 = client.verify_token(&token).await.unwrap();
    assert_eq!(res1, VerificationResult::Valid(user_id));

    // Disconnect stream/simulate outage by deleting the proxy
    drop(guard);
    tokio::time::sleep(Duration::from_secs(2)).await;

    let res2 = client.verify_token(&token).await;
    assert_eq!(res2, Err(TokenServiceError::ServiceDisconnected));
}

#[tokio::test]
async fn test_client_grpc_stream_auto_reconnect() {
    let toxiproxy_api = common::ToxiproxyApi::new();
    let api_base = "test_client_grpc_stream_auto_reconnect";
    let proxy_name = "test_client_grpc_stream_auto_reconnect";
    let server_url = common::server_url();

    let guard = toxiproxy_api
        .create_proxy(
            api_base,
            proxy_name,
            "tokenservice",
            50051,
            common::toxiproxy_grpc_listen_port(),
        )
        .await
        .unwrap();

    let mut client1 =
        TokenServiceClient::<Token16, common::UserUuid>::new(&server_url, Duration::from_secs(5))
            .with_backoff_max_delay(Duration::from_secs(1));
    client1.connect().await.unwrap();

    let user_id = common::test_user_id();
    let token = client1.issue_token(&user_id).await.unwrap();

    let mut client2 =
        TokenServiceClient::<Token16, common::UserUuid>::new(&server_url, Duration::from_secs(5))
            .with_backoff_max_delay(Duration::from_secs(1));
    client2.connect().await.unwrap();

    assert_eq!(
        client2.verify_token(&token).await.unwrap(),
        VerificationResult::Valid(user_id)
    );

    let (_, _) = tokio::join!(
        tokio::time::sleep(Duration::from_secs(2)),
        simulate_service_reconnect(
            &toxiproxy_api,
            api_base,
            proxy_name,
            "tokenservice",
            50051,
            common::toxiproxy_grpc_listen_port(),
            Duration::from_millis(200),
            guard
        )
    );

    client1.revoke_token(&token).await.unwrap();

    // give a time for a revokation event to appear.
    // TODO: use something smarter
    tokio::time::sleep(Duration::from_secs(1)).await;
    assert_eq!(
        client2.verify_token(&token).await.unwrap(),
        VerificationResult::Invalid
    );
}

#[tokio::test]
async fn test_uncached_verify_miss_fails_on_service_disconnect() {
    let toxiproxy_api = common::ToxiproxyApi::new();
    let api_base = "http://127.0.0.1:8474";
    let server_url = common::server_url();

    let guard = toxiproxy_api
        .create_proxy(
            api_base,
            "test_uncached_verify_miss_fails_on_service_disconnect",
            "tokenservice",
            50051,
            common::toxiproxy_grpc_listen_port(),
        )
        .await
        .unwrap();

    let mut client =
        TokenServiceClient::<Token16, common::UserUuid>::new(&server_url, Duration::from_secs(5));
    client.connect().await.unwrap();

    drop(guard);

    let res = client.verify_token(&Token16::new([b'0'; 16])).await;
    assert_eq!(res, Err(TokenServiceError::ServiceDisconnected));
}

#[tokio::test]
async fn test_issue_token_fails_on_service_disconnect() {
    let toxiproxy_api = common::ToxiproxyApi::new();
    let api_base = "http://127.0.0.1:8474";
    let server_url = common::server_url();

    let guard = toxiproxy_api
        .create_proxy(
            api_base,
            "test_issue_token_fails_on_service_disconnect",
            "tokenservice",
            50051,
            common::toxiproxy_grpc_listen_port(),
        )
        .await
        .unwrap();

    let mut client =
        TokenServiceClient::<Token16, common::UserUuid>::new(&server_url, Duration::from_secs(5));
    client.connect().await.unwrap();

    drop(guard);

    let user_id = common::test_user_id();
    let res = client.issue_token(&user_id).await;
    assert_eq!(res, Err(TokenServiceError::ServiceDisconnected));
}

#[tokio::test]
async fn test_revoke_token_fails_on_service_disconnect() {
    let toxiproxy_api = common::ToxiproxyApi::new();
    let api_base = "http://127.0.0.1:8474";
    let server_url = common::server_url();

    let guard = toxiproxy_api
        .create_proxy(
            api_base,
            "test_revoke_token_fails_on_service_disconnect",
            "tokenservice",
            50051,
            common::toxiproxy_grpc_listen_port(),
        )
        .await
        .unwrap();

    let mut client =
        TokenServiceClient::<Token16, common::UserUuid>::new(&server_url, Duration::from_secs(5));
    client.connect().await.unwrap();

    drop(guard);

    let res = client.revoke_token(&Token16::new([b'0'; 16])).await;
    assert_eq!(res, Err(TokenServiceError::ServiceDisconnected));
}

#[tokio::test]
async fn test_uncached_verify_miss_fails_on_storage_disconnect() {
    let toxiproxy_api = common::ToxiproxyApi::new();
    let api_base = "http://127.0.0.1:8474";
    let server_url = common::server_url();

    let guard = toxiproxy_api
        .create_proxy(
            api_base,
            "test_uncached_verify_miss_fails_on_storage_disconnect",
            "redis",
            6379,
            common::toxiproxy_redis_listen_port(),
        )
        .await
        .unwrap();

    let mut client =
        TokenServiceClient::<Token16, common::UserUuid>::new(&server_url, Duration::from_secs(1));
    client.connect().await.unwrap();

    drop(guard);

    let res = client.verify_token(&Token16::new([b'0'; 16])).await;
    assert_eq!(res, Err(TokenServiceError::StorageDisconnected));
}

#[tokio::test]
async fn test_issue_token_fails_on_storage_disconnect() {
    let toxiproxy_api = common::ToxiproxyApi::new();
    let api_base = "http://127.0.0.1:8474";
    let server_url = common::server_url();

    let guard = toxiproxy_api
        .create_proxy(
            api_base,
            "test_issue_token_fails_on_storage_disconnect",
            "redis",
            6379,
            common::toxiproxy_redis_listen_port(),
        )
        .await
        .unwrap();

    let mut client =
        TokenServiceClient::<Token16, common::UserUuid>::new(&server_url, Duration::from_secs(1));
    client.connect().await.unwrap();

    drop(guard);

    let user_id = common::test_user_id();
    let res = client.issue_token(&user_id).await;
    assert_eq!(res, Err(TokenServiceError::StorageDisconnected));
}

#[tokio::test]
async fn test_revoke_token_fails_on_storage_disconnect() {
    let toxiproxy_api = common::ToxiproxyApi::new();
    let api_base = "http://127.0.0.1:8474";
    let server_url = common::server_url();

    let guard = toxiproxy_api
        .create_proxy(
            api_base,
            "redis_proxy_drop_2_9",
            "redis",
            6379,
            common::toxiproxy_redis_listen_port(),
        )
        .await
        .unwrap();

    let mut client =
        TokenServiceClient::<Token16, common::UserUuid>::new(&server_url, Duration::from_secs(1));
    client.connect().await.unwrap();

    drop(guard);

    let res = client.revoke_token(&Token16::new([b'0'; 16])).await;
    assert_eq!(res, Err(TokenServiceError::StorageDisconnected));
}
