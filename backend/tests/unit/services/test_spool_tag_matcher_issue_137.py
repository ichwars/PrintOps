"""RFID-created spools use the catalog row that actually names their core."""

import pytest

from backend.app.models.spool_catalog import SpoolCatalogEntry
from backend.app.services.spool_tag_matcher import create_spool_from_tray


@pytest.mark.asyncio
async def test_rfid_spool_uses_named_low_temp_core_and_preserves_remaining_grams(db_session):
    high = SpoolCatalogEntry(name="Bambu Lab - Plastic High Temp", weight=216)
    low = SpoolCatalogEntry(name="Bambu Lab - Plastic Low Temp", weight=250)
    white = SpoolCatalogEntry(name="Bambu Lab - Plastic White", weight=253)
    db_session.add_all([high, low, white])
    await db_session.flush()

    spool = await create_spool_from_tray(
        db_session,
        {
            "tray_type": "PLA",
            "tray_sub_brands": "PLA Basic",
            "tray_color": "FFFFFFFF",
            "tray_info_idx": "GFL99",
            "tag_uid": "AABBCCDD11223344",
            "tray_uuid": "AABBCCDD11223344AABBCCDD11223344",
            "tray_weight": 1000,
            "remain": 80,
        },
    )

    assert spool.core_weight == 250
    assert spool.core_weight_catalog_id == low.id
    assert spool.label_weight - spool.weight_used == 800
