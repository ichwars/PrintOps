"""A plate check and live camera share the light while they overlap."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from backend.app.services import camera_light, plate_detection
from backend.app.services.camera_light import hand_back_camera_light, hold_camera_light
from backend.app.services.print_event_tasks import check_print_start_plate


@pytest.fixture
def printer():
    return SimpleNamespace(
        name="Test printer",
        plate_detection_enabled=True,
        plate_detection_roi_x=None,
        plate_detection_roi_y=None,
        plate_detection_roi_w=None,
        plate_detection_roi_h=None,
        ip_address="192.0.2.1",
        access_code="fixture",
        model="X1C",
        external_camera_enabled=False,
        external_camera_url=None,
        external_camera_type=None,
        external_camera_snapshot_url=None,
    )


@pytest.mark.asyncio
async def test_print_start_check_leaves_the_light_on_for_an_existing_viewer(monkeypatch, printer):
    monkeypatch.setattr(camera_light, "_EXPOSURE_SETTLE_SECONDS", 0)
    client = Mock(state=SimpleNamespace(chamber_light=False))
    client.set_chamber_light.return_value = True
    detect = AsyncMock(return_value=SimpleNamespace(needs_calibration=False, is_empty=True))
    monkeypatch.setattr(plate_detection, "check_plate_empty", detect)

    async with hold_camera_light(321):
        await check_print_start_plate(
            321,
            printer,
            None,
            logging.getLogger(__name__),
            printer_manager=Mock(get_client=Mock(return_value=client)),
            ws_manager=AsyncMock(),
            notification_service=AsyncMock(),
            _capture_snapshot_for_notification=AsyncMock(),
        )
        client.set_chamber_light.assert_called_once_with(True)
    assert client.set_chamber_light.call_args_list == [call(True), call(False)]
    detect.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["no_camera_frame", "not_calibrated", "error"])
async def test_print_continues_with_an_explicit_check_failure(monkeypatch, printer, caplog, reason):
    monkeypatch.setattr(camera_light, "_EXPOSURE_SETTLE_SECONDS", 0)
    client = Mock(state=SimpleNamespace(chamber_light=True))
    if reason == "error":
        check = AsyncMock(side_effect=RuntimeError("fixture"))
    else:
        check = AsyncMock(
            return_value=plate_detection.PlateDetectionResult(
                True,
                0.0,
                0.0,
                "fixture",
                needs_calibration=reason == "not_calibrated",
                failure_reason=reason if reason != "not_calibrated" else None,
            )
        )
    monkeypatch.setattr(plate_detection, "check_plate_empty", check)
    ws_manager = AsyncMock()
    notification_service = AsyncMock()

    await check_print_start_plate(
        321,
        printer,
        None,
        logging.getLogger(__name__),
        printer_manager=Mock(get_client=Mock(return_value=client)),
        ws_manager=ws_manager,
        notification_service=notification_service,
        _capture_snapshot_for_notification=AsyncMock(),
    )

    ws_manager.broadcast.assert_awaited_once_with(
        {
            "type": "plate_check_failed",
            "printer_id": 321,
            "printer_name": printer.name,
            "reason": reason,
        }
    )
    assert "proceeding with print" in caplog.text
    assert "Plate is empty" not in caplog.text
    client.pause_print.assert_not_called()
    notification_service.on_plate_not_empty.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_light_change_takes_precedence(monkeypatch):
    monkeypatch.setattr(camera_light, "_EXPOSURE_SETTLE_SECONDS", 0)
    client = Mock(state=SimpleNamespace(chamber_light=False))
    client.set_chamber_light.return_value = True

    async with hold_camera_light(321, illuminate_with=client):
        hand_back_camera_light(321)

    client.set_chamber_light.assert_called_once_with(True)
