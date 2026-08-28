# TokenService Specification & Developer Guide

## 1. Overview & Core Concept
**TokenService** (`TokenService`) is a high-performance session token manager designed for sub-microsecond authentication checks. It combines local in-memory client caching, real-time gRPC revocation streams, and Redis storage behind a multi-instance service layout.

Because `TokenService` uses **gRPC** and **Protocol Buffers**, creating a client SDK in virtually any programming language (Go, Java, C#, Node.js, etc.) is trivial—you simply run your language's standard `protoc` code generator on the `.proto` schema file.

---

## 2. Quick Start Example

Here is how simple using `TokenService` is in practice for standard session management.

### Rust Quick Start
```rust
use token_service_client::{TokenClient, Token16, UserId};
use uuid::Uuid;

// 1. Implement UserId trait for your application's user identifier type
#[derive(Debug, Clone, PartialEq, Eq)]
struct UserUUID(Uuid);

impl UserId for UserUUID {
    fn to_bytes(&self) -> Vec<u8> {
        self.0.as_bytes().to_vec()
    }

    fn from_bytes(bytes: &[u8]) -> Result<Self, token_service_client::UserIdError> {
        let array: [u8; 16] = bytes.try_into().map_err(|_| token_service_client::UserIdError::InvalidLength)?;
        Ok(UserUUID(Uuid::from_bytes(array)))
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // 2. Connect client generic over [UserUUID, Token16]
    let client = TokenClient::<UserUUID, Token16>::builder(
        "http://127.0.0.1:50051", Duration::from_secs(30)
    )
        .build()
        .await?;

    // 3. Issue a new 16-byte session token (uses default client token_ttl)
    let user_id = UserUUID(Uuid::parse_str("936da01f-9abd-4d9d-80c7-02af85c822a8")?);
    let token: Token16 = client.issue_token(&user_id).await?;

    // 4. Verify token (Hits local cache instantly; drops network latency to sub-microsecond)
    if let Some(verified_user) = client.verify_token(&token).await? {
        println!("Authenticated User: {:?}", verified_user);
    } else {
        println!("Invalid or expired token");
    }

    Ok(())
}
```

### Python Quick Start
```python
import asyncio
from uuid import UUID
from token_service import TokenClientBuilder, Token16, UserId

# 1. Subclass UserId for your domain type
class UserUUID(UserId):
    def __init__(self, value: UUID):
        self.value = value

    def to_bytes(self) -> bytes:
        return self.value.bytes

    @classmethod
    def from_bytes(cls, data: bytes) -> "UserUUID":
        return cls(UUID(bytes=data))


async def main():
    # 2. Build client generic over [UserUUID, Token16]
    #    (mypy/pyright infers UserUUID & Token16 directly from type annotation or generic Builder)
    async with TokenClientBuilder[UserUUID, Token16](
        "127.0.0.1:50051", timedelta(seconds=30)
    ).build() as client:
        # 3. Issue a 16-byte session token (inherits client default token_ttl)
        user_id = UserUUID(UUID("936da01f-9abd-4d9d-80c7-02af85c822a8"))
        token: Token16 = await client.issue_token(user_id)

        # 4. Verify token using local in-memory cache
        verified_user: UserUUID | None = await client.verify_token(token)
        if verified_user:
            print(f"Authenticated User: {verified_user.value}")


asyncio.run(main())
```

---

## 3. Advanced Configuration Example

For production systems, clients configure token types, default server TTLs (`with_token_ttl`), local cache safety TTLs (`with_local_cache_ttl`), and gRPC auto-reconnect backoff strategies.

### Rust Advanced Configuration
```rust
use token_service_client::{
    TokenClientBuilder, Token32, SessionToken, UserId, BackoffConfig
};
use std::time::Duration;

#[derive(Debug, Clone, PartialEq, Eq)]
struct CustomUserId(u64);

impl UserId for CustomUserId {
    fn to_bytes(&self) -> Vec<u8> {
        self.0.to_be_bytes().to_vec()
    }

    fn from_bytes(bytes: &[u8]) -> Result<Self, token_service_client::UserIdError> {
        let array: [u8; 8] = bytes.try_into().map_err(|_| token_service_client::UserIdError::InvalidLength)?;
        Ok(CustomUserId(u64::from_be_bytes(array)))
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Configure client generic over [CustomUserId, Token32]
    let client = TokenClient::<CustomUserId, Token32>::builder(
        "http://127.0.0.1:50051", Duration::from_secs(30)
    )
        // Default TTL for created tokens on the server (Redis)
        .with_token_ttl(Duration::from_secs(7200))
        // Maximum local cache TTL safety window (prevents stale cache if disconnected)
        .with_local_cache_ttl(Duration::from_secs(120))
        // gRPC streaming reconnection backoff configuration
        .with_reconnect_backoff(BackoffConfig {
            min_delay: Duration::from_millis(100),
            max_delay: Duration::from_secs(10),
            factor: 2.0,
        })
        .build()
        .await?;

    // Issue a 32-byte token (uses 7200s default server TTL)
    let user = CustomUserId(10042);
    let token: Token32 = client.issue_token(&user).await?;

    // Explicitly revoke token
    client.revoke_token(&token).await?;

    Ok(())
}
```

### Python Advanced Configuration
```python
import asyncio
from datetime import timedelta
from token_service import TokenClientBuilder, Token32, UserId, BackoffConfig


class CustomUserId(UserId):
    def __init__(self, user_num: int):
        if user_num <= 0:
            raise ValueError("User number must be positive")
        self.user_num = user_num

    def to_bytes(self) -> bytes:
        return self.user_num.to_bytes(8, byteorder="big")

    @classmethod
    def from_bytes(cls, data: bytes) -> "CustomUserId":
        return cls(int.from_bytes(data, byteorder="big"))


async def main():
    # Properly typed for mypy/pyright via Generic Builder parametrization
    client = (
        TokenClientBuilder[CustomUserId, Token32]("127.0.0.1:50051", timedelta(seconds=30))
        .with_token_ttl(timedelta(hours=2))  # Server TTL for issued tokens
        .with_local_cache_ttl(
            timedelta(minutes=2)
        )  # Safety eviction TTL for local cache
        .with_reconnect_backoff(
            BackoffConfig(
                min_delay=timedelta(milliseconds=100),
                max_delay=timedelta(seconds=10),
                factor=2.0,
            ),
        )
        .build()
    )

    async with client:
        user = CustomUserId(10042)

        # Uses client default token_ttl (2 hours)
        token: Token32 = await client.issue_token(user)

        # Explicitly revoke token
        await client.revoke_token(token)


asyncio.run(main())
```

---

## 4. Type System & Generic Abstractions

### 4.1 `SessionToken` Trait / Abstract Class
`TokenService` avoids raw strings or raw byte slices to prevent type confusion.
* **`Token16`**: Fixed 16-byte array payload (128 bits). Compact, high-performance session ID.
* **`Token32`**: Fixed 32-byte array payload (256 bits). High-entropy cryptographic token.

### 4.2 `UserId` Base Class / Trait
`UserId` is an application-side base class (Python) or trait (Rust).
* **Python**: `UserId` is an `ABC` requiring `to_bytes()` and `from_bytes()`. Subclasses implement domain-specific validation logic (e.g., UUID validation, positive integer checks). **Note**: Type checking for generic parameters (`TokenClientBuilder[UserType, TokenType]`) is enforced strictly at static analysis time via `mypy` / `pyright` type hints with zero runtime performance cost.
* **Rust**: `UserId` is a trait with `to_bytes()` and `from_bytes()` methods enforced at compile time.

`TokenService` server-side storage (Redis) treats the serialized `UserId` bytes as an opaque payload.

---

## 5. Client Cache & Invalidation Architecture

### 1. **Local Cache Read Path**:
   - `verify_token(token)` checks the client's thread-safe in-memory cache.
   - **Cache Hit**: Returns `UserId` instance immediately without hitting the network.
   - **Cache Miss**: Issues a `VerifyToken` gRPC call to `TokenService`. On success, deserializes bytes back into `UserId` and stores result in the local cache bound by **`with_local_cache_ttl`**.

### 2. **Real-Time Revocation Streaming**:
   - The client maintains a background `SubscribeRevocations` gRPC stream.
   - When any manager node revokes a token, it broadcasts the revocation over Redis Pub/Sub to all manager instances.
   - Manager instances push `RevocationEvent` messages down active gRPC streams.
   - Client instances receive the event and instantly drop the token from their local cache.

### 3. **Self-Healing Reconnection & Lost Message Warning**:
   - If the gRPC stream drops due to network flicker or server failure, the client enters an exponential backoff reconnect loop. The client will attempt to reconnect to the server indefinitely (capped at `max_delay`) and will never stop retrying.
   - **Crucial Warning**: Revocation events broadcast during a network stream outage are **lost** for that disconnected client instance.
   - To bound security exposure during network outages, applications **must not rely on long-lived tokens or long `local_cache_ttl` values**. Short `local_cache_ttl` safety windows ensure any cached tokens naturally expire and re-verify against the server shortly after an outage.

### 4. **Error Hierarchy & Disconnect Types**:
    - TokenService distinguishes between application-level verification states and network/infrastructure failures.
        - ServiceDisconnected: The client cannot communicate with the TokenService gRPC node (network down, stream reconnecting).
        - StorageDisconnected: TokenService is reachable, but its underlying storage engine (Redis) is down or unreachable.
        
#### Rust Error Types (TokenServiceError):

```rust
#[derive(thiserror::Error, Debug, Clone, PartialEq, Eq)]
pub enum TokenServiceError {
    #[error("Failed to communicate with TokenService gRPC server")]
    ServiceDisconnected,
    #[error("TokenService storage backend (Redis) is unreachable")]
    StorageDisconnected,
    #[error("Invalid token format or length")]
    InvalidTokenFormat,
}
```

#### Python Exceptions
In Python, infrastructure failures are raised as native exceptions:

```python
class TokenServiceError(Exception):
    """Base exception for TokenService client errors."""

    pass


class ServiceDisconnectedError(TokenServiceError):
    """Raised when the gRPC server connection is broken or reconnecting."""

    pass


class StorageDisconnectedError(TokenServiceError):
    """Raised when the underlying Redis storage backend is offline."""

    pass
```

### 5. **Verification Result Types (VerificationResult)**:
    - To prevent network or storage outages from obscuring the difference between an expired/invalid token and a degraded local cache hit, verify_token returns a structured result enum:

#### Rust Specification:

```rust #[derive(Debug, Clone, PartialEq, Eq)]
pub enum VerificationResult<U> {
    /// Token verified successfully against server or active gRPC stream-backed cache.
    Valid(U),
    /// Token found in local cache, but server/storage is currently DISCONNECTED.
    /// Served under 'with_local_cache_ttl' safety window.
    ValidDegraded(U),
    /// Token is explicitly invalid, revoked, or expired.
    Invalid,
}
```

#### Python Specification:

```python
from dataclasses import dataclass
from typing import Generic, TypeVar, Optional

U = TypeVar("U", bound=UserId)


@dataclass(frozen=True)
class VerificationResult(Generic[U]):
    user: Optional[U]
    is_valid: bool
    is_degraded: bool

    @classmethod
    def valid(cls, user: U) -> "VerificationResult[U]":
        return cls(user=user, is_valid=True, is_degraded=False)

    @classmethod
    def valid_degraded(cls, user: U) -> "VerificationResult[U]":
        return cls(user=user, is_valid=True, is_degraded=True)

    @classmethod
    def invalid(cls) -> "VerificationResult[U]":
        return cls(user=None, is_valid=False, is_degraded=False)
```

### 6. Method Contracts & Disconnect Behavior Matrix

#### `verify_token`

**Signatures:**

* **Rust:** `async fn verify_token(&self, token: &T) -> Result<VerificationResult<U>, TokenServiceError>`
* **Python:** `async def verify_token(self, token: T) -> VerificationResult[U]` *(Raises `TokenServiceError` on network/storage failure)*

| Cache State | Connected | Service Disconnected | Storage Disconnected |
| :--- | :--- | :--- | :--- |
| **Local Cache Hit** | `Valid(User)` | `ValidDegraded(User)` *(within `local_cache_ttl`)* | `ValidDegraded(User)` *(within `local_cache_ttl`)* |
| **Local Cache Miss (Token Valid)** | `Valid(User)` *(caches locally)* | `Err(ServiceDisconnected)` | `Err(StorageDisconnected)` |
| **Local Cache Miss (Token Revoked/Expired)** | `Invalid` | `Err(ServiceDisconnected)` | `Err(StorageDisconnected)` |

#### `issue_token` & `revoke_token`

Mutating operations require write confirmation from the storage engine and cannot be served from local cache.

**Signatures:**

* **Rust:**
* `async fn issue_token(&self, user_id: &U) -> Result<T, TokenServiceError>;`
* `async fn revoke_token(&self, token: &T) -> Result<(), TokenServiceError>;`


* **Python:**
* `async def issue_token(self, user_id: U) -> T:` *(Raises `TokenServiceError` on failure)*
* `async def revoke_token(self, token: T) -> None:` *(Raises `TokenServiceError` on failure)*


**Behavior:**

* **Service Down** $\rightarrow$ Returns `Err(TokenServiceError::ServiceDisconnected)` / raises `ServiceDisconnectedError`.
* **Redis Down** $\rightarrow$ Returns `Err(TokenServiceError::StorageDisconnected)` / raises `StorageDisconnectedError`.
