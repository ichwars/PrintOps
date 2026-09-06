"""Expected AMS protocol types for an assigned local spool."""

from sqlalchemy import select

from backend.app.models.local_preset import LocalPreset
from backend.app.models.spool import Spool
from backend.app.utils.filament_types import printer_filament_type


async def expected_spool_protocol_types(db, spool: Spool) -> set[str]:
    """Return every protocol type the assignment path could have written."""
    values = {printer_filament_type(spool.material).upper()}
    if spool.slicer_filament_name:
        values.add(printer_filament_type(spool.slicer_filament_name).upper())
    reference = (spool.slicer_filament or "").strip()
    if reference.isdigit() and int(reference) <= 2_147_483_647:
        preset_type = await db.scalar(
            select(LocalPreset.filament_type).where(
                LocalPreset.id == int(reference),
                LocalPreset.preset_type == "filament",
            )
        )
        if preset_type:
            values.add(printer_filament_type(preset_type).upper())
    return {value for value in values if value}
