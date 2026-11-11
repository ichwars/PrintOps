"""Bound decoder work on hostile ASN.1 while preserving LDAP responses."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest
from pyasn1.codec.ber import decoder, encoder
from pyasn1.error import PyAsn1Error
from pyasn1.type import univ


def _tlv(tag: int, content: bytes) -> bytes:
    size = len(content)
    length = size.to_bytes(max(1, (size.bit_length() + 7) // 8), "big")
    return bytes((tag, 0x80 | len(length))) + length + content


def _exercise_decoder(case: str) -> None:
    """Use CPU time, independent of parallel-test scheduling, with ample headroom."""
    if case == "bits":
        wire = _tlv(0x23, b"\x03\x02\x00\x96" * 400_000)
        expected_size = 3_200_000
    elif case == "tags":
        components = []
        for index in range(16_000):
            number = 32 + index * sys.hash_info.modulus
            groups = [number & 127]
            number >>= 7
            while number:
                groups.append(0x80 | (number & 127))
                number >>= 7
            components.append(b"\xbf" + bytes(reversed(groups)) + b"\x03\x04\x01x")
        wire = _tlv(0x30, b"".join(components))
        expected_size = len(components)
    elif case == "real":
        wire = _tlv(0x09, b"\x80\x00" + b"\x01" * 800_000)
        expected_size = 6_399_993
    else:
        # CER-shaped sibling fragments, not deep nesting: input size stays bounded.
        fragment = _tlv(0x04, b"x" * 1000)
        wire = b"\x24\x80" + fragment * 16_000 + b"\x00\x00"
        expected_size = 16_000_000

    start = time.process_time()
    value, remaining = decoder.decode(wire)
    elapsed = time.process_time() - start
    assert not remaining
    if case == "real":
        assert value[0].bit_length() == expected_size
    else:
        assert len(value) == expected_size
    if case == "bits":
        assert value[:8] == univ.BitString(hexValue="96")
    elif case == "tags":
        assert value[-1].asOctets() == b"x"
        assert value[-1].tagSet[-1].tagId == 32 + (expected_size - 1) * sys.hash_info.modulus
    elif case == "strings":
        assert value.asOctets() == b"x" * expected_size
    assert elapsed < 5, f"ASN.1 {case} decoding consumed {elapsed:.2f}s CPU"


@pytest.mark.parametrize("case", ["bits", "tags", "real", "strings"])
def test_hostile_asn1_does_not_consume_quadratic_cpu(case):
    """CVE-2026-119194/195/196/197: kill a regressed decoder after 30 seconds."""
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), case],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_truncated_asn1_is_rejected():
    with pytest.raises(PyAsn1Error):
        decoder.decode(b"\x04\x82\xff\xffx")


def test_ldap_bind_response_still_decodes_with_its_schema():
    from ldap3.protocol.rfc4511 import LDAPMessage

    message = LDAPMessage()
    message["messageID"] = 7
    response = message["protocolOp"]["bindResponse"]
    response["resultCode"] = 0
    response["matchedDN"] = "cn=printops,dc=example"
    response["diagnosticMessage"] = ""
    decoded, remaining = decoder.decode(encoder.encode(message), asn1Spec=LDAPMessage())
    assert not remaining
    assert int(decoded["messageID"]) == 7
    assert int(decoded["protocolOp"]["bindResponse"]["resultCode"]) == 0
    assert str(decoded["protocolOp"]["bindResponse"]["matchedDN"]) == "cn=printops,dc=example"


if __name__ == "__main__":
    _exercise_decoder(sys.argv[1])
