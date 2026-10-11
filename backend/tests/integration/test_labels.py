"""Integration tests for the spool-label routes (#809).

Covers both ``POST /inventory/labels`` (local DB) and ``POST /spoolman/labels``
(Spoolman-backed). The renderer itself has its own unit tests; these tests
focus on auth, request validation, mode gating, and the wiring between route
and renderer.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.spool import Spool


@pytest.fixture
async def spool_factory(db_session: AsyncSession):
    """Factory to create test spools."""
    _counter = [0]

    async def _create_spool(**kwargs):
        _counter[0] += 1
        defaults = {
            "material": "PLA",
            "subtype": "Basic",
            "brand": "Polymaker",
            "color_name": f"Test {_counter[0]}",
            "rgba": "FF8800FF",
            "label_weight": 1000,
            "weight_used": 0,
        }
        defaults.update(kwargs)
        spool = Spool(**defaults)
        db_session.add(spool)
        await db_session.commit()
        await db_session.refresh(spool)
        return spool

    return _create_spool


# ── /inventory/labels (local DB) ─────────────────────────────────────────────


class TestLocalInventoryLabels:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_renders_pdf_for_local_spools(self, async_client: AsyncClient, spool_factory):
        s1 = await spool_factory()
        s2 = await spool_factory(material="PETG", brand="Sunlu")

        resp = await async_client.post(
            "/api/v1/inventory/labels",
            json={"spool_ids": [s1.id, s2.id], "template": "box_62x29"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")
        assert int(resp.headers["content-length"]) == len(resp.content)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_all_four_templates_succeed(self, async_client: AsyncClient, spool_factory):
        s = await spool_factory()
        for template in (
            "ams_holder_74x33",
            "ams_holder_75x55",
            "box_62x29",
            "avery_5160",
            "avery_l7160",
        ):
            resp = await async_client.post(
                "/api/v1/inventory/labels",
                json={"spool_ids": [s.id], "template": template},
            )
            assert resp.status_code == 200, f"{template} returned {resp.status_code}: {resp.text}"
            assert resp.content.startswith(b"%PDF")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_unknown_template_rejected(self, async_client: AsyncClient, spool_factory):
        s = await spool_factory()
        resp = await async_client.post(
            "/api/v1/inventory/labels",
            json={"spool_ids": [s.id], "template": "totally_made_up"},
        )
        # Pydantic Literal validation → 422
        assert resp.status_code in (400, 422)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_empty_spool_ids_rejected(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/v1/inventory/labels",
            json={"spool_ids": [], "template": "box_62x29"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_unknown_spool_id_returns_404(self, async_client: AsyncClient, spool_factory):
        s = await spool_factory()
        resp = await async_client.post(
            "/api/v1/inventory/labels",
            json={"spool_ids": [s.id, 99999], "template": "ams_holder_74x33"},
        )
        assert resp.status_code == 404
        assert "99999" in resp.text

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.parametrize("start_position", [1, 21])
    async def test_preserves_request_order(self, async_client: AsyncClient, spool_factory, start_position):
        """Caller's `spool_ids` order should match the on-screen list — important
        for Avery sheet layouts where users curate the layout via filtering."""
        s1 = await spool_factory()
        s2 = await spool_factory()
        s3 = await spool_factory()

        # Reverse order; assert the route doesn't sort them. We can't peek
        # inside the PDF for assertion, but we can call render_labels directly
        # under the same patches and compare bytes deterministically.
        from backend.app.api.routes import labels as labels_module

        captured = {}

        original = labels_module.render_labels

        def _capture(template, data_list, **kwargs):
            captured["ids"] = [d.spool_id for d in data_list]
            captured["position"] = kwargs["start_position"]
            return original(template, data_list, **kwargs)

        with patch.object(labels_module, "render_labels", side_effect=_capture):
            resp = await async_client.post(
                "/api/v1/inventory/labels",
                json={"spool_ids": [s3.id, s1.id, s2.id], "template": "avery_l7160", "start_position": start_position},
            )
        assert resp.status_code == 200
        assert captured["ids"] == [s3.id, s1.id, s2.id]
        assert captured["position"] == start_position


# ── /spoolman/labels (Spoolman-backed) ───────────────────────────────────────


class TestSpoolmanLabels:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_400_when_spoolman_disabled(self, async_client: AsyncClient):
        # Default state in tests: spoolman_enabled is unset / "false"
        resp = await async_client.post(
            "/api/v1/spoolman/labels",
            json={"spool_ids": [1], "template": "box_62x29"},
        )
        assert resp.status_code == 400
        assert "Spoolman" in resp.text

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_503_when_spoolman_unreachable(self, async_client: AsyncClient, db_session: AsyncSession):
        from backend.app.models.settings import Settings

        db_session.add(Settings(key="spoolman_enabled", value="true"))
        await db_session.commit()

        with patch("backend.app.api.routes.labels.get_spoolman_client", AsyncMock(return_value=None)):
            resp = await async_client.post(
                "/api/v1/spoolman/labels",
                json={"spool_ids": [1], "template": "box_62x29"},
            )
        assert resp.status_code == 503

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.parametrize("start_position", [1, 21])
    async def test_renders_pdf_from_spoolman_data(
        self, async_client: AsyncClient, db_session: AsyncSession, start_position
    ):
        from backend.app.models.settings import Settings

        db_session.add(Settings(key="spoolman_enabled", value="true"))
        await db_session.commit()

        spoolman_spool = {
            "id": 42,
            "filament": {
                "name": "PolyTerra Sapphire Blue",
                "material": "PLA",
                "color_hex": "0033AA",
                "vendor": {"name": "Polymaker"},
            },
            "location": "Shelf 5, slot C",
        }
        mock_client = MagicMock()
        mock_client.is_connected = True
        mock_client.get_spools = AsyncMock(return_value=[spoolman_spool])

        from backend.app.api.routes.labels import render_labels

        with (
            patch("backend.app.api.routes.labels.get_spoolman_client", AsyncMock(return_value=mock_client)),
            patch("backend.app.api.routes.labels.render_labels", wraps=render_labels) as render,
        ):
            resp = await async_client.post(
                "/api/v1/spoolman/labels",
                json={"spool_ids": [42], "template": "avery_l7160", "start_position": start_position},
            )

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")
        assert render.call_args.kwargs["start_position"] == start_position

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_returns_404_when_spool_missing_from_spoolman(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        from backend.app.models.settings import Settings

        db_session.add(Settings(key="spoolman_enabled", value="true"))
        await db_session.commit()

        mock_client = MagicMock()
        mock_client.is_connected = True
        mock_client.get_spools = AsyncMock(return_value=[{"id": 1, "filament": {"name": "X", "material": "PLA"}}])

        with patch(
            "backend.app.api.routes.labels.get_spoolman_client",
            AsyncMock(return_value=mock_client),
        ):
            resp = await async_client.post(
                "/api/v1/spoolman/labels",
                json={"spool_ids": [99], "template": "box_62x29"},
            )
        assert resp.status_code == 404
        assert "99" in resp.text


# ── Validation cross-cutting ─────────────────────────────────────────────────


class TestValidation:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_request_body_size_capped(self, async_client: AsyncClient):
        """spool_ids is bounded to MAX_LABELS_PER_REQUEST so a runaway client
        can't flood the renderer."""
        from backend.app.api.routes.labels import MAX_LABELS_PER_REQUEST

        resp = await async_client.post(
            "/api/v1/inventory/labels",
            json={
                "spool_ids": list(range(1, MAX_LABELS_PER_REQUEST + 2)),
                "template": "box_62x29",
            },
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.integration
async def test_png_exports_one_image_or_ordered_zip(async_client, spool_factory):
    import io
    import zipfile

    from PIL import Image

    first, second = await spool_factory(), await spool_factory()
    response = await async_client.post(
        "/api/v1/inventory/labels",
        json={
            "spool_ids": [second.id, first.id],
            "template": "box_40x30",
            "format": "png",
            "dpi": 203,
            "fields": ["spool_id", "qr", "weight"],
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ["label-1.png", "label-2.png"]
        with Image.open(io.BytesIO(archive.read("label-1.png"))) as image:
            assert image.width == 320
            assert round(image.info["dpi"][0]) == 203
    response = await async_client.post(
        "/api/v1/inventory/labels",
        json={
            "spool_ids": [first.id],
            "template": "box_40x30",
            "format": "png",
            "dpi": 600,
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_sheet_preview_renders_one_cell_and_validates_fields(async_client, spool_factory):
    import io

    from PIL import Image

    spool = await spool_factory()
    response = await async_client.post(
        "/api/v1/inventory/labels/preview",
        json={
            "spool_ids": [spool.id],
            "template": "avery_l7160",
            "fields": [],
            "dpi": 203,
            "start_position": 21,
        },
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    with Image.open(io.BytesIO(response.content)) as image:
        assert image.width in (507, 508)
        assert image.height in (304, 305)
    for override in ({"fields": ["unsafe"]}, {"dpi": 1200}, {"format": "html"}):
        response = await async_client.post(
            "/api/v1/inventory/labels/preview",
            json={
                "spool_ids": [spool.id],
                "template": "box_40x30",
                **override,
            },
        )
        assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["inventory", "spoolman"])
async def test_material_number_labels_use_existing_shared_sku_without_allocating(
    async_client, db_session, spool_factory, backend
):
    from contextlib import closing

    import pypdfium2 as pdfium
    from sqlalchemy import select

    from backend.app.models.filament_sku_settings import FilamentSkuSettings
    from backend.app.models.settings import Settings
    from backend.app.models.warehouse_number_sequence import WarehouseNumberSequence

    sku = FilamentSkuSettings(material="PLA", subtype="Basic", brand="Polymaker", color_name="Orange", material_number="MAT-00444")
    db_session.add(sku)
    await db_session.commit()
    if backend == "inventory":
        spool = await spool_factory(color_name="Orange")
        spool_id = spool.id
        request_context = patch("backend.app.api.routes.labels.get_spoolman_client", new_callable=AsyncMock)
    else:
        spool_id = 77
        remote = {"id": spool_id, "extra": {"bambu_color_name": '\"Orange\"'}, "filament": {
            "material": "PLA", "name": "PLA Basic", "weight": 1000, "color_hex": "FF8800", "vendor": {"name": "Polymaker"},
        }}
        db_session.add(Settings(key="spoolman_enabled", value="true"))
        await db_session.commit()
        client = MagicMock(is_connected=True)
        client.get_spools = AsyncMock(return_value=[remote])
        request_context = patch("backend.app.api.routes.labels.get_spoolman_client", new_callable=AsyncMock, return_value=client)
    before = list((await db_session.scalars(select(WarehouseNumberSequence))).all())
    with request_context:
        response = await async_client.post(f"/api/v1/{backend}/labels", json={
            "spool_ids": [spool_id], "template": "ams_holder_75x55", "fields": ["material_number"],
        })
    assert response.status_code == 200, response.text
    with pdfium.PdfDocument(response.content) as document, closing(document[0]) as page, closing(page.get_textpage()) as text:
        assert "MAT-00444" in text.get_text_range()
    assert list((await db_session.scalars(select(WarehouseNumberSequence))).all()) == before
    assert list((await db_session.scalars(select(FilamentSkuSettings))).all()) == [sku]
