import asyncio
import os
import uuid
from typing import Any

import pytest

from tests.utils import (
    TokenServiceAttrs,
    ToxiproxyApi,
    ToxiproxyContainerAttrs,
)
from token_service import (
    Invalid,
    ServiceDisconnectedError,
    StorageDisconnectedError,
    TokenServiceClient,
    TokenType,
    Valid,
    ValidDegraded,
)

TEST_USER_ID = uuid.UUID("936da01f-9abd-4d9d-80c7-02af85c822a8")
SERVER_URL = os.environ.get("TOKEN_SERVICE_URL", "http://127.0.0.1:5111")


async def test_issue_and_verify_token_happy_path() -> None:
    async with TokenServiceClient(server_url=SERVER_URL, timeout=5) as client:
        token = await client.issue_token(user_id=TEST_USER_ID)
        assert len(token) == 16
        res = await client.verify_token(token)
        assert res == Valid(user_id=TEST_USER_ID)


async def test_connect_wasnt_called() -> None:
    client = TokenServiceClient(server_url=SERVER_URL, timeout=5)
    with pytest.raises(ServiceDisconnectedError):
        await client.verify_token(b"0" * 16)


async def test_verify_invalid_or_non_existent_token() -> None:
    async with TokenServiceClient(server_url=SERVER_URL, timeout=5) as client:
        random_token = os.urandom(16)
        res = await client.verify_token(random_token)
        assert res == Invalid()


async def test_server_token_ttl_client_expiration() -> None:
    async with TokenServiceClient(server_url=SERVER_URL, timeout=5, ttl=1.0) as client:
        token = await client.issue_token(user_id=TEST_USER_ID)
        await asyncio.sleep(2.0)
        res = await client.verify_token(token)
        assert res == Invalid()


async def test_server_token_ttl_server_expiration() -> None:
    async with TokenServiceClient(server_url=SERVER_URL, timeout=5, ttl=1.0) as client1:
        token = await client1.issue_token(user_id=TEST_USER_ID)

    await asyncio.sleep(2.0)

    async with TokenServiceClient(server_url=SERVER_URL, timeout=5) as client2:
        res = await client2.verify_token(token)
        assert res == Invalid()


async def test_explicit_token_revocation_single_node() -> None:
    async with TokenServiceClient(server_url=SERVER_URL, timeout=5) as client:
        token = await client.issue_token(user_id=TEST_USER_ID)
        assert await client.verify_token(token) == Valid(user_id=TEST_USER_ID)
        await client.revoke_token(token)
        assert await client.verify_token(token) == Invalid()


async def test_token32_payload_variant() -> None:
    async with TokenServiceClient(
        server_url=SERVER_URL, timeout=5, token_type=TokenType.TOKEN32
    ) as client:
        token = await client.issue_token(user_id=TEST_USER_ID)
        assert len(token) == 32
        res = await client.verify_token(token)
        assert res == Valid(user_id=TEST_USER_ID)


async def test_independent_token_revocation() -> None:
    async with TokenServiceClient(server_url=SERVER_URL, timeout=5) as client:
        t1 = await client.issue_token(user_id=TEST_USER_ID)
        t2 = await client.issue_token(user_id=TEST_USER_ID)

        assert await client.verify_token(t1) == Valid(user_id=TEST_USER_ID)
        assert await client.verify_token(t2) == Valid(user_id=TEST_USER_ID)

        await client.revoke_token(t1)

        assert await client.verify_token(t1) == Invalid()
        assert await client.verify_token(t2) == Valid(user_id=TEST_USER_ID)


async def test_local_in_memory_cache_hit() -> None:
    async with TokenServiceClient(
        server_url=SERVER_URL, timeout=5, local_cache_ttl=60.0
    ) as client:
        token = await client.issue_token(user_id=TEST_USER_ID)
        res1 = await client.verify_token(token)
        assert res1 == Valid(user_id=TEST_USER_ID)

        # TODO: Simulate stopping server process
        res2 = await client.verify_token(token)
        assert res2 == ValidDegraded(user_id=TEST_USER_ID)


async def test_cached_tokens_do_not_outlive_server_side_tokens() -> None:
    async with TokenServiceClient(server_url=SERVER_URL, timeout=5, ttl=3.0) as client1:
        token = await client1.issue_token(user_id=TEST_USER_ID)

    await asyncio.sleep(2.0)

    async with TokenServiceClient(
        server_url=SERVER_URL, timeout=5, local_cache_ttl=60.0
    ) as client2:
        # First verify hits server, cached with remaining TTL = 1s
        assert await client2.verify_token(token) == Valid(user_id=TEST_USER_ID)
        await asyncio.sleep(2.0)
        # Reads local cache, remaining server TTL expired
        assert await client2.verify_token(token) == Invalid()


async def test_stream_outage_and_safety_ttl_eviction() -> None:
    async with TokenServiceClient(
        server_url=SERVER_URL, timeout=5, local_cache_ttl=1.0
    ) as client:
        token = await client.issue_token(user_id=TEST_USER_ID)
        assert await client.verify_token(token) == Valid(user_id=TEST_USER_ID)

        # TODO: Disconnect stream/simulate outage
        await asyncio.sleep(2.0)
        with pytest.raises(ServiceDisconnectedError):
            await client.verify_token(token)


async def test_client_grpc_stream_auto_reconnect() -> None:
    async with TokenServiceClient(
        server_url=SERVER_URL, timeout=5, backoff_max_delay=0.5
    ) as client:
        # TODO: simulate server restart & reconnect window
        await asyncio.sleep(1.0)
        t1 = await client.issue_token(user_id=TEST_USER_ID)
        await client.revoke_token(t1)
        assert await client.verify_token(t1) == Invalid()


async def test_uncached_verify_miss_fails_on_service_disconnect() -> None:
    async with TokenServiceClient(server_url=SERVER_URL, timeout=5) as client:
        # TODO: Simulate server stop
        with pytest.raises(ServiceDisconnectedError):
            await client.verify_token(os.urandom(16))


async def test_issue_token_fails_on_service_disconnect() -> None:
    async with TokenServiceClient(server_url=SERVER_URL, timeout=5) as client:
        # TODO: Simulate server stop
        with pytest.raises(ServiceDisconnectedError):
            await client.issue_token(user_id=TEST_USER_ID)


async def test_revoke_token_fails_on_service_disconnect() -> None:
    async with TokenServiceClient(server_url=SERVER_URL, timeout=5) as client:
        # TODO: Simulate server stop
        with pytest.raises(ServiceDisconnectedError):
            await client.revoke_token(os.urandom(16))


async def test_uncached_verify_miss_fails_on_storage_disconnect() -> None:
    async with TokenServiceClient(server_url=SERVER_URL, timeout=5) as client:
        # TODO: Simulate storage stop
        with pytest.raises(StorageDisconnectedError):
            await client.verify_token(os.urandom(16))


async def test_issue_token_fails_on_storage_disconnect() -> None:
    async with TokenServiceClient(server_url=SERVER_URL, timeout=5) as client:
        # TODO: Simulate storage stop
        with pytest.raises(StorageDisconnectedError):
            await client.issue_token(user_id=TEST_USER_ID)


async def test_revoke_token_fails_on_storage_disconnect() -> None:
    async with TokenServiceClient(server_url=SERVER_URL, timeout=5) as client:
        # TODO: Simulate storage stop
        with pytest.raises(StorageDisconnectedError):
            await client.revoke_token(os.urandom(16))


@pytest.mark.asyncio
async def test_grpc_latency_maps_to_service_disconnected(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    api_base = toxiproxy_container.api_base
    tox_host = toxiproxy_container.host
    listen_port = int(os.environ.get("TOXIPROXY_GRPC_LISTEN_PORT", "15111"))

    # create proxy forwarding to tokenservice. Use network alias `tokenservice` and the
    # service's internal port inside the Docker network.
    proxy_name = f"token_grpc_{uuid.uuid4().hex[:8]}"
    proxy = toxiproxy_api.create_proxy(
        api_base,
        proxy_name,
        upstream_host=tokenservice_container.internal_host,
        upstream_port=tokenservice_container.internal_port,
        listen_port=listen_port,
    )
    try:
        # map listen port to host port for client connection
        mapped_port = toxiproxy_container.map_listen_port(listen_port)
        server_url = f"{tox_host}:{mapped_port}"

        # inject latency greater than client timeout
        toxiproxy_api.add_latency(api_base, proxy["name"], latency_ms=2000)

        async with TokenServiceClient(server_url=server_url, timeout=0.5) as client:
            with pytest.raises(ServiceDisconnectedError):
                await client.issue_token(user_id=TEST_USER_ID)
    finally:
        toxiproxy_api.remove_toxic(api_base, proxy["name"], "latency")
        toxiproxy_api.delete_proxy(api_base, proxy["name"])


@pytest.mark.asyncio
async def test_grpc_connection_drop_maps_to_service_disconnected(
    toxiproxy_container: dict[str, Any],
    toxiproxy_api: Any,
    tokenservice_container: TokenServiceAttrs,
) -> None:
    api_base = toxiproxy_container["api_base"]
    tox_host = toxiproxy_container["host"]
    listen_port = int(os.environ.get("TOXIPROXY_GRPC_LISTEN_PORT", "15111"))

    proxy_name = f"token_grpc_drop_{uuid.uuid4().hex[:8]}"
    proxy = toxiproxy_api.create_proxy(
        api_base,
        proxy_name,
        upstream_host=tokenservice_container.internal_host,
        upstream_port=tokenservice_container.internal_port,
        listen_port=listen_port,
    )
    try:
        mapped_port = toxiproxy_container["map_listen_port"](listen_port)
        server_url = f"{tox_host}:{mapped_port}"

        # delete proxy to simulate immediate connection failure
        toxiproxy_api.delete_proxy(api_base, proxy["name"])

        async with TokenServiceClient(server_url=server_url, timeout=1.0) as client:
            with pytest.raises(ServiceDisconnectedError):
                await client.verify_token(b"0" * 16)
    finally:
        # ensure cleanup if still present
        try:
            toxiproxy_api.delete_proxy(api_base, proxy["name"])
        except Exception:
            pass


@pytest.mark.asyncio
async def test_redis_latency_maps_to_storage_disconnected(
    toxiproxy_container: dict[str, Any],
    toxiproxy_api: Any,
    redis_container: dict[str, Any],
    tokenservice_container: TokenServiceAttrs,
) -> None:
    api_base = toxiproxy_container["api_base"]
    tox_host = toxiproxy_container["host"]
    listen_port = int(os.environ.get("TOXIPROXY_REDIS_LISTEN_PORT", "15112"))

    proxy_name = f"redis_proxy_{uuid.uuid4().hex[:8]}"
    proxy = toxiproxy_api.create_proxy(
        api_base,
        proxy_name,
        upstream_host=redis_container["host"],
        upstream_port=redis_container["port"],
        listen_port=listen_port,
    )
    mapped_port = toxiproxy_container["map_listen_port"](listen_port)
    redis_url = f"{tox_host}:{mapped_port}"

    # Configure the client to use proxied redis via environment or client args.
    # Tests assume TokenServiceClient reads REDIS_URL from the environment; adapt if
    # the client accepts an explicit redis_url parameter.
    prev_redis = os.environ.get("REDIS_URL")
    os.environ["REDIS_URL"] = f"redis://{redis_url}"

    toxiproxy_api.add_latency(api_base, proxy["name"], latency_ms=2000)

    try:
        async with TokenServiceClient(
            server_url=tokenservice_container.host_url,
            timeout=0.5,
        ) as client:
            with pytest.raises(StorageDisconnectedError):
                await client.issue_token(user_id=TEST_USER_ID)
    finally:
        # restore env
        if prev_redis is None:
            os.environ.pop("REDIS_URL", None)
        else:
            os.environ["REDIS_URL"] = prev_redis
        toxiproxy_api.remove_toxic(api_base, proxy["name"], "latency")
        toxiproxy_api.delete_proxy(api_base, proxy["name"])


@pytest.mark.asyncio
async def test_redis_connection_drop_maps_to_storage_disconnected(
    toxiproxy_container: dict[str, Any],
    toxiproxy_api: Any,
    redis_container: dict[str, Any],
    tokenservice_container: TokenServiceAttrs,
) -> None:
    api_base = toxiproxy_container["api_base"]
    tox_host = toxiproxy_container["host"]
    listen_port = int(os.environ.get("TOXIPROXY_REDIS_LISTEN_PORT", "15112"))

    proxy_name = f"redis_proxy_drop_{uuid.uuid4().hex[:8]}"
    proxy = toxiproxy_api.create_proxy(
        api_base,
        proxy_name,
        upstream_host=redis_container["host"],
        upstream_port=redis_container["port"],
        listen_port=listen_port,
    )
    try:
        mapped_port = toxiproxy_container["map_listen_port"](listen_port)
        redis_url = f"{tox_host}:{mapped_port}"
        prev_redis = os.environ.get("REDIS_URL")
        os.environ["REDIS_URL"] = f"redis://{redis_url}"

        # remove proxy to simulate connection refusal
        toxiproxy_api.delete_proxy(api_base, proxy["name"])

        try:
            async with TokenServiceClient(
                server_url=tokenservice_container.host_url,
                timeout=1.0,
            ) as client:
                with pytest.raises(StorageDisconnectedError):
                    await client.verify_token(b"0" * 16)
        finally:
            if prev_redis is None:
                os.environ.pop("REDIS_URL", None)
            else:
                os.environ["REDIS_URL"] = prev_redis
            try:
                toxiproxy_api.delete_proxy(api_base, proxy["name"])
            except Exception:
                pass
    finally:
        # outer cleanup: ensure proxy removed
        try:
            toxiproxy_api.delete_proxy(api_base, proxy["name"])
        except Exception:
            pass
