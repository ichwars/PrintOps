"""Read access cannot alter calibration, history, scans or diagnostics."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.app.api.routes import bug_report, smart_plugs
from backend.app.core.auth import create_access_token
from backend.app.models.group import Group
from backend.app.models.user import User
from backend.app.services import plate_detection
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_printer_history_and_shared_state_require_write_permissions(
    async_client, db_session, printer_factory, monkeypatch
):
    await _setup_admin(async_client)
    visible, hidden = await printer_factory(), await printer_factory()
    read_permissions = [
        "ams_history:read",
        "camera:view",
        "inventory:read",
        "printer_sensor_history:read",
        "settings:read",
        "smart_plugs:read",
    ]
    write_permissions = ["printers:update", "inventory:update", "settings:update", "smart_plugs:create"]
    for username, permissions in (
        ("read_only_state", read_permissions),
        ("edit_device_state", [*read_permissions, *write_permissions]),
    ):
        db_session.add(
            User(
                username=username,
                allowed_printer_ids=[visible.id],
                groups=[Group(name=username, permissions=permissions)],
            )
        )
    await db_session.commit()
    reader, writer = (
        {"Authorization": f"Bearer {create_access_token({'sub': username})}"}
        for username in ("read_only_state", "edit_device_state")
    )

    scanner = SimpleNamespace(scan_range=AsyncMock(), stop=Mock(), progress=(0, 0), is_running=False)
    monkeypatch.setattr(smart_plugs, "tasmota_scanner", scanner)
    monkeypatch.setattr(smart_plugs, "get_local_network_range", lambda: ("192.0.2.1", "192.0.2.2"))
    monkeypatch.setattr(plate_detection, "is_plate_detection_available", lambda: False)
    monkeypatch.setattr(bug_report, "_get_recent_sanitized_logs", AsyncMock(return_value=""))

    camera = "/api/v1/printers/{printer}/camera/plate-detection"
    for method, path, allowed in (
        ("POST", f"{camera}/calibrate", 503),
        ("DELETE", f"{camera}/calibrate", 503),
        ("PUT", f"{camera}/references/0?label=fixture", 503),
        ("DELETE", f"{camera}/references/0", 503),
        ("DELETE", "/api/v1/ams-history/{printer}?days=30", 200),
        ("DELETE", "/api/v1/printer-sensor-history/{printer}?days=30", 200),
    ):
        denied = await async_client.request(method, path.format(printer=visible.id), headers=reader)
        assert denied.status_code == 403, (path, denied.text)
        hidden_response = await async_client.request(method, path.format(printer=hidden.id), headers=writer)
        assert hidden_response.status_code == 404, (path, hidden_response.text)
        authorized = await async_client.request(method, path.format(printer=visible.id), headers=writer)
        assert authorized.status_code == allowed, (path, authorized.text)

    for path in ("/api/v1/ams-history/{printer}/0", "/api/v1/printer-sensor-history/{printer}"):
        assert (await async_client.get(path.format(printer=visible.id), headers=reader)).status_code == 200
        assert (await async_client.get(path.format(printer=hidden.id), headers=reader)).status_code == 404

    for path, allowed in (
        ("/api/v1/bug-report/stop-logging?was_debug=true", 200),
        ("/api/v1/smart-plugs/discover/scan", 200),
        ("/api/v1/smart-plugs/discover/stop", 200),
        ("/api/v1/spoolbuddy/diagnostics/missing/run?diagnostic=scale", 404),
    ):
        denied = await async_client.post(path, headers=reader)
        assert denied.status_code == 403, (path, denied.text)
        authorized = await async_client.post(path, headers=writer)
        assert authorized.status_code == allowed, (path, authorized.text)
    scanner.scan_range.assert_called_once()
    scanner.stop.assert_called_once()
