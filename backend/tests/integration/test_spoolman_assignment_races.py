"""A late manual assignment response cannot configure the replacement spool's slot."""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from backend.app.models.slot_preset import SlotPresetMapping
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.tests.integration.test_spoolman_slot_assignment_mqtt import (  # noqa: F401
    SAMPLE_SPOOL,
    mock_spoolman_client,
    slot_settings,
    test_printer,
)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_a_slow_preset_resolution_does_not_overwrite_a_new_manual_assignment(
    async_client, db_session, slot_settings, test_printer, mock_spoolman_client
):
    resolving, release = asyncio.Event(), asyncio.Event()

    async def spool(spool_id):
        preset = "GFA00" if spool_id == 10 else "GFA01"
        return {**SAMPLE_SPOOL, "id": spool_id, "extra": {"bambu_slicer_filament": json.dumps(preset)}}

    async def resolve(**kwargs):
        preset = kwargs["slicer_filament"]
        if preset == "GFA00":
            resolving.set()
            await release.wait()
        return preset, "GFS" + preset[2:], None, None

    mock_spoolman_client.get_spool.side_effect = spool
    mqtt = MagicMock()
    body = {"printer_id": test_printer.id, "ams_id": 0, "tray_id": 0}
    old_request = None
    with (
        patch("backend.app.api.routes.spoolman_inventory.resolve_slicer_filament", side_effect=resolve),
        patch("backend.app.api.routes.spoolman_inventory.printer_manager") as pm,
    ):
        pm.get_client.return_value = mqtt
        pm.get_status.return_value = None
        try:
            old_request = asyncio.create_task(
                async_client.post("/api/v1/spoolman/inventory/slot-assignments", json={**body, "spoolman_spool_id": 10})
            )
            await asyncio.wait_for(resolving.wait(), 5)
            current = await async_client.post(
                "/api/v1/spoolman/inventory/slot-assignments", json={**body, "spoolman_spool_id": 11}
            )
            assert current.status_code == 200, current.text
            release.set()
            previous = await asyncio.wait_for(old_request, 5)
            assert previous.status_code == 200, previous.text
        finally:
            release.set()
            if old_request and not old_request.done():
                old_request.cancel()
                await asyncio.gather(old_request, return_exceptions=True)

    assert [call.kwargs["tray_info_idx"] for call in mqtt.ams_set_filament_setting.call_args_list] == ["GFA01"]
    assert await db_session.scalar(select(SpoolmanSlotAssignment.spoolman_spool_id)) == 11
    assert await db_session.scalar(select(SlotPresetMapping.tray_info_idx)) == "GFA01"
