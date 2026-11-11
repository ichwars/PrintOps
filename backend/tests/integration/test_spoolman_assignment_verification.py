"""A persisted Spoolman binding is distinct from a later printer acceptance."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from backend.app.services.bambu_mqtt import BambuMQTTClient
from backend.tests.integration.test_spoolman_slot_assignment_mqtt import (  # noqa: F401
    mock_spoolman_client,
    slot_settings,
    test_printer,
)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("link", [False, True])
async def test_a_real_mqtt_client_verifies_a_spoolman_assignment_after_the_next_push(
    async_client, slot_settings, test_printer, mock_spoolman_client, link
):
    mqtt = BambuMQTTClient("192.0.2.1", "VERIFY", "dummy", model="P2S")
    mqtt._client = MagicMock()
    mqtt._client.publish.return_value.rc = 0
    mqtt.on_assignment_verified = Mock()
    mock_spoolman_client.ensure_tag_extra_field = AsyncMock(return_value=True)
    with (
        patch("backend.app.api.routes.spoolman_inventory.printer_manager") as inventory_pm,
        patch("backend.app.api.routes.spoolman.printer_manager") as link_pm,
        patch("backend.app.api.routes.spoolman.get_spoolman_client", AsyncMock(return_value=mock_spoolman_client)),
    ):
        for pm in (inventory_pm, link_pm):
            pm.get_client.return_value = mqtt
            pm.get_status.return_value = None
        if link:
            response = await async_client.post(
                "/api/v1/spoolman/spools/10/link",
                json={
                    "spool_tag": "0123456789ABCDEF",
                    "printer_id": test_printer.id,
                    "ams_id": 0,
                    "tray_id": 1,
                },
            )
        else:
            response = await async_client.post(
                "/api/v1/spoolman/inventory/slot-assignments",
                json={
                    "spoolman_spool_id": 10,
                    "printer_id": test_printer.id,
                    "ams_id": 0,
                    "tray_id": 1,
                },
            )
    assert response.status_code == 200, response.text
    pending = mqtt._pending_assignments[(0, 1)]
    mqtt.on_assignment_verified.assert_not_called()
    mqtt._process_message(
        {
            "print": {
                "ams": {
                    "ams": [
                        {
                            "id": 0,
                            "tray": [
                                {
                                    "id": 1,
                                    "tray_info_idx": pending["tray_info_idx"],
                                    "tray_color": "FF0000FF",
                                    "tray_type": "PLA",
                                }
                            ],
                        }
                    ]
                }
            }
        }
    )
    mqtt.on_assignment_verified.assert_called_once()
    assert mqtt.on_assignment_verified.call_args.args[:3] == (0, 1, True)
    assert mqtt._pending_assignments == {}
