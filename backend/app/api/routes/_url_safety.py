"""Shared URL-safety primitives for the SSRF guards in this package.

PrintOps has two outbound-URL policies:

- LAN services such as Spoolman, ntfy/webhooks, Home Assistant, Obico ML and
  slicer sidecars may legitimately live on loopback or the home LAN.
- Public internet resources such as OIDC issuer/icon URLs must not point to
  private networks.

Both policies reject unsafe cases that are never legitimate: non-HTTP schemes,
numeric-encoded IPs, cloud metadata endpoints, multicast and unspecified
addresses, and IPv4-mapped IPv6 encodings of those addresses.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

# Cloud-provider metadata endpoints — the classic SSRF credential-exfil
# targets. Both guards reject these unconditionally.
CLOUD_METADATA_IPS = frozenset(
    {
        # AWS / GCP / Azure / Oracle / DigitalOcean IMDS
        ipaddress.ip_address("169.254.169.254"),
        # Alibaba Cloud metadata
        ipaddress.ip_address("100.100.100.200"),
        # AWS IMDS IPv6
        ipaddress.ip_address("fd00:ec2::254"),
    }
)

CLOUD_METADATA_HOSTNAMES = frozenset(
    {
        "metadata.google.internal",
        "metadata.goog",
    }
)


# libc and browsers parse numeric-encoded IP forms (decimal ``2130706433``
# for 127.0.0.1, hex ``0x7f000001``) but Python's ``ipaddress.ip_address``
# raises ValueError on these, so they slip past the IP-class checks if
# not caught first. Used by both guards to reject up-front.
NUMERIC_IP_RE = re.compile(r"^(0x[0-9a-f]+|[0-9]+)$", re.I)


def canonical_url_hostname(hostname: str | None) -> str:
    """Normalize a parsed URL hostname for policy checks."""
    return (hostname or "").rstrip(".").lower()


def unwrap_ipv4_mapped(
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Return the underlying IPv4 for an IPv4-mapped IPv6 address, else return *addr*.

    ``::ffff:127.0.0.1`` and similar mapped forms must be unwrapped before
    the per-class checks (``is_private``, ``is_loopback``, …) — otherwise
    an attacker can encode a blocked IPv4 address as an IPv6 literal to
    bypass the guard.
    """
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    return addr


def assert_safe_lan_service_url(url: str, *, label: str) -> None:
    """Raise ValueError if *url* is unsafe for a service that may live on the LAN."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"{label} must use http or https")

    hostname = canonical_url_hostname(parsed.hostname)
    if not hostname:
        raise ValueError(f"{label} must include a hostname")

    if hostname in CLOUD_METADATA_HOSTNAMES:
        raise ValueError(f"{label} must not point to a cloud metadata endpoint")

    if NUMERIC_IP_RE.match(hostname):
        raise ValueError(f"{label} must not use numeric-encoded IP addresses; use standard dotted-decimal notation")

    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        return

    effective = unwrap_ipv4_mapped(addr)

    if effective in CLOUD_METADATA_IPS:
        raise ValueError(f"{label} must not point to a cloud metadata endpoint")

    if effective.is_multicast or effective.is_unspecified:
        raise ValueError(f"{label} must not point to a multicast or unspecified address")
