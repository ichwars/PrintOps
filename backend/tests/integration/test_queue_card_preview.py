"""Card queue data uses the real ASGI authorization and database boundary."""

from datetime import datetime, timezone

import pytest

from backend.app.models.archive import PrintArchive
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def preview_data(async_client, db_session):
    setup = await async_client.post(
        "/api/v1/auth/setup",
        json={
            "auth_enabled": True,
            "admin_username": "previewadmin",
            "admin_password": "PreviewPass1!",
        },
    )
    assert setup.status_code == 200, setup.text
    login = await async_client.post(
        "/api/v1/auth/login",
        json={
            "username": "previewadmin",
            "password": "PreviewPass1!",
        },
    )
    admin = {"Authorization": f"Bearer {login.json()['access_token']}"}
    printers = [
        Printer(
            name=f"Preview {i}",
            serial_number=f"PREVIEW{i}",
            ip_address=f"192.0.2.{i}",
            access_code="12345678",
            model="X1C",
        )
        for i in (1, 2)
    ]
    db_session.add_all(printers)
    await db_session.commit()

    async def reader(name, permissions):
        group = await async_client.post(
            "/api/v1/groups/", headers=admin, json={"name": name, "permissions": permissions}
        )
        assert group.status_code == 201, group.text
        user = await async_client.post(
            "/api/v1/users/",
            headers=admin,
            json={
                "username": name,
                "password": "PreviewPass1!",
                "group_ids": [group.json()["id"]],
                "allowed_printer_ids": [printers[0].id],
            },
        )
        assert user.status_code == 201, user.text
        login = await async_client.post(
            "/api/v1/auth/login",
            json={
                "username": name,
                "password": "PreviewPass1!",
            },
        )
        return user.json()["id"], {"Authorization": f"Bearer {login.json()['access_token']}"}

    owner, own_headers = await reader("ownpreview", ["queue:read_own"])
    _, all_headers = await reader("allpreview", ["queue:read_all"])
    _, denied_headers = await reader("nopreview", ["printers:read"])
    archive = PrintArchive(filename="preview.3mf", file_path="/tmp/preview.3mf", file_size=100, print_time_seconds=10)
    db_session.add(archive)
    await db_session.commit()
    rows = [
        PrintQueueItem(
            printer_id=printers[0].id, created_by_id=owner, position=1, print_time_seconds=90, archive_id=archive.id
        ),
        PrintQueueItem(
            printer_id=None,
            target_model="X1C",
            created_by_id=owner,
            position=1,
            print_time_seconds=30,
            dispatching_at=datetime.now(timezone.utc),
        ),
        PrintQueueItem(printer_id=None, target_model="X1C", position=1, created_by_id=login.json()["user"]["id"]),
        PrintQueueItem(printer_id=printers[1].id, created_by_id=owner, position=0),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    return printers, rows, own_headers, all_headers, denied_headers


async def test_restricted_printer_cannot_return_unassigned_model_candidates(async_client, preview_data):
    printers, _, own, _, _ = preview_data
    response = await async_client.get(f"/api/v1/queue/?printer_id={printers[1].id}&target_model=X1C", headers=own)
    assert response.status_code == 404


async def test_owner_scope_and_stable_tie_order_include_only_authorized_model_rows(async_client, preview_data):
    printers, rows, own, _, _ = preview_data
    response = await async_client.get(f"/api/v1/queue/?printer_id={printers[0].id}&status=pending", headers=own)
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()] == [rows[0].id, rows[1].id]


async def test_read_all_still_respects_printer_scope(async_client, preview_data):
    printers, rows, _, all_headers, _ = preview_data
    response = await async_client.get(f"/api/v1/queue/?printer_id={printers[0].id}", headers=all_headers)
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()] == [row.id for row in rows[:3]]


async def test_no_queue_permission_cannot_read_card_candidates(async_client, preview_data):
    printers, _, _, _, denied = preview_data
    response = await async_client.get(f"/api/v1/queue/?printer_id={printers[0].id}", headers=denied)
    assert response.status_code == 403


async def test_preview_exposes_scheduler_duration_and_dispatch_claim(async_client, preview_data):
    printers, _, own, _, _ = preview_data
    response = await async_client.get(f"/api/v1/queue/?printer_id={printers[0].id}", headers=own)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data[0]["print_time_seconds"] == 10  # Source estimate intentionally differs from SJF
    assert [(row.get("scheduler_print_time_seconds"), row.get("dispatching")) for row in data] == [
        (90, False),
        (30, True),
    ]


async def test_dispatch_claim_refresh_does_not_change_ownership(async_client, preview_data, db_session):
    printers, rows, own, _, _ = preview_data
    rows[0].dispatching_at = datetime.now(timezone.utc)
    rows[1].dispatching_at = None
    await db_session.commit()
    response = await async_client.get(f"/api/v1/queue/?printer_id={printers[0].id}", headers=own)
    assert response.status_code == 200, response.text
    assert [(row["id"], row["dispatching"]) for row in response.json()] == [(rows[0].id, True), (rows[1].id, False)]


async def test_queue_reader_gets_ordering_without_settings_permission(async_client, preview_data, db_session):
    from backend.app.models.settings import Settings

    printers, _, own, _, _ = preview_data
    db_session.add(Settings(key="queue_shortest_first", value="true"))
    await db_session.commit()
    settings = await async_client.get("/api/v1/settings/", headers=own)
    assert settings.status_code == 403
    response = await async_client.get(f"/api/v1/queue/?printer_id={printers[0].id}", headers=own)
    assert response.status_code == 200, response.text
    assert all(row.get("scheduler_shortest_first") is True for row in response.json())
    assert all("settings" not in row for row in response.json())


async def test_non_list_response_does_not_claim_a_default_order(async_client, preview_data, db_session):
    from backend.app.models.settings import Settings

    _, rows, own, _, _ = preview_data
    db_session.add(Settings(key="queue_shortest_first", value="true"))
    await db_session.commit()
    response = await async_client.get(f"/api/v1/queue/{rows[0].id}", headers=own)
    assert response.status_code == 200, response.text
    assert response.json()["scheduler_shortest_first"] is None
