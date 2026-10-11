"""A consumed-counter reset must never refill a spool or lose its metadata."""

import asyncio
import json
from copy import deepcopy

import httpx
import pytest

from backend.app.api.routes._spoolman_helpers import _map_spoolman_spool
from backend.app.services.spoolman import SpoolmanClient


@pytest.fixture
async def spoolman_server():
    stock = {
        "id": 42,
        "filament": {"id": 7, "weight": 1000, "material": "PLA"},
        "initial_weight": 850,
        "remaining_weight": 587,
        "used_weight": 263,
        "extra": {"tag": '"RFID"'},
        "price": 25,
    }
    registered = set()

    async def handle(request):
        await asyncio.sleep(0)
        if "/field/spool/" in request.url.path:
            name = request.url.path.rsplit("/", 1)[1]
            if request.method == "POST":
                assert json.loads(request.content)["field_type"] == "text"
                registered.add(name)
                return httpx.Response(201, json={"name": name})
            return httpx.Response(200 if name in registered else 404, json={})
        if request.method == "PATCH":
            body = json.loads(request.content)
            extra = body.get("extra", {})
            if "bambu_weight_used_baseline" in extra:
                if "bambu_weight_used_baseline" not in registered:
                    return httpx.Response(400, json={"message": "Unknown extra field"})
                assert isinstance(json.loads(extra["bambu_weight_used_baseline"]), str)
            stock.update(body)
            if "used_weight" in body:
                stock["remaining_weight"] = stock["initial_weight"] - body["used_weight"]
        return httpx.Response(200, json=deepcopy(stock))

    client = SpoolmanClient("http://spoolman.test")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    yield client, stock
    await client._client.aclose()


@pytest.mark.asyncio
async def test_reset_preserves_native_stock_and_zeroes_only_displayed_counter(spoolman_server):
    client, stock = spoolman_server
    response = await client.reset_spool_usage(42)
    assert (stock["initial_weight"], stock["remaining_weight"], stock["used_weight"]) == (850, 587, 263)
    assert stock["extra"]["tag"] == '"RFID"'
    assert stock["extra"]["bambu_weight_used_baseline"] == '"263.0"'
    mapped = _map_spoolman_spool(response)
    assert mapped["label_weight"] - mapped["weight_used"] == 587
    assert mapped["weight_used"] - mapped["weight_used_baseline"] == 0


@pytest.mark.asyncio
async def test_reset_and_extra_merge_do_not_overwrite_each_other(spoolman_server):
    client, stock = spoolman_server
    await asyncio.gather(client.reset_spool_usage(42), client.merge_spool_extra(42, {"bambu_color_name": '"Red"'}))
    assert stock["extra"] == {"tag": '"RFID"', "bambu_weight_used_baseline": '"263.0"', "bambu_color_name": '"Red"'}


@pytest.mark.parametrize(
    "baseline,used,remaining,consumed",
    [
        ('"263.0"', 300, 550, 37),
        ("263.0", 300, 550, 37),
        ('"263.0"', 200, 650, 0),
        ('"-20"', 300, 550, 300),
        ('"nan"', 300, 550, 300),
        ('"263.0"', 300, None, 37),
    ],
)
def test_counter_reads_baseline_without_changing_remaining(baseline, used, remaining, consumed):
    spool = {
        "id": 42,
        "filament": {"weight": 1000},
        "used_weight": used,
        "remaining_weight": remaining,
        "extra": {"bambu_weight_used_baseline": baseline},
    }
    mapped = _map_spoolman_spool(spool)
    assert mapped["weight_used"] - mapped["weight_used_baseline"] == consumed
    if remaining is not None:
        assert mapped["label_weight"] - mapped["weight_used"] == remaining


@pytest.mark.asyncio
async def test_reset_http_route_preserves_stock(async_client, monkeypatch, spoolman_server):
    client, stock = spoolman_server

    async def get_client(_):
        return client

    monkeypatch.setattr("backend.app.api.routes.spoolman_inventory._get_client", get_client)
    response = await async_client.post("/api/v1/spoolman/inventory/spools/42/reset-consumed-counter")
    assert response.status_code == 200
    mapped = response.json()
    assert mapped["label_weight"] - mapped["weight_used"] == 587
    assert mapped["weight_used"] - mapped["weight_used_baseline"] == 0
    assert stock["used_weight"] == 263
