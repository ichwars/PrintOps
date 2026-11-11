"""A deleted printer's explicit scopes must never become global."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from backend.app.core.printer_associations import (
    OBICO_PRINTERS_KEY,
    migrate_legacy_virtual_printer,
    repair_deleted_printer_associations,
)
from backend.app.models.api_key import APIKey
from backend.app.models.notification import NotificationProvider
from backend.app.models.settings import Settings
from backend.app.models.smart_plug import SmartPlug
from backend.app.models.virtual_printer import VirtualPrinter
from backend.app.services.smart_plug_manager import smart_plug_manager
from backend.app.services.virtual_printer import virtual_printer_manager

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def api_key(name, printer_ids):
    return APIKey(name=name, key_prefix=f"{name}-prefix", key_hash=f"{name}-fixture-hash", printer_ids=printer_ids)


async def test_printer_delete_preserves_scopes_and_retires_automations(
    async_client, db_session, printer_factory, monkeypatch, tmp_path
):
    removed_id = (await printer_factory()).id
    other_id = (await printer_factory()).id
    bound_plug = SmartPlug(name="Bound plug", printer_id=removed_id)
    bound_vp = VirtualPrinter(name="Bound VP", mode="queue", target_printer_id=removed_id)
    db_session.add_all(
        [
            api_key("only", [removed_id]),
            api_key("both", [removed_id, other_id]),
            api_key("all", None),
            Settings(key=OBICO_PRINTERS_KEY, value=json.dumps([removed_id])),
            Settings(key="virtual_printer_target_printer_id", value=str(removed_id)),
            Settings(key="virtual_printer_enabled", value="true"),
            NotificationProvider(name="Bound", provider_type="ntfy", config="{}", printer_id=removed_id),
            NotificationProvider(name="Other", provider_type="ntfy", config="{}", printer_id=other_id),
            NotificationProvider(name="Global", provider_type="ntfy", config="{}"),
            bound_plug,
            SmartPlug(name="Other plug", printer_id=other_id),
            SmartPlug(name="Global plug"),
            bound_vp,
            VirtualPrinter(name="Other VP", target_printer_id=other_id),
            VirtualPrinter(name="Global VP"),
        ]
    )
    await db_session.commit()
    plug_id, vp_id = bound_plug.id, bound_vp.id
    pending_auto_off = asyncio.create_task(asyncio.Event().wait())
    monkeypatch.setattr(smart_plug_manager, "_pending_off", {plug_id: pending_auto_off})
    stop_vp = AsyncMock()
    monkeypatch.setattr(virtual_printer_manager, "remove_instance", stop_vp)
    monkeypatch.setattr(virtual_printer_manager, "sync_from_db", AsyncMock())
    monkeypatch.setattr(virtual_printer_manager, "_base_dir", tmp_path)

    try:
        response = await async_client.delete(f"/api/v1/printers/{removed_id}", params={"delete_archives": "false"})
        assert response.status_code == 200
        await asyncio.gather(pending_auto_off, return_exceptions=True)
        assert pending_auto_off.cancelled()
        assert plug_id not in smart_plug_manager._pending_off
        stop_vp.assert_awaited_once_with(vp_id)
    finally:
        if not pending_auto_off.done():
            pending_auto_off.cancel()
            await asyncio.gather(pending_auto_off, return_exceptions=True)

    assert set(await db_session.scalars(select(NotificationProvider.name))) == {"Other", "Global"}
    assert set(await db_session.scalars(select(SmartPlug.name))) == {"Other plug", "Global plug"}
    assert set(await db_session.scalars(select(VirtualPrinter.name))) == {"Other VP", "Global VP"}
    keys = dict((await db_session.execute(select(APIKey.name, APIKey.printer_ids))).all())
    assert keys == {"only": [], "both": [other_id], "all": None}
    stored = dict((await db_session.execute(select(Settings.key, Settings.value))).all())
    assert stored[OBICO_PRINTERS_KEY] == "[]"
    assert stored["virtual_printer_enabled"] == "false"
    assert "virtual_printer_target_printer_id" not in stored


async def test_repair_keeps_empty_scope_and_never_reimports_virtual_printer(db_session, printer_factory):
    printer_id = (await printer_factory()).id
    db_session.add_all(
        [
            api_key("none", []),
            api_key("old", [999]),
            api_key("mixed", [printer_id, 999]),
            api_key("all", None),
            Settings(key=OBICO_PRINTERS_KEY, value=f"[{printer_id},999]"),
            Settings(key="virtual_printer_enabled", value="true"),
            Settings(key="virtual_printer_target_printer_id", value="999"),
        ]
    )
    if db_session.get_bind().dialect.name == "sqlite":
        # Legacy SQLite accepted orphan associations. PostgreSQL rejects them on insert.
        db_session.add_all(
            [
                NotificationProvider(name="Orphan", provider_type="ntfy", config="{}", printer_id=999),
                SmartPlug(name="Orphan", printer_id=999),
                VirtualPrinter(name="Orphan", target_printer_id=999),
            ]
        )
    await db_session.flush()
    conn = await db_session.connection()
    await migrate_legacy_virtual_printer(conn)
    await repair_deleted_printer_associations(conn)
    await migrate_legacy_virtual_printer(conn)
    await db_session.commit()

    keys = dict((await db_session.execute(select(APIKey.name, APIKey.printer_ids))).all())
    assert keys == {"none": [], "old": [], "mixed": [printer_id], "all": None}
    assert (
        await db_session.scalar(select(Settings.value).where(Settings.key == OBICO_PRINTERS_KEY)) == f"[{printer_id}]"
    )
    for model in (NotificationProvider, SmartPlug, VirtualPrinter):
        assert await db_session.scalar(select(model.id)) is None


async def test_stale_printer_choices_cannot_be_saved(async_client, db_session):
    key = api_key("existing", None)
    provider = NotificationProvider(name="Global", provider_type="ntfy", config="{}")
    db_session.add_all([key, provider])
    await db_session.commit()
    operations = [
        ("POST", "/api/v1/api-keys/", {"name": "stale", "printer_ids": [999]}),
        ("PATCH", f"/api/v1/api-keys/{key.id}", {"printer_ids": [999]}),
        ("POST", "/api/v1/notifications/", {"name": "Stale", "provider_type": "ntfy", "config": {}, "printer_id": 999}),
        ("PATCH", f"/api/v1/notifications/{provider.id}", {"printer_id": 999}),
        ("PUT", "/api/v1/settings/", {OBICO_PRINTERS_KEY: "[999]"}),
        ("PUT", "/api/v1/slicer-pipelines/999", {"target_printer_id": 999}),
    ]
    for method, route, payload in operations:
        response = await async_client.request(method, route, json=payload)
        assert response.status_code == 400, (method, route, response.json())

    response = await async_client.put("/api/v1/settings/", json={OBICO_PRINTERS_KEY: "[]"})
    assert response.status_code == 200
    assert response.json()[OBICO_PRINTERS_KEY] == "[]"
