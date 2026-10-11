"""Existing/automatically imported external groups gain identity off read paths."""

import copy

import httpx
import pytest
from sqlalchemy import select

from backend.app.models.filament_sku_settings import FilamentSkuSettings
from backend.app.models.settings import Settings
from backend.app.services.spoolman import SpoolmanClient
from backend.tests.integration.test_stock_alert_producer import (
    alert_scheduler as alert_scheduler,
    model_engine as model_engine,
    run_alert_pass,
    test_engine as test_engine,
)


@pytest.mark.asyncio
async def test_background_reconciles_external_groups_without_subscribers_or_read_writes(
    async_client, db_session, alert_scheduler, monkeypatch
):
    raws = [
        {
            "id": 42,
            "initial_weight": 250,
            "remaining_weight": 25,
            "used_weight": 225,
            "archived": False,
            "extra": {"bambu_weight_used_baseline": '"200"', "bambu_color_name": '"Red"'},
            "filament": {"id": 7, "name": "PLA", "material": "PLA", "weight": 1000, "vendor": {"name": "Own"}},
        },
        {"id": 43, "filament": {"name": "PETG", "material": "PETG"}, "extra": {}},
        {"id": 44, "filament": {"name": "PETG", "material": "PETG"}, "extra": {}},
    ]
    snapshot = copy.deepcopy(raws)
    requests = []

    def transport(request):
        requests.append((request.method, request.url.path))
        return httpx.Response(200, json=raws if request.url.path.endswith("/spool") else raws[0])

    client = SpoolmanClient("http://inventory.invalid")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(transport))

    async def background_client():
        return client

    async def route_client(_db):
        return client

    monkeypatch.setattr("backend.app.services.spoolman.get_spoolman_client", background_client)
    monkeypatch.setattr("backend.app.api.routes.spoolman_inventory._get_client", route_client)
    legacy = FilamentSkuSettings(material="PLA", brand="Own", color_name="Red")
    db_session.add_all([legacy, Settings(key="spoolman_enabled", value="true")])
    await db_session.commit()
    try:
        response = await async_client.get("/api/v1/spoolman/inventory/spools/42")
        assert response.status_code == 200, response.text
        assert response.json()["material_number"] is None
        assert legacy.material_number is None  # GET remains lookup-only.
        scheduler, _ = alert_scheduler
        await run_alert_pass(scheduler)
        response = await async_client.get("/api/v1/spoolman/inventory/spools/42")
        assert response.json()["material_number"] == "MAT-00001"
        rows = list(await db_session.scalars(select(FilamentSkuSettings).order_by(FilamentSkuSettings.id)))
        assert [(row.id, row.material_number) for row in rows] == [
            (legacy.id, "MAT-00001"),
            (legacy.id + 1, "MAT-00002"),
        ]
        assert raws == snapshot
        assert all(method == "GET" for method, _path in requests)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_reconciliation_is_bounded_retries_outage_and_only_allocates_new_groups(
    db_session, alert_scheduler, monkeypatch
):
    from backend.app.models.warehouse_number_sequence import WarehouseNumberSequence

    state = {"time": 0, "status": 503}
    raws = [{"id": 42, "filament": {"material": "PLA", "name": "PLA"}, "extra": {}}]
    reads = []

    def transport(request):
        reads.append(request.url.path)
        return httpx.Response(state["status"], json=raws)

    client = SpoolmanClient("http://inventory.invalid")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(transport))

    async def get_client():
        return client

    monkeypatch.setattr("backend.app.services.spoolman.get_spoolman_client", get_client)
    monkeypatch.setattr("backend.app.services.spoolman_sku_reconciliation.monotonic", lambda: state["time"])
    db_session.add(Settings(key="spoolman_enabled", value="true"))
    await db_session.commit()
    scheduler, _ = alert_scheduler
    try:
        for time in (0, 1, 299):
            state["time"] = time
            await run_alert_pass(scheduler)
        assert len(reads) == 3  # One pass retains the real client's bounded HTTP retry.
        assert list(await db_session.scalars(select(FilamentSkuSettings))) == []
        state["time"] = 300
        await run_alert_pass(scheduler)
        assert len(reads) == 6
        state.update(time=600, status=200)
        await run_alert_pass(scheduler)
        rows = list(await db_session.scalars(select(FilamentSkuSettings)))
        assert [(row.material, row.material_number) for row in rows] == [("PLA", "MAT-00001")]
        sequence = await db_session.scalar(select(WarehouseNumberSequence))
        before = (sequence.next_value, sequence.version)
        state["time"] = 900
        await run_alert_pass(scheduler)
        await db_session.refresh(sequence)
        assert (sequence.next_value, sequence.version) == before  # Known groups are lookup-only.
        raws.append({"id": 43, "filament": {"material": "PETG", "name": "PETG"}, "extra": {}})
        state["time"] = 1200
        await run_alert_pass(scheduler)
        rows = list(await db_session.scalars(select(FilamentSkuSettings).order_by(FilamentSkuSettings.id)))
        assert [(row.material, row.material_number) for row in rows] == [("PLA", "MAT-00001"), ("PETG", "MAT-00002")]
        assert len(reads) == 9
    finally:
        await scheduler.close_inventory_alerts()
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("external,available", [(False, True), (True, False)])
async def test_reconciliation_requires_external_mode_and_available_client(
    db_session, alert_scheduler, monkeypatch, external, available
):
    requests = []

    def transport(request):
        requests.append(request.url.path)
        return httpx.Response(200, json=[{"id": 42, "filament": {"material": "PLA"}}])

    client = SpoolmanClient("http://inventory.invalid")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(transport))

    async def get_client():
        return client if available else None

    monkeypatch.setattr("backend.app.services.spoolman.get_spoolman_client", get_client)
    db_session.add(Settings(key="spoolman_enabled", value="true" if external else "false"))
    await db_session.commit()
    try:
        scheduler, _ = alert_scheduler
        await run_alert_pass(scheduler)
        assert requests == []
        assert list(await db_session.scalars(select(FilamentSkuSettings))) == []
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_external_identity_snapshot_timeout_is_cancelled_and_rate_limited(
    db_session, alert_scheduler, monkeypatch
):
    import asyncio

    state = {"time": 0}
    requests = []
    cancelled = asyncio.Event()
    release = asyncio.Event()

    async def transport(request):
        requests.append(request.url.path)
        try:
            await release.wait()
        finally:
            cancelled.set()
        return httpx.Response(200, json=[])

    client = SpoolmanClient("http://inventory.invalid")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(transport))

    async def get_client():
        return client

    monkeypatch.setattr("backend.app.services.spoolman.get_spoolman_client", get_client)
    monkeypatch.setattr("backend.app.services.spoolman_sku_reconciliation.monotonic", lambda: state["time"])
    db_session.add(Settings(key="spoolman_enabled", value="true"))
    await db_session.commit()
    scheduler, _ = alert_scheduler
    try:
        await asyncio.wait_for(run_alert_pass(scheduler), timeout=6)
        assert cancelled.is_set()
        state["time"] = 1
        await run_alert_pass(scheduler)
        assert len(requests) == 1
        assert list(await db_session.scalars(select(FilamentSkuSettings))) == []
    finally:
        release.set()
        await scheduler.close_inventory_alerts()
        await client.close()
