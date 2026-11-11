"""Legacy project imports and edits use the same accepted states on both stores."""

import json

import pytest

from backend.app.models.project import Project
from backend.app.models.smart_plug import SmartPlug
from backend.app.services.project_lifecycle import repair_project_choices

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.mark.parametrize("as_file", [False, True])
@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({}, ("normal", "active")),
        ({"priority": "urgent", "status": "archived"}, ("urgent", "archived")),
        ({"priority": 0, "status": None}, ("normal", "active")),
        ({"priority": "x" * 90, "status": "y" * 90}, ("normal", "active")),
    ],
)
async def test_import_project_normalizes_legacy_values(async_client, as_file, values, expected):
    data = {"name": "Imported project", **values}
    if as_file:
        response = await async_client.post(
            "/api/v1/projects/import/file", files={"file": ("project.json", json.dumps(data), "application/json")}
        )
    else:
        response = await async_client.post("/api/v1/projects/import", json=data)
    assert response.status_code == 200, response.text
    assert (response.json()["priority"], response.json()["status"]) == expected


async def test_new_project_rejects_unknown_priority(async_client):
    response = await async_client.post("/api/v1/projects/", json={"name": "New", "priority": "whenever"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid priority"


async def test_repaired_project_is_editable_and_keeps_its_update_timestamp(async_client, db_session):
    legacy = Project(name="Legacy", priority="0", status="done")
    preserved = Project(name="Valid", priority="high", status="completed")
    db_session.add_all([legacy, preserved])
    await db_session.commit()
    await db_session.refresh(legacy)
    previous_update = legacy.updated_at
    for _ in range(2):
        await repair_project_choices(await db_session.connection())
        await db_session.commit()
    await db_session.refresh(legacy)
    await db_session.refresh(preserved)
    assert (legacy.priority, legacy.status, legacy.updated_at) == ("normal", "active", previous_update)
    assert (preserved.priority, preserved.status) == ("high", "completed")

    response = await async_client.patch(
        f"/api/v1/projects/{legacy.id}",
        json={"name": "Renamed", "priority": legacy.priority, "status": legacy.status},
    )
    assert response.status_code == 200, response.text


async def test_nonexistent_printer_zero_is_rejected_for_plugs_and_virtual_printers(async_client, db_session):
    plug = SmartPlug(name="Existing plug", ip_address="192.0.2.1")
    db_session.add(plug)
    await db_session.commit()
    created = await async_client.post(
        "/api/v1/smart-plugs/", json={"name": "New plug", "ip_address": "192.0.2.2", "printer_id": 0}
    )
    changed = await async_client.patch(f"/api/v1/smart-plugs/{plug.id}", json={"printer_id": 0})
    proxy = await async_client.post(
        "/api/v1/virtual-printers",
        json={"name": "Fixture VP", "mode": "proxy", "target_printer_id": 0, "enabled": False},
    )
    assert created.status_code == changed.status_code == proxy.status_code == 400
    await db_session.refresh(plug)
    assert plug.printer_id is None
