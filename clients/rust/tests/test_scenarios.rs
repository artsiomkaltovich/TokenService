mod common;

use std::time::Duration;
use token_service_client::{
    Token16, Token32, TokenServiceClient, TokenServiceError, VerificationResult,
};

#[tokio::test]
async fn test_issue_and_verify_token_happy_path() {
    let mut client = TokenServiceClient::<Token16, common::UserUuid>::new(
        common::server_url(),
        Duration::from_secs(5),
    );
    client.connect().await.unwrap();

    let user_id = common::test_user_id();
    let token = client.issue_token(&user_id).await.unwrap();
    assert_eq!(token.as_bytes().len(), 16);

    let res = client.verify_token(&token).await.unwrap();
    assert_eq!(res, VerificationResult::Valid(user_id));
}

#[tokio::test]
async fn test_connect_wasnt_called() {
    let client = TokenServiceClient::<Token16, common::UserUuid>::new(
        common::server_url(),
        Duration::from_secs(5),
    );
    let res = client.verify_token(&Token16::new([b'0'; 16])).await;
    assert_eq!(res, Err(TokenServiceError::ServiceDisconnected));
}

#[tokio::test]
async fn test_verify_invalid_or_non_existent_token() {
    let mut client = TokenServiceClient::<Token16, common::UserUuid>::new(
        common::server_url(),
        Duration::from_secs(5),
    );
    client.connect().await.unwrap();

    let res = client
        .verify_token(&Token16::new([b'0'; 16]))
        .await
        .unwrap();
    assert_eq!(res, VerificationResult::Invalid);
}

#[tokio::test]
async fn test_server_token_ttl_client_expiration() {
    let mut client = TokenServiceClient::<Token16, common::UserUuid>::new(
        common::server_url(),
        Duration::from_secs(5),
    )
    .with_token_ttl(Duration::from_secs(1));
    client.connect().await.unwrap();

    let user_id = common::test_user_id();
    let token = client.issue_token(&user_id).await.unwrap();

    tokio::time::sleep(Duration::from_secs(2)).await;

    let res = client.verify_token(&token).await.unwrap();
    assert_eq!(res, VerificationResult::Invalid);
}

#[tokio::test]
async fn test_server_token_ttl_server_expiration() {
    let user_id = common::test_user_id();
    let token = {
        let mut client1 = TokenServiceClient::<Token16, common::UserUuid>::new(
            common::server_url(),
            Duration::from_secs(5),
        )
        .with_token_ttl(Duration::from_secs(1));
        client1.connect().await.unwrap();
        client1.issue_token(&user_id).await.unwrap()
    };

    tokio::time::sleep(Duration::from_secs(2)).await;

    let mut client2 = TokenServiceClient::<Token16, common::UserUuid>::new(
        common::server_url(),
        Duration::from_secs(5),
    );
    client2.connect().await.unwrap();

    let res = client2.verify_token(&token).await.unwrap();
    assert_eq!(res, VerificationResult::Invalid);
}

#[tokio::test]
async fn test_explicit_token_revocation_single_node() {
    let mut client = TokenServiceClient::<Token16, common::UserUuid>::new(
        common::server_url(),
        Duration::from_secs(5),
    );
    client.connect().await.unwrap();

    let user_id = common::test_user_id();
    let token = client.issue_token(&user_id).await.unwrap();

    let res = client.verify_token(&token).await.unwrap();
    assert_eq!(res, VerificationResult::Valid(user_id));

    client.revoke_token(&token).await.unwrap();

    let res_after = client.verify_token(&token).await.unwrap();
    assert_eq!(res_after, VerificationResult::Invalid);
}

#[tokio::test]
async fn test_token32_payload_variant() {
    let mut client = TokenServiceClient::<Token32, common::UserUuid>::new(
        common::server_url(),
        Duration::from_secs(5),
    );
    client.connect().await.unwrap();

    let user_id = common::test_user_id();
    let token = client.issue_token(&user_id).await.unwrap();
    assert_eq!(token.as_bytes().len(), 32);

    let res = client.verify_token(&token).await.unwrap();
    assert_eq!(res, VerificationResult::Valid(user_id));
}

#[tokio::test]
async fn test_independent_token_revocation() {
    let mut client = TokenServiceClient::<Token16, common::UserUuid>::new(
        common::server_url(),
        Duration::from_secs(5),
    );
    client.connect().await.unwrap();

    let user_id = common::test_user_id();
    let t1 = client.issue_token(&user_id).await.unwrap();
    let t2 = client.issue_token(&user_id).await.unwrap();

    assert_eq!(
        client.verify_token(&t1).await.unwrap(),
        VerificationResult::Valid(user_id.clone())
    );
    assert_eq!(
        client.verify_token(&t2).await.unwrap(),
        VerificationResult::Valid(user_id.clone())
    );

    client.revoke_token(&t1).await.unwrap();

    assert_eq!(
        client.verify_token(&t1).await.unwrap(),
        VerificationResult::Invalid
    );
    assert_eq!(
        client.verify_token(&t2).await.unwrap(),
        VerificationResult::Valid(user_id)
    );
}

#[tokio::test]
async fn test_cached_tokens_do_not_outlive_server_side_tokens() {
    let user_id = common::test_user_id();
    let token = {
        let mut client1 = TokenServiceClient::<Token16, common::UserUuid>::new(
            common::server_url(),
            Duration::from_secs(5),
        )
        .with_token_ttl(Duration::from_secs(3))
        .with_local_cache_ttl(Duration::from_secs(60));
        client1.connect().await.unwrap();
        client1.issue_token(&user_id).await.unwrap()
    };

    tokio::time::sleep(Duration::from_secs(2)).await;

    let mut client2 = TokenServiceClient::<Token16, common::UserUuid>::new(
        common::server_url(),
        Duration::from_secs(5),
    )
    .with_local_cache_ttl(Duration::from_secs(60));
    client2.connect().await.unwrap();

    // First verify hits server, cached with remaining TTL = 1s
    assert_eq!(
        client2.verify_token(&token).await.unwrap(),
        VerificationResult::Valid(user_id)
    );

    tokio::time::sleep(Duration::from_secs(2)).await;

    // Reads local cache, remaining server TTL expired
    assert_eq!(
        client2.verify_token(&token).await.unwrap(),
        VerificationResult::Invalid
    );
}
