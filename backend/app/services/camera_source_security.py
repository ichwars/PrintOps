"""Fail-closed preparation of user-configured external camera sources.

The prepared URL always points at a short-lived loopback relay.  The relay,
not aiohttp/ffmpeg/go2rtc, owns the outbound connection and dials the exact IP
address validated here.  This keeps DNS validation and use in one boundary.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
import ssl
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from backend.app.services.camera import rewrite_rtsp_request_url

logger = logging.getLogger(__name__)

_CLOUD_METADATA_HOSTS = frozenset(
    {
        "metadata.google",
        "metadata.google.internal",
        "instance-data",
        "instance-data.ec2.internal",
    }
)
_CLOUD_METADATA_ADDRESSES = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("168.63.129.16"),
        ipaddress.ip_address("fd00:ec2::254"),
        ipaddress.ip_address("fd20:ce::254"),
    }
)
_MAX_REQUEST_HEAD = 64 * 1024
_CONNECT_TIMEOUT = 10.0


@dataclass(frozen=True)
class _ParsedCameraUrl:
    scheme: str
    hostname: str
    port: int
    explicit_port: bool
    userinfo: str
    authority: str
    path_and_query: str
    sanitized_url: str


@dataclass
class PreparedCameraSource:
    """A loopback URL and the relay that owns its validated outbound dial."""

    url: str
    local_server: asyncio.Server
    target_host: str
    connect_ip: str

    async def close(self) -> None:
        self.local_server.close()
        await self.local_server.wait_closed()


def _parse_ip_address(hostname: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse modern and resolver-accepted legacy IP spellings."""
    host = hostname.rstrip(".")
    if ":" not in host:
        try:
            return ipaddress.IPv4Address(socket.inet_aton(host))
        except OSError:
            pass
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def _unsafe_destination_reason(hostname: str) -> str | None:
    host = hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return "localhost"
    if host in _CLOUD_METADATA_HOSTS:
        return "cloud metadata hostname"

    address = _parse_ip_address(host)
    if address is None:
        return None
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    if address in _CLOUD_METADATA_ADDRESSES:
        return "cloud metadata address"
    if address.is_loopback:
        return "loopback address"
    if address.is_unspecified:
        return "unspecified address"
    if address.is_link_local:
        return "link-local address"
    if address.is_multicast:
        return "multicast address"
    return None


def _parse_camera_url(url: str, allowed_schemes: tuple[str, ...]) -> _ParsedCameraUrl | None:
    if not isinstance(url, str) or not url or any(ord(char) < 32 or ord(char) == 127 for char in url):
        return None
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in allowed_schemes or not parsed.netloc or parsed.fragment:
            return None
        hostname = parsed.hostname
        if not hostname or _unsafe_destination_reason(hostname):
            return None
        port = parsed.port or (
            443 if scheme == "https" else 322 if scheme == "rtsps" else 554 if scheme == "rtsp" else 80
        )
    except (TypeError, ValueError):
        return None

    userinfo = f"{parsed.netloc.rsplit('@', 1)[0]}@" if "@" in parsed.netloc else ""
    host_token = f"[{hostname}]" if ":" in hostname else hostname
    explicit_port = parsed.port is not None
    port_text = f":{parsed.port}" if explicit_port else ""
    authority = f"{host_token}{port_text}"
    path = parsed.path or ""
    path_and_query = f"{path}?{parsed.query}" if parsed.query else path
    sanitized_url = f"{scheme}://{userinfo}{authority}{path_and_query}"
    return _ParsedCameraUrl(
        scheme=scheme,
        hostname=hostname,
        port=port,
        explicit_port=explicit_port,
        userinfo=userinfo,
        authority=authority,
        path_and_query=path_and_query,
        sanitized_url=sanitized_url,
    )


def sanitize_camera_url(url: str, allowed_schemes: tuple[str, ...]) -> str | None:
    """Return a canonical, credential-preserving URL after lexical/IP checks."""
    parsed = _parse_camera_url(url, allowed_schemes)
    return parsed.sanitized_url if parsed is not None else None


async def _resolve_allowed_address(hostname: str, port: int) -> str | None:
    literal = _parse_ip_address(hostname)
    if literal is not None:
        return str(literal)

    try:
        answers = await asyncio.get_running_loop().getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except (OSError, UnicodeError):
        return None

    addresses: list[str] = []
    for answer in answers:
        address = answer[4][0]
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        return None
    for address in addresses:
        if _unsafe_destination_reason(address):
            return None
    return addresses[0]


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(64 * 1024):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError, asyncio.CancelledError, RuntimeError):
        pass


async def _relay_bidirectionally(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    upstream_reader: asyncio.StreamReader,
    upstream_writer: asyncio.StreamWriter,
) -> None:
    tasks = {
        asyncio.create_task(_pipe(client_reader, upstream_writer)),
        asyncio.create_task(_pipe(upstream_reader, client_writer)),
    }
    _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def _rewrite_http_host(request_head: bytes, authority: str) -> bytes:
    lines = request_head.split(b"\r\n")
    replacement = f"Host: {authority}".encode("ascii")
    for index in range(1, len(lines)):
        if lines[index].lower().startswith(b"host:"):
            lines[index] = replacement
            break
    else:
        lines.insert(1, replacement)
    return b"\r\n".join(lines)


async def _start_http_relay(parsed: _ParsedCameraUrl, connect_ip: str) -> tuple[str, asyncio.Server]:
    ssl_context = ssl.create_default_context() if parsed.scheme == "https" else None

    async def handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
        upstream_writer: asyncio.StreamWriter | None = None
        try:
            request_head = await asyncio.wait_for(client_reader.readuntil(b"\r\n\r\n"), _CONNECT_TIMEOUT)
            if len(request_head) > _MAX_REQUEST_HEAD:
                return
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection(
                    connect_ip,
                    parsed.port,
                    ssl=ssl_context,
                    server_hostname=parsed.hostname if ssl_context is not None else None,
                ),
                _CONNECT_TIMEOUT,
            )
            upstream_writer.write(_rewrite_http_host(request_head, parsed.authority))
            await upstream_writer.drain()
            await _relay_bidirectionally(client_reader, client_writer, upstream_reader, upstream_writer)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError, OSError, TimeoutError):
            pass
        finally:
            for writer in (client_writer, upstream_writer):
                if writer is not None and not writer.is_closing():
                    writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    local_port = server.sockets[0].getsockname()[1]
    local_url = f"http://{parsed.userinfo}127.0.0.1:{local_port}{parsed.path_and_query}"
    return local_url, server


async def _start_rtsp_relay(parsed: _ParsedCameraUrl, connect_ip: str) -> tuple[str, asyncio.Server]:
    ssl_context: ssl.SSLContext | None = None
    if parsed.scheme == "rtsps":
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    local_port_ref = [0]

    async def handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
        upstream_writer: asyncio.StreamWriter | None = None
        try:
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection(
                    connect_ip,
                    parsed.port,
                    ssl=ssl_context,
                    server_hostname=parsed.hostname if ssl_context is not None else None,
                ),
                _CONNECT_TIMEOUT,
            )
            proxy_url = f"rtsp://127.0.0.1:{local_port_ref[0]}".encode()
            real_url = f"{parsed.scheme}://{parsed.authority}".encode()

            async def forward_requests() -> None:
                try:
                    while data := await client_reader.read(64 * 1024):
                        upstream_writer.write(rewrite_rtsp_request_url(data, proxy_url, real_url))
                        await upstream_writer.drain()
                except (ConnectionError, OSError, asyncio.CancelledError, RuntimeError):
                    pass

            tasks = {
                asyncio.create_task(forward_requests()),
                asyncio.create_task(_pipe(upstream_reader, client_writer)),
            }
            _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        except (ConnectionError, OSError, TimeoutError):
            pass
        finally:
            for writer in (client_writer, upstream_writer):
                if writer is not None and not writer.is_closing():
                    writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    local_port_ref[0] = server.sockets[0].getsockname()[1]
    local_url = f"rtsp://{parsed.userinfo}127.0.0.1:{local_port_ref[0]}{parsed.path_and_query}"
    return local_url, server


async def prepare_external_camera_url(
    url: str,
    allowed_schemes: tuple[str, ...],
) -> PreparedCameraSource | None:
    """Validate, resolve, and pin an external source behind a loopback relay."""
    parsed = _parse_camera_url(url, allowed_schemes)
    if parsed is None:
        return None
    connect_ip = await _resolve_allowed_address(parsed.hostname, parsed.port)
    if connect_ip is None:
        return None

    try:
        if parsed.scheme in ("http", "https"):
            local_url, server = await _start_http_relay(parsed, connect_ip)
        else:
            local_url, server = await _start_rtsp_relay(parsed, connect_ip)
    except OSError:
        return None
    return PreparedCameraSource(local_url, server, parsed.hostname, connect_ip)


def safe_usb_device_path(device: str) -> str | None:
    """Return an exact `/dev/videoN` path (N 0..99) when it exists."""
    match = re.fullmatch(r"/dev/video(\d{1,2})", device)
    if match is None:
        return None
    safe_path = Path(f"/dev/video{int(match.group(1))}")
    return str(safe_path) if safe_path.exists() else None
