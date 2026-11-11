"""Exercise the firmware and AMS gates through the printer entry points."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.app.models.print_queue import PrintQueueItem
from backend.app.services import firmware_update
from backend.app.services.bambu_mqtt import PrinterState
from backend.app.services.drying_ownership import claim_queue_item
from backend.app.services.firmware_update import FirmwareUploadStatus
from backend.app.services.print_scheduler import PrintScheduler
from backend.app.services.printer_manager import printer_manager

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
def printer_status(monkeypatch):
    state = PrinterState()
    state.state, state.connected = "IDLE", True
    state.firmware_version, state.sdcard = "01.06.00.00", True
    monkeypatch.setattr(firmware_update.printer_manager, "get_status", lambda _: state)
    monkeypatch.setattr(firmware_update.printer_manager, "is_connected", lambda _: state.connected)
    monkeypatch.setattr(firmware_update, "_upload_states", {})
    return state


@pytest.fixture
def firmware_source(monkeypatch):
    source = Mock()
    source.check_for_update = AsyncMock(return_value={"update_available": True, "latest_version": "01.07.00.00"})
    source.get_firmware_file_info = AsyncMock(return_value={"filename": "firmware.bin"})
    source.download_firmware = AsyncMock()
    monkeypatch.setattr(firmware_update, "get_firmware_service", lambda: source)
    monkeypatch.setattr(firmware_update, "get_storage_info_async", AsyncMock(return_value={"free_bytes": 10**9}))
    return source


@pytest.mark.parametrize("state", ["RUNNING", "PAUSE", "PREPARE", "SLICING", "UNKNOWN"])
async def test_firmware_preparation_and_start_refuse_non_idle_state(
    async_client, printer_factory, printer_status, firmware_source, state
):
    printer = await printer_factory()
    printer_status.state = state
    url = f"/api/v1/firmware/updates/{printer.id}"
    prepared = await async_client.get(f"{url}/prepare")
    assert prepared.status_code == 200
    assert not prepared.json()["can_proceed"]
    assert "idle" in prepared.json()["errors"][0]
    response = await async_client.post(f"{url}/upload")
    assert response.status_code == 400
    assert "idle" in response.json()["detail"]
    firmware_source.check_for_update.assert_not_awaited()
    firmware_source.download_firmware.assert_not_awaited()


@pytest.mark.parametrize("state", ["IDLE", "FINISH", "FAILED"])
async def test_firmware_prepare_allows_idle_printer(
    async_client, printer_factory, printer_status, firmware_source, state
):
    printer = await printer_factory()
    printer_status.state = state
    response = await async_client.get(f"/api/v1/firmware/updates/{printer.id}/prepare")
    assert response.status_code == 200
    assert response.json()["can_proceed"]


async def test_firmware_queue_dispatch_race_is_blocked(async_client, printer_factory, db_session, printer_status):
    printer = await printer_factory()
    queue_item = PrintQueueItem(printer_id=printer.id, status="pending", dispatching_at=datetime.now(timezone.utc))
    db_session.add(queue_item)
    await db_session.commit()
    response = await async_client.post(f"/api/v1/firmware/updates/{printer.id}/upload")
    assert response.status_code == 400
    assert "idle" in response.json()["detail"]


@pytest.mark.parametrize(
    "status", [FirmwareUploadStatus.PREPARING, FirmwareUploadStatus.DOWNLOADING, FirmwareUploadStatus.UPLOADING]
)
async def test_firmware_blocks_scheduler_selection_and_direct_queue_claim(
    printer_factory, db_session, printer_status, status
):
    printer = await printer_factory()
    item = PrintQueueItem(printer_id=printer.id, status="pending")
    db_session.add(item)
    await db_session.commit()
    state = firmware_update.get_upload_state(printer.id)
    state.status = status

    assert not PrintScheduler()._is_printer_idle(printer.id, require_plate_clear=False)
    assert not await claim_queue_item(db_session, item.id, printer.id)
    await db_session.refresh(item)
    assert item.dispatching_at is None

    state.status = FirmwareUploadStatus.COMPLETE
    assert PrintScheduler()._is_printer_idle(printer.id, require_plate_clear=False)
    assert await claim_queue_item(db_session, item.id, printer.id)


async def test_external_print_started_during_download_prevents_ftp_write(
    printer_status, firmware_source, monkeypatch, tmp_path
):
    path = tmp_path / "firmware.bin"
    path.write_bytes(b"fixture")

    async def download(*args, **kwargs):
        printer_status.state = "RUNNING"
        return path

    firmware_source.download_firmware.side_effect = download
    upload = AsyncMock()
    monkeypatch.setattr(firmware_update, "upload_file_async", upload)
    service = firmware_update.FirmwareUpdateService()
    monkeypatch.setattr(service, "_broadcast_progress", AsyncMock())

    await service._do_upload(123, "192.0.2.1", "fixture", "X1C", "01.07.00.00")

    assert firmware_update.get_upload_state(123).status == FirmwareUploadStatus.ERROR
    assert "idle" in firmware_update.get_upload_state(123).error
    upload.assert_not_awaited()


@pytest.mark.parametrize("state", ["IDLE", "RUNNING", "PAUSE", "PREPARE", "SLICING"])
async def test_ams_reset_uses_current_printer_state(async_client, printer_factory, state):
    printer = await printer_factory()
    client = Mock(state=SimpleNamespace(state=state))
    with patch.object(printer_manager, "get_client", return_value=client):
        response = await async_client.post(f"/api/v1/printers/{printer.id}/ams/0/tray/1/reset")

    if state == "IDLE":
        assert response.status_code == 200, response.text
        client.reset_ams_slot.assert_called_once_with(ams_id=0, tray_id=1)
    else:
        assert response.status_code == 409, response.text
        client.reset_ams_slot.assert_not_called()
