from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class TokenType(Enum):
    TOKEN16 = "token16"
    TOKEN32 = "token32"


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
