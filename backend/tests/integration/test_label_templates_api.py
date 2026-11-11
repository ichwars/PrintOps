"""Shared sheet templates, paper geometry and all three label sources."""

import io
import zipfile
from unittest.mock import AsyncMock

import pypdfium2
import pytest
from PIL import Image
from reportlab.lib.pagesizes import letter

from backend.app.api.routes import labels
from backend.app.models.settings import Settings
from backend.app.models.spool import Spool
from backend.tests.integration.test_media_tokens import _admin_token, _make_user

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

TEMPLATES = "/api/v1/label-templates/"
LAYOUT = {
    "page": "letter",
    "label_w_mm": 70,
    "label_h_mm": 35,
    "cols": 2,
    "rows": 2,
    "left_mm": 7,
    "top_mm": 13,
    "col_gap_mm": 3,
    "row_gap_mm": 2,
}


async def test_templates_can_be_replaced_and_have_unique_normalized_names(async_client):
    async def save(name):
        return await async_client.post(TEMPLATES, json={"name": name, "layout": LAYOUT})

    first = await save("  Étiquette 10 ")
    assert first.status_code == 201, first.text
    template = first.json()
    assert template["name"] == "Étiquette 10"
    assert template["layout"] == LAYOUT
    assert (await save("e\N{COMBINING ACUTE ACCENT}TIQUETTE 10")).status_code == 409
    second = await save("Étiquette 2")
    assert second.status_code == 201, second.text
    assert [row["name"] for row in (await async_client.get(TEMPLATES)).json()] == ["Étiquette 2", "Étiquette 10"]

    route = f"{TEMPLATES}{template['id']}"
    updated = await async_client.put(route, json={"name": "Étiquette 10", "layout": {**LAYOUT, "page": "a4"}})
    assert updated.status_code == 200, updated.text
    assert updated.json()["layout"]["page"] == "a4"
    assert (await async_client.delete(route)).status_code == 200
    assert (await async_client.delete(route)).status_code == 404


async def test_template_read_and_update_use_inventory_permissions(async_client):
    admin_jwt = await _admin_token(async_client, "label_templates")
    admin = {"Authorization": f"Bearer {admin_jwt}"}
    created = await async_client.post(TEMPLATES, headers=admin, json={"name": "Shared", "layout": LAYOUT})
    assert created.status_code == 201, created.text
    detail = f"{TEMPLATES}{created.json()['id']}"

    read_jwt, _ = await _make_user(async_client, admin_jwt, username="sheet_reader", permissions=["inventory:read"])
    no_inventory_jwt, _ = await _make_user(
        async_client, admin_jwt, username="sheet_denied", permissions=["printers:read"]
    )
    reader = {"Authorization": f"Bearer {read_jwt}"}
    denied = {"Authorization": f"Bearer {no_inventory_jwt}"}
    assert (await async_client.get(TEMPLATES)).status_code == 401
    assert (await async_client.get(TEMPLATES, headers=denied)).status_code == 403
    assert (await async_client.get(TEMPLATES, headers=reader)).json() == [created.json()]
    body = {"name": "Changed", "layout": LAYOUT}
    assert (await async_client.post(TEMPLATES, json=body, headers=reader)).status_code == 403
    assert (await async_client.put(detail, json=body, headers=reader)).status_code == 403
    assert (await async_client.delete(detail, headers=reader)).status_code == 403


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"template": "avery_l7160", "layout": LAYOUT},
        {"layout": {**LAYOUT, "left_mm": 100}},
        {"layout": {**LAYOUT, "label_w_mm": 39.9}},
        {"layout": {**LAYOUT, "cols": 1.5}},
        {"layout": {**LAYOUT, "row_gap_mm": -0.1}},
        {"layout": LAYOUT, "start_position": 5},
    ],
)
async def test_invalid_custom_sheet_rejected_before_inventory_lookup(async_client, options):
    response = await async_client.post(
        "/api/v1/inventory/labels", json={"spool_ids": [99999], "template": "custom", **options}
    )
    assert response.status_code == 422, response.text


async def test_renders_pdf_and_png_zip_from_the_last_slot_and_previews_one_cell(async_client, db_session):
    spools = [Spool(id=id_, material="PLA", label_weight=1000) for id_ in (9998, 9999)]
    db_session.add_all(spools)
    await db_session.commit()
    body = {"spool_ids": [9998, 9999], "template": "custom", "layout": LAYOUT, "start_position": 4}
    path = "/api/v1/inventory/labels"
    response = await async_client.post(path, json=body)
    assert response.status_code == 200, response.text
    assert "printops-labels-custom.pdf" in response.headers["content-disposition"]
    with pypdfium2.PdfDocument(response.content) as pdf:
        assert len(pdf) == 2
        for index, spool_id in enumerate((9998, 9999)):
            page = pdf[index]
            text = page.get_textpage()
            assert page.get_size() == pytest.approx(letter)
            assert f"#{spool_id}" in text.get_text_bounded()
            text.close()
            page.close()

    pngs = await async_client.post(path, json={**body, "format": "png", "dpi": 203})
    assert pngs.status_code == 200, pngs.text
    with zipfile.ZipFile(io.BytesIO(pngs.content)) as archive:
        assert archive.namelist() == ["label-1.png", "label-2.png"]
        assert archive.read("label-2.png").startswith(b"\x89PNG")

    preview = await async_client.post(
        f"{path}/preview",
        json={
            "spool_ids": [9999],
            "template": "custom",
            "layout": {
                **LAYOUT,
                "label_w_mm": 40,
                "label_h_mm": 20,
            },
            "dpi": 203,
        },
    )
    assert preview.status_code == 200, preview.text
    with Image.open(io.BytesIO(preview.content)) as image:
        assert image.size == (320, 160)


@pytest.mark.parametrize(
    ("resource", "id_key"), [("inventory", "spool_ids"), ("spoolman", "spool_ids"), ("small-parts", "small_part_ids")]
)
async def test_sheet_raster_limit_precedes_item_lookup(async_client, resource, id_key):
    response = await async_client.post(
        f"/api/v1/{resource}/labels",
        json={
            id_key: list(range(1, 27)),
            "template": "custom",
            "layout": {**LAYOUT, "rows": 1, "cols": 1},
            "format": "png",
            "dpi": 600,
        },
    )
    assert response.status_code == 422, response.text
    assert "25 sheet pages" in response.text


async def test_materials_and_spoolman_can_print_on_custom_sheets(async_client, db_session, monkeypatch):
    await async_client.post(
        "/api/v1/small-parts/settings/units", json={"code": "C62", "label": "Piece", "decimal_places": 0}
    )
    part = await async_client.post(
        "/api/v1/small-parts", json={"sku": "F04", "name": "Custom part", "unit_code": "C62"}
    )
    assert part.status_code == 201, part.text
    db_session.add(Settings(key="spoolman_enabled", value="true"))
    await db_session.commit()
    fake_spoolman = AsyncMock()
    fake_spoolman.is_connected = True
    fake_spoolman.get_all_spools.return_value = [{"id": 19, "filament": {"name": "Remote", "material": "PLA"}}]
    monkeypatch.setattr(labels, "get_spoolman_client", AsyncMock(return_value=fake_spoolman))

    for source, selection in (
        ("small-parts", {"small_part_ids": [part.json()["id"]]}),
        ("spoolman", {"spool_ids": [19]}),
    ):
        response = await async_client.post(
            f"/api/v1/{source}/labels", json={**selection, "template": "custom", "layout": LAYOUT}
        )
        assert response.status_code == 200, response.text
        with pypdfium2.PdfDocument(response.content) as pdf:
            page = pdf[0]
            assert page.get_size() == pytest.approx(letter)
            page.close()
