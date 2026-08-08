import os
import time
from collections.abc import Iterator
from contextlib import suppress

import pytest
import requests
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network

from tests.utils import (
    RedisContainerAttrs,
    TokenServiceAttrs,
    TokenServiceController,
    ToxiproxyApi,
    ToxiproxyContainerAttrs,
)

DEFAULT_TOXIPROXY_IMAGE = os.environ.get("TOXIPROXY_IMAGE", "shopify/toxiproxy:2.1.4")
DEFAULT_REDIS_IMAGE = os.environ.get("REDIS_IMAGE", "redis:8-alpine")
DEFAULT_TOKEN_IMAGE = os.environ.get("TOKEN_SERVICE_IMAGE", "tokenservice:local")

# Default listen ports inside the toxiproxy container; overridable via env
DEFAULT_GRPC_LISTEN = int(os.environ.get("TOXIPROXY_GRPC_LISTEN_PORT", "15111"))
DEFAULT_REDIS_LISTEN = int(os.environ.get("TOXIPROXY_REDIS_LISTEN_PORT", "15112"))


@pytest.fixture(scope="session")
def docker_network() -> Iterator[Network]:
    """Create a Docker user-defined network for test containers to share.

    The network allows containers to address each other by network alias
    (container name), which Toxiproxy can use as upstream host values.
    """
    net = Network()
    net.create()
    try:
        yield net
    finally:
        with suppress(Exception):
            net.remove()


@pytest.fixture(scope="session")
def tokenservice_container(docker_network: Network) -> Iterator[TokenServiceAttrs]:
    """Start the tokenservice container on the test network.

    Yields a dict with keys:
      - internal_host: the container network alias for the service
      - internal_port: the service port inside Docker
      - host: the host address to reach the container from the test runner
      - host_port: the mapped host port for the service
      - container: the DockerContainer instance
    """
    image = os.environ.get("TOKEN_SERVICE_IMAGE", DEFAULT_TOKEN_IMAGE)
    container = (
        DockerContainer(image)
        .with_exposed_ports(50051)
        .with_network(docker_network)
        .with_network_aliases("tokenservice")
    )
    container.start()
    # host-accessible mapping
    host_ip = container.get_container_host_ip()
    host_port = container.get_exposed_port(50051)
    try:
        yield TokenServiceAttrs(
            container=container,
            internal_host="tokenservice",
            internal_port=50051,
            host=host_ip,
            host_port=host_port,
        )
    finally:
        with suppress(Exception):
            container.stop()


@pytest.fixture
def token_service_control(
    tokenservice_container: TokenServiceAttrs,
) -> TokenServiceController:
    """Provides simple control helpers for the tokenservice container used in tests."""

    container = tokenservice_container.container

    return TokenServiceController(container)


@pytest.fixture(scope="session")
def redis_container(docker_network: Network) -> Iterator[RedisContainerAttrs]:
    """Start a redis container on the test network.

    Yields a dict with keys:
      - host: the container network alias for redis
      - port: the internal redis port (6379)
      - container: the DockerContainer instance
    """
    image = os.environ.get("REDIS_IMAGE", DEFAULT_REDIS_IMAGE)
    container = (
        DockerContainer(image)
        .with_exposed_ports(6379)
        .with_network(docker_network)
        .with_network_aliases("redis")
    )
    container.start()
    try:
        yield RedisContainerAttrs(container, "redis", 6379)
    finally:
        with suppress(Exception):
            container.stop()


@pytest.fixture(scope="session")
def toxiproxy_container(docker_network: Network) -> Iterator[ToxiproxyContainerAttrs]:
    """Start toxiproxy on the test network and expose control/API and proxy listen
    ports.

    Yields a dict with keys:
      - api_base: str (http://host:control_port)
      - host: str (host to connect to exposed listen ports)
      - map_listen_port(listen_port:int) -> host_port:int
    """
    image = os.environ.get("TOXIPROXY_IMAGE", DEFAULT_TOXIPROXY_IMAGE)
    grpc_listen = DEFAULT_GRPC_LISTEN
    redis_listen = DEFAULT_REDIS_LISTEN

    container = (
        DockerContainer(image)
        .with_exposed_ports(8474, grpc_listen, redis_listen)
        .with_network(docker_network)
        .with_network_aliases("toxiproxy")
    )
    container.start()

    host = container.get_container_host_ip()
    control_port = int(container.get_exposed_port(8474))
    api_base = f"http://{host}:{control_port}"

    # wait for control API to be ready
    for _ in range(30):
        try:
            r = requests.get(f"{api_base}/proxies")
            if r.status_code < 500:
                break
        except Exception:
            time.sleep(0.2)
    else:
        # control API didn't become ready
        raise RuntimeError("Toxiproxy control API not responsive")

    def map_listen_port(listen_port: int) -> int:
        return int(container.get_exposed_port(listen_port))

    try:
        yield ToxiproxyContainerAttrs(container, api_base, host)
    finally:
        with suppress(Exception):
            container.stop()


@pytest.fixture
def toxiproxy_api() -> ToxiproxyApi:
    """Expose helper functions to tests as a simple namespace object.

    Tests can use: toxiproxy_api.create_proxy(...), toxiproxy_api.add_latency(...), etc.
    """
    return ToxiproxyApi()
