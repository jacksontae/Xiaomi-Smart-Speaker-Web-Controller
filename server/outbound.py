"""Outbound HTTP: the shared clients, the stream relay's connections and the public-internet checks."""
import asyncio
import ipaddress
import socket
import urllib.parse

import httpcore
import httpx
from fastapi import HTTPException

http = httpx.AsyncClient(timeout=30, follow_redirects=True)
# For URLs users type in (podcast feeds): redirects are followed by hand so each hop is checked first.
feed_http = httpx.AsyncClient(timeout=20, follow_redirects=False)


class IcyStream(httpcore.AsyncNetworkStream):
    """A connection that reads SHOUTcast v1's "ICY 200 OK" status line as "HTTP/1.0 200 OK" (httpx refuses the
    former). Only the first bytes a connection receives are looked at; everything after passes as is."""

    def __init__(self, inner):
        self.inner, self.checked = inner, False

    async def read(self, max_bytes, timeout=None):
        if self.checked:
            return await self.inner.read(max_bytes, timeout)
        head = b""
        while len(head) < 4:  # enough to tell "ICY " from "HTTP"
            chunk = await self.inner.read(max_bytes, timeout)
            if not chunk:
                break
            head += chunk
        self.checked = True
        return b"HTTP/1.0" + head[3:] if head.startswith(b"ICY ") else head

    async def write(self, buffer, timeout=None):
        await self.inner.write(buffer, timeout)

    async def aclose(self):
        await self.inner.aclose()

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        return IcyStream(await self.inner.start_tls(ssl_context, server_hostname, timeout))

    def get_extra_info(self, info):
        return self.inner.get_extra_info(info)


class RelayBackend(httpcore.AsyncNetworkBackend):
    """Connections for the stream relay: to an address checked public right then (so a host whose DNS answer
    changes after check_public_url can't point the relay inside), reading ICY status lines (IcyStream)."""

    def __init__(self):
        self.inner = httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        try:
            addresses = await asyncio.to_thread(public_addresses, host)
        except (OSError, ValueError) as e:
            raise httpcore.ConnectError(f"{host}: {e}") from e
        error = None
        for address in addresses:
            try:
                return IcyStream(await self.inner.connect_tcp(address, port, timeout, local_address, socket_options))
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as e:
                error = e
        raise error

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise httpcore.ConnectError("the relay only connects to internet hosts")

    async def sleep(self, seconds):
        await self.inner.sleep(seconds)


def relay_transport():
    """httpx's own transport on RelayBackend connections (httpx has no public option for a network backend)."""
    transport = httpx.AsyncHTTPTransport()
    transport._pool = httpcore.AsyncConnectionPool(ssl_context=httpx.create_ssl_context(),
                                                   network_backend=RelayBackend())
    return transport


# For the "This device" stream proxy: a stalled upstream (no bytes for 30 s) ends the relay.
stream_http = httpx.AsyncClient(transport=relay_transport(), timeout=httpx.Timeout(10, read=30),
                                follow_redirects=False)


# --- Hosts this server fetches from (feeds, relayed streams) must be on the public internet ---

def resolve_host(host):
    return {info[4][0] for info in socket.getaddrinfo(host, None)}


def check_public_url(url, what="feed"):
    """Refuse URLs that point into this machine's networks (the server fetches them, not the speaker)."""
    host = urllib.parse.urlsplit(url).hostname
    if not host:
        raise HTTPException(400, f"{what} must be an http(s) URL")
    try:
        addresses = resolve_host(host)
    except OSError as e:
        raise HTTPException(502, f"Can't resolve {host}") from e
    if not all(map(is_public_address, addresses)):
        raise HTTPException(400, f"{what} must be on the public internet")


def is_public_address(address):
    return ipaddress.ip_address(address.split("%")[0]).is_global


def public_addresses(host):
    """The addresses the relay may connect to for `host`, checked again at connect time; ValueError when any
    of them is inside this machine's networks."""
    addresses = resolve_host(host)
    if not addresses or not all(map(is_public_address, addresses)):
        raise ValueError("not on the public internet")
    return sorted(addresses, key=lambda a: ":" in a)  # IPv4 first
