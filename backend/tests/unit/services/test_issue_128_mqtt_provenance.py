"""Regression tests for per-print tray provenance from MQTT (issue #128)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.bambu_mqtt import BambuMQTTClient


def _tray_message(tray_now: int) -> dict:
    return {"print": {"ams": {"tray_now": str(tray_now)}}}


@pytest.fixture(autouse=True)
def _clear_request_topic_state():
    BambuMQTTClient._request_topic_cache.clear()
    failures = getattr(BambuMQTTClient, "_request_topic_probe_failures", None)
    if failures is not None:
        failures.clear()
    yield
    BambuMQTTClient._request_topic_cache.clear()
    if failures is not None:
        failures.clear()


def _client(serial: str = "ISSUE128") -> BambuMQTTClient:
    client = BambuMQTTClient(
        ip_address="10.0.0.9",
        serial_number=serial,
        access_code="12345678",
    )
    client._stale_reconnecting = False
    client._last_message_time = 0.0
    return client


def _start_request_topic_probe(client: BambuMQTTClient) -> None:
    import time

    client._request_topic_sub_mid = 7
    client._request_topic_sub_time = time.time()
    client._request_topic_confirmed = False


def _drop_during_probe(client: BambuMQTTClient) -> None:
    client._on_disconnect(
        None,
        None,
        disconnect_flags=None,
        rc=SimpleNamespace(is_failure=True),
    )


def test_running_tray_transitions_are_emitted_once():
    client = _client()
    client._was_running = True
    client._completion_triggered = False
    seen: list[tuple[int, int]] = []
    client.on_tray_change = lambda tray, layer: seen.append((tray, layer))

    client.state.layer_num = 0
    client._process_message(_tray_message(2))
    client.state.layer_num = 40
    client._process_message(_tray_message(2))
    client.state.layer_num = 80
    client._process_message(_tray_message(3))

    assert seen == [(2, 0), (3, 80)]
    assert client.state.tray_change_log == [(2, 0), (3, 80)]


def test_one_unexplained_probe_drop_keeps_mapping_capture_enabled():
    client = _client()
    _start_request_topic_probe(client)

    _drop_during_probe(client)

    assert client._request_topic_supported is True
    assert BambuMQTTClient._request_topic_cache.get("ISSUE128") is None
    assert BambuMQTTClient._request_topic_probe_failures["ISSUE128"] == 1


def test_second_consecutive_probe_drop_disables_mapping_capture():
    client = _client()
    _start_request_topic_probe(client)
    _drop_during_probe(client)
    _start_request_topic_probe(client)

    _drop_during_probe(client)

    assert client._request_topic_supported is False
    assert BambuMQTTClient._request_topic_cache["ISSUE128"] is False


def test_confirmed_suback_clears_prior_probe_failure():
    client = _client()
    _start_request_topic_probe(client)
    _drop_during_probe(client)
    client._request_topic_sub_mid = 7

    client._on_subscribe(
        None,
        None,
        7,
        [SimpleNamespace(is_failure=False, value=0, getName=lambda: "ok")],
    )

    assert BambuMQTTClient._request_topic_cache["ISSUE128"] is True
    assert "ISSUE128" not in BambuMQTTClient._request_topic_probe_failures


@pytest.mark.asyncio
async def test_printer_manager_forwards_tray_change_callback_to_client():
    from backend.app.services.printer_manager import PrinterManager

    manager = PrinterManager()
    callback = AsyncMock()
    manager.set_tray_change_callback(callback)
    printer = SimpleNamespace(
        id=42,
        ip_address="10.0.0.42",
        serial_number="ISSUE128-MANAGER",
        access_code="12345678",
        model="P1S",
        model_code="C12",
        firmware_version="01.07.00.00",
        name="P1S",
    )
    client = MagicMock()
    client.state.connected = True

    with (
        patch("backend.app.services.printer_manager.BambuMQTTClient", return_value=client) as constructor,
        patch("backend.app.services.printer_manager.asyncio.sleep", new_callable=AsyncMock),
    ):
        await manager.connect_printer(printer)

    assert callable(constructor.call_args.kwargs["on_tray_change"])
