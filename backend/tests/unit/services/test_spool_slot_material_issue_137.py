"""Telemetry accepts only AMS types the stored spool could have produced."""

import pytest

from backend.app.models.local_preset import LocalPreset
from backend.app.models.spool import Spool
from backend.app.services.spool_slot_material import expected_spool_protocol_types


@pytest.mark.asyncio
async def test_expected_types_cover_product_and_authoritative_local_preset(db_session):
    preset = LocalPreset(
        name="Bambu PLA Aero @BBL P1S",
        preset_type="filament",
        source="orcaslicer",
        filament_type="PLA-AERO",
        setting="{}",
    )
    db_session.add(preset)
    await db_session.flush()
    spool = Spool(
        material="PLA+",
        slicer_filament=str(preset.id),
        label_weight=1000,
        core_weight=250,
        weight_used=0,
    )

    assert await expected_spool_protocol_types(db_session, spool) == {"PLA", "PLA-AERO"}


@pytest.mark.asyncio
async def test_unrelated_material_is_not_accepted(db_session):
    spool = Spool(material="PLA Silk", label_weight=1000, core_weight=250, weight_used=0)
    assert "ABS" not in await expected_spool_protocol_types(db_session, spool)


@pytest.mark.asyncio
async def test_legacy_product_type_normalizes_to_assignment_type(db_session):
    spool = Spool(material="PLA+", label_weight=1000, core_weight=250, weight_used=0)
    expected = await expected_spool_protocol_types(db_session, spool)
    assert "PLA" in expected
