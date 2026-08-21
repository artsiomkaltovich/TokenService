use std::fmt::Debug;

#[derive(thiserror::Error, Debug, Clone, PartialEq, Eq)]
pub enum TokenServiceError {
    #[error("Failed to communicate with TokenService gRPC server")]
    ServiceDisconnected,
    #[error("TokenService storage backend (Redis) is unreachable")]
    StorageDisconnected,
    #[error("Invalid token format or length")]
    InvalidTokenFormat,
}

pub trait TokenType: Clone + PartialEq + Eq + Debug + Send + Sync + 'static {
    fn byte_len() -> usize;
    fn as_bytes(&self) -> &[u8];
    fn from_slice(bytes: &[u8]) -> Result<Self, TokenServiceError>;
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Token16(pub [u8; 16]);

impl Token16 {
    pub fn new(bytes: [u8; 16]) -> Self {
        Self(bytes)
    }

    pub fn as_bytes(&self) -> &[u8] {
        &self.0
    }
}

impl TokenType for Token16 {
    fn byte_len() -> usize {
        16
    }

    fn as_bytes(&self) -> &[u8] {
        &self.0
    }

    fn from_slice(bytes: &[u8]) -> Result<Self, TokenServiceError> {
        let array: [u8; 16] = bytes
            .try_into()
            .map_err(|_| TokenServiceError::InvalidTokenFormat)?;
        Ok(Self(array))
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Token32(pub [u8; 32]);

impl Token32 {
    pub fn new(bytes: [u8; 32]) -> Self {
        Self(bytes)
    }

    pub fn as_bytes(&self) -> &[u8] {
        &self.0
    }
}

impl TokenType for Token32 {
    fn byte_len() -> usize {
        32
    }

    fn as_bytes(&self) -> &[u8] {
        &self.0
    }

    fn from_slice(bytes: &[u8]) -> Result<Self, TokenServiceError> {
        let array: [u8; 32] = bytes
            .try_into()
            .map_err(|_| TokenServiceError::InvalidTokenFormat)?;
        Ok(Self(array))
    }
}

pub trait UserId: Clone + PartialEq + Eq + Debug + Send + Sync + 'static {
    fn to_bytes(&self) -> Vec<u8>;
    fn from_bytes(bytes: &[u8]) -> Result<Self, TokenServiceError>;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum VerificationResult<U: UserId = u32> {
    Valid(U),
    ValidDegraded(U),
    Invalid,
}

impl UserId for String {
    fn to_bytes(&self) -> Vec<u8> {
        self.as_bytes().to_vec()
    }

    fn from_bytes(bytes: &[u8]) -> Result<Self, TokenServiceError> {
        String::from_utf8(bytes.to_vec()).map_err(|_| TokenServiceError::InvalidTokenFormat)
    }
}

impl UserId for u32 {
    fn to_bytes(&self) -> Vec<u8> {
        u32::to_be_bytes(*self).to_vec()
    }

    fn from_bytes(bytes: &[u8]) -> Result<Self, TokenServiceError> {
        let bytes: &[u8; 4] = bytes
            .try_into()
            .map_err(|_| TokenServiceError::InvalidTokenFormat)?;
        Ok(u32::from_be_bytes(*bytes))
    }
}
