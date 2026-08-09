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
    Token32,
    TokenServiceClient,
    Valid,
    ValidDegraded,
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


@pytest.mark.asyncio
async def test_grpc_latency_maps_to_service_disconnected(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    with service_proxing(
        toxiproxy_api, toxiproxy_container, tokenservice_container
    ) as (proxy, server_url):
        # delete proxy to simulate immediate connection failure
        toxiproxy_api.add_latency(
            toxiproxy_container.api_base, proxy["name"], latency_ms=2000
        )

        async with TokenServiceClient[Token16](
            server_url=server_url, timeout=0.5
        ) as client:
            with pytest.raises(ServiceDisconnectedError):
                await client.verify_token(Token16(b"0" * 16))


@pytest.mark.asyncio
async def test_grpc_connection_drop_maps_to_service_disconnected(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    with service_proxing(
        toxiproxy_api, toxiproxy_container, tokenservice_container
    ) as (proxy, server_url):
        # delete proxy to simulate immediate connection failure
        toxiproxy_api.delete_proxy(toxiproxy_container.api_base, proxy["name"])

        async with TokenServiceClient[Token16](
            server_url=server_url, timeout=1.0
        ) as client:
            with pytest.raises(ServiceDisconnectedError):
                await client.verify_token(Token16(b"0" * 16))


@pytest.mark.asyncio
async def test_redis_latency_maps_to_storage_disconnected(
    toxiproxy_container: ToxiproxyContainerAttrs,
    toxiproxy_api: ToxiproxyApi,
    redis_container: RedisContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    with redis_proxing(toxiproxy_api, toxiproxy_container, redis_container) as proxy:
        # deleting of proxy is done by proxing context manager
        # deletion of proxy also should cause deletion of toxics
        toxiproxy_api.add_latency(
            toxiproxy_container.api_base, proxy["name"], latency_ms=2000
        )
        async with TokenServiceClient[Token16](
            server_url=tokenservice_container.host_url,
            timeout=0.5,
        ) as client:
            with pytest.raises(StorageDisconnectedError):
                await client.issue_token(user_id=TEST_USER_ID)


@pytest.mark.asyncio
async def test_redis_connection_drop_maps_to_storage_disconnected(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    redis_container: RedisContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    # first
    with redis_proxing(toxiproxy_api, toxiproxy_container, redis_container) as proxy:
        toxiproxy_api.delete_proxy(toxiproxy_container.api_base, proxy["name"])
        async with TokenServiceClient[Token16](
            server_url=tokenservice_container.host_url,
            timeout=1.0,
        ) as client:
            with pytest.raises(StorageDisconnectedError):
                await client.verify_token(Token16(b"0" * 16))
