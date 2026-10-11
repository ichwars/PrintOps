"""A K-only status update restores the assigned spool's scoped calibration."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from backend.app.models.settings import Settings
from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spool_k_profile import SpoolKProfile
from backend.app.models.spoolman_k_profile import SpoolmanKProfile
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services.bambu_mqtt import BambuMQTTClient, NozzleInfo


@pytest.fixture
async def recovery(async_client, printer_factory, db_session, monkeypatch):
    from backend.app import main

    printer = await printer_factory(model="X1C")
    spool = Spool(material="PLA", rgba="FF0000FF", label_weight=1000, k_profiles=[])
    db_session.add(spool)
    await db_session.flush()
    assignment = SpoolAssignment(
        printer_id=printer.id,
        spool_id=spool.id,
        ams_id=0,
        tray_id=0,
        fingerprint_type="PLA",
        fingerprint_color="FF0000FF",
    )
    spool.k_profiles.append(
        SpoolKProfile(printer_id=printer.id, extruder=0, nozzle_diameter="0.4", cali_idx=7, k_value=0.025)
    )
    # Other diameters remain stored independently and must not be selected.
    spool.k_profiles.append(
        SpoolKProfile(printer_id=printer.id, extruder=0, nozzle_diameter="0.6", cali_idx=9, k_value=0.06)
    )
    db_session.add(assignment)
    await db_session.commit()
    mqtt = BambuMQTTClient("127.0.0.1", "DRIFT", "test", model="X1C")
    mqtt._client = MagicMock()
    mqtt.state.connected = True
    mqtt.state.state = "IDLE"
    mqtt.state.nozzles = [NozzleInfo("", "0.4"), NozzleInfo()]
    mqtt.state.raw_data = {
        "ams": [
            {
                "id": "0",
                "tray": [
                    {
                        "id": "0",
                        "exists": True,
                        "tray_type": "PLA",
                        "tray_color": "FF0000FF",
                        "tray_info_idx": "GFA00",
                        "cali_idx": 7,
                    }
                ],
            }
        ]
    }
    mqtt._handle_kprofile_response(
        {
            "nozzle_diameter": "0.4",
            "filaments": [{"cali_idx": 7, "extruder_id": 0, "filament_id": "GFL99", "k_value": "0.025"}],
        }
    )
    mqtt._handle_kprofile_response(
        {
            "nozzle_diameter": "0.6",
            "filaments": [{"cali_idx": 9, "extruder_id": 0, "filament_id": "GFL66", "k_value": "0.06"}],
        }
    )
    monkeypatch.setattr(main.printer_manager, "get_status", lambda _: mqtt.state)
    monkeypatch.setattr(main.printer_manager, "get_client", lambda _: mqtt)
    monkeypatch.setattr(main.printer_manager, "get_model", lambda _: printer.model)
    monkeypatch.setattr(main.printer_manager, "get_printer", lambda _: None)
    monkeypatch.setattr(main.ws_manager, "send_printer_status", AsyncMock())
    monkeypatch.setattr(main.ws_manager, "broadcast", AsyncMock())
    main._printer_reconciled_since_connect[printer.id] = True
    main._last_status_broadcast.pop(printer.id, None)
    coroutines = []

    def spawn(coro, name=None):
        coroutines.append(coro)

    monkeypatch.setattr(main, "spawn_background_task", spawn)

    async def push():
        await main.on_printer_status_change(printer.id, mqtt.state)
        while coroutines:
            await coroutines.pop(0)

    yield printer, spool.id, assignment.id, mqtt, push
    for coro in coroutines:
        coro.close()
    main._printer_reconciled_since_connect.pop(printer.id, None)
    main._last_status_broadcast.pop(printer.id, None)


def selections(mqtt):
    return [
        payload["print"]
        for call in mqtt._client.publish.call_args_list
        if (payload := json.loads(call.args[1])).get("print", {}).get("command") == "extrusion_cali_sel"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("spoolman", [False, True])
async def test_k_only_status_drift_recovers_active_ledger(recovery, db_session, spoolman):
    printer, _, _, mqtt, push = recovery
    if spoolman:
        db_session.add_all(
            [
                Settings(key="spoolman_enabled", value="true"),
                SpoolmanSlotAssignment(printer_id=printer.id, ams_id=0, tray_id=0, spoolman_spool_id=42),
                SpoolmanKProfile(
                    printer_id=printer.id,
                    spoolman_spool_id=42,
                    extruder=0,
                    nozzle_diameter="0.4",
                    cali_idx=8,
                    k_value=0.03,
                ),
            ]
        )
        await db_session.commit()
        mqtt._handle_kprofile_response(
            {
                "nozzle_diameter": "0.4",
                "filaments": [{"cali_idx": 8, "extruder_id": 0, "filament_id": "GFL88", "k_value": "0.03"}],
            }
        )
    await push()
    assert selections(mqtt) == []
    # Same material, color, tag and remaining amount; on_ams_change never fires.
    mqtt.state.raw_data["ams"][0]["tray"][0]["cali_idx"] = -1
    await push()
    selected = selections(mqtt)
    assert len(selected) == 1
    assert selected[0]["cali_idx"] == (8 if spoolman else 7)
    assert selected[0]["filament_id"] == ("GFL88" if spoolman else "GFL99")
    assert selected[0]["nozzle_diameter"] == "0.4"
    # A send requests a selection; it does not manufacture a firmware report.
    assert mqtt.state.raw_data["ams"][0]["tray"][0]["cali_idx"] == -1


@pytest.mark.asyncio
async def test_deliberate_default_survives_status_drift(async_client, recovery, db_session):
    printer, _, _, mqtt, push = recovery
    response = await async_client.post(
        f"/api/v1/printers/{printer.id}/slots/0/0/configure",
        params={
            "tray_info_idx": "GFA00",
            "tray_type": "PLA",
            "tray_sub_brands": "PLA",
            "tray_color": "FF0000FF",
            "nozzle_temp_min": 190,
            "nozzle_temp_max": 230,
            "cali_idx": -1,
        },
    )
    assert response.status_code == 200, response.text
    mqtt._client.publish.reset_mock()
    # Firmware may echo the previous real selection once after the Default pick.
    await push()
    mqtt.state.raw_data["ams"][0]["tray"][0]["cali_idx"] = -1
    await push()
    assert selections(mqtt) == []
    # The own AMS callback also reasserts existing RFID profiles. It must
    # respect the same user intent instead of undoing Configure Slot.
    from backend.app import main

    spool = await db_session.get(Spool, recovery[1])
    spool.tray_uuid = "A" * 32
    spool.tag_uid = "1" * 16
    await db_session.commit()
    tray = mqtt.state.raw_data["ams"][0]["tray"][0]
    tray.update(tray_uuid=spool.tray_uuid, tag_uid=spool.tag_uid)
    await main.on_ams_change(printer.id, mqtt.state.raw_data["ams"])
    assert selections(mqtt) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("different_real", None),
        ("malformed", None),
        ("nonfinite", None),
        ("boolean", None),
        ("missing_index", 7),
        ("physical_empty", None),
        ("unknown_diameter", None),
        ("other_diameter", 9),
        ("unknown_model", None),
        ("dual_nozzle", None),
        ("wrong_hotend", None),
        ("wrong_flow", None),
        ("ambiguous_live", None),
        ("deleted_profile", None),
        ("legacy_unreceived", 7),
        ("pending_config", None),
        ("different_color", None),
        ("different_type", None),
        ("different_tag", None),
    ],
)
async def test_drift_uses_safe_reported_context(recovery, db_session, scenario, expected):
    printer, spool_id, assignment_id, mqtt, push = recovery
    tray = mqtt.state.raw_data["ams"][0]["tray"][0]
    tray["cali_idx"] = -1
    if scenario == "different_real":
        tray["cali_idx"] = 5
    elif scenario == "malformed":
        tray["cali_idx"] = "unknown"
    elif scenario == "nonfinite":
        tray["cali_idx"] = float("-inf")
    elif scenario == "boolean":
        tray["cali_idx"] = True
    elif scenario == "missing_index":
        del tray["cali_idx"]
    elif scenario == "physical_empty":
        tray["exists"] = False
    elif scenario in ("unknown_diameter", "other_diameter"):
        mqtt.state.nozzles[0].nozzle_diameter = "" if scenario == "unknown_diameter" else "0.6"
    elif scenario == "unknown_model":
        printer.model = "FUTURE"
    elif scenario == "dual_nozzle":
        printer.model = "H2D"
        mqtt.state.nozzles[1].nozzle_diameter = "0.4"
        mqtt.state.ams_extruder_map = {"0": 1}
    elif scenario in ("wrong_hotend", "wrong_flow", "ambiguous_live", "deleted_profile"):
        entry = {"cali_idx": 7, "extruder_id": 0, "filament_id": "GFL99", "k_value": "0.025"}
        if scenario == "wrong_hotend":
            entry["extruder_id"] = 1
        elif scenario == "wrong_flow":
            entry["nozzle_id"] = "HH00-0.4"
        entries = (
            [] if scenario == "deleted_profile" else [entry, dict(entry)] if scenario == "ambiguous_live" else [entry]
        )
        mqtt._handle_kprofile_response({"nozzle_diameter": "0.4", "filaments": entries})
    elif scenario == "legacy_unreceived":
        mqtt.state.kprofiles = []
        mqtt.state.kprofile_diameters = set()
    elif scenario == "pending_config":
        assignment = await db_session.get(SpoolAssignment, assignment_id)
        assignment.fingerprint_type = ""
        await db_session.commit()
    elif scenario == "different_color":
        tray["tray_color"] = "00FFFFFF"
    elif scenario == "different_type":
        tray["tray_type"] = "PETG"
    elif scenario == "different_tag":
        spool = await db_session.get(Spool, spool_id)
        spool.tag_uid = "1111111111111111"
        tray["tag_uid"] = "2222222222222222"
        await db_session.commit()
    await push()
    assert [command["cali_idx"] for command in selections(mqtt)] == ([] if expected is None else [expected])


@pytest.mark.asyncio
@pytest.mark.parametrize("gcode_state", ["RUNNING", "PAUSE", "PREPARE", "SLICING", "UNKNOWN"])
async def test_busy_printer_is_never_reconfigured(recovery, gcode_state):
    _, _, _, mqtt, push = recovery
    mqtt.state.state = gcode_state
    mqtt.state.raw_data["ams"][0]["tray"][0]["cali_idx"] = -1
    await push()
    assert selections(mqtt) == []


@pytest.mark.asyncio
async def test_reported_flow_selects_only_its_stored_profile(recovery, db_session):
    printer, spool_id, _, mqtt, push = recovery
    for flow, index in [("HS00", 11), ("HH00", 12)]:
        db_session.add(
            SpoolKProfile(
                spool_id=spool_id,
                printer_id=printer.id,
                extruder=0,
                nozzle_diameter="0.4",
                nozzle_type=flow,
                cali_idx=index,
                k_value=0.025,
            )
        )
    await db_session.commit()
    mqtt.state.nozzles[0].nozzle_type = "HS01"
    mqtt.state.raw_data["ams"][0]["tray"][0]["cali_idx"] = -1
    mqtt._handle_kprofile_response(
        {
            "nozzle_diameter": "0.4",
            "filaments": [
                {"cali_idx": index, "extruder_id": 0, "nozzle_id": flow, "filament_id": "GFL99", "k_value": "0.025"}
                for flow, index in [("HS00-0.4", 11), ("HH00-0.4", 12)]
            ],
        }
    )
    await push()
    assert [command["cali_idx"] for command in selections(mqtt)] == [11]


@pytest.mark.asyncio
async def test_retry_budget_resets_after_firmware_confirmation_and_disconnect(recovery, monkeypatch, caplog):
    from backend.app.services import kprofile_drift

    _, _, _, mqtt, push = recovery
    now = [1000.0]
    monkeypatch.setattr(kprofile_drift, "_now", lambda: now[0])
    tray = mqtt.state.raw_data["ams"][0]["tray"][0]
    tray["cali_idx"] = -1
    for _ in range(6):
        await push()
        await push()  # An immediate echo of -1 cannot cause a second request.
        now[0] += 30
    assert len(selections(mqtt)) == 3
    assert caplog.text.count("giving up") == 1
    tray["cali_idx"] = 7
    await push()
    tray["cali_idx"] = -1
    await push()
    assert len(selections(mqtt)) == 4
    mqtt.state.connected = False
    await push()
    mqtt.state.connected = True
    await push()
    assert len(selections(mqtt)) == 5


@pytest.mark.asyncio
async def test_status_recovery_exception_keeps_broadcast_alive(recovery, monkeypatch):
    from backend.app import main
    from backend.app.services import kprofile_drift

    _, _, _, _, push = recovery
    monkeypatch.setattr(kprofile_drift, "needs_check", MagicMock(side_effect=RuntimeError("unavailable")))
    await push()
    main.ws_manager.send_printer_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_malformed_index_does_not_hide_another_lost_slot(recovery, db_session):
    printer, spool_id, _, mqtt, push = recovery
    trays = mqtt.state.raw_data["ams"][0]["tray"]
    trays[0]["cali_idx"] = float("-inf")
    trays.append({**trays[0], "id": 1, "cali_idx": -1})
    db_session.add(
        SpoolAssignment(
            printer_id=printer.id,
            spool_id=spool_id,
            ams_id=0,
            tray_id=1,
            fingerprint_type="PLA",
            fingerprint_color="FF0000FF",
        )
    )
    await db_session.commit()
    await push()
    assert [(command["tray_id"], command["cali_idx"]) for command in selections(mqtt)] == [(1, 7)]


@pytest.mark.asyncio
async def test_restart_waits_for_fresh_nozzle_and_table_then_recovers(recovery, db_session, monkeypatch):
    from backend.app.services import kprofile_drift

    printer, spool_id, _, mqtt, push = recovery
    stored = await db_session.scalar(
        select(SpoolKProfile).where(SpoolKProfile.spool_id == spool_id, SpoolKProfile.nozzle_diameter == "0.4")
    )
    stored.nozzle_type = "HS00"
    await db_session.commit()
    now = [1000.0]
    monkeypatch.setattr(kprofile_drift, "_now", lambda: now[0])
    monkeypatch.setattr(mqtt, "_request_push_all", lambda: None)
    monkeypatch.setattr(mqtt, "_request_version", lambda: None)
    monkeypatch.setattr(mqtt, "_prime_kprofile_request", lambda: None)
    mqtt._request_topic_supported = False
    mqtt.state.connected = False
    await push()
    # Real reconnect invalidates the formerly authoritative calibration cache
    # and reported nozzle dimensions; stale pre-restart evidence is unusable.
    mqtt._on_connect(mqtt._client, None, None, 0)
    mqtt.state.raw_data["ams"][0]["tray"][0]["cali_idx"] = -1
    await push()
    assert selections(mqtt) == []
    mqtt.state.nozzles[0].nozzle_diameter = "0.4"
    mqtt.state.nozzles[0].nozzle_type = "HS01"
    mqtt._handle_kprofile_response(
        {
            "nozzle_diameter": "0.4",
            "filaments": [
                {"cali_idx": 7, "extruder_id": 0, "nozzle_id": "HS00-0.4", "filament_id": "GFL99", "k_value": "0.025"}
            ],
        }
    )
    now[0] += 31
    await push()
    assert [command["cali_idx"] for command in selections(mqtt)] == [7]
