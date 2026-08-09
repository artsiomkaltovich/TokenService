from dataclasses import dataclass
from uuid import UUID


class TokenType:
    pass


class Token16(TokenType):
    def __init__(self, value: bytes):
        assert len(value) == 16
        self._value = value


class Token32(TokenType):
    def __init__(self, value: bytes):
        assert len(value) == 32
        self._value = value


@dataclass(frozen=True)
class Valid:
    user_id: UUID | str


@dataclass(frozen=True)
class ValidDegraded:
    user_id: UUID | str


@dataclass(frozen=True)
class Invalid:
    pass


VerificationResult = Valid | ValidDegraded | Invalid


class TokenServiceError(Exception):
    """Base exception for TokenService client errors."""


class ServiceDisconnectedError(TokenServiceError):
    """Raised when gRPC service is disconnected or unreachable."""


class StorageDisconnectedError(TokenServiceError):
    """Raised when underlying storage (e.g. Redis) is disconnected or failing."""
