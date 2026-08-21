import os
import time
import uuid

import pytest

from tests.utils import (
    RedisContainerAttrs,
    TokenServiceAttrs,
    ToxiproxyApi,
    ToxiproxyContainerAttrs,
    redis_proxing,
    service_proxing,
)
from token_service import (
    ServiceDisconnectedError,
    StorageDisconnectedError,
    Token16,
    TokenServiceClient,
    Valid,
    ValidDegraded,
)

TEST_USER_ID = uuid.UUID("936da01f-9abd-4d9d-80c7-02af85c822a8")
SERVER_URL = os.environ.get("TOKEN_SERVICE_URL", "http://127.0.0.1:5111")


@pytest.mark.asyncio
async def test_custom_timeout_default_applies_to_all_operations() -> None:
    # TEST 3.1: Custom Timeout Default Applies to All Operations
    async with TokenServiceClient[Token16](
        server_url=SERVER_URL, timeout=10.0
    ) as client:
        token = await client.issue_token(user_id=TEST_USER_ID)
        assert token is not None

        res = await client.verify_token(token)
        assert res == Valid(user_id=TEST_USER_ID)

        await client.revoke_token(token)


@pytest.mark.asyncio
async def test_timeout_on_slow_server(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    # TEST 3.2: Timeout on Slow Server
    with service_proxing(
        "test_timeout_on_slow_server",
        toxiproxy_api,
        toxiproxy_container,
        tokenservice_container,
    ) as (proxy, server_url):
        # Add latency > timeout value
        toxiproxy_api.add_latency(
            toxiproxy_container.api_base, proxy["name"], latency_ms=2000
        )

        async with TokenServiceClient[Token16](
            server_url=server_url, timeout=0.5
        ) as client:
            # issue_token
            start_time = time.monotonic()
            with pytest.raises(ServiceDisconnectedError):
                await client.issue_token(user_id=TEST_USER_ID)
            duration = time.monotonic() - start_time
            assert duration >= 0.5
            assert duration < 1.0

            # verify_token
            start_time = time.monotonic()
            with pytest.raises(ServiceDisconnectedError):
                await client.verify_token(Token16(b"0" * 16))
            duration = time.monotonic() - start_time
            assert duration >= 0.5
            assert duration < 1.0

            # revoke_token
            start_time = time.monotonic()
            with pytest.raises(ServiceDisconnectedError):
                await client.revoke_token(Token16(b"0" * 16))
            duration = time.monotonic() - start_time
            assert duration >= 0.5
            assert duration < 1.0


@pytest.mark.asyncio
async def test_timeout_does_not_affect_local_cache_hits(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    # TEST 3.3: Timeout Does Not Affect Local Cache Hits
    with service_proxing(
        "test_timeout_does_not_affect_local_cache_hits",
        toxiproxy_api,
        toxiproxy_container,
        tokenservice_container,
    ) as (proxy, server_url):
        async with TokenServiceClient[Token16](
            server_url=server_url, timeout=1.0, local_cache_ttl=60.0
        ) as client:
            # 1. Issue and verify to populate local cache
            token = await client.issue_token(user_id=TEST_USER_ID)
            res1 = await client.verify_token(token)
            assert res1 == Valid(user_id=TEST_USER_ID)

            # 2. Stop the server (by deleting proxy)
            toxiproxy_api.delete_proxy(toxiproxy_container.api_base, proxy["name"])

            # 3. Verify again (should hit local cache)
            start_time = time.monotonic()
            res2 = await client.verify_token(token)
            duration = time.monotonic() - start_time

            # Assert:
            # - Cached verification returns ValidDegraded without timeout error
            assert res2 == ValidDegraded(user_id=TEST_USER_ID)
            # - Cached verification took less than 1 second to complete
            assert duration < 1.0


@pytest.mark.asyncio
async def test_timeout_on_slow_redis(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    redis_container: RedisContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    # TEST 3.4: Timeout on Slow Storage (Redis)
    with redis_proxing(
        "test_timeout_on_slow_redis",
        toxiproxy_api,
        toxiproxy_container,
        redis_container,
    ) as proxy:
        # Add latency > timeout value
        toxiproxy_api.add_latency(
            toxiproxy_container.api_base, proxy["name"], latency_ms=2000
        )

        async with TokenServiceClient[Token16](
            server_url=tokenservice_container.host_url, timeout=0.5
        ) as client:
            # issue_token
            start_time = time.monotonic()
            with pytest.raises(StorageDisconnectedError):
                await client.issue_token(user_id=TEST_USER_ID)
            duration = time.monotonic() - start_time
            assert duration >= 0.5
            assert duration < 1.0

            # verify_token
            start_time = time.monotonic()
            with pytest.raises(StorageDisconnectedError):
                await client.verify_token(Token16(b"0" * 16))
            duration = time.monotonic() - start_time
            assert duration >= 0.5
            assert duration < 1.0

            # revoke_token
            start_time = time.monotonic()
            with pytest.raises(StorageDisconnectedError):
                await client.revoke_token(Token16(b"0" * 16))
            duration = time.monotonic() - start_time
            assert duration >= 0.5
            assert duration < 1.0
