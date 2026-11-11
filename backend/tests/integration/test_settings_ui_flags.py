"""Browser UI configuration is available independently of settings administration."""

import pytest

from backend.app.models.settings import Settings
from backend.tests.integration.test_media_tokens import _admin_token, _make_user

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.mark.parametrize("permissions", [["printers:read"], ["archives:read_own", "queue:create"]])
async def test_signed_in_user_reads_safe_ui_flags_without_settings_read(async_client, db_session, permissions):
    admin = await _admin_token(async_client, "_ui_flags")
    token, _ = await _make_user(async_client, admin, username="ui_flags_user", permissions=permissions)
    db_session.add_all(
        [
            Settings(key="default_flow_cali", value="false"),
            Settings(key="time_format", value="24h"),
            Settings(key="queue_shortest_first", value="true"),
            Settings(key="spoolman_enabled", value="true"),
            Settings(key="mqtt_password", value="fixture"),
            Settings(key="gcode_snippets", value='{"P1S":{"start_gcode":"G28"}}'),
        ]
    )
    await db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}
    response = await async_client.get("/api/v1/settings/ui-flags", headers=headers)
    assert response.status_code == 200, response.text
    values = response.json()
    assert values["default_flow_cali"] is False
    assert values["time_format"] == "24h"
    assert values["queue_shortest_first"] is True
    assert values["spoolman_enabled"] is True
    assert values["has_gcode_snippets"] is True
    assert set(values).isdisjoint({"gcode_snippets", "mqtt_password", "ha_token", "spoolman_url", "ldap_bind_password"})
    assert (await async_client.get("/api/v1/settings/", headers=headers)).status_code == 403
    assert (
        await async_client.put("/api/v1/settings/", headers=headers, json={"default_flow_cali": True})
    ).status_code == 403
    assert (await async_client.get("/api/v1/settings/ui-flags")).status_code == 401


async def test_local_instance_gets_defaults_and_no_empty_gcode_flag(async_client, db_session):
    db_session.add(Settings(key="gcode_snippets", value=" {} "))
    await db_session.commit()
    flags = (await async_client.get("/api/v1/settings/ui-flags")).json()
    assert flags["has_gcode_snippets"] is False
    assert "gcode_snippets" not in flags
    preferences = (await async_client.get("/api/v1/settings/ui-preferences")).json()
    assert preferences["time_format"] == flags["time_format"]
    assert "spoolman_enabled" not in preferences
