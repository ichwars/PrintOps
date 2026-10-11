"""The real queue dispatch requests recovery before sending the print command."""

import json
from unittest.mock import MagicMock

import pytest

from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spool_k_profile import SpoolKProfile
from backend.app.services.bambu_mqtt import BambuMQTTClient, NozzleInfo
from backend.tests.unit.test_scheduler_cleanup_library import _dispatch_library_item, queue_factory  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mapping,use_ams,expected",
    [([1], True, [8]), ([254], False, [9]), ([-1], True, []), ([1], False, [8]), (None, False, [9])],
)
async def test_dispatch_recovery_uses_final_mapped_trays(
    queue_factory, monkeypatch, caplog, mapping, use_ams, expected
):
    ctx = await queue_factory(cleanup=False)
    mqtt = BambuMQTTClient("127.0.0.1", "DISPATCH-K", "test", model="X1C")
    mqtt._client = MagicMock()
    mqtt.state.connected = True
    mqtt.state.state = "IDLE"
    mqtt.state.nozzles = [NozzleInfo("", "0.4"), NozzleInfo()]
    mqtt.state.raw_data = {
        "ams": [{"id": 0, "tray": [{"id": i, "tray_type": "PLA", "cali_idx": -1} for i in range(2)]}],
        "vt_tray": [{"id": 254, "tray_type": "PLA", "cali_idx": -1}],
    }
    mqtt._handle_kprofile_response(
        {
            "nozzle_diameter": "0.4",
            "filaments": [
                {"cali_idx": index, "extruder_id": 0, "filament_id": "GFA00", "k_value": "0.025"} for index in (7, 8, 9)
            ],
        }
    )
    ctx.status, ctx.mqtt = mqtt.state, mqtt
    monkeypatch.setattr("backend.app.core.database.async_session", ctx.session_maker)
    monkeypatch.setattr("backend.app.services.printer_manager.printer_manager.get_model", lambda _: "X1C")
    async with ctx.session_maker() as db:
        item = await db.get(PrintQueueItem, ctx.queue_item_id)
        item.ams_mapping = json.dumps(mapping)
        item.use_ams = use_ams
        for ams, tray, index in [(0, 0, 7), (0, 1, 8), (255, 0, 9)]:
            spool = Spool(material="PLA", k_profiles=[])
            spool.k_profiles.append(
                SpoolKProfile(
                    printer_id=ctx.printer_id, extruder=0, nozzle_diameter="0.4", cali_idx=index, k_value=0.025
                )
            )
            db.add(spool)
            await db.flush()
            db.add(
                SpoolAssignment(
                    printer_id=ctx.printer_id,
                    spool_id=spool.id,
                    ams_id=ams,
                    tray_id=tray,
                    fingerprint_type="PLA",
                )
            )
        await db.commit()

    def start(*args, **kwargs):
        commands = [json.loads(c.args[1])["print"] for c in mqtt._client.publish.call_args_list]
        assert [c["cali_idx"] for c in commands if c["command"] == "extrusion_cali_sel"] == expected
        return True

    ctx.start_print.side_effect = start
    await _dispatch_library_item(ctx)
    ctx.start_print.assert_called_once()
    if expected:
        assert "recovery before dispatch is unconfirmed" in caplog.text
