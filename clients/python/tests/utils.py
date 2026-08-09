import asyncio
import os
from collections.abc import Generator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from functools import cached_property, lru_cache
from typing import Any, TypedDict, cast

import requests
from testcontainers.core.container import DockerContainer

DEFAULT_TOXIPROXY_IMAGE = os.environ.get("TOXIPROXY_IMAGE", "shopify/toxiproxy:2.1.4")
DEFAULT_REDIS_IMAGE = os.environ.get("REDIS_IMAGE", "redis:8-alpine")
DEFAULT_TOKEN_IMAGE = os.environ.get("TOKEN_SERVICE_IMAGE", "tokenservice:local")

# Default listen ports inside the toxiproxy container; overridable via env
DEFAULT_GRPC_LISTEN = int(os.environ.get("TOXIPROXY_GRPC_LISTEN_PORT", "15111"))
DEFAULT_REDIS_LISTEN = int(os.environ.get("TOXIPROXY_REDIS_LISTEN_PORT", "15112"))


class ToxicAttributesDict(TypedDict, total=False):
    # Latency toxic
    latency: int  # Delay in ms
    jitter: int  # Variable delay added/subtracted in ms

    # Bandwidth toxic
    rate: int  # Rate limit in KB/s

    # Slow close toxic
    delay: int  # Delay before closing socket in ms

    # Slicer toxic
    average_size: int  # Average size of sliced packets in bytes
    size_variation: int  # Variation in packet size

    # Limit data toxic
    bytes: int  # Max bytes before closing connection

    # Timeout toxic
    timeout: int  # Connection timeout in ms


class ToxicDict(TypedDict, total=False):
    name: str
    type: str
    stream: str
    toxicity: float
    attributes: ToxicAttributesDict


class ProxyDict(TypedDict):
    name: str
    listen: str
    upstream: str
    enabled: bool
    toxics: list[ToxicDict]


class TokenServiceController:
    def __init__(self, container: DockerContainer | None) -> None:
        self._container = container


@dataclass(frozen=True)
class TokenServiceAttrs:
    container: DockerContainer
    internal_host: str
    internal_port: int
    host: str
    host_port: int

    @cached_property
    def internal_url(self) -> str:
        return f"{self.internal_host}:{self.internal_port}"

    @cached_property
    def host_url(self) -> str:
        return f"{self.host}:{self.host_port}"


@dataclass(frozen=True)
class ToxiproxyContainerAttrs:
    container: DockerContainer
    api_base: str
    host: str

    def map_listen_port(self, listen_port: int) -> int:
        return self.container.get_exposed_port(listen_port)


@dataclass(frozen=True)
class RedisContainerAttrs:
    container: DockerContainer
    host: str
    port: int


class ToxiproxyApi:
    def __init__(self) -> None:
        self.create_proxy = create_proxy
        self.add_latency = add_latency
        self.add_timeout = add_timeout_toxic
        self.remove_toxic = remove_toxic
        self.delete_proxy = delete_proxy


@lru_cache
def listen_port() -> int:
    return int(os.environ.get("TOXIPROXY_GRPC_LISTEN_PORT", "15111"))


@contextmanager
def service_proxing(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
) -> Generator[tuple[ProxyDict, str], None, None]:
    api_base = toxiproxy_container.api_base
    tox_host = toxiproxy_container.host

    proxy_name = "token_grpc_cache_"
    proxy = toxiproxy_api.create_proxy(
        api_base,
        proxy_name,
        upstream_host=tokenservice_container.internal_host,
        upstream_port=tokenservice_container.internal_port,
        listen_port=listen_port(),
    )
    try:
        mapped_port = toxiproxy_container.map_listen_port(listen_port())
        server_url = f"{tox_host}:{mapped_port}"
        yield proxy, server_url
    finally:
        with suppress(Exception):
            toxiproxy_api.delete_proxy(api_base, proxy["name"])


async def simulate_service_reconnect(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    tokenservice_container: TokenServiceAttrs,
    proxy: ProxyDict,
    reconnect_duration: float,
) -> ProxyDict:
    # Simulate server restart & reconnect by deleting/recreating proxy
    #
    # Note: `service_proxing` remove only the proxy it created (by name)
    # So if proxy name for new proxy is different (e.g. proxy["name"] was assigned)
    # it could last in container.
    toxiproxy_api.delete_proxy(toxiproxy_container.api_base, proxy["name"])
    await asyncio.sleep(reconnect_duration)
    return toxiproxy_api.create_proxy(
        toxiproxy_container.api_base,
        proxy["name"],
        upstream_host=tokenservice_container.internal_host,
        upstream_port=tokenservice_container.internal_port,
        listen_port=listen_port(),
    )


@contextmanager
def redis_proxing(
    toxiproxy_api: ToxiproxyApi,
    toxiproxy_container: ToxiproxyContainerAttrs,
    redis_container: RedisContainerAttrs,
) -> Generator[ProxyDict, None, None]:
    api_base = toxiproxy_container.api_base
    tox_host = toxiproxy_container.host
    listen_port = int(os.environ.get("TOXIPROXY_REDIS_LISTEN_PORT", "15112"))

    proxy_name = "redis_proxy_drop_"
    proxy = toxiproxy_api.create_proxy(
        api_base,
        proxy_name,
        upstream_host=redis_container.host,
        upstream_port=redis_container.port,
        listen_port=listen_port,
    )
    try:
        mapped_port = toxiproxy_container.map_listen_port(listen_port)
        redis_url = f"{tox_host}:{mapped_port}"
        prev_redis = os.environ.get("REDIS_URL")
        os.environ["REDIS_URL"] = f"redis://{redis_url}"
        try:
            yield proxy
        finally:
            if prev_redis is None:
                os.environ.pop("REDIS_URL", None)
            else:
                os.environ["REDIS_URL"] = prev_redis
    finally:
        with suppress(Exception):
            toxiproxy_api.delete_proxy(api_base, proxy["name"])


def create_proxy(
    api_base: str,
    name: str,
    upstream_host: str,
    upstream_port: int,
    listen_port: int | None = None,
) -> ProxyDict:
    if listen_port is None:
        raise ValueError("listen_port must be provided")
    payload: dict[str, Any] = {
        "name": name,
        "listen": f"0.0.0.0:{listen_port}",
        "upstream": f"{upstream_host}:{upstream_port}",
    }
    r = requests.post(f"{api_base}/proxies", json=payload)
    r.raise_for_status()
    return cast(ProxyDict, r.json())


def add_latency(
    api_base: str, proxy_name: str, latency_ms: int, toxic_name: str | None = None
) -> dict[str, Any]:
    toxic: dict[str, Any] = {
        "name": toxic_name or "latency",
        "type": "latency",
        "stream": "downstream",
        "attributes": {"latency": latency_ms, "jitter": 0},
    }
    r = requests.post(f"{api_base}/proxies/{proxy_name}/toxics", json=toxic)
    r.raise_for_status()
    return cast(dict[str, Any], r.json())


def add_timeout_toxic(
    api_base: str, proxy_name: str, timeout_ms: int, toxic_name: str | None = None
) -> dict[str, Any]:
    toxic: dict[str, Any] = {
        "name": toxic_name or "timeout",
        "type": "timeout",
        "stream": "downstream",
        "attributes": {"timeout": timeout_ms},
    }
    r = requests.post(f"{api_base}/proxies/{proxy_name}/toxics", json=toxic)
    r.raise_for_status()
    return cast(dict[str, Any], r.json())


def remove_toxic(api_base: str, proxy_name: str, toxic_name: str) -> None:
    try:
        r = requests.delete(f"{api_base}/proxies/{proxy_name}/toxics/{toxic_name}")
        if r.status_code and r.status_code >= 400 and r.status_code != 404:
            r.raise_for_status()
    except Exception:
        # ignore errors during cleanup
        pass


def delete_proxy(api_base: str, proxy_name: str) -> None:
    try:
        r = requests.delete(f"{api_base}/proxies/{proxy_name}")
        if r.status_code and r.status_code >= 400 and r.status_code != 404:
            r.raise_for_status()
    except Exception:
        # ignore errors during cleanup
        pass
