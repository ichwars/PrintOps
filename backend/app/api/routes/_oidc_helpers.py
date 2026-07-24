"""Pure helper functions for OIDC routes.

Hosts the SSRF guard for admin-supplied icon URLs. Stricter than
``_spoolman_helpers.assert_safe_spoolman_url`` — Spoolman intentionally allows
loopback/RFC-1918 (same-LAN topology) while OIDC icons must be reachable on
the public internet (IdP-hosted), so private addresses there are SSRF probes.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import urlparse

import httpx

from backend.app.api.routes._url_safety import CLOUD_METADATA_IPS, NUMERIC_IP_RE, unwrap_ipv4_mapped


class OIDCEndpointPolicyError(ValueError):
    """An OIDC server-side endpoint violates the outbound network policy."""


async def _resolve_oidc_host(hostname: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    """Resolve a hostname once so the validated address can be pinned to the connection."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            hostname,
            443,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise OIDCEndpointPolicyError(f"OIDC endpoint hostname could not be resolved: {hostname}") from exc

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        address = unwrap_ipv4_mapped(ipaddress.ip_address(info[4][0]))
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise OIDCEndpointPolicyError(f"OIDC endpoint hostname did not resolve: {hostname}")
    return tuple(addresses)


def _oidc_address_scope(
    addresses: Iterable[ipaddress.IPv4Address | ipaddress.IPv6Address],
) -> str:
    """Return ``public`` or ``private`` after rejecting ambiguous/unsafe answers."""
    scopes: set[str] = set()
    for address in addresses:
        if address in CLOUD_METADATA_IPS:
            raise OIDCEndpointPolicyError("OIDC endpoint must not resolve to a cloud metadata address")
        if address.is_unspecified or address.is_multicast or address.is_link_local:
            raise OIDCEndpointPolicyError("OIDC endpoint resolved to an unusable network address")
        scopes.add("public" if address.is_global else "private")
    if len(scopes) != 1:
        raise OIDCEndpointPolicyError("OIDC endpoint returned mixed public/private DNS answers")
    return scopes.pop()


def _validated_oidc_url(url: httpx.URL) -> None:
    if url.scheme != "https" or not url.host:
        raise OIDCEndpointPolicyError("OIDC server endpoints must use https://")
    if url.username or url.password:
        raise OIDCEndpointPolicyError("OIDC server endpoints must not contain URL credentials")
    if url.fragment:
        raise OIDCEndpointPolicyError("OIDC server endpoints must not contain fragments")


class OIDCPinnedTransport(httpx.AsyncBaseTransport):
    """Validate and DNS-pin every OIDC request while retaining private IdP support.

    The configured issuer is an operator-selected trust anchor and may resolve
    wholly to private addresses. Discovery-provided endpoints may use a
    different hostname only when both issuer and endpoint are wholly public.
    Same-host private deployments (PocketID, Authentik, Keycloak) remain
    supported. Each request is rewritten to the validated IP while preserving
    the original Host header and TLS SNI, eliminating the DNS check/connect
    race. Callers keep redirects disabled; a discovered redirect can therefore
    never create an unvalidated second hop.
    """

    def __init__(
        self,
        issuer_url: str,
        *,
        allow_private_network: bool = False,
        inner: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._issuer_url = httpx.URL(issuer_url)
        _validated_oidc_url(self._issuer_url)
        self._allow_private_network = allow_private_network
        self._inner = inner or httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        original_url = request.url
        _validated_oidc_url(original_url)

        issuer_addresses = await _resolve_oidc_host(self._issuer_url.host)
        issuer_scope = _oidc_address_scope(issuer_addresses)
        if issuer_scope == "private" and not self._allow_private_network:
            raise OIDCEndpointPolicyError(
                "OIDC issuer resolved to a private address, but private-network access is disabled"
            )
        if issuer_scope == "private" and (original_url.port or 443) != (self._issuer_url.port or 443):
            raise OIDCEndpointPolicyError("private OIDC endpoints must use the configured issuer TLS port")

        if original_url.host == self._issuer_url.host:
            endpoint_addresses = issuer_addresses
        else:
            endpoint_addresses = await _resolve_oidc_host(original_url.host)
            endpoint_scope = _oidc_address_scope(endpoint_addresses)
            private_same_service = (
                issuer_scope == "private"
                and endpoint_scope == "private"
                and set(endpoint_addresses) == set(issuer_addresses)
                and (original_url.port or 443) == (self._issuer_url.port or 443)
            )
            if not private_same_service and (issuer_scope != "public" or endpoint_scope != "public"):
                raise OIDCEndpointPolicyError(
                    "private OIDC endpoints must resolve to the issuer service and use its TLS port"
                )

        pinned_address = endpoint_addresses[0]
        request.url = original_url.copy_with(host=str(pinned_address))
        request.headers["Host"] = original_url.netloc.decode("ascii")
        request.extensions["sni_hostname"] = original_url.host
        return await self._inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self._inner.aclose()


def assert_safe_public_https_url(url: str) -> None:
    """Raise ValueError if *url* is unsafe to fetch as a public HTTPS resource.

    Used for OIDC provider icon URLs (#1333). Stricter than the Spoolman SSRF
    guard: also rejects loopback, private (RFC-1918), and link-local addresses
    because an OIDC icon legitimately lives only on the public internet.

    Checks performed:
    - Scheme must be ``https`` (no ``http://``, ``file://``, ``gopher://``, …).
    - Numeric-encoded IPv4 (decimal ``2130706433``, hex ``0x7f000001``) is
      rejected — libc and browsers parse those as valid addresses while
      Python's ``ipaddress`` raises ValueError, so they bypass the IP block
      below if not caught first.
    - Cloud-provider metadata endpoints (169.254.169.254, 100.100.100.200,
      fd00:ec2::254) — classic SSRF credential-exfil targets.
    - Loopback (127.0.0.0/8, ::1), private RFC-1918 (10/8, 172.16/12,
      192.168/16) and link-local (169.254/16, fe80::/10) addresses.
    - Multicast (224.0.0.0/4, ff00::/8) and unspecified (0.0.0.0, ::).
    - IPv4-mapped IPv6 (``::ffff:127.0.0.1``) — unwrapped before the IP-class
      check so an attacker can't bypass via IPv6 encoding.

    Hostname-based addresses are accepted without DNS resolution (consistent
    with ``_validate_issuer_url`` policy — the operator is trusted to
    configure a sensible IdP host).
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("icon URL must use https://")

    hostname = (parsed.hostname or "").lower()

    if NUMERIC_IP_RE.match(hostname):
        raise ValueError("icon URL must not use numeric-encoded IP addresses")

    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        return  # hostname — out of scope (no DNS check by design)

    effective = unwrap_ipv4_mapped(addr)

    if effective in CLOUD_METADATA_IPS:
        raise ValueError("icon URL must not point to a cloud metadata endpoint")

    # Order matters: 0.0.0.0 sets BOTH is_private and is_unspecified — check
    # the more-specific is_unspecified first so the error message points at
    # the actual misuse. Similarly 127.0.0.1 sets is_loopback and is_private
    # (private under IANA's reservation); is_loopback first is clearer.
    if effective.is_unspecified:
        raise ValueError("icon URL must not point to an unspecified address")
    if effective.is_loopback:
        raise ValueError("icon URL must not point to a loopback address")
    if effective.is_link_local:
        raise ValueError("icon URL must not point to a link-local address")
    if effective.is_multicast:
        raise ValueError("icon URL must not point to a multicast address")
    if effective.is_private:
        raise ValueError("icon URL must not point to a private (RFC-1918) address")
