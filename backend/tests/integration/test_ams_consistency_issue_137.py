"""End-to-end AMS assignment consistency for issue #137."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.models.printer import Printer
from backend.app.models.settings import Settings
from backend.app.models.spool import Spool


def _mqtt():
    client = MagicMock()
    client.ams_set_filament_setting.return_value = True
    client.extrusion_cali_sel.return_value = True
    return client


def _status(ams_data=None):
    status = MagicMock()
    status.raw_data = {"ams": {"ams": ams_data or []}}
    status.nozzles = [MagicMock(nozzle_diameter="0.4")]
    status.ams_extruder_map = None
    status.kprofiles = []
    status.state = "IDLE"
    return status


def _spoolman_spool(material: str, spool_id: int):
    return {
        "id": spool_id,
        "filament": {
            "id": 1,
            "name": "Cool White",
            "material": material,
            "color_hex": "09ff00",
            "weight": 1000,
            "vendor": {"id": 1, "name": "eSUN"},
        },
        "remaining_weight": 800.0,
        "used_weight": 200.0,
        "archived": False,
        "extra": {},
    }


def _spoolman_client(spool):
    client = MagicMock()
    client.base_url = "http://localhost:7912"
    client.health_check = AsyncMock(return_value=True)
    client.ensure_tag_extra_field = AsyncMock(return_value=True)
    client.get_spool = AsyncMock(return_value=spool)
    client.get_spools = AsyncMock(return_value=[spool])
    client.merge_spool_extra = AsyncMock(return_value=spool)
    return client


@pytest.fixture
async def spoolman_settings(db_session):
    db_session.add_all(
        [
            Settings(key="spoolman_enabled", value="true"),
            Settings(key="spoolman_url", value="http://localhost:7912"),
        ]
    )
    await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_internal_assignment_keeps_product_but_sends_protocol_type(async_client, db_session, printer_factory):
    printer = await printer_factory(model="P1S")
    spool = Spool(
        material="PLA+",
        brand="eSUN",
        subtype="Silk",
        rgba="09ff00ff",
        label_weight=1000,
        weight_used=0,
    )
    db_session.add(spool)
    await db_session.commit()
    mqtt = _mqtt()
    live = [{"id": 0, "tray": [{"id": 1, "tray_type": "PLA", "tray_color": "09FF00FF", "state": 11}]}]
    with patch("backend.app.services.printer_manager.printer_manager") as manager:
        manager.get_client.return_value = mqtt
        manager.get_status.return_value = _status(live)
        response = await async_client.post(
            "/api/v1/inventory/assignments",
            json={"spool_id": spool.id, "printer_id": printer.id, "ams_id": 0, "tray_id": 1},
        )

    assert response.status_code == 200
    sent = mqtt.ams_set_filament_setting.call_args.kwargs
    assert sent["tray_type"] == "PLA"
    assert sent["tray_sub_brands"] == "eSUN PLA+ Silk"
    assert sent["tray_info_idx"] == "GFL99"
    assert (sent["nozzle_temp_min"], sent["nozzle_temp_max"]) == (190, 230)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_manual_slot_configuration_reduces_product_type(async_client, printer_factory):
    printer = await printer_factory(model="P1S")
    mqtt = _mqtt()
    with patch("backend.app.api.routes.printers_ams.printer_manager") as manager:
        manager.get_client.return_value = mqtt
        manager.get_status.return_value = _status()
        response = await async_client.post(
            f"/api/v1/printers/{printer.id}/slots/0/1/configure",
            params={
                "tray_info_idx": "",
                "tray_type": "PLA+",
                "tray_sub_brands": "eSUN PLA+",
                "tray_color": "#09ff00ff",
                "nozzle_temp_min": 190,
                "nozzle_temp_max": 230,
            },
        )

    assert response.status_code == 200
    sent = mqtt.ams_set_filament_setting.call_args.kwargs
    assert sent["tray_type"] == "PLA"
    assert sent["tray_info_idx"] == "GFL99"
    assert sent["tray_sub_brands"] == "eSUN PLA+"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_spoolman_inventory_assignment_uses_same_material_contract(async_client, db_session, spoolman_settings):
    printer = Printer(name="Spoolman", serial_number="ISSUE137SM", ip_address="192.168.1.7", access_code="secret")
    db_session.add(printer)
    await db_session.commit()
    spool = _spoolman_spool("PLA+", 1371)
    mqtt = _mqtt()
    with (
        patch("backend.app.api.routes.spoolman_inventory.printer_manager") as manager,
        patch(
            "backend.app.api.routes.spoolman_inventory.get_spoolman_client",
            AsyncMock(return_value=_spoolman_client(spool)),
        ),
    ):
        manager.get_client.return_value = mqtt
        manager.get_status.return_value = _status()
        response = await async_client.post(
            "/api/v1/spoolman/inventory/slot-assignments",
            json={"spoolman_spool_id": 1371, "printer_id": printer.id, "ams_id": 0, "tray_id": 2},
        )

    assert response.status_code == 200
    sent = mqtt.ams_set_filament_setting.call_args.kwargs
    assert (sent["tray_type"], sent["tray_info_idx"]) == ("PLA", "GFL99")
    assert sent["tray_sub_brands"] == "eSUN PLA+ Cool White"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_spoolman_tag_link_uses_same_material_contract(async_client, db_session, spoolman_settings):
    printer = Printer(name="Link", serial_number="ISSUE137LK", ip_address="192.168.1.8", access_code="secret")
    db_session.add(printer)
    await db_session.commit()
    client = _spoolman_client(_spoolman_spool("PLA+", 1372))
    mqtt = _mqtt()
    with (
        patch("backend.app.api.routes.spoolman.get_spoolman_client", AsyncMock(return_value=client)),
        patch("backend.app.api.routes.spoolman.init_spoolman_client", AsyncMock(return_value=client)),
        patch("backend.app.api.routes.spoolman.printer_manager") as manager,
    ):
        manager.get_client.return_value = mqtt
        manager.get_status.return_value = _status()
        response = await async_client.post(
            "/api/v1/spoolman/spools/1372/link",
            json={
                "tray_uuid": "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4",
                "printer_id": printer.id,
                "ams_id": 0,
                "tray_id": 3,
            },
        )

    assert response.status_code == 200
    sent = mqtt.ams_set_filament_setting.call_args.kwargs
    assert (sent["tray_type"], sent["tray_info_idx"]) == ("PLA", "GFL99")
    assert sent["tray_sub_brands"] == "eSUN PLA+ Cool White"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_assignment_survives_normalized_telemetry(async_client, db_session, printer_factory):
    from backend.app.main import on_ams_change
    from backend.app.models.spool_assignment import SpoolAssignment

    printer = await printer_factory(model="P1S")
    spool = Spool(material="PLA+", brand="eSUN", rgba="09ff00ff", label_weight=1000, weight_used=0)
    db_session.add(spool)
    await db_session.commit()
    assignment = SpoolAssignment(
        spool_id=spool.id,
        printer_id=printer.id,
        ams_id=0,
        tray_id=2,
        fingerprint_color="FFFFFFFF",
        fingerprint_type="PETG",
    )
    db_session.add(assignment)
    await db_session.commit()
    assignment_id = assignment.id
    ams = [{"id": 0, "tray": [{"id": 2, "tray_type": "PLA", "tray_color": "09FF00FF", "state": 11}]}]
    with (
        patch("backend.app.main.printer_manager") as manager,
        patch("backend.app.main.mqtt_relay") as relay,
        patch("backend.app.main.ws_manager") as websocket,
    ):
        manager.get_printer.return_value = MagicMock(name="P1S", serial_number="ISSUE137")
        manager.get_status.return_value = _status(ams)
        manager.get_model.return_value = "P1S"
        relay.on_ams_change = AsyncMock()
        websocket.send_printer_status = AsyncMock()
        websocket.broadcast = AsyncMock()
        await on_ams_change(printer.id, ams)

    db_session.expunge_all()
    surviving = await db_session.get(SpoolAssignment, assignment_id)
    assert surviving is not None
    assert surviving.spool_id == spool.id
    assert surviving.fingerprint_type == "PLA"
