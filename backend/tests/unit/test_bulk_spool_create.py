"""Unit tests for bulk spool creation.

Tests:
- SpoolBulkCreate schema validation (quantity bounds)
- Bulk create endpoint creates the requested number of spools
- Bulk create with quantity=1 (single spool)
- Bulk create returns spools with k_profiles loaded
"""

import pytest
from pydantic import ValidationError

from backend.app.schemas.spool import SpoolBulkCreate, SpoolCreate

# ── Schema Validation ──────────────────────────────────────────────────────


class TestSpoolBulkCreateSchema:
    """Tests for the SpoolBulkCreate Pydantic model."""

    def test_default_quantity_is_1(self):
        data = SpoolBulkCreate(spool=SpoolCreate(material="PLA"))
        assert data.quantity == 1

    def test_quantity_within_range(self):
        data = SpoolBulkCreate(spool=SpoolCreate(material="PLA"), quantity=50)
        assert data.quantity == 50

    def test_quantity_max_100(self):
        data = SpoolBulkCreate(spool=SpoolCreate(material="PLA"), quantity=100)
        assert data.quantity == 100

    def test_quantity_zero_rejected(self):
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            SpoolBulkCreate(spool=SpoolCreate(material="PLA"), quantity=0)

    def test_quantity_negative_rejected(self):
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            SpoolBulkCreate(spool=SpoolCreate(material="PLA"), quantity=-1)

    def test_quantity_over_100_rejected(self):
        with pytest.raises(ValidationError, match="less than or equal to 100"):
            SpoolBulkCreate(spool=SpoolCreate(material="PLA"), quantity=101)

    def test_spool_fields_preserved(self):
        data = SpoolBulkCreate(
            spool=SpoolCreate(
                material="PETG",
                brand="Polymaker",
                subtype="Basic",
                color_name="Red",
                rgba="FF0000FF",
                label_weight=750,
                note="Test batch",
            ),
            quantity=5,
        )
        assert data.spool.material == "PETG"
        assert data.spool.brand == "Polymaker"
        assert data.spool.label_weight == 750
        assert data.spool.note == "Test batch"
        assert data.quantity == 5

    def test_spool_without_slicer_filament_is_stock(self):
        """A spool without slicer_filament is a 'stock' spool (computed, not stored)."""
        data = SpoolBulkCreate(
            spool=SpoolCreate(material="PLA", label_weight=1000),
            quantity=3,
        )
        assert data.spool.slicer_filament is None

    def test_spool_with_slicer_filament_is_configured(self):
        data = SpoolBulkCreate(
            spool=SpoolCreate(material="PLA", slicer_filament="GFL99"),
            quantity=2,
        )
        assert data.spool.slicer_filament == "GFL99"

    def test_material_required(self):
        with pytest.raises(ValidationError):
            SpoolBulkCreate(spool=SpoolCreate(material=""), quantity=1)


# ── Endpoint Logic ─────────────────────────────────────────────────────────


class TestBulkCreateEndpoint:
    """Verify the public operation against a real database and numbered SKU."""

    @pytest.mark.asyncio
    async def test_creates_requested_number_of_spools(self, async_client, db_session):
        from sqlalchemy import select

        from backend.app.models.filament_sku_settings import FilamentSkuSettings
        from backend.app.models.spool import Spool

        response = await async_client.post(
            "/api/v1/inventory/spools/bulk",
            json={"spool": {"material": "PLA", "brand": "Test", "label_weight": 1000}, "quantity": 3},
        )
        assert response.status_code == 200, response.text
        spools = response.json()
        assert len(spools) == 3
        assert len({row["id"] for row in spools}) == 3
        assert len(list(await db_session.scalars(select(Spool)))) == 3
        skus = list(await db_session.scalars(select(FilamentSkuSettings)))
        assert len(skus) == 1
        assert {row["material_number"] for row in spools} == {skus[0].material_number}
        assert skus[0].material_number
        assert all(row["k_profiles"] == [] for row in spools)

    @pytest.mark.asyncio
    async def test_single_quantity_creates_one_spool(self, async_client):
        response = await async_client.post(
            "/api/v1/inventory/spools/bulk", json={"spool": {"material": "PETG"}, "quantity": 1},
        )
        assert response.status_code == 200, response.text
        assert len(response.json()) == 1
        assert response.json()[0]["material"] == "PETG"

    @pytest.mark.asyncio
    async def test_all_spools_have_same_fields(self, async_client):
        expected = {"material": "ABS", "brand": "Bambu Lab", "color_name": "Black", "rgba": "000000FF", "label_weight": 750}
        response = await async_client.post(
            "/api/v1/inventory/spools/bulk", json={"spool": expected, "quantity": 3},
        )
        assert response.status_code == 200, response.text
        assert len(response.json()) == 3
        for spool in response.json():
            assert all(spool[field] == value for field, value in expected.items())
