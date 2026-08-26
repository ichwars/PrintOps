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
_DNS_TIMEOUT = 5.0


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
    connect_ips: tuple[str, ...]

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
    if parsed.params:
        path = f"{path};{parsed.params}"
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


async def _resolve_allowed_address(hostname: str, port: int) -> tuple[str, ...] | None:
    literal = _parse_ip_address(hostname)
    if literal is not None:
        return (str(literal),)

    try:
        answers = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(
                hostname,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            ),
            _DNS_TIMEOUT,
        )
    except (OSError, UnicodeError, TimeoutError):
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
    return tuple(addresses)


async def _open_connection_any(
    connect_ips: tuple[str, ...] | str,
    port: int,
    *,
    ssl_context: ssl.SSLContext | None = None,
    server_hostname: str | None = None,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Try every validated DNS answer before declaring the camera unreachable."""
    addresses = (connect_ips,) if isinstance(connect_ips, str) else connect_ips
    last_error: BaseException | None = None
    for address in addresses:
        try:
            return await asyncio.wait_for(
                asyncio.open_connection(
                    address,
                    port,
                    ssl=ssl_context,
                    server_hostname=server_hostname if ssl_context is not None else None,
                ),
                _CONNECT_TIMEOUT,
            )
        except (ConnectionError, OSError, TimeoutError) as exc:
            last_error = exc
    raise OSError("all validated camera addresses are unreachable") from last_error


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
    connection_seen = False
    for index in range(1, len(lines)):
        if lines[index].lower().startswith(b"host:"):
            lines[index] = replacement
        elif lines[index].lower().startswith(b"connection:"):
            lines[index] = b"Connection: close"
            connection_seen = True
    if not any(line.lower().startswith(b"host:") for line in lines[1:]):
        lines.insert(1, replacement)
    if not connection_seen:
        lines.insert(-2, b"Connection: close")
    return b"\r\n".join(lines)


async def _start_http_relay(parsed: _ParsedCameraUrl, connect_ips: tuple[str, ...] | str) -> tuple[str, asyncio.Server]:
    ssl_context = ssl.create_default_context() if parsed.scheme == "https" else None

    async def handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
        upstream_writer: asyncio.StreamWriter | None = None
        try:
            request_head = await asyncio.wait_for(client_reader.readuntil(b"\r\n\r\n"), _CONNECT_TIMEOUT)
            if len(request_head) > _MAX_REQUEST_HEAD:
                return
            upstream_reader, upstream_writer = await _open_connection_any(
                connect_ips,
                parsed.port,
                ssl_context=ssl_context,
                server_hostname=parsed.hostname,
            )
            upstream_writer.write(_rewrite_http_host(request_head, parsed.authority))
            await upstream_writer.drain()
            response_head = await asyncio.wait_for(upstream_reader.readuntil(b"\r\n\r\n"), _CONNECT_TIMEOUT)
            if len(response_head) > _MAX_REQUEST_HEAD:
                return
            status_line = response_head.split(b"\r\n", 1)[0]
            status_match = re.match(rb"HTTP/\d(?:\.\d)?\s+(\d{3})(?:\s|$)", status_line)
            if status_match and 300 <= int(status_match.group(1)) < 400:
                client_writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                await client_writer.drain()
                return
            client_writer.write(response_head)
            await client_writer.drain()
            await _pipe(upstream_reader, client_writer)
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


async def _start_rtsp_relay(parsed: _ParsedCameraUrl, connect_ips: tuple[str, ...] | str) -> tuple[str, asyncio.Server]:
    ssl_context: ssl.SSLContext | None = None
    if parsed.scheme == "rtsps":
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    local_port_ref = [0]

    async def handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
        upstream_writer: asyncio.StreamWriter | None = None
        try:
            upstream_reader, upstream_writer = await _open_connection_any(
                connect_ips,
                parsed.port,
                ssl_context=ssl_context,
                server_hostname=parsed.hostname,
            )
            proxy_url = f"rtsp://127.0.0.1:{local_port_ref[0]}".encode()
            real_url = f"{parsed.scheme}://{parsed.authority}".encode()

            async def forward_requests() -> None:
                try:
                    while True:
                        request_head = await client_reader.readuntil(b"\r\n\r\n")
                        if len(request_head) > _MAX_REQUEST_HEAD:
                            return
                        content_length_match = re.search(rb"(?im)^Content-Length:\s*(\d+)\s*$", request_head)
                        content_length = int(content_length_match.group(1)) if content_length_match else 0
                        request_body = await client_reader.readexactly(content_length) if content_length else b""
                        if re.search(rb"(?im)^Authorization:\s*Digest\s", request_head):
                            upstream_writer.write(request_head + request_body)
                        else:
                            upstream_writer.write(
                                rewrite_rtsp_request_url(request_head, proxy_url, real_url) + request_body
                            )
                        await upstream_writer.drain()
                except (
                    asyncio.IncompleteReadError,
                    asyncio.LimitOverrunError,
                    ConnectionError,
                    OSError,
                    asyncio.CancelledError,
                    RuntimeError,
                ):
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
    connect_ips = await _resolve_allowed_address(parsed.hostname, parsed.port)
    if connect_ips is None:
        return None

    try:
        if parsed.scheme in ("http", "https"):
            local_url, server = await _start_http_relay(parsed, connect_ips)
        else:
            local_url, server = await _start_rtsp_relay(parsed, connect_ips)
    except OSError:
        return None
    addresses = (connect_ips,) if isinstance(connect_ips, str) else connect_ips
    return PreparedCameraSource(local_url, server, parsed.hostname, addresses[0], addresses)


def safe_usb_device_path(device: str) -> str | None:
    """Return an exact `/dev/videoN` path (N 0..99) when it exists."""
    match = re.fullmatch(r"/dev/video(\d{1,2})", device)
    if match is None:
        return None
    safe_path = Path(f"/dev/video{int(match.group(1))}")
    return str(safe_path) if safe_path.exists() else None
