"""Unit tests for the shared SSRF-data primitives (#1333).

These primitives are imported by both ``_spoolman_helpers.assert_safe_spoolman_url``
and ``_oidc_helpers.assert_safe_public_https_url``. Test them in isolation
so a future change to one consumer doesn't accidentally drift the data.
"""

import ipaddress

import pytest

from backend.app.api.routes._oidc_helpers import assert_safe_public_https_url
from backend.app.api.routes._url_safety import (
    CLOUD_METADATA_HOSTNAMES,
    CLOUD_METADATA_IPS,
    assert_safe_lan_service_url,
    canonical_url_hostname,
    is_numeric_encoded_ip,
    unwrap_ipv4_mapped,
)
from backend.app.services.camera_source_security import sanitize_camera_url


def test_cloud_metadata_set_contains_known_endpoints():
    # Both v4 and v6 IMDS endpoints, plus Alibaba's variant.
    assert ipaddress.ip_address("169.254.169.254") in CLOUD_METADATA_IPS
    assert ipaddress.ip_address("100.100.100.200") in CLOUD_METADATA_IPS
    assert ipaddress.ip_address("fd00:ec2::254") in CLOUD_METADATA_IPS


def test_cloud_metadata_set_is_frozen():
    # frozenset is the right immutable container — protects against
    # accidental mutation in tests/imports.
    assert isinstance(CLOUD_METADATA_IPS, frozenset)


@pytest.mark.parametrize(
    "candidate",
    [
        "2130706433",  # decimal-encoded 127.0.0.1
        "0x7f000001",  # hex-encoded 127.0.0.1
        "0xFFFFFFFF",  # uppercase hex
        "0",
        "4294967295",  # max uint32
        "127.1",
        "0177.0.0.1",
        "0x7f.0x0.0x0.0x1",
        "0x7f.1",
        "192.168.000.20",
    ],
)
def test_alternate_numeric_ipv4_forms_detected(candidate):
    assert is_numeric_encoded_ip(candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        "127.0.0.1",  # dotted-decimal — not "numeric-encoded"
        "example.com",
        "spoolman.lan",
        "::1",
        "localhost",
    ],
)
def test_standard_hosts_are_not_numeric_encodings(candidate):
    assert not is_numeric_encoded_ip(candidate)


def test_unwrap_ipv4_mapped_unwraps_mapped_address():
    mapped = ipaddress.ip_address("::ffff:127.0.0.1")
    result = unwrap_ipv4_mapped(mapped)
    assert result == ipaddress.ip_address("127.0.0.1")
    assert isinstance(result, ipaddress.IPv4Address)


def test_unwrap_ipv4_mapped_passes_through_pure_ipv4():
    addr = ipaddress.ip_address("8.8.8.8")
    assert unwrap_ipv4_mapped(addr) is addr


def test_unwrap_ipv4_mapped_passes_through_pure_ipv6():
    addr = ipaddress.ip_address("2001:db8::1")
    assert unwrap_ipv4_mapped(addr) is addr


def test_canonical_url_hostname_strips_trailing_dot_and_lowercases():
    assert canonical_url_hostname("Metadata.Google.Internal.") == "metadata.google.internal"


def test_lan_service_guard_rejects_metadata_hostname_with_trailing_dot():
    with pytest.raises(ValueError, match="cloud metadata"):
        assert_safe_lan_service_url("https://metadata.google.internal./latest", label="service URL")


def test_public_https_guard_rejects_metadata_hostname_with_trailing_dot():
    with pytest.raises(ValueError, match="cloud metadata"):
        assert_safe_public_https_url("https://metadata.google.internal./icon.png")


@pytest.mark.parametrize(
    "host",
    [
        *sorted(CLOUD_METADATA_HOSTNAMES),
        *sorted(str(address) if address.version == 4 else f"[{address}]" for address in CLOUD_METADATA_IPS),
        "INSTANCE-DATA.",
        "[fd00:ec2::23%25eth0]",
        "[fe80::a9fe:a9fe%25eth0]",
    ],
)
def test_lan_public_and_camera_guards_block_shared_metadata_endpoints(host):
    url = f"https://{host}/metadata"
    with pytest.raises(ValueError, match="cloud metadata"):
        assert_safe_lan_service_url(url, label="service URL")
    with pytest.raises(ValueError, match="cloud metadata"):
        assert_safe_public_https_url(url)
    assert sanitize_camera_url(url, ("https",)) is None


@pytest.mark.parametrize("host", ["169.254.1.1", "[::ffff:169.254.1.1]"])
def test_lan_guard_rejects_ipv4_link_local(host):
    with pytest.raises(ValueError, match="IPv4 link-local"):
        assert_safe_lan_service_url(f"http://{host}/api", label="service URL")


@pytest.mark.parametrize("host", ["127.0.0.1", "192.168.1.10", "[fd12::1234]", "[fe80::1%25eth0]"])
def test_lan_guard_accepts_local_service_addresses(host):
    assert_safe_lan_service_url(f"http://{host}/api", label="service URL")


@pytest.mark.parametrize("host", ["0xa9.0xfe.0xa9.0xfe", "0251.0376.0251.0376", "169.254.43518", "0x7f.1."])
def test_url_guards_reject_nonstandard_ip_notation(host):
    url = f"https://{host}/test"
    with pytest.raises(ValueError, match="numeric-encoded"):
        assert_safe_lan_service_url(url, label="service URL")
    with pytest.raises(ValueError, match="numeric-encoded"):
        assert_safe_public_https_url(url)
    assert sanitize_camera_url(url, ("https",)) is None


@pytest.mark.parametrize(
    "host",
    [
        "metadata\u3002google\u3002internal",
        "\uff11\uff12\uff17.0.0.1",
        "\u24dcetadata.google.internal",
    ],
)
def test_url_guards_reject_non_ascii_host_spellings(host):
    url = f"https://{host}/test"
    with pytest.raises(ValueError, match="ASCII hostname"):
        assert_safe_lan_service_url(url, label="service URL")
    with pytest.raises(ValueError, match="ASCII hostname"):
        assert_safe_public_https_url(url)
    assert sanitize_camera_url(url, ("https",)) is None


def test_url_guards_accept_punycode_hosts():
    url = "https://xn--kamera-kche-dlb.example.test/camera"
    assert_safe_lan_service_url(url, label="service URL")
    assert_safe_public_https_url(url)
    assert sanitize_camera_url(url, ("https",)) == url
