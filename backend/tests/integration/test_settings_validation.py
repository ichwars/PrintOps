"""Settings requests cannot poison subsequent reads of typed settings."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from backend.app.models.settings import Settings


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("method", ["put", "patch"])
@pytest.mark.parametrize(
    "key",
    [
        "auto_archive",
        "ams_humidity_good",
        "default_filament_cost",
        "bed_cooled_threshold",
        "local_backup_enabled",
        "local_backup_retention",
        "obico_enabled",
        "obico_poll_interval",
        "small_parts_default_minimum_stock",
    ],
)
async def test_null_typed_setting_rejects_entire_update(async_client: AsyncClient, db_session, method, key):
    """Removing the null guard would write both the bad scalar and currency."""
    response = await getattr(async_client, method)("/api/v1/settings/", json={key: None, "currency": "EUR"})

    assert response.status_code == 422
    assert key in str(response.json()["detail"])
    stored = (await db_session.execute(select(Settings).where(Settings.key.in_([key, "currency"])))).scalars().all()
    assert stored == []
    assert (await async_client.get("/api/v1/settings/")).json()["currency"] == "USD"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    ("key", "stored", "expected"),
    [
        ("default_filament_cost", "None", 25.0),
        ("default_filament_cost", "NaN", 25.0),
        ("default_filament_cost", "Infinity", 25.0),
        ("ams_humidity_good", "broken", 40),
        ("bed_cooled_threshold", "None", 35.0),
        ("local_backup_retention", "broken", 5),
        ("obico_poll_interval", "broken", 10),
        ("auto_archive", "broken", True),
        ("show_sponsor_prompts", "None", True),
        ("small_parts_default_minimum_stock", "None", "0"),
        ("small_parts_default_minimum_stock", "-1", "0"),
        ("default_printer_id", "broken", None),
    ],
)
async def test_corrupt_typed_row_reads_as_schema_default(async_client: AsyncClient, db_session, key, stored, expected):
    """Unchecked casts or bool string comparisons would fail or return a wrong value."""
    db_session.add(Settings(key=key, value=stored))
    await db_session.commit()

    response = await async_client.get("/api/v1/settings/")

    assert response.status_code == 200
    assert response.json()[key] == expected


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
async def test_nonfinite_number_rejected_before_any_setting_is_written(async_client: AsyncClient, db_session, value):
    response = await async_client.put("/api/v1/settings/", json={"default_filament_cost": value, "currency": "EUR"})

    assert response.status_code == 422
    assert (await db_session.execute(select(Settings))).scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_nullable_choices_and_secret_clearing_remain_supported(async_client: AsyncClient):
    response = await async_client.put(
        "/api/v1/settings/",
        json={"default_printer_id": 42, "open_in_slicer": "orcaslicer", "mqtt_password": "temporary"},
    )
    assert response.status_code == 200

    response = await async_client.put(
        "/api/v1/settings/", json={"default_printer_id": None, "open_in_slicer": None, "mqtt_password": ""}
    )

    assert response.status_code == 200
    assert response.json()["default_printer_id"] is None
    assert response.json()["open_in_slicer"] is None
    assert response.json()["mqtt_password"] == ""


@pytest.mark.asyncio
@pytest.mark.integration
async def test_negative_small_parts_stock_default_is_rejected(async_client: AsyncClient, db_session):
    response = await async_client.put("/api/v1/settings/", json={"small_parts_default_minimum_stock": "-1"})

    assert response.status_code == 422
    assert (await db_session.execute(select(Settings))).scalars().all() == []
