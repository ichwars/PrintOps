"""Regression tests for the webhook printer-status / stop / cancel routes.

Pre-fix the routes treated ``printer_manager.get_status(...)``'s return value
as a dict and called ``.get(...)`` on it. The return is a ``PrinterState``
dataclass (``backend/app/services/bambu_mqtt.py``), so the call raised
``AttributeError`` and surfaced as a generic 500 for any printer that
actually had a status row. See #1584.
"""

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from backend.app.services.bambu_mqtt import PrinterState


@pytest.fixture
async def api_key_data(async_client: AsyncClient, db_session):
    """API key with read_status + control_printer scopes — covers status,
    stop, and cancel in a single fixture."""
    from backend.app.core.auth import generate_api_key
    from backend.app.models.api_key import APIKey

    full_key, key_hash, key_prefix = generate_api_key()
    api_key = APIKey(
        name="webhook-status-test-key",
        key_hash=key_hash,
        key_prefix=key_prefix,
        can_read_status=True,
        can_control_printer=True,
        enabled=True,
    )
    db_session.add(api_key)
    await db_session.commit()
    return full_key


@pytest.fixture
async def printer_row(db_session):
    from backend.app.models.printer import Printer

    printer = Printer(
        name="StatusTest",
        ip_address="192.168.1.44",
        access_code="12345678",
        serial_number="00M00A000000010",
        model="P1S",
    )
    db_session.add(printer)
    await db_session.commit()
    return printer


class TestWebhookGetPrinterStatus:
    """``GET /api/v1/webhook/printer/{id}/status`` — the route reads the
    dataclass via attribute access, not ``.get(...)``. Pre-fix the call
    raised AttributeError → 500 for every printer with a status row.
    """

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_200_with_connected_dataclass_status(
        self,
        async_client: AsyncClient,
        api_key_data,
        printer_row,
    ):
        """A live PrinterState dataclass must yield a 200 with the
        attributes mapped into the response — this is the exact regression
        from #1584 where the dataclass crashed the ``.get(...)`` calls."""
        state = PrinterState(
            connected=True,
            state="RUNNING",
            current_print="bench.3mf",
            progress=42.0,
            remaining_time=1234,
        )
        with patch(
            "backend.app.api.routes.webhook.printer_manager.get_status",
            MagicMock(return_value=state),
        ):
            resp = await async_client.get(
                f"/api/v1/webhook/printer/{printer_row.id}/status",
                headers={"X-API-Key": api_key_data},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == printer_row.id
        assert body["name"] == "StatusTest"
        assert body["connected"] is True
        assert body["state"] == "RUNNING"
        assert body["current_print"] == "bench.3mf"
        assert body["progress"] == 42.0
        assert body["remaining_time"] == 1234

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_200_when_status_is_none(
        self,
        async_client: AsyncClient,
        api_key_data,
        printer_row,
    ):
        """A registered printer the manager hasn't seen yet returns None from
        ``get_status``; the response must still be 200 with sensible
        defaults rather than 500."""
        with patch(
            "backend.app.api.routes.webhook.printer_manager.get_status",
            MagicMock(return_value=None),
        ):
            resp = await async_client.get(
                f"/api/v1/webhook/printer/{printer_row.id}/status",
                headers={"X-API-Key": api_key_data},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == printer_row.id
        assert body["connected"] is False
        assert body["state"] is None
        assert body["current_print"] is None
        assert body["progress"] is None
        assert body["remaining_time"] is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_404_when_printer_does_not_exist(
        self,
        async_client: AsyncClient,
        api_key_data,
    ):
        resp = await async_client.get(
            "/api/v1/webhook/printer/99999/status",
            headers={"X-API-Key": api_key_data},
        )
        assert resp.status_code == 404


class TestWebhookStopPrint:
    """``POST /api/v1/webhook/printer/{id}/stop`` — same dataclass-shape
    fix applies to the connection / state precondition checks (#1584)."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_503_when_disconnected(
        self,
        async_client: AsyncClient,
        api_key_data,
        printer_row,
    ):
        state = PrinterState(connected=False, state="unknown")
        with patch(
            "backend.app.api.routes.webhook.printer_manager.get_status",
            MagicMock(return_value=state),
        ):
            resp = await async_client.post(
                f"/api/v1/webhook/printer/{printer_row.id}/stop",
                headers={"X-API-Key": api_key_data},
            )
        # Pre-fix this would have 500'd on `status.get(...)`. Now it
        # cleanly returns the documented 503.
        assert resp.status_code == 503

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_409_when_not_running(
        self,
        async_client: AsyncClient,
        api_key_data,
        printer_row,
    ):
        state = PrinterState(connected=True, state="FINISH")
        with patch(
            "backend.app.api.routes.webhook.printer_manager.get_status",
            MagicMock(return_value=state),
        ):
            resp = await async_client.post(
                f"/api/v1/webhook/printer/{printer_row.id}/stop",
                headers={"X-API-Key": api_key_data},
            )
        assert resp.status_code == 409


class TestWebhookCancelPrint:
    """``POST /api/v1/webhook/printer/{id}/cancel`` — same fix shape."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_503_when_disconnected(
        self,
        async_client: AsyncClient,
        api_key_data,
        printer_row,
    ):
        state = PrinterState(connected=False, state="unknown")
        with patch(
            "backend.app.api.routes.webhook.printer_manager.get_status",
            MagicMock(return_value=state),
        ):
            resp = await async_client.post(
                f"/api/v1/webhook/printer/{printer_row.id}/cancel",
                headers={"X-API-Key": api_key_data},
            )
        assert resp.status_code == 503

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_409_when_not_running_or_paused(
        self,
        async_client: AsyncClient,
        api_key_data,
        printer_row,
    ):
        state = PrinterState(connected=True, state="IDLE")
        with patch(
            "backend.app.api.routes.webhook.printer_manager.get_status",
            MagicMock(return_value=state),
        ):
            resp = await async_client.post(
                f"/api/v1/webhook/printer/{printer_row.id}/cancel",
                headers={"X-API-Key": api_key_data},
            )
        assert resp.status_code == 409


@pytest.mark.parametrize("action", ["stop", "cancel"])
@pytest.mark.parametrize("sent", [True, False])
async def test_webhook_stops_a_paused_print_and_marks_only_a_sent_command(
    action, sent, async_client, api_key_data, printer_row, monkeypatch
):
    from backend.app import main
    from backend.app.services.printer_manager import printer_manager

    monkeypatch.setattr(main, "_user_stopped_printers", set())
    stop = MagicMock(return_value=sent)
    monkeypatch.setattr(printer_manager, "stop_print", stop)
    monkeypatch.setattr(printer_manager, "get_status", lambda _: PrinterState(connected=True, state="PAUSE"))
    response = await async_client.post(
        f"/api/v1/webhook/printer/{printer_row.id}/{action}", headers={"X-API-Key": api_key_data}
    )
    assert response.status_code == (200 if sent else 503), response.text
    stop.assert_called_once_with(printer_row.id)
    assert (printer_row.id in main._user_stopped_printers) is sent


async def test_hms_stop_marks_the_print_before_the_acknowledgement(async_client, printer_row, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from backend.app import main
    from backend.app.api.routes import printers_controls

    monkeypatch.setattr(main, "_user_stopped_printers", set())
    observed = []
    client = SimpleNamespace(_last_message_time=10)

    def acknowledge():
        observed.append(printer_row.id in main._user_stopped_printers)
        client._last_message_time += 1

    def execute(*args):
        asyncio.get_running_loop().call_soon(acknowledge)
        return True

    client.execute_hms_action = MagicMock(side_effect=execute)
    monkeypatch.setattr(printers_controls, "printer_manager", SimpleNamespace(get_client=lambda _: client))
    monkeypatch.setattr(printers_controls, "_hms_action_ack_wait_seconds", lambda: 0)
    response = await async_client.post(
        f"/api/v1/printers/{printer_row.id}/hms/execute-action",
        json={"print_error": "03008001", "action": "STOP_PRINTING", "job_id": "123"},
    )
    assert response.status_code == 200, response.text
    assert observed == [True]
    client.execute_hms_action.assert_called_once_with("03008001", "STOP_PRINTING", "123")
