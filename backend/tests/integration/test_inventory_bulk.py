"""Bulk inventory endpoint coverage for the batch-edit feature (#1795).

Endpoints under test:
- POST /api/v1/inventory/spools/bulk-update
- POST /api/v1/inventory/spools/bulk-delete
- POST /api/v1/inventory/spools/bulk-archive
- POST /api/v1/inventory/spools/bulk-restore

The Spoolman-mode equivalents live in test_spoolman_inventory_api.py.
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spool_k_profile import SpoolKProfile
from backend.app.models.spool_refill_event import SpoolRefillEvent
from backend.app.models.spool_usage_history import SpoolUsageHistory


@pytest.fixture
async def spool_factory(db_session: AsyncSession):
    async def _create(**kwargs):
        defaults = {
            "material": "PLA",
            "subtype": "Basic",
            "brand": "Bambu",
            "color_name": "Red",
            "rgba": "FF0000FF",
            "label_weight": 1000,
            "core_weight": 250,
            "weight_used": 0,
            "weight_used_baseline": 0,
            "weight_locked": False,
        }
        defaults.update(kwargs)
        spool = Spool(**defaults)
        db_session.add(spool)
        await db_session.commit()
        await db_session.refresh(spool)
        return spool

    return _create


class TestBulkUpdate:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_applies_patch_to_all_listed_spools(self, async_client: AsyncClient, spool_factory, db_session):
        a = await spool_factory(brand="Bambu", note=None)
        b = await spool_factory(brand="Bambu", note=None)
        c = await spool_factory(brand="Bambu", note=None)

        resp = await async_client.post(
            "/api/v1/inventory/spools/bulk-update",
            json={"ids": [a.id, b.id, c.id], "update": {"brand": "Sunlu", "note": "From bulk edit"}},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] == 3
        assert body["not_found"] == []

        for spool in (a, b, c):
            await db_session.refresh(spool)
            assert spool.brand == "Sunlu"
            assert spool.note == "From bulk edit"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_reports_unknown_ids_in_not_found(self, async_client: AsyncClient, spool_factory, db_session):
        real = await spool_factory(brand="Bambu")
        resp = await async_client.post(
            "/api/v1/inventory/spools/bulk-update",
            json={"ids": [real.id, 999_999], "update": {"brand": "Sunlu"}},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] == 1
        assert body["not_found"] == [999_999]

        await db_session.refresh(real)
        assert real.brand == "Sunlu"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_empty_update_rejected(self, async_client: AsyncClient, spool_factory):
        a = await spool_factory()
        resp = await async_client.post(
            "/api/v1/inventory/spools/bulk-update",
            json={"ids": [a.id], "update": {}},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_setting_weight_used_auto_locks(self, async_client: AsyncClient, spool_factory, db_session):
        a = await spool_factory(weight_locked=False, weight_used=0.0)
        resp = await async_client.post(
            "/api/v1/inventory/spools/bulk-update",
            json={"ids": [a.id], "update": {"weight_used": 250.5}},
        )
        assert resp.status_code == 200
        await db_session.refresh(a)
        assert a.weight_used == 250.5
        assert a.weight_locked is True

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_empty_ids_list_rejected(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/v1/inventory/spools/bulk-update",
            json={"ids": [], "update": {"brand": "X"}},
        )
        assert resp.status_code == 422


class TestSpoolRefill:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_refill_reduces_used_weight_and_records_event(
        self, async_client: AsyncClient, spool_factory, db_session
    ):
        spool = await spool_factory(label_weight=1000, weight_used=740)

        resp = await async_client.post(
            f"/api/v1/inventory/spools/{spool.id}/refill",
            json={"added_weight": 500, "note": "cardboard refill"},
        )

        assert resp.status_code == 200, resp.text
        await db_session.refresh(spool)
        assert spool.weight_used == 240

        events = (
            (await db_session.execute(select(SpoolRefillEvent).where(SpoolRefillEvent.spool_id == spool.id)))
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].before_weight_used == 740
        assert events[0].after_weight_used == 240
        assert events[0].added_weight == 500
        assert events[0].note == "cardboard refill"


class TestSpoolMerge:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_merge_reassigns_related_records_and_archives_sources(
        self, async_client: AsyncClient, spool_factory, printer_factory, db_session
    ):
        target = await spool_factory(weight_used=100, weight_locked=False)
        source = await spool_factory(weight_used=420, weight_locked=True, tag_uid="2728C17B")
        printer = await printer_factory()
        usage = SpoolUsageHistory(spool_id=source.id, printer_id=printer.id, print_name="duplicate", weight_used=12.5)
        assignment = SpoolAssignment(spool_id=source.id, printer_id=printer.id, ams_id=0, tray_id=0)
        k_profile = SpoolKProfile(
            spool_id=source.id,
            printer_id=printer.id,
            nozzle_diameter="0.4",
            k_value=0.02,
            name="source kp",
        )
        db_session.add_all([usage, assignment, k_profile])
        await db_session.commit()

        resp = await async_client.post(
            "/api/v1/inventory/spools/merge",
            json={"target_id": target.id, "source_ids": [source.id]},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["merged"] == 1
        assert body["reassigned"]["usage_history"] == 1
        assert body["reassigned"]["assignments"] == 1
        assert body["reassigned"]["k_profiles"] == 1

        await db_session.refresh(target)
        await db_session.refresh(source)
        await db_session.refresh(usage)
        await db_session.refresh(assignment)
        await db_session.refresh(k_profile)
        assert source.archived_at is not None
        assert usage.spool_id == target.id
        assert assignment.spool_id == target.id
        assert k_profile.spool_id == target.id
        assert target.weight_used == 420
        assert target.weight_locked is True
        assert target.tag_uid == "2728C17B"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_merge_rejects_target_as_source(self, async_client: AsyncClient, spool_factory):
        target = await spool_factory()

        resp = await async_client.post(
            "/api/v1/inventory/spools/merge",
            json={"target_id": target.id, "source_ids": [target.id]},
        )

        assert resp.status_code == 400


class TestBulkDelete:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_deletes_listed_spools(self, async_client: AsyncClient, spool_factory, db_session):
        a = await spool_factory()
        b = await spool_factory()
        kept = await spool_factory()

        resp = await async_client.post(
            "/api/v1/inventory/spools/bulk-delete",
            json={"ids": [a.id, b.id]},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted"] == 2
        assert body["not_found"] == []

        remaining = (await db_session.execute(select(Spool.id))).scalars().all()
        assert kept.id in remaining
        assert a.id not in remaining
        assert b.id not in remaining

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_reports_unknown_ids(self, async_client: AsyncClient, spool_factory):
        a = await spool_factory()
        resp = await async_client.post(
            "/api/v1/inventory/spools/bulk-delete",
            json={"ids": [a.id, 999_999]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted"] == 1
        assert body["not_found"] == [999_999]


class TestBulkArchiveRestore:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_bulk_archive_sets_archived_at(self, async_client: AsyncClient, spool_factory, db_session):
        a = await spool_factory()
        b = await spool_factory()

        resp = await async_client.post(
            "/api/v1/inventory/spools/bulk-archive",
            json={"ids": [a.id, b.id]},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["archived"] == 2
        assert body["already_archived"] == []
        assert body["not_found"] == []

        for s in (a, b):
            await db_session.refresh(s)
            assert s.archived_at is not None

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_bulk_archive_skips_already_archived(self, async_client: AsyncClient, spool_factory, db_session):
        active = await spool_factory()
        already = await spool_factory(archived_at=datetime.now(timezone.utc))

        resp = await async_client.post(
            "/api/v1/inventory/spools/bulk-archive",
            json={"ids": [active.id, already.id]},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["archived"] == 1
        assert body["already_archived"] == [already.id]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_bulk_restore_clears_archived_at(self, async_client: AsyncClient, spool_factory, db_session):
        archived = await spool_factory(archived_at=datetime.now(timezone.utc))
        active = await spool_factory(archived_at=None)

        resp = await async_client.post(
            "/api/v1/inventory/spools/bulk-restore",
            json={"ids": [archived.id, active.id]},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["restored"] == 1
        assert body["already_active"] == [active.id]

        await db_session.refresh(archived)
        assert archived.archived_at is None
