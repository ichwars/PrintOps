"""Unit tests for K-profile write acknowledgements."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.app.api.routes import kprofiles
from backend.app.schemas.kprofile import KProfileCreate, KProfileDelete


def _db_with_printer(model: str = "X1C") -> AsyncMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(model=model)
    db = AsyncMock()
    db.execute.return_value = result
    return db


def _connected_client(monkeypatch) -> MagicMock:
    client = MagicMock()
    client.state.connected = True
    client._is_dual_nozzle = False
    client.await_cali_ack = AsyncMock(return_value=(False, "invalid calibration"))
    monkeypatch.setattr(kprofiles.printer_manager, "get_client", lambda _printer_id: client)
    return client


def _profile(slot_id: int = 0) -> KProfileCreate:
    return KProfileCreate(
        slot_id=slot_id,
        nozzle_id="HS00-0.4",
        nozzle_diameter="0.4",
        filament_id="GFL99",
        name="PLA",
        k_value="0.020000",
    )


@pytest.mark.asyncio
async def test_set_kprofile_reports_printer_rejection(monkeypatch):
    client = _connected_client(monkeypatch)
    client.set_kprofile.return_value = "41"

    with pytest.raises(HTTPException, match="Printer rejected the K-profile") as error:
        await kprofiles.set_kprofile(1, _profile(), _db_with_printer(), None)

    assert error.value.status_code == 500
    client.await_cali_ack.assert_awaited_once_with("41")


@pytest.mark.asyncio
async def test_set_kprofiles_batch_reports_printer_rejection(monkeypatch):
    client = _connected_client(monkeypatch)
    client.set_kprofiles_batch.return_value = "42"

    with pytest.raises(HTTPException, match="Printer rejected the K-profiles"):
        await kprofiles.set_kprofiles_batch(1, [_profile()], _db_with_printer(), None)

    client.await_cali_ack.assert_awaited_once_with("42")


@pytest.mark.asyncio
async def test_delete_kprofile_reports_printer_rejection(monkeypatch):
    client = _connected_client(monkeypatch)
    client.delete_kprofile.return_value = "43"
    profile = KProfileDelete(
        slot_id=7,
        nozzle_id="HS00-0.4",
        nozzle_diameter="0.4",
        filament_id="GFL99",
    )

    with pytest.raises(HTTPException, match="Printer rejected the delete"):
        await kprofiles.delete_kprofile(1, profile, _db_with_printer(), None)

    client.await_cali_ack.assert_awaited_once_with("43")


@pytest.mark.asyncio
async def test_edit_stops_when_delete_is_rejected(monkeypatch):
    client = _connected_client(monkeypatch)
    client.delete_kprofile.return_value = "44"

    with pytest.raises(HTTPException, match="Printer rejected the K-profile edit"):
        await kprofiles.set_kprofile(1, _profile(slot_id=7), _db_with_printer(), None)

    client.await_cali_ack.assert_awaited_once_with("44")
    client.set_kprofile.assert_not_called()
