"""An unsent filament configuration stays eligible for a later replay."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_a_refused_publication_cannot_settle_a_pending_slot():
    from backend.app.api.routes.inventory import apply_spool_to_slot_via_mqtt

    spool = SimpleNamespace(
        id=4,
        material="PLA",
        subtype=None,
        brand=None,
        rgba="FF0000FF",
        nozzle_temp_min=None,
        nozzle_temp_max=None,
        k_profiles=[],
    )
    preset = SimpleNamespace(slicer_filament=None, slicer_filament_name=None, configured=False)
    assignment = SimpleNamespace(fingerprint_color=None, fingerprint_type=None)
    client, db = MagicMock(), AsyncMock()
    client.ams_set_filament_setting.return_value = False
    with (
        patch("backend.app.services.printer_manager.printer_manager") as pm,
        patch("backend.app.api.routes.inventory.resolve_spool_preset", AsyncMock(return_value=preset)),
        patch(
            "backend.app.api.routes.inventory.resolve_slicer_filament",
            AsyncMock(return_value=("GFL99", "GFSL99", None, None)),
        ),
    ):
        pm.get_client.return_value = client
        pm.get_status.return_value = None
        pm.get_model.return_value = "P2S"
        sent = await apply_spool_to_slot_via_mqtt(
            db=db,
            spool=spool,
            printer_id=1,
            ams_id=0,
            tray_id=0,
            assignment=assignment,
            current_user=None,
        )
    assert sent is False
    assert (assignment.fingerprint_type, assignment.fingerprint_color) == (None, None)
    client.extrusion_cali_sel.assert_not_called()
    client.register_assignment_verification.assert_not_called()
    db.commit.assert_not_awaited()
