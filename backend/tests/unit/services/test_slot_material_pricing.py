from unittest.mock import AsyncMock, patch

from backend.app.models.settings import Settings
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services.filament_deficit import build_slot_materials
from backend.tests.unit.services.test_filament_deficit import TestFilamentDeficitBackupAware as _DeficitFixtures


async def test_slot_prices_follow_spoolman_charges(db_session, printer_factory):
    printer = await printer_factory(model="X1C")
    db_session.add(Settings(key="spoolman_enabled", value="true"))
    db_session.add(SpoolmanSlotAssignment(printer_id=printer.id, ams_id=0, tray_id=0, spoolman_spool_id=10))
    await db_session.commit()
    client = AsyncMock()
    client.get_spool.return_value = {
        "id": 10,
        "price": 0,
        "initial_weight": 1000,
        "remaining_weight": 320,
        "filament": {"material": "PLA", "weight": 500, "price": 12},
    }
    patches = _DeficitFixtures._patch_status(printer_id=printer.id, backup_on=False, model="X1C")
    for mock in patches:
        mock.start()
    try:
        with patch("backend.app.services.spoolman.get_spoolman_client", AsyncMock(return_value=client)):
            slots = await build_slot_materials(db_session, printer.id)
    finally:
        for mock in patches:
            mock.stop()
    assert slots[0].remaining_grams == 320
    assert slots[0].cost_per_kg == 24
    assert slots[0].to_dict()["cost_per_kg"] == 24
