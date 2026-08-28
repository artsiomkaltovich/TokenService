use std::marker::PhantomData;
use std::time::Duration;

use crate::models::{Token16, TokenServiceError, TokenType, UserId, VerificationResult};

pub struct TokenServiceClient<T: TokenType = Token16, U: UserId = u32> {
    pub server_url: String,
    pub timeout: Duration,
    pub token_ttl: Option<Duration>,
    pub local_cache_ttl: Duration,
    pub backoff_max_delay: Duration,
    _connected: bool,
    _marker: PhantomData<(T, U)>,
}

impl<T: TokenType, U: UserId> TokenServiceClient<T, U> {
    pub fn new(server_url: impl Into<String>, timeout: Duration) -> Self {
        Self {
            server_url: server_url.into(),
            timeout,
            token_ttl: None,
            local_cache_ttl: Duration::from_secs(60),
            backoff_max_delay: Duration::from_millis(500),
            _connected: false,
            _marker: PhantomData,
        }
    }

    pub fn with_token_ttl(mut self, ttl: Duration) -> Self {
        self.token_ttl = Some(ttl);
        self
    }

    pub fn with_local_cache_ttl(mut self, local_cache_ttl: Duration) -> Self {
        self.local_cache_ttl = local_cache_ttl;
        self
    }

    pub fn with_backoff_max_delay(mut self, backoff_max_delay: Duration) -> Self {
        self.backoff_max_delay = backoff_max_delay;
        self
    }

    pub async fn connect(&mut self) -> Result<(), TokenServiceError> {
        unimplemented!("TokenServiceClient is not implemented yet")
    }

    pub async fn close(&mut self) -> Result<(), TokenServiceError> {
        unimplemented!("TokenServiceClient is not implemented yet")
    }

    pub async fn issue_token(&self, _user_id: &U) -> Result<T, TokenServiceError> {
        unimplemented!("TokenServiceClient is not implemented yet")
    }

    pub async fn verify_token(
        &self,
        _token: &T,
    ) -> Result<VerificationResult<U>, TokenServiceError> {
        unimplemented!("TokenServiceClient is not implemented yet")
    }

    pub async fn revoke_token(&self, _token: &T) -> Result<(), TokenServiceError> {
        unimplemented!("TokenServiceClient is not implemented yet")
    }
}
