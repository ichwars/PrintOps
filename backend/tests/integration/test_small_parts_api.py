from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import event, func, select

from backend.app.api.routes import small_parts as small_parts_route
from backend.app.core.permissions import Permission
from backend.app.models.group import Group
from backend.app.models.procurement import ProcurementOffer, Supplier
from backend.app.models.settings import Settings
from backend.app.models.small_part import SmallPart, SmallPartLedgerEntry
from backend.app.models.user import User


def _csv_upload(text: str):
    return {"file": ("material.csv", text.encode("utf-8"), "text/csv")}


@pytest.mark.asyncio
async def test_missing_material_uses_visible_material_terminology(async_client):
    response = await async_client.get("/api/v1/small-parts/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == {"code": "not_found", "message": "Material fehlt"}


@pytest.mark.asyncio
async def test_material_create_books_opening_stock_atomically(async_client):
    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück"},
    )

    created = await async_client.post(
        "/api/v1/small-parts",
        json={
            "sku": "MAT-1",
            "name": "Magnet",
            "unit_code": "C62",
            "opening_quantity": "25",
            "default_consumption_reason": "Produktion",
            "internal_notes": "Nur trocken lagern",
        },
    )

    assert created.status_code == 201, created.text
    body = created.json()
    ledger = await async_client.get(f"/api/v1/small-parts/{body['id']}/ledger")
    assert body["balance"]["physical"] == "25.000000"
    assert body["default_consumption_reason"] == "Produktion"
    assert body["internal_notes"] == "Nur trocken lagern"
    assert "opening_quantity" not in body
    assert ledger.json()[0]["entry_kind"] == "opening"
    assert ledger.json()[0]["reason"] == "Anfangsbestand"


@pytest.mark.asyncio
async def test_material_create_rolls_back_when_opening_entry_fails(
    async_client,
    db_session,
    monkeypatch,
):
    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück"},
    )

    real_append_ledger_entry = small_parts_route.service.append_ledger_entry

    async def fail_after_opening_entry(*args, **kwargs):
        await real_append_ledger_entry(*args, **kwargs)
        raise RuntimeError("opening ledger failed")

    monkeypatch.setattr(
        small_parts_route.service,
        "append_ledger_entry",
        fail_after_opening_entry,
    )

    failed = await async_client.post(
        "/api/v1/small-parts",
        json={
            "sku": "MAT-ROLLBACK",
            "name": "Rollback material",
            "unit_code": "C62",
            "opening_quantity": "2",
        },
    )

    assert failed.status_code == 503
    stored_count = await db_session.scalar(select(func.count(SmallPart.id)).where(SmallPart.sku == "MAT-ROLLBACK"))
    ledger_count = await db_session.scalar(
        select(func.count(SmallPartLedgerEntry.id)).where(
            SmallPartLedgerEntry.idempotency_key.like("material-opening:%")
        )
    )
    assert stored_count == 0
    assert ledger_count == 0


@pytest.mark.asyncio
async def test_small_part_create_uses_material_number_sequence_when_sku_is_blank(async_client):
    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück", "decimal_places": 0},
    )
    sequence = await async_client.post(
        "/api/v1/inventory/number-sequences",
        json={
            "key": "material",
            "prefix": "MAT",
            "pattern": "{PREFIX}-{#####}",
            "next_value": 1012,
            "reset_policy": "none",
        },
    )
    assert sequence.status_code == 201, sequence.text

    created = await async_client.post(
        "/api/v1/small-parts",
        json={"sku": "", "name": "Sequenced material", "unit_code": "C62"},
    )

    assert created.status_code == 201, created.text
    assert created.json()["sku"] == "MAT-01012"
    listed = await async_client.get("/api/v1/inventory/number-sequences")
    material = next(item for item in listed.json() if item["key"] == "material")
    assert material["next_value"] == 1013


@pytest.mark.asyncio
async def test_small_part_create_skips_existing_generated_material_skus(async_client):
    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück", "decimal_places": 0},
    )
    existing = await async_client.post(
        "/api/v1/small-parts",
        json={"sku": "MAT-00001", "name": "Existing material", "unit_code": "C62"},
    )
    assert existing.status_code == 201, existing.text

    created = await async_client.post(
        "/api/v1/small-parts",
        json={"sku": "", "name": "Sequenced material", "unit_code": "C62"},
    )

    assert created.status_code == 201, created.text
    assert created.json()["sku"] == "MAT-00002"
    listed = await async_client.get("/api/v1/inventory/number-sequences")
    material = next(item for item in listed.json() if item["key"] == "material")
    assert material["next_value"] == 3


@pytest.mark.asyncio
async def test_material_metadata_defaults_and_opening_quantity_is_create_only(async_client):
    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück"},
    )
    created = await async_client.post(
        "/api/v1/small-parts",
        json={"sku": "MAT-DEFAULTS", "name": "Default material", "unit_code": "C62"},
    )

    assert created.status_code == 201, created.text
    assert created.json()["default_consumption_reason"] == "Produktion"
    assert created.json()["internal_notes"] is None
    rejected = await async_client.patch(
        f"/api/v1/small-parts/{created.json()['id']}",
        json={"opening_quantity": "5"},
    )
    assert rejected.status_code == 422


@pytest.mark.asyncio
async def test_material_list_batches_nested_preferred_offers(
    async_client,
    db_session,
    test_engine,
):
    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück"},
    )
    parts = []
    for index in range(2):
        response = await async_client.post(
            "/api/v1/small-parts",
            json={
                "sku": f"MAT-OFFER-{index}",
                "name": f"Offer material {index}",
                "unit_code": "C62",
            },
        )
        assert response.status_code == 201, response.text
        parts.append(response.json())

    supplier = Supplier(name="Batch Supplier", name_key="batch supplier")
    db_session.add(supplier)
    await db_session.flush()
    db_session.add_all(
        [
            ProcurementOffer(
                supplier_id=supplier.id,
                small_part_id=part["id"],
                filament_sku_settings_id=None,
                resource_key=f"material:{part['id']}",
                net_price=Decimal(str(index + 1)),
                gross_price=Decimal(str(index + 1)),
                is_preferred=True,
            )
            for index, part in enumerate(parts)
        ]
    )
    await db_session.commit()

    offer_selects: list[str] = []

    def capture_offer_selects(connection, cursor, statement, parameters, context, executemany):
        normalized = statement.lstrip().lower()
        if normalized.startswith("select") and "procurement_offers" in normalized:
            offer_selects.append(statement)

    event.listen(test_engine.sync_engine, "before_cursor_execute", capture_offer_selects)
    try:
        listed = await async_client.get("/api/v1/small-parts")
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", capture_offer_selects)

    assert listed.status_code == 200, listed.text
    by_sku = {item["sku"]: item for item in listed.json()["items"]}
    assert by_sku["MAT-OFFER-0"]["preferred_offer"]["supplier"]["name"] == "Batch Supplier"
    assert by_sku["MAT-OFFER-1"]["preferred_offer"]["net_price"] == "2.000000"
    assert len(offer_selects) == 1


@pytest.mark.asyncio
async def test_small_part_api_tracks_receipt_search_and_correction(async_client):
    unit = await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück", "decimal_places": 0},
    )
    assert unit.status_code == 201
    category = await async_client.post(
        "/api/v1/small-parts/settings/categories",
        json={"name": "Gewindeeinsätze"},
    )
    assert category.status_code == 201

    created = await async_client.post(
        "/api/v1/small-parts",
        json={
            "sku": "M3-INSERT",
            "name": "M3 Gewindeeinsatz",
            "search_terms": "Messing Insert",
            "unit_code": "C62",
            "category_id": category.json()["id"],
            "location_id": None,
            "minimum_stock": "20",
            "unit_cost": "0.08",
            "is_active": True,
        },
    )
    assert created.status_code == 201
    part_id = created.json()["id"]

    receipt_payload = {
        "entry_kind": "receipt",
        "quantity": "100",
        "reason": "Purchase",
        "idempotency_key": "receipt-M3-20260718",
    }
    receipt = await async_client.post(f"/api/v1/small-parts/{part_id}/ledger", json=receipt_payload)
    duplicate = await async_client.post(f"/api/v1/small-parts/{part_id}/ledger", json=receipt_payload)
    assert receipt.status_code == 201
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == receipt.json()["id"]

    detail = (await async_client.get(f"/api/v1/small-parts/{part_id}")).json()
    assert detail["balance"] == {
        "physical": "100.000000",
        "reserved": "0.000000",
        "available": "100.000000",
        "is_low_stock": False,
    }
    search = await async_client.get("/api/v1/small-parts/search", params={"q": "gewindeeinsätze"})
    assert search.status_code == 200
    assert [(item["sku"], item["available"]) for item in search.json()] == [("M3-INSERT", "100.000000")]

    overdraw = await async_client.post(
        f"/api/v1/small-parts/{part_id}/ledger",
        json={
            "entry_kind": "correction",
            "quantity": "-101",
            "reason": "Inventory count",
            "idempotency_key": "correction-M3-overdraw",
        },
    )
    assert overdraw.status_code == 409
    assert overdraw.json()["detail"]["code"] == "insufficient_stock"


@pytest.mark.asyncio
async def test_inactive_small_parts_are_excluded_from_search_by_default(async_client):
    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück", "decimal_places": 0},
    )
    created = await async_client.post(
        "/api/v1/small-parts",
        json={
            "sku": "OLD-PART",
            "name": "Inaktives Kleinteil",
            "unit_code": "C62",
            "minimum_stock": "0",
            "unit_cost": "0",
            "is_active": False,
        },
    )
    assert created.status_code == 201

    search = await async_client.get("/api/v1/small-parts/search", params={"q": "OLD"})

    assert search.status_code == 200
    assert search.json() == []

    listed = await async_client.get("/api/v1/small-parts")
    assert listed.status_code == 200
    assert [item["sku"] for item in listed.json()["items"]] == ["OLD-PART"]


@pytest.mark.asyncio
async def test_duplicate_sku_update_returns_conflict(async_client):
    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück", "decimal_places": 0},
    )
    first = await async_client.post(
        "/api/v1/small-parts",
        json={"sku": "PART-A", "name": "Teil A", "unit_code": "C62"},
    )
    second = await async_client.post(
        "/api/v1/small-parts",
        json={"sku": "PART-B", "name": "Teil B", "unit_code": "C62"},
    )

    response = await async_client.patch(
        f"/api/v1/small-parts/{second.json()['id']}",
        json={"sku": first.json()["sku"]},
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_small_part_csv_export_and_import_round_trip(async_client):
    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück", "decimal_places": 0},
    )
    await async_client.post(
        "/api/v1/small-parts",
        json={
            "sku": "MAT-CSV-1",
            "name": "CSV Material",
            "unit_code": "C62",
            "opening_quantity": "12",
            "minimum_stock": "5",
            "unit_cost": "0.25",
        },
    )

    export = await async_client.get("/api/v1/small-parts/export")

    assert export.status_code == 200, export.text
    assert export.headers["content-type"].startswith("text/csv")
    assert "Artikelnummer;Bezeichnung" in export.text
    assert "MAT-CSV-1" in export.text

    preview = await async_client.post(
        "/api/v1/small-parts/import?dry_run=true",
        files=_csv_upload("Artikelnummer;Bezeichnung;Einheit;Physisch\nMAT-CSV-2;Neue Schraube;C62;8\n"),
    )

    assert preview.status_code == 200, preview.text
    assert preview.json()["valid_count"] == 1
    assert preview.json()["rows"][0]["action"] == "create"

    imported = await async_client.post(
        "/api/v1/small-parts/import",
        files=_csv_upload("Artikelnummer;Bezeichnung;Einheit;Physisch\nMAT-CSV-2;Neue Schraube;C62;8\n"),
    )

    assert imported.status_code == 200, imported.text
    assert imported.json() == {"created": 1, "updated": 0, "skipped": 0, "errors": 0, "error_rows": []}
    listed = await async_client.get("/api/v1/small-parts", params={"q": "MAT-CSV-2"})
    assert listed.json()["items"][0]["balance"]["physical"] == "8.000000"


@pytest.mark.asyncio
async def test_small_part_csv_import_updates_existing_material(async_client):
    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück", "decimal_places": 0},
    )
    created = await async_client.post(
        "/api/v1/small-parts",
        json={"sku": "MAT-UPD", "name": "Alt", "unit_code": "C62", "minimum_stock": "1"},
    )
    assert created.status_code == 201, created.text

    imported = await async_client.post(
        "/api/v1/small-parts/import",
        files=_csv_upload("Artikelnummer;Bezeichnung;Einheit;Mindestbestand\nMAT-UPD;Neu;C62;9\n"),
    )

    assert imported.status_code == 200, imported.text
    assert imported.json()["updated"] == 1
    detail = await async_client.get(f"/api/v1/small-parts/{created.json()['id']}")
    assert detail.json()["name"] == "Neu"
    assert detail.json()["minimum_stock"] == "9.000000"


@pytest.mark.asyncio
async def test_small_part_csv_import_preserves_internal_notes_and_updates_stock(async_client):
    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück", "decimal_places": 0},
    )
    created = await async_client.post(
        "/api/v1/small-parts",
        json={
            "sku": "MAT-NOTES",
            "name": "Alt",
            "unit_code": "C62",
            "opening_quantity": "3",
            "internal_notes": "Nur intern sichtbar",
        },
    )

    imported = await async_client.post(
        "/api/v1/small-parts/import",
        files=_csv_upload("Artikelnummer;Bezeichnung;Einheit;Physisch\nMAT-NOTES;Neu;C62;11\n"),
    )

    assert imported.status_code == 200, imported.text
    assert imported.json()["updated"] == 1
    detail = await async_client.get(f"/api/v1/small-parts/{created.json()['id']}")
    assert detail.json()["internal_notes"] == "Nur intern sichtbar"
    assert detail.json()["balance"]["physical"] == "11.000000"


@pytest.mark.asyncio
async def test_small_part_csv_import_rolls_back_batch_when_late_row_fails(async_client):
    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück", "decimal_places": 0},
    )
    too_long_name = "X" * 256

    imported = await async_client.post(
        "/api/v1/small-parts/import",
        files=_csv_upload(
            "Artikelnummer;Bezeichnung;Einheit;Physisch\n"
            "MAT-ATOMIC-1;Gültig;C62;5\n"
            f"MAT-ATOMIC-2;{too_long_name};C62;2\n"
        ),
    )

    assert imported.status_code == 200, imported.text
    assert imported.json()["created"] == 0
    assert imported.json()["errors"] == 1
    listed = await async_client.get("/api/v1/small-parts", params={"q": "MAT-ATOMIC"})
    assert listed.json()["total"] == 0


@pytest.mark.asyncio
async def test_small_part_csv_export_escapes_spreadsheet_formulas(async_client):
    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück", "decimal_places": 0},
    )
    await async_client.post(
        "/api/v1/small-parts",
        json={"sku": "MAT-FORMULA", "name": "=SUM(A1:A2)", "unit_code": "C62"},
    )

    export = await async_client.get("/api/v1/small-parts/export")

    assert export.status_code == 200, export.text
    assert "'=SUM(A1:A2)" in export.text


@pytest.mark.asyncio
async def test_small_part_csv_import_update_requires_update_permission(async_client, db_session):
    from backend.app.core.auth import create_access_token, get_password_hash

    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück", "decimal_places": 0},
    )
    created = await async_client.post(
        "/api/v1/small-parts",
        json={"sku": "MAT-PERM", "name": "Alt", "unit_code": "C62"},
    )
    assert created.status_code == 201, created.text

    db_session.add(Settings(key="auth_enabled", value="true"))
    group = Group(name="material-create-only", permissions=[Permission.INVENTORY_CREATE.value])
    user = User(username="material_importer", password_hash=get_password_hash("password"), is_active=True)
    user.groups.append(group)
    db_session.add_all([group, user])
    await db_session.commit()
    token = create_access_token(data={"sub": user.username})

    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        response = await async_client.post(
            "/api/v1/small-parts/import",
            files=_csv_upload("Artikelnummer;Bezeichnung;Einheit\nMAT-PERM;Neu;C62\n"),
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_small_part_labels_route_preserves_request_order(async_client):
    await async_client.post(
        "/api/v1/small-parts/settings/units",
        json={"code": "C62", "label": "Stück", "decimal_places": 0},
    )
    first = await async_client.post(
        "/api/v1/small-parts",
        json={"sku": "MAT-LABEL-1", "name": "Label eins", "unit_code": "C62"},
    )
    second = await async_client.post(
        "/api/v1/small-parts",
        json={"sku": "MAT-LABEL-2", "name": "Label zwei", "unit_code": "C62"},
    )
    captured = {}

    from backend.app.api.routes import labels as labels_module

    original = labels_module.render_labels

    def _capture(template, data_list, **kwargs):
        captured["ids"] = [data.spool_id for data in data_list]
        captured["names"] = [data.name for data in data_list]
        captured["urls"] = [data.deeplink_url for data in data_list]
        return original(template, data_list, **kwargs)

    with patch.object(labels_module, "render_labels", side_effect=_capture):
        response = await async_client.post(
            "/api/v1/small-parts/labels",
            json={"small_part_ids": [second.json()["id"], first.json()["id"]], "template": "box_62x29"},
        )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert captured["ids"] == [second.json()["id"], first.json()["id"]]
    assert captured["names"] == ["Label zwei", "Label eins"]
    assert captured["urls"][0].endswith(f"/warehouse/parts?part={second.json()['id']}")
    assert captured["urls"][1].endswith(f"/warehouse/parts?part={first.json()['id']}")
