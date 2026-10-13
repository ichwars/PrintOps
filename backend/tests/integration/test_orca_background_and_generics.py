"""O02 round2: background identity and full catalog fallback contracts."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from backend.app.api.routes.cloud import _BUILTIN_FILAMENT_NAMES
from backend.app.models.settings import Settings
from backend.app.models.slot_preset import SlotPresetMapping
from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spool_k_profile import SpoolKProfile
from backend.app.models.spoolman_k_profile import SpoolmanKProfile
from backend.app.services.orca_filament_lookup import OrcaFilamentLookup, _orca_generic_filament_id
from backend.app.utils.filament_ids import filament_id_to_setting_id, normalize_slicer_filament

ORCA_ID = "34d8f588-860b-5be1-bcbe-c0d46d96324b"
GENERIC_ROWS = [
    (name.removeprefix("Generic "), fid) for fid, name in _BUILTIN_FILAMENT_NAMES.items() if name.startswith("Generic ")
]


def state_for(tray):
    from backend.app.services.bambu_mqtt import PrinterState

    state = PrinterState()
    state.nozzles = [SimpleNamespace(nozzle_diameter="0.4", nozzle_type="")]
    state.ams_extruder_map = {"0": 0}
    state.raw_data = {"ams": {"ams": [{"id": 0, "tray": [tray]}]}}
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("flow", ["local_rfid", "spoolman_rfid", "insertion_replay"])
@pytest.mark.parametrize("material, reported", [("PLA", "Pfc74047"), ("PEEK", "")])
async def test_auth_enabled_background_preserves_live_orca_identity_without_any_pairing_lookup(
    async_client, db_session, printer_factory, flow, material, reported
):
    printer = await printer_factory(model="X1C")
    spool = Spool(
        material=material, label_weight=1000, slicer_filament=ORCA_ID, slicer_filament_name="Mine PLA", k_profiles=[]
    )
    db_session.add_all(
        [
            spool,
            Settings(key="auth_enabled", value="true"),
            Settings(key="orca_cloud_token", value="oc_ext_someone_else"),
        ]
    )
    await db_session.flush()
    spool.k_profiles.append(
        SpoolKProfile(printer_id=printer.id, extruder=0, nozzle_diameter="0.4", cali_idx=5, k_value=0.02)
    )
    db_session.add(
        SpoolmanKProfile(
            spoolman_spool_id=10, printer_id=printer.id, extruder=0, nozzle_diameter="0.4", cali_idx=5, k_value=0.02
        )
    )
    if flow == "insertion_replay":
        db_session.add(
            SpoolAssignment(
                spool_id=spool.id,
                printer_id=printer.id,
                ams_id=0,
                tray_id=2,
                fingerprint_color=None,
                fingerprint_type=None,
            )
        )
    await db_session.commit()
    tray = {
        "id": 2,
        "tray_type": material,
        "tray_color": "FF0000FF",
        "tray_info_idx": reported,
        "cali_idx": 0,
        "state": 11,
    }
    state, client = state_for(tray), MagicMock()
    sm = {
        "id": 10,
        "filament": {"name": "Mine PLA", "material": material, "weight": 1000},
        "extra": {"bambu_slicer_filament": json.dumps(ORCA_ID)},
    }
    with (
        patch("backend.app.api.routes.orca_cloud._build_authenticated_service", AsyncMock()) as builder,
        patch("backend.app.services.printer_manager.printer_manager") as pm,
        patch("backend.app.main.printer_manager") as main_pm,
        patch("backend.app.main.printer_state_to_dict", return_value={}),
        patch("backend.app.main.mqtt_relay") as relay,
        patch("backend.app.main.ws_manager") as ws,
    ):
        for manager in (pm, main_pm):
            manager.get_status.return_value = state
            manager.get_client.return_value = client
            manager.get_model.return_value = "X1C"
            manager.get_printer.return_value = printer
        relay.on_ams_change = AsyncMock()
        ws.send_printer_status = AsyncMock()
        ws.broadcast = AsyncMock()
        if flow == "local_rfid":
            from backend.app.services.spool_filament_presets import apply_spool_rfid_calibration

            await apply_spool_rfid_calibration(db_session, client, spool, state, "X1C", printer.id, 0, 2, tray)
        elif flow == "spoolman_rfid":
            from backend.app.services.spool_filament_presets import reconcile_spoolman_rfid_slot

            await reconcile_spoolman_rfid_slot(
                db=db_session,
                spoolman_spool=sm,
                printer_id=printer.id,
                ams_id=0,
                tray_id=2,
                tray_info_idx=reported,
                tray_type=material,
                tray_sub_brands="Mine PLA",
            )
        else:
            from backend.app.main import on_ams_change

            await on_ams_change(printer.id, state.raw_data["ams"]["ams"])
        builder.assert_not_awaited()
    if not reported:
        client.ams_set_filament_setting.assert_not_called()
        client.extrusion_cali_sel.assert_not_called()
        return
    assert client.extrusion_cali_sel.call_args.kwargs["filament_id"] == "Pfc74047"
    assert client.extrusion_cali_sel.call_args.kwargs["cali_idx"] == 5
    if flow == "insertion_replay":
        assert client.ams_set_filament_setting.call_args.kwargs["tray_info_idx"] == "Pfc74047"
        mapping = (await db_session.execute(select(SlotPresetMapping))).scalar_one()
        assert mapping.tray_info_idx == "Pfc74047"
    else:
        client.ams_set_filament_setting.assert_not_called()


@pytest.mark.parametrize("material, expected", GENERIC_ROWS)
def test_orca_generic_fallback_covers_every_existing_builtin(material, expected):
    assert _orca_generic_filament_id(material) == expected


@pytest.mark.parametrize("filament, setting", [("GFS99", "GFSS99"), ("GFS98", "GFSS98"), ("GFS97", "GFSS97")])
def test_supported_support_generics_have_unambiguous_setting_identity(filament, setting):
    assert filament_id_to_setting_id(filament) == setting
    assert normalize_slicer_filament(filament) == (filament, setting)
    assert normalize_slicer_filament(setting + "_07") == (filament, setting)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "material, expected",
    [("PPS-CF", "GFT98"), ("PPA-CF", "GFN97"), ("BVOH", "GFS97"), ("PHA", "GFR98"), ("EVA", "GFR99")],
)
@pytest.mark.parametrize("flow", ["configure", "inventory"])
async def test_supported_orca_generic_http_configuration_uses_catalog_identity(
    async_client, db_session, printer_factory, material, expected, flow
):
    printer = await printer_factory()
    spool = Spool(material=material, label_weight=1000, slicer_filament=ORCA_ID, k_profiles=[])
    db_session.add(spool)
    await db_session.commit()
    client = MagicMock()
    with (
        patch("backend.app.api.routes.printers.printer_manager") as configure_pm,
        patch("backend.app.services.printer_manager.printer_manager") as inventory_pm,
        patch(
            "backend.app.api.routes.printers_ams.lookup_orca_filament_id",
            AsyncMock(return_value=OrcaFilamentLookup(reason="no_filament_id", filament_type=material)),
        ),
    ):
        for pm in (configure_pm, inventory_pm):
            pm.get_status.return_value = None
            pm.get_client.return_value = client
        if flow == "configure":
            response = await async_client.post(
                f"/api/v1/printers/{printer.id}/slots/0/2/configure",
                params={
                    "orca_profile_id": ORCA_ID,
                    "tray_info_idx": "",
                    "tray_type": material,
                    "tray_sub_brands": material,
                    "tray_color": "FF0000FF",
                    "nozzle_temp_min": 200,
                    "nozzle_temp_max": 300,
                },
            )
        else:
            response = await async_client.post(
                "/api/v1/inventory/assignments",
                json={"spool_id": spool.id, "printer_id": printer.id, "ams_id": 0, "tray_id": 2},
            )
    assert response.status_code == 200, response.text
    assert client.ams_set_filament_setting.call_args.kwargs["tray_info_idx"] == expected
    if flow == "configure":
        assert response.json()["tray_info_idx"] == expected
        assert response.json()["orca_fallback_reason"] == "no_filament_id"
    else:
        assert response.json()["pending_config"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("flow", ["configure", "inventory"])
async def test_unknown_orca_generic_never_sends_empty_or_borrows_previous_slot(
    async_client, db_session, printer_factory, flow
):
    printer = await printer_factory()
    spool = Spool(material="PEEK", label_weight=1000, slicer_filament=ORCA_ID, k_profiles=[])
    db_session.add(spool)
    await db_session.commit()
    client = MagicMock()
    state = state_for({"id": 2, "tray_type": "PEEK", "tray_info_idx": "P1234567"})
    with (
        patch("backend.app.api.routes.printers.printer_manager") as configure_pm,
        patch("backend.app.services.printer_manager.printer_manager") as inventory_pm,
        patch(
            "backend.app.api.routes.printers_ams.lookup_orca_filament_id",
            AsyncMock(return_value=OrcaFilamentLookup(reason="no_filament_id", filament_type="PEEK")),
        ),
    ):
        for pm in (configure_pm, inventory_pm):
            pm.get_status.return_value = state
            pm.get_client.return_value = client
        if flow == "configure":
            response = await async_client.post(
                f"/api/v1/printers/{printer.id}/slots/0/2/configure",
                params={
                    "orca_profile_id": ORCA_ID,
                    "tray_info_idx": "",
                    "tray_type": "PEEK",
                    "tray_sub_brands": "PEEK",
                    "tray_color": "FF0000FF",
                    "nozzle_temp_min": 350,
                    "nozzle_temp_max": 400,
                },
            )
            assert response.status_code == 422
            assert response.json()["detail"]["code"] == "orca_no_generic_filament_id"
        else:
            response = await async_client.post(
                "/api/v1/inventory/assignments",
                json={"spool_id": spool.id, "printer_id": printer.id, "ams_id": 0, "tray_id": 2},
            )
            assert response.status_code == 200
            assert response.json()["pending_config"] is True
    client.ams_set_filament_setting.assert_not_called()
    client.extrusion_cali_sel.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kprofile_filament_id", ["GFL99", "P4d64437"])
async def test_unknown_orca_generic_rejects_unverified_kprofile_identity_before_side_effects(
    async_client, db_session, printer_factory, kprofile_filament_id
):
    printer = await printer_factory()
    client = MagicMock()
    with (
        patch("backend.app.api.routes.printers.printer_manager") as pm,
        patch(
            "backend.app.api.routes.printers_ams.lookup_orca_filament_id",
            AsyncMock(return_value=OrcaFilamentLookup(reason="no_filament_id", filament_type="PEEK")),
        ),
    ):
        pm.get_client.return_value = client
        response = await async_client.post(
            f"/api/v1/printers/{printer.id}/slots/0/2/configure",
            params={
                "orca_profile_id": ORCA_ID,
                "tray_info_idx": "",
                "tray_type": "PEEK",
                "tray_sub_brands": "PEEK",
                "tray_color": "FF0000FF",
                "nozzle_temp_min": 350,
                "nozzle_temp_max": 400,
                "kprofile_filament_id": kprofile_filament_id,
            },
        )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "orca_no_generic_filament_id"
    pm.get_status.assert_not_called()
    client.ams_set_filament_setting.assert_not_called()
    client.extrusion_cali_sel.assert_not_called()
    client.extrusion_cali_set.assert_not_called()
    client.request_status_update.assert_not_called()
    assert (await db_session.execute(select(SlotPresetMapping))).scalars().all() == []


def test_generic_catalog_keeps_all_29_existing_builtin_entries():
    assert len(GENERIC_ROWS) == 29
    assert len({fid for _, fid in GENERIC_ROWS}) == 29
