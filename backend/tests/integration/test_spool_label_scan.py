"""Spool label resolution and transactional moves of manually scanned spools."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from backend.app.api.routes import inventory, spoolman_inventory
from backend.app.models.settings import Settings
from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services.spoolman_tracking import get_fallback_spool_tag_for_slot
from backend.tests.integration.test_media_tokens import _admin_token, _make_user

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]
RESOLVE = "/api/v1/inventory/labels/resolve-spool"


async def test_label_resolution_accepts_only_this_install_and_its_public_url(async_client, db_session):
    db_session.add(Settings(key="external_url", value="https://printops.example/printing"))
    await db_session.commit()
    for payload in (
        "http://test/inventory?spool=23",
        "/inventory?spool=23",
        "https://printops.example/printing/inventory?spool=23&source=inventory",
    ):
        response = await async_client.post(RESOLVE, json={"payload": payload})
        assert response.status_code == 200, response.text
        assert response.json() == {"spool_id": 23, "source": "inventory"}
    for payload in (
        "https://other.example/inventory?spool=23",
        "https://printops.example@other.example/printing/inventory?spool=23",
        "http://test/jobs?spool=23",
        "http://test/inventory?spool=23&spool=24",
        "http://test/inventory?spool=23&source=spoolman",
        "http://test/inventory?spool=2147483648",
        "web+spoolman:s-23",
    ):
        assert (await async_client.post(RESOLVE, json={"payload": payload})).status_code == 422


async def test_spoolman_label_resolution_accepts_matching_remote_and_typed_tag(async_client, db_session):
    db_session.add_all(
        [
            Settings(key="spoolman_enabled", value="true"),
            Settings(key="spoolman_url", value="http://spoolman.example:7912/sm"),
        ]
    )
    await db_session.commit()
    for payload in (
        "web+spoolman:s-23",
        "http://spoolman.example:7912/sm/spool/show/23",
        "http://test/inventory?spool=23&source=spoolman",
    ):
        response = await async_client.post(RESOLVE, json={"payload": payload})
        assert response.status_code == 200, response.text
        assert response.json() == {"spool_id": 23, "source": "spoolman"}
    for payload in ("http://wrong.example/sm/spool/show/23", "http://test/inventory?spool=23&source=inventory"):
        assert (await async_client.post(RESOLVE, json={"payload": payload})).status_code == 422


async def test_native_move_leaves_other_printer_scopes_intact(async_client, db_session, printer_factory):
    old, hidden, target = [await printer_factory() for _ in range(3)]
    spool = Spool(material="PLA", label_weight=1000)
    db_session.add(spool)
    await db_session.flush()
    db_session.add_all(
        [
            SpoolAssignment(spool_id=spool.id, printer_id=old.id, ams_id=0, tray_id=0),
            SpoolAssignment(spool_id=spool.id, printer_id=hidden.id, ams_id=0, tray_id=0),
        ]
    )
    await db_session.commit()
    admin_jwt = await _admin_token(async_client, "scan_moves")
    token, user_id = await _make_user(
        async_client, admin_jwt, username="scan_editor", permissions=["inventory:read", "inventory:update"]
    )
    from backend.app.models.user import User

    user = await db_session.get(User, user_id)
    user.allowed_printer_ids = [old.id, target.id]
    await db_session.commit()

    url = "/api/v1/inventory/assignments"
    headers = {"Authorization": f"Bearer {token}"}
    body = {"spool_id": spool.id, "ams_id": 0, "tray_id": 1, "move": True}
    denied = await async_client.post(url, headers=headers, json={**body, "printer_id": hidden.id})
    assert denied.status_code == 404
    result = await async_client.post(url, headers=headers, json={**body, "printer_id": target.id})
    assert result.status_code == 200, result.text
    assert result.json()["printer_id"] == target.id
    rows = (await db_session.execute(select(SpoolAssignment.printer_id, SpoolAssignment.tray_id))).tuples().all()
    assert set(rows) == {(hidden.id, 0), (target.id, 1)}


async def test_two_scans_of_same_spool_commit_one_final_slot(async_client, db_session, printer_factory):
    first, second = [await printer_factory() for _ in range(2)]
    spool = Spool(material="PLA", label_weight=1000)
    db_session.add(spool)
    await db_session.commit()
    body = {"spool_id": spool.id, "ams_id": 0, "tray_id": 0, "move": True}
    responses = await asyncio.gather(
        *(
            async_client.post("/api/v1/inventory/assignments", json={**body, "printer_id": printer.id})
            for printer in (first, second)
        )
    )
    assert all(response.status_code == 200 for response in responses), [response.text for response in responses]
    rows = list(await db_session.scalars(select(SpoolAssignment).where(SpoolAssignment.spool_id == spool.id)))
    assert len(rows) == 1


@pytest.mark.parametrize("fail_write", [False, True])
async def test_spoolman_move_releases_fallback_tag_or_restores_it_on_failure(
    async_client,
    db_session,
    printer_factory,
    monkeypatch,
    fail_write,
):
    old, target = [await printer_factory() for _ in range(2)]
    spool_id = 42
    tag = get_fallback_spool_tag_for_slot(old.serial_number, 0, 0)
    original_extra = {"tag": json.dumps(tag), "user_note": json.dumps("keep")}
    db_session.add(SpoolmanSlotAssignment(spoolman_spool_id=spool_id, printer_id=old.id, ams_id=0, tray_id=0))
    await db_session.commit()
    client = SimpleNamespace(
        get_spool=AsyncMock(return_value={"id": spool_id, "extra": original_extra, "filament": {"material": "PLA"}}),
        update_spool_full=AsyncMock(),
        extra_lock=lambda _: asyncio.Lock(),
    )
    monkeypatch.setattr(spoolman_inventory, "_get_client", AsyncMock(return_value=client))
    monkeypatch.setattr(spoolman_inventory, "_clear_stale_slot_fallback_tag_links", AsyncMock())
    if fail_write:
        monkeypatch.setattr(
            inventory.spool_swaps, "record_assignment", AsyncMock(side_effect=RuntimeError("write failed"))
        )
    response = await async_client.post(
        "/api/v1/spoolman/inventory/slot-assignments",
        json={"spoolman_spool_id": spool_id, "printer_id": target.id, "ams_id": 0, "tray_id": 1, "move": True},
    )
    assert response.status_code == (500 if fail_write else 200), response.text
    patches = [call.kwargs["extra"] for call in client.update_spool_full.await_args_list]
    expected = [{**original_extra, "tag": json.dumps("")}]
    if fail_write:
        expected.append(original_extra)
    assert patches == expected
    rows = (
        (await db_session.execute(select(SpoolmanSlotAssignment.printer_id, SpoolmanSlotAssignment.tray_id)))
        .tuples()
        .all()
    )
    assert rows == [(old.id, 0)] if fail_write else rows == [(target.id, 1)]
