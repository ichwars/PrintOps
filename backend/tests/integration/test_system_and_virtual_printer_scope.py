"""System, support and virtual printer permissions with real route authentication."""

from types import SimpleNamespace

import pytest
from sqlalchemy import update

from backend.app.api.routes import settings as settings_routes, system
from backend.app.core.auth import generate_api_key
from backend.app.models.api_key import APIKey
from backend.app.models.settings import Settings
from backend.app.models.user import User
from backend.app.models.virtual_printer import VirtualPrinter
from backend.app.services.log_health import LogFinding, ScanResult
from backend.app.services.virtual_printer import virtual_printer_manager
from backend.tests.integration.test_media_tokens import _admin_token, _make_user

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def scoped_system(async_client, db_session, printer_factory):
    visible = await printer_factory(name="Visible device")
    hidden = await printer_factory(name="Hidden device")
    token = await _admin_token(async_client, "_system_scope")
    read_permissions = ["system:read", "settings:read", "printers:read"]
    reader, reader_id = await _make_user(
        async_client, token, username="scoped_system_reader", permissions=read_permissions
    )
    editor, editor_id = await _make_user(
        async_client, token, username="scoped_system_editor", permissions=[*read_permissions, "settings:update"]
    )
    await db_session.execute(
        update(User).where(User.id.in_([reader_id, editor_id])).values(allowed_printer_ids=[visible.id])
    )
    secret, key_hash, prefix = generate_api_key()
    db_session.add(
        APIKey(
            name="System scope",
            key_hash=key_hash,
            key_prefix=prefix,
            can_read_status=True,
            printer_ids=[visible.id],
        )
    )
    await db_session.commit()
    admin_headers, reader_headers, editor_headers = (
        {"Authorization": f"Bearer {jwt}"} for jwt in (token, reader, editor)
    )
    return visible, hidden, admin_headers, reader_headers, editor_headers, {"X-API-Key": secret}


async def test_system_and_diagnostic_printer_counts_use_the_requested_scope(async_client, scoped_system, monkeypatch):
    visible, hidden, admin, reader, _, key = scoped_system
    clients = {p.id: SimpleNamespace(state=SimpleNamespace(connected=True, state="IDLE")) for p in (visible, hidden)}
    monkeypatch.setattr(system.printer_manager, "_clients", clients)
    for headers, expected in ((admin, [visible.id, hidden.id]), (reader, [visible.id]), (key, [visible.id])):
        response = await async_client.get("/api/v1/system/info", headers=headers)
        assert response.status_code == 200
        assert response.json()["database"]["printers"] == len(expected)
        assert [printer["id"] for printer in response.json()["printers"]["connected_list"]] == expected
        response = await async_client.get("/api/v1/printers/", headers=headers)
        assert response.status_code == 200
        assert sorted(printer["id"] for printer in response.json()) == expected


async def test_support_logs_are_private_and_scoped_health_hides_samples(async_client, scoped_system, monkeypatch):
    _, _, admin, reader, editor, key = scoped_system
    finding = LogFinding(
        signature_id="example",
        severity="warning",
        category="environment",
        wiki_anchor="example",
        count=1,
        first_seen="10:00",
        last_seen="10:00",
        sample="A private printer message",
    )
    monkeypatch.setattr(
        system,
        "scan_logs",
        lambda **kwargs: ScanResult(findings=[finding], scanned_entries=1, log_available=True, summary={"total": 1}),
    )
    for headers in (reader, key):
        response = await async_client.get("/api/v1/system/health", headers=headers)
        assert response.status_code == 200
        assert response.json()["findings"][0]["sample"] == ""
        assert (await async_client.get("/api/v1/support/logs", headers=headers)).status_code == 403
        assert (await async_client.get("/api/v1/support/bundle", headers=headers)).status_code == 403
    response = await async_client.get("/api/v1/system/health", headers=admin)
    assert response.json()["findings"][0]["sample"] == finding.sample
    assert (await async_client.get("/api/v1/support/logs", headers=editor)).status_code == 200


async def test_virtual_printer_targets_and_legacy_settings_follow_the_scope(
    async_client, db_session, scoped_system, monkeypatch
):
    visible, hidden, admin, reader, editor, key = scoped_system
    visible_vp = VirtualPrinter(name="Visible proxy", mode="proxy", target_printer_id=visible.id, position=2)
    hidden_vp = VirtualPrinter(name="Hidden proxy", mode="proxy", target_printer_id=hidden.id, position=1)
    db_session.add_all([visible_vp, hidden_vp, Settings(key="virtual_printer_target_printer_id", value=str(hidden.id))])
    await db_session.commit()
    monkeypatch.setattr(
        virtual_printer_manager,
        "get_status",
        lambda: {"running": True, "name": "Hidden proxy", "serial": "hidden", "target_printer_ip": "192.0.2.30"},
    )
    base = "/api/v1/virtual-printers"
    for headers in (reader, key):
        listing = await async_client.get(base, headers=headers)
        assert [row["id"] for row in listing.json()["printers"]] == [visible_vp.id]
        assert (await async_client.get(f"{base}/{hidden_vp.id}", headers=headers)).status_code == 404
        assert (await async_client.get(f"{base}/{hidden_vp.id}/diagnostic", headers=headers)).status_code == 404
        legacy = await async_client.get("/api/v1/settings/virtual-printer", headers=headers)
        assert legacy.json()["target_printer_id"] is None
        assert legacy.json()["status"] == {"running": True}

    assert (await async_client.delete(f"{base}/{hidden_vp.id}", headers=editor)).status_code == 404
    assert (
        await async_client.put(f"{base}/{hidden_vp.id}", headers=editor, json={"target_printer_id": visible.id})
    ).status_code == 404
    assert (
        await async_client.put(f"{base}/{visible_vp.id}", headers=editor, json={"target_printer_id": hidden.id})
    ).status_code == 400
    assert (
        await async_client.post(base, headers=editor, json={"name": "Denied", "target_printer_id": hidden.id})
    ).status_code == 400
    response = await async_client.put("/api/v1/settings/virtual-printer", headers=editor, params={"enabled": False})
    assert response.status_code == 404
    assert await settings_routes.get_setting(db_session, "virtual_printer_target_printer_id") == str(hidden.id)
    assert (await async_client.get(f"{base}/{hidden_vp.id}", headers=admin)).status_code == 200
