"""Validation shared by advertised-address configuration and wire protocols."""

from ipaddress import IPv4Address


def validate_advertised_ip(value: str | None) -> str | None:
    """Accept an optional literal unicast IPv4 address reachable by a slicer.

    Hostnames and IPv6 are unsupported by the existing SSDP/PASV wire format.
    Reject special-purpose destinations rather than advertising an unusable IP.
    Reachability itself depends on the operator's routing and port mappings.
    """
    if value is None or not value.strip():
        return None
    address = IPv4Address(value.strip())
    if (
        address.is_unspecified
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or int(address) < 0x01000000
    ):
        raise ValueError("Advertised address must be a unicast IPv4 address")
    return str(address)
