"""Spool deletion and archival release and announce the affected slots."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("operation", ["delete", "bulk-delete", "archive", "bulk-archive"])
async def test_spool_mutation_frees_and_announces_slots(async_client, db_session, printer_factory, operation):
    printer = await printer_factory()
    printer_id = printer.id
    spool = Spool(material="PLA", label_weight=1000, weight_used=0)
    db_session.add(spool)
    await db_session.flush()
    spool_id = spool.id
    db_session.add(SpoolAssignment(spool_id=spool_id, printer_id=printer_id, ams_id=128, tray_id=0))
    await db_session.commit()
    with patch("backend.app.core.websocket.ws_manager.broadcast", AsyncMock()) as broadcast:
        if operation == "delete":
            response = await async_client.delete(f"/api/v1/inventory/spools/{spool_id}")
        elif operation.startswith("bulk-"):
            response = await async_client.post(f"/api/v1/inventory/spools/{operation}", json={"ids": [spool_id]})
        else:
            response = await async_client.post(f"/api/v1/inventory/spools/{spool_id}/archive")
    assert response.status_code == 200, response.text
    assert (await db_session.execute(select(SpoolAssignment))).scalars().all() == []
    assert any(
        call.args[0] == {"type": "spool_assignment_changed", "printer_id": printer_id, "ams_id": 128, "tray_id": 0}
        for call in broadcast.await_args_list
    )


async def test_deleting_a_printer_releases_builtin_assignments(async_client, db_session, printer_factory):
    printer = await printer_factory()
    spool = Spool(material="PLA", label_weight=1000)
    db_session.add(spool)
    await db_session.flush()
    db_session.add(SpoolAssignment(spool_id=spool.id, printer_id=printer.id, ams_id=0, tray_id=0))
    await db_session.commit()
    response = await async_client.delete(f"/api/v1/printers/{printer.id}")
    assert response.status_code == 200, response.text
    assert (await db_session.execute(select(SpoolAssignment))).scalars().all() == []
