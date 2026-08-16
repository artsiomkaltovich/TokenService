import asyncio
import os
import uuid

import pytest

from token_service import (
    Invalid,
    ServiceDisconnectedError,
    Token16,
    Token32,
    TokenServiceClient,
    Valid,
)

TEST_USER_ID = uuid.UUID("936da01f-9abd-4d9d-80c7-02af85c822a8")
SERVER_URL = os.environ.get("TOKEN_SERVICE_URL", "http://127.0.0.1:5111")


async def test_issue_and_verify_token_happy_path() -> None:
    async with TokenServiceClient[Token16](server_url=SERVER_URL, timeout=5) as client:
        token = await client.issue_token(user_id=TEST_USER_ID)
        assert len(token._value) == 16
        res = await client.verify_token(token)
        assert res == Valid(user_id=TEST_USER_ID)


async def test_connect_wasnt_called() -> None:
    client = TokenServiceClient[Token16](server_url=SERVER_URL, timeout=5)
    with pytest.raises(ServiceDisconnectedError):
        await client.verify_token(Token16(b"0" * 16))


async def test_verify_invalid_or_non_existent_token() -> None:
    async with TokenServiceClient[Token16](server_url=SERVER_URL, timeout=5) as client:
        assert await client.verify_token(Token16(b"0" * 16)) == Invalid()


async def test_server_token_ttl_client_expiration() -> None:
    async with TokenServiceClient[Token16](
        server_url=SERVER_URL, timeout=5, ttl=1.0
    ) as client:
        token = await client.issue_token(user_id=TEST_USER_ID)
        await asyncio.sleep(2.0)
        res = await client.verify_token(token)
        assert res == Invalid()


async def test_server_token_ttl_server_expiration() -> None:
    async with TokenServiceClient[Token16](
        server_url=SERVER_URL, timeout=5, ttl=1.0
    ) as client1:
        token = await client1.issue_token(user_id=TEST_USER_ID)

    await asyncio.sleep(2.0)

    async with TokenServiceClient[Token16](server_url=SERVER_URL, timeout=5) as client2:
        res = await client2.verify_token(token)
        assert res == Invalid()


async def test_explicit_token_revocation_single_node() -> None:
    async with TokenServiceClient[Token16](server_url=SERVER_URL, timeout=5) as client:
        token = await client.issue_token(user_id=TEST_USER_ID)
        assert await client.verify_token(token) == Valid(user_id=TEST_USER_ID)
        await client.revoke_token(token)
        assert await client.verify_token(token) == Invalid()


async def test_token32_payload_variant() -> None:
    async with TokenServiceClient[Token32](server_url=SERVER_URL, timeout=5) as client:
        token = await client.issue_token(user_id=TEST_USER_ID)
        assert len(token._value) == 32
        res = await client.verify_token(token)
        assert res == Valid(user_id=TEST_USER_ID)


async def test_independent_token_revocation() -> None:
    async with TokenServiceClient[Token16](server_url=SERVER_URL, timeout=5) as client:
        t1 = await client.issue_token(user_id=TEST_USER_ID)
        t2 = await client.issue_token(user_id=TEST_USER_ID)

        assert await client.verify_token(t1) == Valid(user_id=TEST_USER_ID)
        assert await client.verify_token(t2) == Valid(user_id=TEST_USER_ID)

        await client.revoke_token(t1)

        assert await client.verify_token(t1) == Invalid()
        assert await client.verify_token(t2) == Valid(user_id=TEST_USER_ID)


async def test_cached_tokens_do_not_outlive_server_side_tokens() -> None:
    async with TokenServiceClient[Token16](
        server_url=SERVER_URL, timeout=5, ttl=3.0, local_cache_ttl=60.0
    ) as client1:
        token = await client1.issue_token(user_id=TEST_USER_ID)

    await asyncio.sleep(2.0)

    async with TokenServiceClient[Token16](
        server_url=SERVER_URL, timeout=5, local_cache_ttl=60.0
    ) as client2:
        # First verify hits server, cached with remaining TTL = 1s
        assert await client2.verify_token(token) == Valid(user_id=TEST_USER_ID)
        await asyncio.sleep(2.0)
        # Reads local cache, remaining server TTL expired
        assert await client2.verify_token(token) == Invalid()
