"""Model overrides must not replace another model's or the legacy preset."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.models.spool import Spool

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def legacy_spool(db_session):
    spool = Spool(material="PLA", slicer_filament="GFA00", slicer_filament_name="Legacy PLA", k_profiles=[])
    db_session.add(spool)
    await db_session.commit()
    return spool


async def test_existing_spool_has_no_model_overrides(async_client, legacy_spool):
    response = await async_client.get(f"/api/v1/inventory/spools/{legacy_spool.id}/filament-presets")
    assert response.status_code == 200
    assert response.json() == []


async def test_mixed_models_and_explicit_generic_override(async_client, db_session, legacy_spool, printer_factory):
    url = f"/api/v1/inventory/spools/{legacy_spool.id}/filament-presets"
    rows = [
        {"printer_model": "Bambu Lab P2S", "slicer_filament": "GFA02", "slicer_filament_name": "P2S PLA"},
        {"printer_model": "C11", "slicer_filament": None, "slicer_filament_name": None},
    ]
    response = await async_client.put(url, json=rows)
    assert response.status_code == 200
    assert [r["printer_model"] for r in response.json()] == ["P2S", "X1C"]

    from backend.app.services.spool_filament_presets import resolve_spool_preset

    for model, expected in [("P2S", "GFA02"), ("N7", "GFA02"), ("X1C", None), ("P1S", "GFA00"), ("Unknown", "GFA00")]:
        printer = await printer_factory(model=model)
        resolved = await resolve_spool_preset(db_session, legacy_spool, printer.id)
        assert resolved.slicer_filament == expected
    await db_session.refresh(legacy_spool)
    assert legacy_spool.slicer_filament == "GFA00"

    assert (await async_client.put(url, json=[])).status_code == 200
    assert (await async_client.get(url)).json() == []


@pytest.mark.parametrize(
    "rows",
    [
        [{"printer_model": "Unknown", "slicer_filament": "GFA00"}],
        [{"printer_model": "P2S", "nozzle_diameter": "0.4"}],
        [{"printer_model": "P2S"}, {"printer_model": "Bambu Lab P2S"}],
        [{"printer_model": "P2S", "slicer_filament": "x" * 129}],
    ],
)
async def test_reject_invalid_map_without_losing_saved_rows(async_client, legacy_spool, rows):
    url = f"/api/v1/inventory/spools/{legacy_spool.id}/filament-presets"
    assert (await async_client.put(url, json=[{"printer_model": "P2S", "slicer_filament": "GFA02"}])).status_code == 200
    assert (await async_client.put(url, json=rows)).status_code == 422
    assert (await async_client.get(url)).json()[0]["slicer_filament"] == "GFA02"


async def test_missing_spool(async_client):
    url = "/api/v1/inventory/spools/9999/filament-presets"
    assert (await async_client.get(url)).status_code == 404
    assert (await async_client.put(url, json=[])).status_code == 404


async def test_spoolman_map_is_local_and_namespaced(async_client, db_session, legacy_spool, printer_factory):
    client = AsyncMock()
    client.get_spool.return_value = {"id": legacy_spool.id}
    with patch("backend.app.api.routes.spoolman_inventory._get_client", return_value=client):
        url = f"/api/v1/spoolman/inventory/spools/{legacy_spool.id}/filament-presets"
        assert (
            await async_client.put(url, json=[{"printer_model": "X1C", "slicer_filament": "GFA02"}])
        ).status_code == 200
        assert (await async_client.get(url)).json()[0]["slicer_filament"] == "GFA02"
        client.merge_spool_extra.assert_not_called()
    from backend.app.services.spool_filament_presets import resolve_spool_preset

    printer = await printer_factory(model="X1C")
    local = await resolve_spool_preset(db_session, legacy_spool, printer.id)
    remote = await resolve_spool_preset(
        db_session, {"id": legacy_spool.id, "slicer_filament": "GFL99"}, printer.id, spoolman=True
    )
    assert local.slicer_filament == "GFA00"
    assert remote.slicer_filament == "GFA02"


@pytest.mark.parametrize(
    "model, preset, expected", [("P2S", "GFA02", "GFA02"), ("X1C", None, "GFL99"), ("P2S", "99999", "GFL99")]
)
async def test_manual_assignment_uses_persisted_model_and_generic_not_previous_slot(
    async_client, db_session, legacy_spool, printer_factory, model, preset, expected
):
    from backend.app.models.spool_filament_preset import SpoolFilamentPreset

    printer = await printer_factory(model=model)
    db_session.add(SpoolFilamentPreset(spool_id=legacy_spool.id, printer_model=model, slicer_filament=preset))
    await db_session.commit()
    state = SimpleNamespace(
        nozzles=[SimpleNamespace(nozzle_diameter="0.4", nozzle_type="stainless_steel")],
        nozzle_rack=[],
        ams_extruder_map={},
        kprofiles=[],
        kprofile_diameters={"0.4"},
        raw_data={"ams": {"ams": [{"id": 0, "tray": [{"id": 0, "tray_type": "PLA", "tray_info_idx": "GFA00"}]}]}},
    )
    mqtt = MagicMock()
    with patch("backend.app.services.printer_manager.printer_manager") as manager:
        manager.get_client.return_value = mqtt
        manager.get_model.return_value = model
        manager.get_status.return_value = state
        response = await async_client.post(
            "/api/v1/inventory/assignments",
            json={"spool_id": legacy_spool.id, "printer_id": printer.id, "ams_id": 0, "tray_id": 0},
        )
    assert response.status_code == 200
    assert mqtt.ams_set_filament_setting.call_args.kwargs["tray_info_idx"] == expected
    assert mqtt.extrusion_cali_sel.call_args.kwargs["filament_id"] == expected


async def test_rfid_uses_model_preset_without_overwriting_tag_metadata(db_session, legacy_spool, printer_factory):
    from backend.app.models.spool_filament_preset import SpoolFilamentPreset
    from backend.app.services.spool_filament_presets import apply_spool_rfid_calibration

    printer = await printer_factory(model="P2S")
    db_session.add(SpoolFilamentPreset(spool_id=legacy_spool.id, printer_model="P2S", slicer_filament="GFA02"))
    await db_session.commit()
    state = SimpleNamespace(
        nozzles=[SimpleNamespace(nozzle_diameter="0.4", nozzle_type="stainless_steel")],
        nozzle_rack=[],
        ams_extruder_map={},
        kprofiles=[],
        kprofile_diameters={"0.4"},
    )
    mqtt = MagicMock()
    await apply_spool_rfid_calibration(
        db_session, mqtt, legacy_spool, state, "P2S", printer.id, 0, 0, {"tray_info_idx": "GFA00", "cali_idx": 1}
    )
    assert mqtt.extrusion_cali_sel.call_args.kwargs["filament_id"] == "GFA02"
    mqtt.ams_set_filament_setting.assert_not_called()


@pytest.mark.parametrize("mode", ["inventory", "spoolman/inventory"])
@pytest.mark.parametrize(
    "permissions,get_status,put_status",
    [([], 403, 403), (["inventory:read"], 200, 403), (["inventory:update"], 403, 200)],
)
async def test_inventory_domain_permissions(
    async_client, db_session, legacy_spool, mode, permissions, get_status, put_status
):
    from backend.app.core.auth import create_access_token
    from backend.app.models.group import Group
    from backend.app.models.settings import Settings
    from backend.app.models.user import User

    user = User(username="preset-user", groups=[Group(name="preset-role", permissions=permissions)])
    db_session.add_all([user, Settings(key="auth_enabled", value="true")])
    await db_session.commit()
    headers = {"Authorization": "Bearer " + create_access_token({"sub": user.username})}
    client = AsyncMock()
    client.get_spool.return_value = {"id": legacy_spool.id}
    with patch("backend.app.api.routes.spoolman_inventory._get_client", return_value=client):
        url = f"/api/v1/{mode}/spools/{legacy_spool.id}/filament-presets"
        assert (await async_client.get(url, headers=headers)).status_code == get_status
        assert (await async_client.put(url, json=[], headers=headers)).status_code == put_status


async def test_startup_creates_tables_on_existing_database_without_changing_legacy(
    test_engine, db_session, legacy_spool
):
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateTable

    from backend.app.core.database import Base
    from backend.app.models.spool_filament_preset import SpoolFilamentPreset, SpoolmanFilamentPreset

    async with test_engine.begin() as connection:
        for model in (SpoolFilamentPreset, SpoolmanFilamentPreset):
            await connection.run_sync(lambda conn, model=model: model.__table__.drop(conn))
        # This is the same portable create_all step used by init_db, twice for idempotence.
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(Base.metadata.create_all)
    assert await db_session.scalar(select(Spool.slicer_filament).where(Spool.id == legacy_spool.id)) == "GFA00"
    for model in (SpoolFilamentPreset, SpoolmanFilamentPreset):
        for dialect in (postgresql.dialect(), sqlite.dialect()):
            ddl = str(CreateTable(model.__table__).compile(dialect=dialect))
            assert "UNIQUE" in ddl and "printer_model" in ddl
    db_session.add(SpoolFilamentPreset(spool_id=legacy_spool.id, printer_model="X1C", slicer_filament="GFA02"))
    await db_session.commit()
    await db_session.delete(legacy_spool)
    await db_session.commit()
    assert await db_session.scalar(select(SpoolFilamentPreset.id)) is None


@pytest.mark.parametrize("path", ["assign", "link", "rfid"])
async def test_spoolman_manual_tag_and_rfid_use_the_same_model_override(
    async_client, db_session, printer_factory, path
):
    import json

    from backend.app.models.spool_filament_preset import SpoolmanFilamentPreset
    from backend.tests.integration.test_spoolman_slot_assignment_mqtt import SAMPLE_SPOOL

    printer = await printer_factory(model="P2S")
    db_session.add(
        SpoolmanFilamentPreset(
            spoolman_spool_id=10, printer_model="P2S", slicer_filament="GFA02", slicer_filament_name="P2S preset"
        )
    )
    await db_session.commit()
    spool = {**SAMPLE_SPOOL, "extra": {"bambu_slicer_filament": json.dumps("GFA00")}}
    client = AsyncMock()
    client.get_spool.return_value = spool
    client.get_spools.return_value = []
    client.ensure_tag_extra_field.return_value = True
    mqtt = MagicMock()
    tray = {"id": 0, "tray_info_idx": "GFA00", "cali_idx": 7}
    state = SimpleNamespace(
        nozzles=[SimpleNamespace(nozzle_diameter="0.4", nozzle_type="stainless_steel")],
        nozzle_rack=[],
        ams_extruder_map={},
        kprofiles=[],
        kprofile_diameters={"0.4"},
        raw_data={"ams": {"ams": [{"id": 0, "tray": [tray]}]}},
    )
    with (
        patch("backend.app.api.routes.spoolman_inventory._get_client", return_value=client),
        patch("backend.app.api.routes.spoolman.get_spoolman_client", return_value=client),
        patch(
            "backend.app.api.routes.spoolman.get_spoolman_settings",
            return_value={"enabled": True, "url": "http://localhost:7912"},
        ),
        patch("backend.app.services.printer_manager.printer_manager") as manager,
        patch("backend.app.api.routes.spoolman_inventory.printer_manager") as inventory_manager,
        patch("backend.app.api.routes.spoolman.printer_manager") as link_manager,
    ):
        for pm in (manager, inventory_manager, link_manager):
            pm.get_client.return_value = mqtt
            pm.get_model.return_value = "P2S"
            pm.get_status.return_value = state
        if path == "assign":
            response = await async_client.post(
                "/api/v1/spoolman/inventory/slot-assignments",
                json={"spoolman_spool_id": 10, "printer_id": printer.id, "ams_id": 0, "tray_id": 0},
            )
        elif path == "link":
            response = await async_client.post(
                "/api/v1/spoolman/spools/10/link",
                json={
                    "tray_uuid": "ABCDEF1234567890ABCDEF1234567890",
                    "printer_id": printer.id,
                    "ams_id": 0,
                    "tray_id": 0,
                },
            )
        else:
            from backend.app.services.spool_filament_presets import reconcile_spoolman_rfid_slot

            await reconcile_spoolman_rfid_slot(
                db=db_session,
                spoolman_spool=spool,
                printer_id=printer.id,
                ams_id=0,
                tray_id=0,
                tray_info_idx="GFA00",
                tray_sub_brands="PLA",
                tray_type="PLA",
            )
            tray["cali_idx"] = -1
            await reconcile_spoolman_rfid_slot(
                db=db_session,
                spoolman_spool=spool,
                printer_id=printer.id,
                ams_id=0,
                tray_id=0,
                tray_info_idx="GFA00",
                tray_sub_brands="PLA",
                tray_type="PLA",
            )
            mqtt.ams_set_filament_setting.assert_not_called()
            mqtt.extrusion_cali_sel.assert_called_once()
        if path != "rfid":
            assert response.status_code == 200
            assert mqtt.ams_set_filament_setting.call_args.kwargs["tray_info_idx"] == "GFA02"
        assert mqtt.extrusion_cali_sel.call_args.kwargs["filament_id"] == "GFA02"


@pytest.mark.parametrize(
    "raw",
    [None, {}, {"ams": None}, {"ams": {"ams": None}}, {"ams": {"ams": [{"id": 0, "tray": None}]}}, {"vt_tray": None}],
)
async def test_rfid_outages_and_partial_status_do_not_publish(db_session, printer_factory, raw):
    from backend.app.services.spool_filament_presets import reconcile_spoolman_rfid_slot

    printer = await printer_factory(model="P2S")
    mqtt = MagicMock()
    state = SimpleNamespace(raw_data=raw)
    with patch("backend.app.services.printer_manager.printer_manager") as manager:
        manager.get_status.return_value = state
        manager.get_client.return_value = mqtt
        await reconcile_spoolman_rfid_slot(
            db=db_session,
            spoolman_spool={"id": 10, "filament": {"material": "PLA"}},
            printer_id=printer.id,
            ams_id=0,
            tray_id=0,
            tray_info_idx="GFA00",
            tray_sub_brands="PLA",
            tray_type="PLA",
        )
    mqtt.extrusion_cali_sel.assert_not_called()
    mqtt.ams_set_filament_setting.assert_not_called()
