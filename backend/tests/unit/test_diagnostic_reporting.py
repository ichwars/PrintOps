import asyncio
import json
import logging
import ssl
from concurrent.futures import Future
from email.mime.multipart import MIMEMultipart
from email.utils import parsedate_to_datetime
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from backend.app.core.logging_filters import ShutdownCancelledRequestFilter
from backend.app.services import printer_diagnostic
from backend.app.services.email_service import add_message_headers
from backend.app.services.firmware_check import FirmwareCheckService
from backend.app.services.homeassistant import _tls_connection_error
from backend.app.services.printer_manager import PrinterManager


def test_mail_headers_use_the_sender_domain_without_overwriting_headers():
    message = MIMEMultipart()
    add_message_headers(message, "PrintOps <reports@example.test>")
    message_id = message["Message-ID"]
    assert parsedate_to_datetime(message["Date"]).utcoffset().total_seconds() == 0
    assert message_id.endswith("@example.test>")
    add_message_headers(message, "other@example.net")
    assert message.get_all("Message-ID") == [message_id]
    assert len(message.get_all("Date")) == 1


def test_only_uvicorn_grace_period_cancellation_is_downgraded():
    diagnostic_filter = ShutdownCancelledRequestFilter()
    for text, expected in [
        ("timeout graceful shutdown exceeded", logging.INFO),
        ("client cancellation", logging.ERROR),
    ]:
        try:
            raise asyncio.CancelledError(text)
        except asyncio.CancelledError as error:
            record = logging.LogRecord(
                "uvicorn.error",
                logging.ERROR,
                "",
                0,
                "Exception in ASGI application",
                (),
                (type(error), error, error.__traceback__),
            )
        assert diagnostic_filter.filter(record)
        assert record.levelno == expected
        assert (record.exc_info is None) == (expected == logging.INFO)


@pytest.mark.parametrize(
    ("link", "expected"),
    [
        ({"info_kind": "veth"}, "bridge"),
        ({"info_kind": "macvlan"}, "macvlan"),
        ({"info_kind": "ipvlan", "info_data": {"mode": "l2"}}, "ipvlan"),
        ({"info_kind": "ipvlan", "info_data": {"mode": "l3s"}}, "ipvlan_l3"),
    ],
)
def test_network_probe_uses_kernel_link_kind(monkeypatch, link, expected):
    monkeypatch.setattr(printer_diagnostic.socket, "if_nameindex", lambda: [(1, "lo"), (2, "eth0")])
    runner = Mock(return_value=SimpleNamespace(stdout=json.dumps([{"ifname": "eth0", "linkinfo": link}])))
    monkeypatch.setattr(printer_diagnostic.subprocess, "run", runner)
    assert printer_diagnostic._detect_docker_network_mode() == expected
    assert runner.call_args.args == (["ip", "-d", "-j", "link", "show"],)


@pytest.mark.parametrize("verify_code, description", [(62, "hostname"), (10, "expired"), (18, "trust store")])
def test_home_assistant_tls_diagnostics_use_safe_specific_messages(verify_code, description):
    cert_error = ssl.SSLCertVerificationError(1, "test detail")
    cert_error.verify_code = verify_code
    failure = httpx.ConnectError("connection failed")
    failure.__cause__ = cert_error
    message = _tls_connection_error(failure)
    assert description in message
    assert "test detail" not in message
    assert _tls_connection_error(httpx.ConnectError("unreachable")) == "Could not connect to Home Assistant"


async def test_firmware_transport_logs_each_host_outage_once_and_rearms_after_recovery(caplog):
    service = FirmwareCheckService()
    try:
        with caplog.at_level(logging.INFO, logger="backend.app.services.firmware_check"):
            caplog.clear()
            url = "https://wiki.bambulab.com/fixture"
            for _ in range(3):
                service._report_transport(url, httpx.ConnectError("fixture"))
            service._report_transport(url)
            service._report_transport(url, httpx.ConnectError("fixture"))
            assert [entry.levelno for entry in caplog.records] == [logging.WARNING, logging.INFO, logging.WARNING]
    finally:
        await service._client.aclose()


def test_mqtt_callback_cancellation_keeps_other_callback_errors_visible(monkeypatch, caplog):
    manager = PrinterManager()
    manager._loop = Mock()
    outcome = Future()

    def schedule(coro, _loop):
        coro.close()
        return outcome

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", schedule)
    manager._schedule_async(asyncio.sleep(0))
    outcome.cancel()
    assert "Exception in scheduled callback" not in caplog.text
    outcome = Future()
    manager._schedule_async(asyncio.sleep(0))
    outcome.set_exception(RuntimeError("callback fixture failure"))
    assert "callback fixture failure" in caplog.text
