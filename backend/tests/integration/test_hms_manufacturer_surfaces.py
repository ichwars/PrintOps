"""One parsed manufacturer fault retains its description on every live surface."""

from unittest.mock import patch

from backend.app.services.bambu_mqtt import BambuMQTTClient
from backend.app.services.printer_manager import printer_state_to_dict
from backend.tests.integration.test_webhook_printer_status import api_key_data, printer_row  # noqa: F401


async def test_live_fault_description_agrees_in_rest_camwall_webhook_and_websocket(
    async_client,
    printer_row,
    api_key_data,
):
    mqtt = BambuMQTTClient(ip_address="192.0.2.1", serial_number="093TEST", access_code="fixture")
    mqtt._update_state({"hms": [{"attr": 0x03000200, "code": 0x00010008}], "subtask_id": "job-7"})
    mqtt.state.connected = True
    fault = mqtt.state.hms_errors[0]
    with patch("backend.app.services.printer_manager.printer_manager.get_status", return_value=mqtt.state):
        status = await async_client.get(f"/api/v1/printers/{printer_row.id}/status")
        wall = await async_client.get("/api/v1/camwall/printers")
        webhook = await async_client.get(
            f"/api/v1/webhook/printer/{printer_row.id}/status", headers={"X-API-Key": api_key_data}
        )
    assert status.status_code == wall.status_code == webhook.status_code == 200
    surfaces = [
        status.json()["hms_errors"][0],
        wall.json()[0]["hms_errors"][0],
        webhook.json()["hms_errors"][0],
        printer_state_to_dict(mqtt.state)["hms_errors"][0],
    ]
    for data in surfaces:
        assert data["description"] == fault.description and "nozzle temperature" in data["description"]
        assert data["severity"] == 1 and data["full_code"] == "0300020000010008"
        assert data["actions"] == fault.actions and data["job_id"] == "job-7"


async def test_real_status_callback_notifies_new_task_stopping_fault_on_same_part_once(
    async_client,
    db_session,
    printer_factory,
    monkeypatch,
):
    from unittest.mock import AsyncMock

    import httpx

    from backend.app import main
    from backend.app.models.notification import NotificationProvider

    printer = await printer_factory()
    db_session.add(
        NotificationProvider(name="HMS", provider_type="ntfy", config='{"topic":"hms"}', on_printer_error=True)
    )
    await db_session.commit()
    mqtt = BambuMQTTClient(ip_address="192.0.2.1", serial_number="093TEST", access_code="fixture")
    mqtt.state.connected = False
    main._last_status_broadcast.pop(printer.id, None)
    main._notified_hms_errors.pop(printer.id, None)
    monkeypatch.setattr(main.printer_manager, "get_printer", lambda _: None)
    monkeypatch.setattr(main, "_capture_snapshot_for_notification", AsyncMock(return_value=None))
    monkeypatch.setattr(main.ws_manager, "send_printer_status", AsyncMock())
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "sent"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        monkeypatch.setattr(main.notification_service, "_get_client", AsyncMock(return_value=client))
        mqtt._update_state({"hms": [{"attr": 0x03000200, "code": 0x00010008}]})
        await main.on_printer_status_change(printer.id, mqtt.state)
        mqtt._update_state({"hms": [{"attr": 0x03000200, "code": 0x00010009}]})
        await main.on_printer_status_change(printer.id, mqtt.state)
        await main.on_printer_status_change(printer.id, mqtt.state)
    assert len(requests) == 2, "distinct full fault codes must survive unchanged temperature/progress status dedup"
    assert mqtt.state.hms_errors[0].description.encode() in requests[-1].content
    main._last_status_broadcast.pop(printer.id, None)
    main._notified_hms_errors.pop(printer.id, None)
