import asyncio
import os
import uuid

import pytest

from tests.utils import (
    RedisContainerAttrs,
    TokenServiceAttrs,
    ToxiproxyApi,
    ToxiproxyContainerAttrs,
    redis_proxing,
    service_proxing,
    simulate_service_reconnect,
)
from token_service import (
    Invalid,
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
async def test_local_in_memory_cache_hit(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    with service_proxing(
        toxiproxy_api, toxiproxy_container, tokenservice_container
    ) as (proxy, server_url):
        async with TokenServiceClient[Token16](
            server_url=server_url, timeout=5, local_cache_ttl=60.0
        ) as client:
            token = await client.issue_token(user_id=TEST_USER_ID)
            res1 = await client.verify_token(token)
            assert res1 == Valid(user_id=TEST_USER_ID)

            # Simulate stopping server process by deleting the proxy
            toxiproxy_api.delete_proxy(toxiproxy_container.api_base, proxy["name"])
            res2 = await client.verify_token(token)
            assert res2 == ValidDegraded(user_id=TEST_USER_ID)


@pytest.mark.asyncio
async def test_stream_outage_and_safety_ttl_eviction(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    with service_proxing(
        toxiproxy_api, toxiproxy_container, tokenservice_container
    ) as (proxy, server_url):
        async with TokenServiceClient[Token16](
            server_url=server_url, timeout=5, local_cache_ttl=1.0
        ) as client:
            token = await client.issue_token(user_id=TEST_USER_ID)
            assert await client.verify_token(token) == Valid(user_id=TEST_USER_ID)

            # Disconnect stream/simulate outage by deleting the proxy
            toxiproxy_api.delete_proxy(toxiproxy_container.api_base, proxy["name"])
            await asyncio.sleep(2.0)
            with pytest.raises(ServiceDisconnectedError):
                await client.verify_token(token)


@pytest.mark.asyncio
async def test_client_grpc_stream_auto_reconnect(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    with service_proxing(
        toxiproxy_api, toxiproxy_container, tokenservice_container
    ) as (proxy, server_url):
        async with TokenServiceClient[Token16](
            server_url=server_url, timeout=5, backoff_max_delay=1
        ) as client1:
            token = await client1.issue_token(user_id=TEST_USER_ID)

            async with TokenServiceClient[Token16](
                server_url=server_url, timeout=5, backoff_max_delay=1
            ) as client2:
                assert await client2.verify_token(token) == Valid(TEST_USER_ID)
                coros = (
                    simulate_service_reconnect(
                        # simulate_service_reconnect will drop connections for 2 clients
                        # but is shouldn't be a problem for what the test asserts
                        toxiproxy_api,
                        toxiproxy_container,
                        tokenservice_container,
                        proxy,
                        reconnect_duration=0.2,
                    ),
                    asyncio.sleep(2.0),
                )
                await asyncio.wait(asyncio.create_task(c) for c in coros)
                await client1.revoke_token(token)
                # give a time for a revokation event to appear.
                # TODO: use something smarter
                await asyncio.sleep(1)
                assert await client2.verify_token(token) == Invalid()


@pytest.mark.asyncio
async def test_uncached_verify_miss_fails_on_service_disconnect(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    with service_proxing(
        toxiproxy_api, toxiproxy_container, tokenservice_container
    ) as (proxy, server_url):
        async with TokenServiceClient[Token16](
            server_url=server_url, timeout=5
        ) as client:
            # Simulate server stop by deleting the proxy before calling verify
            toxiproxy_api.delete_proxy(toxiproxy_container.api_base, proxy["name"])
            with pytest.raises(ServiceDisconnectedError):
                await client.verify_token(Token16(b"0" * 16))


@pytest.mark.asyncio
async def test_issue_token_fails_on_service_disconnect(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    with service_proxing(
        toxiproxy_api, toxiproxy_container, tokenservice_container
    ) as (proxy, server_url):
        async with TokenServiceClient[Token16](
            server_url=server_url, timeout=5
        ) as client:
            # Simulate server stop by deleting the proxy before calling issue_token
            toxiproxy_api.delete_proxy(toxiproxy_container.api_base, proxy["name"])
            with pytest.raises(ServiceDisconnectedError):
                await client.issue_token(user_id=TEST_USER_ID)


@pytest.mark.asyncio
async def test_revoke_token_fails_on_service_disconnect(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    with service_proxing(
        toxiproxy_api, toxiproxy_container, tokenservice_container
    ) as (proxy, server_url):
        async with TokenServiceClient[Token16](
            server_url=server_url, timeout=5
        ) as client:
            # Simulate server stop by deleting the proxy before calling revoke_token
            toxiproxy_api.delete_proxy(toxiproxy_container.api_base, proxy["name"])
            with pytest.raises(ServiceDisconnectedError):
                await client.verify_token(Token16(b"0" * 16))


@pytest.mark.asyncio
async def test_uncached_verify_miss_fails_on_storage_disconnect(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    redis_container: RedisContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    with redis_proxing(toxiproxy_api, toxiproxy_container, redis_container) as proxy:
        # Simulate storage stop by deleting the proxy before calling verify
        toxiproxy_api.delete_proxy(toxiproxy_container.api_base, proxy["name"])
        async with TokenServiceClient[Token16](
            server_url=tokenservice_container.host_url,
            timeout=1.0,
        ) as client:
            with pytest.raises(StorageDisconnectedError):
                await client.verify_token(Token16(b"0" * 16))


@pytest.mark.asyncio
async def test_issue_token_fails_on_storage_disconnect(
    toxiproxy_container: ToxiproxyContainerAttrs,
    toxiproxy_api: ToxiproxyApi,
    redis_container: RedisContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    with redis_proxing(toxiproxy_api, toxiproxy_container, redis_container) as proxy:
        toxiproxy_api.delete_proxy(toxiproxy_container.api_base, proxy["name"])

        async with TokenServiceClient[Token16](
            server_url=tokenservice_container.host_url,
            timeout=1.0,
        ) as client:
            with pytest.raises(StorageDisconnectedError):
                await client.issue_token(user_id=TEST_USER_ID)


@pytest.mark.asyncio
async def test_revoke_token_fails_on_storage_disconnect(
    toxiproxy_container: ToxiproxyContainerAttrs,
    toxiproxy_api: ToxiproxyApi,
    redis_container: RedisContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    with redis_proxing(toxiproxy_api, toxiproxy_container, redis_container) as proxy:
        # Simulate storage stop by deleting the proxy before calling revoke_token
        toxiproxy_api.delete_proxy(toxiproxy_container.api_base, proxy["name"])
        async with TokenServiceClient[Token16](
            server_url=tokenservice_container.host_url,
            timeout=1.0,
        ) as client:
            with pytest.raises(StorageDisconnectedError):
                await client.verify_token(Token16(b"0" * 16))
