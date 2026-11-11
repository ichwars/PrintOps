"""Record only firmware-observed drying on spools present for the cycle."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.api.routes._spoolman_helpers import _map_spoolman_spool
from backend.app.models.settings import Settings
from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.services import spool_drying
from backend.app.services.bambu_mqtt import BambuMQTTClient
from backend.app.services.drying_cycle import DryingCycleEnd
from backend.app.services.drying_telemetry import observe_ams_drying
from backend.app.services.spoolman import SpoolmanClient
from backend.app.services.spoolman_slot_sync import upsert_spoolman_slot
from backend.app.utils.local_time import utcnow_naive

pytestmark = pytest.mark.integration


def test_firmware_countdown_distinguishes_completed_and_interrupted_drying():
    records = []
    client = BambuMQTTClient("192.0.2.1", "FIXTURE", "fixture", on_drying_cycle_end=records.append)
    client._client = MagicMock()

    def report(minutes, tag="ABCDEF1234567890"):
        unit = {"id": "0", "tray": [{"id": "0", "tag_uid": tag, "exists": True}]}
        if minutes is not None:
            unit["dry_time"] = minutes
        observe_ams_drying(client, [unit], [unit])

    report(0)
    assert client.send_drying_command(0, 65, 8)
    report(480)
    report(472)
    report(0)
    assert records == []

    assert client.send_drying_command(0, 65, 8)
    report(480)
    report(None, "CBAFED3216540987")
    report(2, "CBAFED3216540987")
    report(0, "CBAFED3216540987")
    report(0, "CBAFED3216540987")
    assert len(records) == 1
    assert records[0].excluded_slots == {0}
    assert records[0].target_temp == 65 and records[0].hours == 8.0


@pytest.mark.asyncio
async def test_native_drying_skips_replacement_and_applies_manual_date(async_client, db_session, printer_factory):
    printer = await printer_factory()
    prior, replacement, removed = (Spool(material="PLA") for _ in range(3))
    db_session.add_all([prior, replacement, removed])
    await db_session.flush()
    end = utcnow_naive()
    first = end - timedelta(hours=8)
    for tray, spool, created in (
        (0, prior, first),
        (1, replacement, first + timedelta(minutes=1)),
        (2, removed, first),
    ):
        db_session.add(
            SpoolAssignment(spool_id=spool.id, printer_id=printer.id, ams_id=0, tray_id=tray, created_at=created)
        )
    await db_session.commit()
    record = DryingCycleEnd(0, first, end, frozenset({2}), 65, 8.0)
    assert await spool_drying.record_drying_cycle(db_session, printer.id, record) == 1
    assert await spool_drying.record_drying_cycle(db_session, printer.id, record) == 0
    await db_session.refresh(prior)
    await db_session.refresh(replacement)
    await db_session.refresh(removed)
    assert prior.last_dried_at == end and prior.last_dried_hours == 8
    assert replacement.last_dried_at is None and removed.last_dried_at is None

    res = await async_client.patch(
        f"/api/v1/inventory/spools/{prior.id}", json={"last_dried_at": "2026-11-10T14:31:00+01:00"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["last_dried_at"] == "2026-11-10T13:31:00"
    assert res.json()["last_dried_temp"] is None and res.json()["last_dried_hours"] is None
    res = await async_client.patch(f"/api/v1/inventory/spools/{prior.id}", json={"last_dried_at": None})
    assert res.status_code == 200 and res.json()["last_dried_at"] is None, res.text


@pytest.mark.asyncio
async def test_spoolman_marks_only_original_spools_and_keeps_other_extra(db_session, printer_factory, monkeypatch):
    printer = await printer_factory(spoolman_enabled=True)
    await upsert_spoolman_slot(db_session, (printer.id, 0, 0), 101)
    await upsert_spoolman_slot(db_session, (printer.id, 0, 1), 102)
    await db_session.commit()
    first = utcnow_naive()
    await upsert_spoolman_slot(db_session, (printer.id, 0, 0), 101)
    await upsert_spoolman_slot(db_session, (printer.id, 0, 1), 103)
    await db_session.commit()

    spools = {101: {"id": 101, "filament": {"material": "PLA"}, "extra": {"tag": '"original"'}}}
    client = SpoolmanClient("http://fixture")
    monkeypatch.setattr(client, "ensure_extra_field", AsyncMock(return_value=True))
    monkeypatch.setattr(client, "get_spool", AsyncMock(side_effect=lambda spool_id: spools[spool_id]))

    def update(spool_id, extra):
        spools[spool_id]["extra"] = extra
        return spools[spool_id]

    monkeypatch.setattr(client, "update_spool_full", AsyncMock(side_effect=update))
    monkeypatch.setattr(spool_drying, "get_spoolman_client", AsyncMock(return_value=client))
    end = first + timedelta(hours=8)
    record = DryingCycleEnd(0, first, end, frozenset(), 60, 8.0)
    assert await spool_drying.record_drying_cycle(db_session, printer.id, record) == 1
    assert await spool_drying.record_drying_cycle(db_session, printer.id, record) == 0
    mapped = _map_spoolman_spool(spools[101])
    assert datetime.fromisoformat(mapped["last_dried_at"]) == end
    assert mapped["last_dried_temp"] == 60 and mapped["last_dried_hours"] == 8
    assert spools[101]["extra"]["tag"] == '"original"'
    client.update_spool_full.assert_awaited_once()
