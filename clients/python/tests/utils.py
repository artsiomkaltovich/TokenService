import os
from dataclasses import dataclass
from functools import cached_property
from typing import Any, cast

import requests
from testcontainers.core.container import DockerContainer

DEFAULT_TOXIPROXY_IMAGE = os.environ.get("TOXIPROXY_IMAGE", "shopify/toxiproxy:2.1.4")
DEFAULT_REDIS_IMAGE = os.environ.get("REDIS_IMAGE", "redis:8-alpine")
DEFAULT_TOKEN_IMAGE = os.environ.get("TOKEN_SERVICE_IMAGE", "tokenservice:local")

# Default listen ports inside the toxiproxy container; overridable via env
DEFAULT_GRPC_LISTEN = int(os.environ.get("TOXIPROXY_GRPC_LISTEN_PORT", "15111"))
DEFAULT_REDIS_LISTEN = int(os.environ.get("TOXIPROXY_REDIS_LISTEN_PORT", "15112"))


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


def create_proxy(
    api_base: str,
    name: str,
    upstream_host: str,
    upstream_port: int,
    listen_port: int | None = None,
) -> dict[str, Any]:
    if listen_port is None:
        raise ValueError("listen_port must be provided")
    payload: dict[str, Any] = {
        "name": name,
        "listen": f"0.0.0.0:{listen_port}",
        "upstream": f"{upstream_host}:{upstream_port}",
    }
    r = requests.post(f"{api_base}/proxies", json=payload)
    r.raise_for_status()
    return cast(dict[str, Any], r.json())


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
