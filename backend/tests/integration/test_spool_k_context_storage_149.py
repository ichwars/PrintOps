"""A stored calibration index is scoped by diameter, extruder and reported flow."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.models.spool import Spool
from backend.app.services.calibration_context import resolve_spool_calibration

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def spool(db_session):
    value = Spool(material="PLA", k_profiles=[])
    db_session.add(value)
    await db_session.commit()
    return value


@pytest.mark.parametrize("remote", [False, True])
async def test_two_flows_reusing_index_coexist_update_and_delete_independently(
    async_client, db_session, printer_factory, spool, remote
):
    printer = await printer_factory(model="P2S")
    prefix = "spoolman/inventory" if remote else "inventory"
    url = f"/api/v1/{prefix}/spools/{spool.id}/k-profiles"
    client = AsyncMock()
    client.get_spool.return_value = {"id": spool.id}
    rows = [
        {
            "printer_id": printer.id,
            "extruder": 0,
            "nozzle_diameter": "0.4",
            "nozzle_type": flow,
            "cali_idx": 5,
            "k_value": value,
            "setting_id": f"P{flow}",
        }
        for flow, value in [("HS", 0.02), ("HH", 0.04)]
    ]
    with patch("backend.app.api.routes.spoolman_inventory._get_client", return_value=client):
        response = await async_client.put(url, json=rows)
        assert response.status_code == 200, response.text
        saved = (await async_client.get(url)).json()
        assert {(r["nozzle_type"], r["cali_idx"]) for r in saved} == {("HS", 5), ("HH", 5)}
        rows[0]["k_value"] = 0.03
        assert (await async_client.put(url, json=rows)).status_code == 200
        saved = (await async_client.get(url)).json()
        assert {r["nozzle_type"]: r["k_value"] for r in saved} == {"HS": 0.03, "HH": 0.04}
        assert (await async_client.put(url, json=rows[1:])).status_code == 200
        assert [(r["nozzle_type"], r["k_value"]) for r in (await async_client.get(url)).json()] == [("HH", 0.04)]


@pytest.mark.parametrize("remote", [False, True])
@pytest.mark.parametrize("types", [("HS00_0.4", "HS07_0.4"), (None, "hardened_steel")])
async def test_duplicate_context_rejected_without_erasing_saved_rows(
    async_client, printer_factory, spool, remote, types
):
    printer = await printer_factory(model="X1C")
    url = f"/api/v1/{'spoolman/inventory' if remote else 'inventory'}/spools/{spool.id}/k-profiles"
    client = AsyncMock()
    client.get_spool.return_value = {"id": spool.id}
    existing = {"printer_id": printer.id, "nozzle_diameter": "0.4", "nozzle_type": "HH", "k_value": 0.04}
    with patch("backend.app.api.routes.spoolman_inventory._get_client", return_value=client):
        assert (await async_client.put(url, json=[existing])).status_code == 200
        duplicate = [{**existing, "nozzle_type": value} for value in types]
        response = await async_client.put(url, json=duplicate)
        assert response.status_code == 422
        saved = (await async_client.get(url)).json()
        assert len(saved) == 1 and saved[0]["nozzle_type"] == "HH"


@pytest.mark.parametrize("remote", [False, True])
async def test_flow_storage_does_not_change_unknown_legacy_fallback(db_session, printer_factory, spool, remote):
    from backend.app.models.spool_k_profile import SpoolKProfile
    from backend.app.models.spoolman_k_profile import SpoolmanKProfile

    printer = await printer_factory(model="X1C")
    table = SpoolmanKProfile if remote else SpoolKProfile
    key = "spoolman_spool_id" if remote else "spool_id"
    legacy = table(**{key: spool.id}, printer_id=printer.id, nozzle_type="hardened_steel", k_value=0.02, cali_idx=5)
    db_session.add(legacy)
    await db_session.commit()
    state = SimpleNamespace(
        nozzles=[SimpleNamespace(nozzle_diameter="0.4", nozzle_type="hardened_steel")],
        nozzle_rack=[],
        ams_extruder_map={},
        kprofiles=[],
        kprofile_diameters=set(),
    )
    _, selected, _ = resolve_spool_calibration([legacy], state, "X1C", printer.id, 0, 0)
    assert selected is legacy
    state.nozzles[0].nozzle_type = "HS"
    _, selected, _ = resolve_spool_calibration([legacy], state, "X1C", printer.id, 0, 0)
    assert selected is None
