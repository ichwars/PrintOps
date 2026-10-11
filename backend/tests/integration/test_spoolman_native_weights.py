"""Spool-specific weights must survive list/edit/weigh and usage calculation."""

import json

import httpx
import pytest

from backend.app.api.routes._spoolman_helpers import _map_spoolman_spool
from backend.app.models.color_catalog import ColorCatalogEntry
from backend.app.models.settings import Settings
from backend.app.services.spoolman import AMSTray, SpoolmanClient
from backend.app.services.spoolman_costs import spoolman_usage_cost
from backend.app.services.spoolman_weights import spoolman_net_weight, spoolman_tare
from backend.tests.integration.test_inventory_tag_conflicts import remote_spoolman as remote_spoolman


@pytest.mark.asyncio
async def test_rfid_product_line_does_not_reuse_other_same_color_filament():
    tray = AMSTray(0, 0, "PLA", "PLA Matte", "000000FF", 80, "04A1B2C3", "A" * 32, "GFA01", 250)

    def transport(request):
        if request.url.path.endswith("/vendor"):
            return httpx.Response(200, json=[{"id": 3, "name": "Bambu Lab"}])
        if request.url.path.endswith("/filament"):
            return httpx.Response(
                200,
                json=[
                    {"id": 1, "name": "PLA Basic", "vendor_id": 3, "material": "PLA", "color_hex": "000000"},
                    {"id": 2, "name": "PLA Matte", "vendor_id": 3, "material": "PLA", "color_hex": "000000"},
                ],
            )
        raise AssertionError(f"Unexpected external request: {request.method} {request.url}")

    client = SpoolmanClient("http://spoolman.invalid")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    try:
        chosen = await client._find_or_create_filament(tray)
        assert chosen["id"] == 2
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_rfid_creation_uses_own_catalog_product_line_and_preserves_both_tags(db_session):
    db_session.add_all(
        [
            ColorCatalogEntry(manufacturer="Bambu Lab", material="PLA Basic", hex_color="#000000", color_name="Black"),
            ColorCatalogEntry(
                manufacturer="Bambu Lab", material="PLA Matte", hex_color="#000000", color_name="Charcoal"
            ),
        ]
    )
    await db_session.commit()
    created = {}

    def transport(request):
        path = request.url.path
        if "/field/spool/" in path:
            return httpx.Response(200, json={})
        if path.endswith("/vendor"):
            return httpx.Response(200, json=[{"id": 3, "name": "Bambu Lab"}])
        if path.endswith("/external/filament"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "bambulab_matte_charcoal",
                        "manufacturer": "Bambu Lab",
                        "name": "Matte Charcoal",
                        "material": "PLA",
                        "color_hex": "000000",
                        "weight": 250,
                        "density": 1.31,
                    }
                ],
            )
        if path.endswith("/filament"):
            if request.method == "POST":
                created["filament"] = json.loads(request.content)
                return httpx.Response(200, json={"id": 7, **created["filament"]})
            return httpx.Response(200, json=[])
        if path.endswith("/spool"):
            if request.method == "POST":
                created["spool"] = json.loads(request.content)
                return httpx.Response(200, json={"id": 42, **created["spool"]})
            return httpx.Response(200, json=[])
        raise AssertionError(str(request.url))

    client = SpoolmanClient("http://spoolman.invalid")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    tray = AMSTray(0, 0, "PLA", "PLA Matte", "000000FF", 80, "04A1B2C3", "A" * 32, "GFA01", 250)
    try:
        result = await client.sync_ams_tray(tray, "Printer", db=db_session)
        assert result["id"] == 42
        assert created["filament"]["name"] == "PLA Matte"
        assert created["filament"]["density"] == 1.31
        assert created["spool"]["initial_weight"] == 250
        assert created["spool"]["remaining_weight"] == 200
        assert json.loads(created["spool"]["extra"]["bambu_color_name"]) == "Charcoal"
        assert json.loads(created["spool"]["extra"]["bambu_tag_uid"]) == "04A1B2C3"
        assert json.loads(created["spool"]["extra"]["bambu_tray_uuid"]) == "A" * 32
    finally:
        await client.close()


def test_own_net_and_vendor_tare_drive_stock_consumed_and_price():
    mapped = _map_spoolman_spool(
        {
            "id": 1,
            "initial_weight": 250.7,
            "remaining_weight": 100,
            "used_weight": 150,
            "price": 5.014,
            "extra": {"bambu_weight_used_baseline": '"125"'},
            "filament": {"weight": 1000, "material": "PLA", "vendor": {"empty_spool_weight": 180}},
        }
    )
    assert mapped["label_weight"] == 250
    assert mapped["core_weight"] == 180
    assert mapped["label_weight"] - mapped["weight_used"] == 100
    assert mapped["weight_used"] - mapped["weight_used_baseline"] == 25
    assert mapped["cost_per_kg"] == pytest.approx(20)


def test_usage_cost_uses_native_net_size():
    spool = {"initial_weight": 250, "used_weight": 100, "price": 5, "filament": {"weight": 1000}}
    assert spoolman_usage_cost(spool, 50) == 1


@pytest.mark.parametrize("invalid", [None, 0, -1, True, float("nan"), float("inf"), "invalid"])
def test_unset_or_invalid_initial_weight_preserves_catalog_fallback(invalid):
    assert spoolman_net_weight({"initial_weight": invalid, "filament": {"weight": 500}}) == 500
    assert spoolman_tare({"spool_weight": 0, "filament": {"spool_weight": 200}}) == (0, "spool")


@pytest.mark.asyncio
async def test_create_writes_own_net_size_and_explicit_zero_tare(async_client, remote_spoolman):
    state, _, patches = remote_spoolman
    response = await async_client.post(
        "/api/v1/spoolman/inventory/spools",
        json={"spoolman_filament_id": 7, "label_weight": 250, "core_weight": 0, "weight_used": 50},
    )
    assert response.status_code == 200, response.text
    assert state["initial_weight"] == 250
    assert state["spool_weight"] == 0
    assert state["remaining_weight"] == 200
    assert response.json()["label_weight"] == 250
    assert all("used_weight" not in body for body in patches)


@pytest.mark.asyncio
async def test_noop_edit_preserves_own_size_and_baseline(async_client, remote_spoolman):
    state, _, patches = remote_spoolman
    state["initial_weight"] = 500
    response = await async_client.patch("/api/v1/spoolman/inventory/spools/42", json={"note": "new"})
    assert response.status_code == 200, response.text
    assert response.json()["label_weight"] == 500
    assert state["remaining_weight"] == 750
    assert state["extra"]["bambu_weight_used_baseline"] == '"200"'
    assert not any("weight" in body for body in patches)


@pytest.mark.asyncio
async def test_size_and_tare_edit_changes_only_native_spool_fields(async_client, remote_spoolman):
    state, _, patches = remote_spoolman
    state["initial_weight"] = 1000
    response = await async_client.patch(
        "/api/v1/spoolman/inventory/spools/42", json={"label_weight": 250, "core_weight": 0, "cost_per_kg": 20}
    )
    assert response.status_code == 200, response.text
    assert state["initial_weight"] == 250
    assert state["spool_weight"] == 0
    assert state["filament"]["weight"] == 1000
    assert state["price"] == 5
    assert state["remaining_weight"] == 750
    assert not any("weight" in body for body in patches)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["/api/v1/spoolman/inventory/spools/42/weight", "/api/v1/spoolbuddy/scale/update-spool-weight"]
)
async def test_scale_uses_vendor_tare_and_own_net_weight(async_client, db_session, remote_spoolman, monkeypatch, path):
    state, _, _ = remote_spoolman
    state["initial_weight"] = 250
    state["filament"]["vendor"]["empty_spool_weight"] = 180
    db_session.add(Settings(key="spoolman_enabled", value="true"))
    await db_session.commit()
    from backend.app.api.routes import spoolman_inventory

    monkeypatch.setattr(
        "backend.app.api.routes.spoolbuddy._get_spoolman_client_or_none", spoolman_inventory._get_client
    )
    response = await (
        async_client.patch(path, json={"weight_grams": 280})
        if path.endswith("/weight")
        else async_client.post(path, json={"spool_id": 42, "weight_grams": 280})
    )
    assert response.status_code == 200, response.text
    assert state["remaining_weight"] == 100
    assert response.json()["weight_used"] == 150
    assert not response.json().get("warnings")
