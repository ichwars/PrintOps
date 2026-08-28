"""Serial-number normalization on the printer schema (#1465).

Bambu serial numbers are uppercase alphanumeric and the MQTT report topic
``device/<serial>/report`` is case-sensitive. A serial entered in the wrong
case connects and subscribes without error but never receives a message, so
the schema normalizes it on input.
"""

import pytest
from pydantic import ValidationError

from backend.app.schemas.printer import PrinterCreate


def _make(serial: str) -> PrinterCreate:
    return PrinterCreate(
        name="Test Printer",
        serial_number=serial,
        ip_address="192.168.1.50",
        access_code="12345678",
    )


def test_serial_number_uppercased():
    assert _make("01p00a3b1234567").serial_number == "01P00A3B1234567"


def test_serial_number_whitespace_stripped():
    assert _make("  01P00A3B1234567  ").serial_number == "01P00A3B1234567"


def test_serial_number_stripped_and_uppercased():
    assert _make(" 31b8c0ca1234567 ").serial_number == "31B8C0CA1234567"


def test_already_normalized_serial_unchanged():
    assert _make("31B8C0CA1234567").serial_number == "31B8C0CA1234567"


def test_blank_serial_number_rejected():
    with pytest.raises(ValidationError):
        _make("   ")


def test_h2c_requires_raw_model_code():
    with pytest.raises(ValidationError, match="raw model_code"):
        PrinterCreate(
            name="H2C",
            serial_number="09400A000000000",
            ip_address="192.168.1.51",
            access_code="12345678",
            model="H2C",
        )


@pytest.mark.parametrize("raw_code", ["O1C", "O1C2", " o1c2 "])
def test_h2c_preserves_normalized_raw_model_code(raw_code):
    request = PrinterCreate(
        name="H2C",
        serial_number="09400A000000000",
        ip_address="192.168.1.51",
        access_code="12345678",
        model="H2C",
        model_code=raw_code,
    )
    assert request.model_code in {"O1C", "O1C2"}
