"""Calibration responses cannot overwrite or resolve another nozzle context."""

import pytest

from backend.app.services.bambu_mqtt import BambuMQTTClient, NozzleInfo, PrinterState
from backend.app.services.printer_manager import printer_state_to_dict


def client():
    return BambuMQTTClient(ip_address="127.0.0.1", serial_number="TEST", access_code="test")


def response(diameter, *, flow="", extruder=0, index=7, value="0.02"):
    return {
        "nozzle_diameter": diameter,
        "filaments": [
            {"cali_idx": index, "extruder_id": extruder, "nozzle_id": flow, "filament_id": "GFL99", "k_value": value}
        ],
    }


def state(diameter="0.4", flow=""):
    return PrinterState(
        nozzles=[NozzleInfo(flow, diameter), NozzleInfo()],
        raw_data={"ams": [{"id": "0", "tray": [{"id": "0", "cali_idx": 7}]}]},
    )


def slot_k(mqtt, model="P2S"):
    return printer_state_to_dict(mqtt.state, model=model)["ams"][0]["tray"][0]["k"]


def test_response_for_other_diameter_preserves_first_table():
    mqtt = client()
    mqtt._handle_kprofile_response(response("0.4"))
    mqtt._handle_kprofile_response(response("0.6", value="0.06"))
    mqtt._handle_kprofile_response({"nozzle_diameter": "0.8", "filaments": []})
    assert {(p.nozzle_diameter, p.k_value) for p in mqtt.state.kprofiles} == {("0.4", "0.02"), ("0.6", "0.06")}


def test_empty_answer_clears_only_reported_table():
    mqtt = client()
    mqtt._handle_kprofile_response(response("0.4"))
    mqtt._handle_kprofile_response(response("0.6"))
    mqtt._handle_kprofile_response({"nozzle_diameter": "0.6", "filaments": []})
    assert [p.nozzle_diameter for p in mqtt.state.kprofiles] == ["0.4"]


def test_unknown_empty_answer_does_not_delete_known_table():
    mqtt = client()
    mqtt._handle_kprofile_response(response("0.4"))
    mqtt._handle_kprofile_response({"filaments": []})
    assert len(mqtt.state.kprofiles) == 1


def test_slot_k_value_uses_installed_diameter_not_bare_index():
    mqtt = client()
    mqtt.state = state()
    mqtt._handle_kprofile_response(response("0.4"))
    mqtt._handle_kprofile_response(response("0.6", value="0.06"))
    assert slot_k(mqtt) == 0.02


def test_unknown_installed_diameter_does_not_guess_cached_k():
    mqtt = client()
    mqtt.state = state("")
    mqtt._handle_kprofile_response(response("0.4"))
    assert slot_k(mqtt, "X1C") is None


@pytest.mark.parametrize("flow,want", [("HS01", 0.02), ("HH01", 0.06), ("", None)])
def test_standard_and_high_flow_same_index_are_not_cross_applied(flow, want):
    mqtt = client()
    mqtt.state = state(flow=flow)
    answer = response("0.4", flow="HS00-0.4")
    answer["filaments"] += response("0.4", flow="HH00-0.4", value="0.06")["filaments"]
    mqtt._handle_kprofile_response(answer)
    assert slot_k(mqtt) == want


def test_unmapped_h2_context_does_not_guess_hotend():
    mqtt = client()
    mqtt.state = state()
    mqtt._handle_kprofile_response(response("0.4"))
    assert slot_k(mqtt, "H2D") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["manual", "rfid"])
async def test_assignment_does_not_select_wrong_hotend(path, db_session, monkeypatch):
    from unittest.mock import MagicMock

    from backend.app.api.routes.inventory import apply_spool_to_slot_via_mqtt
    from backend.app.models.printer import Printer
    from backend.app.models.spool import Spool
    from backend.app.models.spool_k_profile import SpoolKProfile
    from backend.app.services.printer_manager import printer_manager
    from backend.app.services.spool_tag_matcher import auto_assign_spool

    printer = Printer(name="P2S", model="P2S", serial_number="TEST149", ip_address="127.0.0.1", access_code="test")
    spool = Spool(material="PLA", slicer_filament="GFL99", k_profiles=[])
    db_session.add_all([printer, spool])
    await db_session.flush()
    # Wrong hotend, even though its diameter and calibration index agree.
    spool.k_profiles.append(
        SpoolKProfile(printer_id=printer.id, extruder=1, nozzle_diameter="0.4", k_value=0.02, cali_idx=7)
    )
    mqtt = client()
    mqtt.state = state()
    wire = MagicMock()
    monkeypatch.setattr(printer_manager, "get_client", lambda pid: wire)
    monkeypatch.setattr(printer_manager, "get_status", lambda pid: mqtt.state)
    monkeypatch.setattr(printer_manager, "get_model", lambda pid: "P2S")
    if path == "manual":
        await apply_spool_to_slot_via_mqtt(
            db=db_session, current_user=None, spool=spool, printer_id=printer.id, ams_id=0, tray_id=0
        )
    else:
        await auto_assign_spool(printer.id, 0, 0, spool, printer_manager, db_session)
    assert wire.extrusion_cali_sel.call_args.kwargs["cali_idx"] == -1


@pytest.mark.asyncio
async def test_rest_status_uses_same_scoped_k_as_websocket(async_client, db_session, monkeypatch):
    from backend.app.models.printer import Printer
    from backend.app.services.printer_manager import printer_manager

    printer = Printer(name="X1C", model="X1C", serial_number="REST149", ip_address="127.0.0.1", access_code="test")
    db_session.add(printer)
    await db_session.commit()
    mqtt = client()
    mqtt.state = state()
    mqtt._handle_kprofile_response(response("0.4"))
    mqtt._handle_kprofile_response(response("0.6", value="0.06"))
    monkeypatch.setattr(printer_manager, "get_status", lambda pid: mqtt.state)
    result = await async_client.get(f"/api/v1/printers/{printer.id}/status")
    assert result.status_code == 200
    assert result.json()["ams"][0]["tray"][0]["k"] == 0.02


@pytest.mark.parametrize("order", [("0.4", "0.6"), ("0.6", "0.4")])
def test_swapping_installed_nozzle_changes_resolved_context_only(order):
    mqtt = client()
    mqtt.state = state()
    for size in order:
        mqtt._handle_kprofile_response(response(size, value="0.02" if size == "0.4" else "0.06"))
    assert slot_k(mqtt) == 0.02
    mqtt.state.nozzles[0].nozzle_diameter = "0.6"
    assert slot_k(mqtt) == 0.06
    mqtt.state.nozzles[0].nozzle_diameter = "0.8"
    assert slot_k(mqtt) is None


def test_same_index_on_other_hotend_does_not_override_single_nozzle():
    mqtt = client()
    mqtt.state = state()
    answer = response("0.4")
    answer["filaments"] += response("0.4", extruder=1, value="0.08")["filaments"]
    mqtt._handle_kprofile_response(answer)
    assert slot_k(mqtt) == 0.02
    assert len(mqtt.state.kprofiles) == 2


def test_duplicate_compatible_index_is_ambiguous():
    mqtt = client()
    mqtt.state = state()
    answer = response("0.4")
    answer["filaments"] += response("0.4", value="0.08")["filaments"]
    mqtt._handle_kprofile_response(answer)
    assert slot_k(mqtt) is None


@pytest.mark.parametrize("model", ["X1C", "P2S", "BL-P001", "N7"])
def test_unique_legacy_assignment_only_before_authoritative_table(model):
    from types import SimpleNamespace

    from backend.app.services.calibration_context import resolve_spool_calibration

    spool_profile = SimpleNamespace(printer_id=1, extruder=None, nozzle_diameter="0.4", nozzle_type=None, cali_idx=7)
    mqtt = client()
    mqtt.state = state()
    assert resolve_spool_calibration([spool_profile], mqtt.state, model, 1, 0, 0)[1] is spool_profile
    mqtt._handle_kprofile_response({"nozzle_diameter": "0.4", "filaments": []})
    assert resolve_spool_calibration([spool_profile], mqtt.state, model, 1, 0, 0)[1] is None


def test_legacy_reference_cannot_fill_unknown_flow_after_swap():
    from types import SimpleNamespace

    from backend.app.services.calibration_context import resolve_spool_calibration

    spool_profile = SimpleNamespace(printer_id=1, extruder=0, nozzle_diameter="0.4", nozzle_type=None, cali_idx=7)
    mqtt = client()
    mqtt.state = state(flow="HH01")
    assert resolve_spool_calibration([spool_profile], mqtt.state, "P2S", 1, 0, 0)[1] is None


def test_reconnect_invalidates_calibration_cache(monkeypatch):
    from unittest.mock import MagicMock

    mqtt = client()
    mqtt._handle_kprofile_response(response("0.4"))
    # Mock transport requests; reconnecting in this test cannot contact hardware.
    monkeypatch.setattr(mqtt, "_request_push_all", lambda: None)
    monkeypatch.setattr(mqtt, "_request_version", lambda: None)
    monkeypatch.setattr(mqtt, "_prime_kprofile_request", lambda: None)
    mqtt._request_topic_supported = False
    mqtt._on_connect(MagicMock(), None, None, 0)
    assert mqtt.state.kprofiles == []
    assert mqtt.state.kprofile_diameters == set()


def test_single_nozzle_hardware_info_does_not_imply_toolchanger():
    mqtt = client()
    mqtt.state = state()
    mqtt.state.nozzle_rack = [{"id": 0, "diameter": "0.4", "type": "hardened_steel"}]
    mqtt._handle_kprofile_response(response("0.4"))
    assert slot_k(mqtt) == 0.02


def test_nozzle_identifier_conflict_cannot_calibrate_envelope_size():
    mqtt = client()
    mqtt.state = state(flow="HH01")
    mqtt._handle_kprofile_response(response("0.4", flow="HH00-0.6"))
    assert slot_k(mqtt) is None


def test_malformed_table_does_not_crash_callback():
    mqtt = client()
    mqtt._handle_kprofile_response({"nozzle_diameter": "0.4", "filaments": None})
    assert mqtt.state.kprofiles == []


def test_reconnect_cannot_resolve_legacy_profile_from_stale_nozzle(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from backend.app.services.calibration_context import resolve_spool_calibration

    mqtt = client()
    mqtt.state = state()
    stored = SimpleNamespace(printer_id=1, extruder=0, nozzle_diameter="0.4", nozzle_type=None, cali_idx=7)
    monkeypatch.setattr(mqtt, "_request_push_all", lambda: None)
    monkeypatch.setattr(mqtt, "_request_version", lambda: None)
    monkeypatch.setattr(mqtt, "_prime_kprofile_request", lambda: None)
    mqtt._request_topic_supported = False
    mqtt._on_connect(MagicMock(), None, None, 0)
    assert resolve_spool_calibration([stored], mqtt.state, "P2S", 1, 0, 0)[1] is None
