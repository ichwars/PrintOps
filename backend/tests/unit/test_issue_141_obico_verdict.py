"""Regression coverage for honest Obico verdict states (issue #141)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.obico_detection import ObicoDetectionService
from backend.app.services.obico_smoothing import PrintState

SETTINGS = {
    "enabled": True,
    "ml_url": "http://obico:3333",
    "ml_token": "wrong-token",
    "sensitivity": "medium",
    "action": "notify",
    "poll_interval": 10,
    "enabled_printers": None,
    "external_url": "http://printops:8000",
}


def _status(state: str = "RUNNING") -> MagicMock:
    return MagicMock(state=state, task_name="job", subtask_name="")


def _client(**get_kwargs) -> MagicMock:
    client = MagicMock()
    client.get = AsyncMock(**get_kwargs)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def test_pending_first_inference_is_unknown_not_safe():
    service = ObicoDetectionService()
    service._states[1] = PrintState()
    service._state_keys[1] = "job"

    entry = service.get_per_printer()[1]

    assert entry["class"] == "unknown"
    assert entry["error"] is None


@pytest.mark.asyncio
async def test_capture_failure_replaces_previous_safe_verdict_with_error():
    service = ObicoDetectionService()
    service._last_class[1] = "safe"
    with patch.object(service, "_capture_frame", new=AsyncMock(return_value=None)):
        await service._check_printer(1, _status(), SETTINGS)

    entry = service.get_per_printer()[1]

    assert entry["class"] == "error"
    assert "capture" in entry["error"].lower()
    assert entry["frame_count"] == 0


@pytest.mark.asyncio
async def test_new_print_clears_previous_verdict_before_capture_completes():
    service = ObicoDetectionService()
    service._states[1] = PrintState()
    service._state_keys[1] = "previous-job"
    service._last_class[1] = "safe"

    async def observe_pending_state(_printer_id: int):
        assert service.get_per_printer()[1]["class"] == "unknown"
        return None

    with patch.object(service, "_capture_frame", side_effect=observe_pending_state):
        await service._check_printer(1, _status(), SETTINGS)

    assert service.get_per_printer()[1]["class"] == "error"


@pytest.mark.asyncio
async def test_rejected_token_reports_actionable_per_printer_error():
    service = ObicoDetectionService()
    response = MagicMock(status_code=401)
    with (
        patch(
            "backend.app.services.obico_detection.httpx.AsyncClient",
            return_value=_client(return_value=response),
        ),
        patch.object(service, "_capture_frame", new=AsyncMock(return_value=b"jpeg")),
    ):
        await service._check_printer(1, _status(), SETTINGS)

    entry = service.get_per_printer()[1]

    assert entry["class"] == "error"
    assert "ML API Token" in entry["error"]


@pytest.mark.asyncio
async def test_successful_inference_recovers_from_error_to_real_safe_verdict():
    service = ObicoDetectionService()
    with patch.object(service, "_capture_frame", new=AsyncMock(return_value=None)):
        await service._check_printer(1, _status(), SETTINGS)
    assert service.get_per_printer()[1]["class"] == "error"

    response = MagicMock(status_code=200)
    response.json.return_value = {"detections": []}
    response.raise_for_status = MagicMock()
    with (
        patch(
            "backend.app.services.obico_detection.httpx.AsyncClient",
            return_value=_client(return_value=response),
        ),
        patch.object(service, "_capture_frame", new=AsyncMock(return_value=b"jpeg")),
    ):
        await service._check_printer(1, _status(), SETTINGS)

    entry = service.get_per_printer()[1]

    assert entry["class"] == "safe"
    assert entry["error"] is None
    assert entry["frame_count"] == 1


@pytest.mark.asyncio
async def test_print_end_clears_verdict_and_error_state():
    service = ObicoDetectionService()
    service._states[1] = PrintState()
    service._state_keys[1] = "job"
    service._last_class[1] = "safe"
    service._errors[1] = "camera failed"
    manager = MagicMock()
    manager.get_all_statuses.return_value = {1: _status("IDLE")}
    manager.is_connected.return_value = True

    with patch.dict(
        "sys.modules",
        {"backend.app.services.printer_manager": MagicMock(printer_manager=manager)},
    ):
        await service._poll_once(SETTINGS)

    assert service.get_per_printer() == {}
    assert service._last_class == {}
    assert service._errors == {}


@pytest.mark.asyncio
async def test_disconnect_clears_verdict_and_error_state():
    service = ObicoDetectionService()
    service._states[1] = PrintState()
    service._state_keys[1] = "job"
    service._last_class[1] = "safe"
    service._errors[1] = "camera failed"
    manager = MagicMock()
    manager.get_all_statuses.return_value = {1: _status()}
    manager.is_connected.return_value = False

    with patch.dict(
        "sys.modules",
        {"backend.app.services.printer_manager": MagicMock(printer_manager=manager)},
    ):
        await service._poll_once(SETTINGS)

    assert service.get_per_printer() == {}
    assert service._last_class == {}
    assert service._errors == {}
