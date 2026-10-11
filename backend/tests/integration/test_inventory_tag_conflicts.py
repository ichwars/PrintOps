"""RFID conflicts and independent identifier clearing through the real routes."""

import copy
import json

import httpx
import pytest

from backend.app.models.spool import Spool
from backend.app.services.spoolman import SpoolmanClient

UUID = "AABBCCDDEEFF0011AABBCCDDEEFF0011"
UID = "04A1B2C3"


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("tag_uid", UID), ("tray_uuid", UUID)])
async def test_legacy_duplicate_holders_return_structured_conflict(async_client, db_session, field, value):
    spools = [Spool(material="PLA", label_weight=1000, **{field: value.lower()}) for _ in range(2)]
    target = Spool(material="PETG", label_weight=750)
    db_session.add_all([*spools, target])
    await db_session.commit()
    response = await async_client.patch(f"/api/v1/inventory/spools/{target.id}/link-tag", json={field: value})
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "tag_already_linked",
        "field": field,
        "spool_id": spools[0].id,
        "message": f"Tag is already linked to spool {spools[0].id}",
    }
    await db_session.refresh(target)
    assert getattr(target, field) is None


@pytest.fixture
async def remote_spoolman(monkeypatch):
    """Real client; only the external HTTP boundary is replaced."""
    state = {
        "id": 42,
        "filament": {
            "id": 7,
            "name": "PLA",
            "material": "PLA",
            "weight": 1000,
            "color_hex": "FF0000",
            "vendor": {"name": "Bambu"},
        },
        "remaining_weight": 750,
        "used_weight": 250,
        "archived": False,
        "extra": {
            "tag": json.dumps(UUID),
            "bambu_tray_uuid": json.dumps(UUID),
            "bambu_tag_uid": json.dumps(UID),
            "bambu_weight_used_baseline": '"200"',
            "custom": '"keep"',
        },
    }
    others = []
    patches = []

    def transport(request):
        if request.method in {"PATCH", "POST"}:
            body = json.loads(request.content)
            patches.append(body)
            state.update({k: v for k, v in body.items() if k != "extra"})
            state["extra"].update(body.get("extra", {}))
            return httpx.Response(200, json=state)
        if request.url.path.endswith("/spool"):
            return httpx.Response(200, json=[*others, state])
        return httpx.Response(200, json=state)

    client = SpoolmanClient("http://spoolman.invalid")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(transport))

    async def get_client(_db):
        return client

    monkeypatch.setattr("backend.app.api.routes.spoolman_inventory._get_client", get_client)
    yield state, others, patches
    await client.close()


@pytest.mark.asyncio
async def test_spoolman_checks_both_identifiers_and_reports_lowest_holder(async_client, remote_spoolman):
    state, others, patches = remote_spoolman
    others.extend(
        [
            {"id": 9, "extra": {"bambu_tag_uid": json.dumps(UID.lower())}},
            {"id": 2, "extra": {"tag": json.dumps(UID)}},
            {"id": 3, "extra": "legacy garbage"},
        ]
    )
    before = copy.deepcopy(state)
    response = await async_client.patch(
        "/api/v1/spoolman/inventory/spools/42/tag", json={"tray_uuid": UUID, "tag_uid": UID}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["spool_id"] == 2
    assert response.json()["detail"]["code"] == "tag_already_linked"
    assert not patches
    assert state == before


@pytest.mark.asyncio
async def test_spoolman_uuid_clear_preserves_uid_native_stock_and_baseline(async_client, remote_spoolman):
    state, _, patches = remote_spoolman
    response = await async_client.patch("/api/v1/spoolman/inventory/spools/42", json={"tray_uuid": None})
    assert response.status_code == 200, response.text
    assert response.json()["tray_uuid"] is None
    assert response.json()["tag_uid"] == UID
    assert json.loads(state["extra"]["tag"]) == UID
    assert state["extra"]["bambu_weight_used_baseline"] == '"200"'
    assert state["extra"]["custom"] == '"keep"'
    assert state["remaining_weight"] == 750
    assert state["used_weight"] == 250
    assert all("used_weight" not in p for p in patches)
