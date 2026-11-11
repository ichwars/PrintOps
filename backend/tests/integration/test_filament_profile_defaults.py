from sqlalchemy import select

from backend.app.core.auth import create_access_token
from backend.app.core.permissions import Permission
from backend.app.models.group import Group
from backend.app.models.spool_filament_preset import SpoolFilamentPreset
from backend.app.models.user import User
from backend.tests.integration.test_media_tokens import _admin_token

BASE = "/api/v1/inventory/profile-defaults/"
PRODUCT = {"brand": "Bambu Lab", "material": "PLA", "subtype": "Silk+"}


async def test_general_and_color_defaults_fill_new_spools_without_overwriting_existing_profiles(
    async_client, db_session, printer_factory
):
    printer = await printer_factory()
    general = {
        **PRODUCT,
        "slicer_filament": "GFA06",
        "presets": [{"printer_model": "X1C", "slicer_filament": "Spool preset"}],
        "k_profiles": [{"printer_id": printer.id, "k_value": 0.02, "cali_idx": 1}],
    }
    result = await async_client.put(BASE, json=general)
    assert result.status_code == 200, result.text
    general_id = result.json()["id"]
    color = {
        **PRODUCT,
        "color_name": "Titan Gray",
        "slicer_filament": "Gray preset",
        "k_profiles": [{"printer_id": printer.id, "k_value": 0.03, "cali_idx": 2}],
    }
    result = await async_client.put(BASE, json=color)
    assert result.status_code == 200, result.text

    create = await async_client.post("/api/v1/inventory/spools", json={**PRODUCT, "color_name": " titan gray "})
    assert create.status_code == 200, create.text
    spool = create.json()
    assert spool["slicer_filament"] == "Gray preset"
    assert [row["k_value"] for row in spool["k_profiles"]] == [0.03]
    preset = await db_session.scalar(select(SpoolFilamentPreset).where(SpoolFilamentPreset.spool_id == spool["id"]))
    assert preset.slicer_filament == "Spool preset"

    bulk = await async_client.post(
        "/api/v1/inventory/spools/bulk",
        json={"spool": {**PRODUCT, "color_name": "Silver", "slicer_filament": "User preset"}, "quantity": 2},
    )
    assert bulk.status_code == 200, bulk.text
    assert [(sp["slicer_filament"], sp["k_profiles"][0]["k_value"]) for sp in bulk.json()] == [
        ("User preset", 0.02),
        ("User preset", 0.02),
    ]
    apply = await async_client.post(f"{BASE}{general_id}/apply")
    assert apply.json() == {"applied": 0, "failed": 0}
    assert (await async_client.delete(f"{BASE}{general_id}")).status_code == 200
    get_spool = await async_client.get(f"/api/v1/inventory/spools/{spool['id']}")
    assert get_spool.json()["slicer_filament"] == "Gray preset"


async def test_calibration_defaults_are_scoped_to_allowed_printers(async_client, db_session, printer_factory):
    allowed, hidden = await printer_factory(), await printer_factory()
    token = await _admin_token(async_client, "profile_defaults")
    admin = {"Authorization": f"Bearer {token}"}
    result = await async_client.put(
        BASE, json={**PRODUCT, "k_profiles": [{"printer_id": hidden.id, "k_value": 0.04}]}, headers=admin
    )
    assert result.status_code == 200, result.text
    profile_id = result.json()["id"]
    db_session.add(
        User(
            username="scoped_profiles",
            allowed_printer_ids=[allowed.id],
            groups=[
                Group(
                    name="Profile editor",
                    permissions=[Permission.INVENTORY_READ.value, Permission.INVENTORY_UPDATE.value],
                )
            ],
        )
    )
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': 'scoped_profiles'})}"}
    response = await async_client.get(BASE, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()[0]["k_profiles"] == []
    assert response.json()[0]["can_edit"] is False
    assert (await async_client.put(BASE, headers=headers, json=PRODUCT)).status_code == 404
    assert (await async_client.delete(f"{BASE}{profile_id}", headers=headers)).status_code == 404
    assert (await async_client.get(BASE)).status_code == 401


async def test_spoolman_template_fills_profiles_without_a_local_spool_id(async_client, db_session, printer_factory):
    from unittest.mock import AsyncMock

    from backend.app.models.spoolman_k_profile import SpoolmanKProfile
    from backend.app.services.filament_profile_defaults import apply_product_defaults

    printer = await printer_factory()
    template = {
        **PRODUCT,
        "slicer_filament": "GFA06",
        "k_profiles": [{"printer_id": printer.id, "k_value": 0.02}],
    }
    response = await async_client.put(BASE, json=template)
    assert response.status_code == 200, response.text
    spool = {"id": 21, **PRODUCT, "color_name": "Silver", "slicer_filament": None}
    client = AsyncMock()
    client.merge_spool_extra.return_value = {
        "id": 21,
        "extra": {"bambu_slicer_filament": '"GFA06"'},
        "filament": {"name": "Silk+", "material": "PLA", "vendor": {"name": "Bambu Lab"}},
    }
    assert await apply_product_defaults(db_session, spool, client=client) is True
    await db_session.commit()
    profile = await db_session.scalar(select(SpoolmanKProfile))
    assert (profile.spoolman_spool_id, profile.printer_id, profile.k_value) == (21, printer.id, 0.02)
    client.merge_spool_extra.assert_awaited_once_with(21, {"bambu_slicer_filament": '"GFA06"'})
    assert spool["slicer_filament"] == "GFA06"
