mod common;

use std::time::{Duration, Instant};
use token_service_client::{Token16, TokenServiceClient, TokenServiceError, VerificationResult};

#[tokio::test]
async fn test_custom_timeout_default_applies_to_all_operations() {
    let mut client = TokenServiceClient::<Token16, common::UserUuid>::new(
        common::server_url(),
        Duration::from_secs(10),
    );
    client.connect().await.unwrap();

    let user_id = common::test_user_id();
    let token = client.issue_token(&user_id).await.unwrap();

    let res = client.verify_token(&token).await.unwrap();
    assert_eq!(res, VerificationResult::Valid(user_id));

    client.revoke_token(&token).await.unwrap();
}

#[tokio::test]
async fn test_timeout_on_slow_server() {
    let toxiproxy_api = common::ToxiproxyApi::new();
    let api_base = "http://127.0.0.1:8474";
    let proxy_name = "test_timeout_on_slow_server";
    let server_url = common::server_url();

    let _guard = toxiproxy_api
        .create_proxy(
            api_base,
            proxy_name,
            "tokenservice",
            50051,
            common::toxiproxy_grpc_listen_port(),
        )
        .await
        .unwrap();

    toxiproxy_api
        .add_latency(api_base, proxy_name, 2000, Some("latency"))
        .await
        .unwrap();

    let mut client = TokenServiceClient::<Token16, common::UserUuid>::new(
        &server_url,
        Duration::from_millis(500),
    );
    client.connect().await.unwrap();

    let user_id = common::test_user_id();

    // issue_token
    let start = Instant::now();
    let issue_res = client.issue_token(&user_id).await;
    let duration = start.elapsed();
    assert_eq!(issue_res, Err(TokenServiceError::ServiceDisconnected));
    assert!(duration >= Duration::from_millis(500));
    assert!(duration < Duration::from_millis(1000));

    // verify_token
    let start = Instant::now();
    let verify_res = client.verify_token(&Token16::new([b'0'; 16])).await;
    let duration = start.elapsed();
    assert_eq!(verify_res, Err(TokenServiceError::ServiceDisconnected));
    assert!(duration >= Duration::from_millis(500));
    assert!(duration < Duration::from_millis(1000));

    // revoke_token
    let start = Instant::now();
    let revoke_res = client.revoke_token(&Token16::new([b'0'; 16])).await;
    let duration = start.elapsed();
    assert_eq!(revoke_res, Err(TokenServiceError::ServiceDisconnected));
    assert!(duration >= Duration::from_millis(500));
    assert!(duration < Duration::from_millis(1000));
}

#[tokio::test]
async fn test_timeout_does_not_affect_local_cache_hits() {
    let toxiproxy_api = common::ToxiproxyApi::new();
    let api_base = "http://127.0.0.1:8474";
    let server_url = common::server_url();

    let guard = toxiproxy_api
        .create_proxy(
            api_base,
            "test_timeout_does_not_affect_local_cache_hits",
            "tokenservice",
            50051,
            common::toxiproxy_grpc_listen_port(),
        )
        .await
        .unwrap();

    let mut client =
        TokenServiceClient::<Token16, common::UserUuid>::new(&server_url, Duration::from_secs(1))
            .with_local_cache_ttl(Duration::from_secs(60));
    client.connect().await.unwrap();

    // 1. Issue and verify to populate local cache
    let user_id = common::test_user_id();
    let token = client.issue_token(&user_id).await.unwrap();
    let res1 = client.verify_token(&token).await.unwrap();
    assert_eq!(res1, VerificationResult::Valid(user_id.clone()));
    // 2. Stop the server (by deleting proxy)
    drop(guard);
    // 3. Verify again (should hit local cache)
    let start = Instant::now();
    let res2 = client.verify_token(&token).await.unwrap();
    let duration = start.elapsed();

    assert_eq!(res2, VerificationResult::ValidDegraded(user_id));
    assert!(duration < Duration::from_secs(1));
}

#[tokio::test]
async fn test_timeout_on_slow_redis() {
    let toxiproxy_api = common::ToxiproxyApi::new();
    let api_base = "http://127.0.0.1:8474";
    let proxy_name = "test_timeout_on_slow_redis";
    let server_url = common::server_url();

    let _guard = toxiproxy_api
        .create_proxy(
            api_base,
            proxy_name,
            "redis",
            6379,
            common::toxiproxy_redis_listen_port(),
        )
        .await
        .unwrap();

    toxiproxy_api
        .add_latency(api_base, proxy_name, 2000, Some("latency"))
        .await
        .unwrap();

    let mut client = TokenServiceClient::<Token16, common::UserUuid>::new(
        &server_url,
        Duration::from_millis(500),
    );
    client.connect().await.unwrap();

    let user_id = common::test_user_id();

    // issue_token
    let start = Instant::now();
    let issue_res = client.issue_token(&user_id).await;
    let duration = start.elapsed();
    assert_eq!(issue_res, Err(TokenServiceError::StorageDisconnected));
    assert!(duration >= Duration::from_millis(500));
    assert!(duration < Duration::from_millis(1000));

    // verify_token
    let start = Instant::now();
    let verify_res = client.verify_token(&Token16::new([b'0'; 16])).await;
    let duration = start.elapsed();
    assert_eq!(verify_res, Err(TokenServiceError::StorageDisconnected));
    assert!(duration >= Duration::from_millis(500));
    assert!(duration < Duration::from_millis(1000));

    // revoke_token
    let start = Instant::now();
    let revoke_res = client.revoke_token(&Token16::new([b'0'; 16])).await;
    let duration = start.elapsed();
    assert_eq!(revoke_res, Err(TokenServiceError::StorageDisconnected));
    assert!(duration >= Duration::from_millis(500));
    assert!(duration < Duration::from_millis(1000));
}
