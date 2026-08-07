from types import TracebackType
from typing import Self
from uuid import UUID

from token_service.models import (
    TokenType,
    VerificationResult,
)


class TokenServiceClient:
    """Client SDK for interacting with TokenService."""

    def __init__(
        self,
        server_url: str,
        timeout: float,
        token_type: TokenType = TokenType.TOKEN16,
        ttl: float | None = None,
        local_cache_ttl: float = 60.0,
        backoff_max_delay: float = 0.5,
    ) -> None:
        self.server_url = server_url
        self.timeout = timeout
        self.token_type = token_type
        self.ttl = ttl
        self.local_cache_ttl = local_cache_ttl
        self.backoff_max_delay = backoff_max_delay
        self._connected = False

    async def _connect(self) -> None:
        """Establish connection to TokenService."""
        raise NotImplementedError("TokenServiceClient is not implemented yet")

    async def _close(self) -> None:
        """Close connection to TokenService."""
        raise NotImplementedError("TokenServiceClient is not implemented yet")

    async def __aenter__(self) -> Self:
        await self._connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self._close()

    async def issue_token(
        self,
        user_id: UUID | str,
    ) -> bytes:
        """Issue a token for the specified user."""
        raise NotImplementedError("TokenServiceClient is not implemented yet")

    async def verify_token(self, token: bytes) -> VerificationResult:
        """Verify the validity of a token."""
        raise NotImplementedError("TokenServiceClient is not implemented yet")

    async def revoke_token(self, token: bytes) -> None:
        """Revoke an issued token."""
        raise NotImplementedError("TokenServiceClient is not implemented yet")
