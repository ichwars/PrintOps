from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient


class TestPrinterSettingsAPI:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_update_printer_name(self, async_client: AsyncClient, printer_factory, db_session):
        """Verify printer name can be updated."""
        printer = await printer_factory(name="Original Name")

        response = await async_client.patch(f"/api/v1/printers/{printer.id}", json={"name": "Updated Name"})

        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_update_printer_active_status(self, async_client: AsyncClient, printer_factory, db_session):
        """Verify printer active status can be updated."""
        printer = await printer_factory(is_active=True)

        response = await async_client.patch(f"/api/v1/printers/{printer.id}", json={"is_active": False})

        assert response.status_code == 200
        assert response.json()["is_active"] is False

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_deactivate_printer_requests_wled_offline(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory(is_active=True)
        with (
            patch("backend.app.api.routes.printers.printer_manager.disconnect_printer") as disconnect,
            patch("backend.app.api.routes.printers.wled_manager.handle_offline") as offline,
        ):
            response = await async_client.patch(f"/api/v1/printers/{printer.id}", json={"is_active": False})
        assert response.status_code == 200
        disconnect.assert_called_once_with(printer.id)
        offline.assert_called_once_with(printer.id)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_manual_disconnect_requests_wled_offline_without_status_callback(
        self, async_client: AsyncClient, printer_factory
    ):
        printer = await printer_factory(is_active=True)
        with (
            patch("backend.app.api.routes.printers.printer_manager.disconnect_printer") as disconnect,
            patch("backend.app.api.routes.printers.wled_manager.handle_offline") as offline,
            patch("backend.app.api.routes.printers.printer_manager._on_status_change") as status_callback,
        ):
            response = await async_client.post(f"/api/v1/printers/{printer.id}/disconnect")
        assert response.status_code == 200
        disconnect.assert_called_once_with(printer.id)
        offline.assert_called_once_with(printer.id)
        status_callback.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_update_printer_auto_archive(self, async_client: AsyncClient, printer_factory, db_session):
        """Verify auto_archive setting can be updated."""
        printer = await printer_factory(auto_archive=True)

        response = await async_client.patch(f"/api/v1/printers/{printer.id}", json={"auto_archive": False})

        assert response.status_code == 200
        assert response.json()["auto_archive"] is False

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_wled_config_round_trip_and_clear(self, async_client: AsyncClient, printer_factory, db_session):
        printer = await printer_factory(name="WLED Printer")
        config = {
            "enabled": True,
            "base_url": "http://wled.local/",
            "presets": {"idle": 1, "printing": 3, "finished": 9},
            "finished_timeout_seconds": 120,
        }

        with (
            patch("backend.app.api.routes.printers.printer_manager.disconnect_printer") as disconnect,
            patch("backend.app.api.routes.printers.printer_manager.connect_printer", new=AsyncMock()) as connect,
        ):
            response = await async_client.patch(f"/api/v1/printers/{printer.id}", json={"wled_config": config})

        disconnect.assert_not_called()
        connect.assert_not_awaited()

        assert response.status_code == 200
        assert response.json()["wled_config"] == {
            "enabled": True,
            "base_url": "http://wled.local",
            "presets": {
                "idle": 1,
                "prepare": None,
                "printing": 3,
                "paused": None,
                "finished": 9,
                "error": None,
                "queue_waiting": None,
                "filament_problem": None,
                "hms_error": None,
                "offline": None,
            },
            "finished_timeout_seconds": 120,
        }
        assert (await async_client.get(f"/api/v1/printers/{printer.id}")).json()["wled_config"] == response.json()[
            "wled_config"
        ]

        cleared = await async_client.patch(f"/api/v1/printers/{printer.id}", json={"wled_config": None})
        assert cleared.status_code == 200
        assert cleared.json()["wled_config"] is None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_legacy_wled_url_does_not_break_reads_or_weaken_input_validation(
        self, async_client: AsyncClient, printer_factory, db_session
    ):
        printer = await printer_factory(name="Legacy WLED")
        unsafe_url = "http://169.254.169.254/latest/meta-data"
        printer.wled_config = {"enabled": True, "base_url": unsafe_url, "presets": {"printing": 3}}
        await db_session.commit()

        listed = await async_client.get("/api/v1/printers/")
        assert listed.status_code == 200
        assert next(p for p in listed.json() if p["id"] == printer.id)["wled_config"]["base_url"] == unsafe_url

        detail = await async_client.get(f"/api/v1/printers/{printer.id}")
        assert detail.status_code == 200
        assert detail.json()["wled_config"]["base_url"] == unsafe_url

        rejected = await async_client.patch(f"/api/v1/printers/{printer.id}", json={"wled_config": printer.wled_config})
        assert rejected.status_code == 422

        rejected_create = await async_client.post(
            "/api/v1/printers/",
            json={
                "name": "Unsafe WLED",
                "serial_number": "00M09A999999999",
                "ip_address": "192.168.1.99",
                "access_code": "12345678",
                "wled_config": printer.wled_config,
            },
        )
        assert rejected_create.status_code == 422

        printer.wled_config = {"enabled": True, "base_url": "http://user:secret@wled.local"}
        await db_session.commit()
        redacted = await async_client.get(f"/api/v1/printers/{printer.id}")
        assert redacted.status_code == 200
        assert redacted.json()["wled_config"]["base_url"] == "http://user:[REDACTED]@wled.local"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_load_wled_presets(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory(name="WLED Printer")
        with patch(
            "backend.app.api.routes.printers.wled_manager.list_presets",
            new=AsyncMock(return_value=[{"id": 3, "name": "Printing Blue"}]),
        ) as list_presets:
            response = await async_client.post(
                f"/api/v1/printers/{printer.id}/wled/presets",
                json={"base_url": "http://wled.local/"},
            )

        assert response.status_code == 200
        assert response.json() == [{"id": 3, "name": "Printing Blue"}]
        list_presets.assert_awaited_once_with("http://wled.local")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_load_wled_presets_reports_offline(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory(name="Offline WLED")
        with patch(
            "backend.app.api.routes.printers.wled_manager.list_presets",
            new=AsyncMock(side_effect=httpx.ConnectError("offline")),
        ):
            response = await async_client.post(
                f"/api/v1/printers/{printer.id}/wled/presets",
                json={"base_url": "http://wled.local"},
            )

        assert response.status_code == 502
        assert response.json()["detail"] == "Could not load WLED presets"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_wled_connection_and_preset_test(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory(name="Test WLED")

        with patch(
            "backend.app.api.routes.printers.wled_manager.get_info",
            new=AsyncMock(return_value={"name": "Kitchen LEDs", "version": "0.15.0"}),
        ) as get_info:
            response = await async_client.post(
                f"/api/v1/printers/{printer.id}/wled/test-connection",
                json={"base_url": "http://wled.local/"},
            )

        assert response.status_code == 200
        assert response.json() == {"name": "Kitchen LEDs", "version": "0.15.0"}
        get_info.assert_awaited_once_with("http://wled.local")

        with patch(
            "backend.app.api.routes.printers.wled_manager.send_preset",
            new=AsyncMock(return_value=True),
        ) as send_preset:
            response = await async_client.post(
                f"/api/v1/printers/{printer.id}/wled/test-preset",
                json={"base_url": "http://wled.local/", "preset_id": 3},
            )

        assert response.status_code == 200
        assert response.json() == {"success": True}
        send_preset.assert_awaited_once_with(printer.id, "http://wled.local", 3)
