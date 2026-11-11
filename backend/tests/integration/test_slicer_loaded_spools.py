"""Live slot shape and effective credential scope for the slicer dialog."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.group import Group
from backend.app.models.settings import Settings
from backend.app.models.slot_preset import SlotPresetMapping
from backend.app.models.user import User

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

URL = "/api/v1/slicer/loaded-spools"


async def test_connected_trays_only_with_live_presence(async_client, db_session, printer_factory):
    active = await printer_factory(model="BL-P001")
    offline = await printer_factory()
    inactive = await printer_factory(is_active=False)
    db_session.add(
        SlotPresetMapping(
            printer_id=active.id,
            ams_id=255,
            tray_id=1,
            preset_id="local_7",
            preset_name="PETG workshop",
            preset_source="local",
            tray_info_idx="GFG02",
        )
    )
    await db_session.commit()
    raw = {
        "ams": {
            "ams": [
                {"id": "broken", "tray": []},
                {
                    "id": "128",
                    "tray": [
                        {"id": "0", "exists": True, "state": "9"},
                        {"id": 1, "exists": False, "tray_type": "PLA"},
                        {"id": "invalid", "tray_type": "ABS"},
                    ],
                },
            ]
        },
        "vt_tray": [{"id": "invalid"}, {"id": "255", "tray_type": "PETG", "tray_info_idx": "GFG02"}],
    }
    statuses = {
        active.id: SimpleNamespace(connected=True, raw_data=raw),
        offline.id: SimpleNamespace(connected=False, raw_data=raw),
        inactive.id: SimpleNamespace(connected=True, raw_data=raw),
    }
    with patch("backend.app.api.routes.slicer_loaded_spools.printer_manager.get_status", side_effect=statuses.get):
        response = await async_client.get(URL)
    assert response.status_code == 200, response.text
    [printer] = response.json()["printers"]
    assert (printer["id"], printer["model"]) == (active.id, "X1C")
    [unit] = printer["ams"]
    assert unit["id"] == 128
    first, second = unit["trays"]
    assert first["exists"] is True and first["state"] == 9 and first["tray_type"] is None
    assert second["exists"] is False and second["saved_preset"] is None
    [external] = printer["external"]
    assert printer["external_holders"] == 2
    assert (external["ams_id"], external["tray_id"]) == (255, 1)
    assert external["saved_preset"]["preset_id"] == "local_7"


async def test_scope_is_user_and_key_intersection_and_denials_fail_closed(async_client, db_session, printer_factory):
    visible, owner_only, key_only = [await printer_factory() for _ in range(3)]
    db_session.add(Settings(key="auth_enabled", value="true"))
    owner = User(
        username="slicer-operator",
        allowed_printer_ids=[visible.id, owner_only.id],
        groups=[Group(name="Slicing", permissions=[Permission.PRINTERS_READ.value, Permission.LIBRARY_UPLOAD.value])],
    )
    db_session.add(owner)
    await db_session.flush()

    def key(name, **kwargs):
        token, digest, prefix = generate_api_key()
        db_session.add(APIKey(name=name, key_hash=digest, key_prefix=prefix, user_id=owner.id, **kwargs))
        return {"X-API-Key": token}

    allowed = key("allowed", printer_ids=[visible.id, key_only.id])
    denied = key("denied", can_manage_library=False)
    revoked = key("revoked", enabled=False)
    await db_session.commit()
    jwt = {"Authorization": f"Bearer {create_access_token({'sub': owner.username})}"}
    expired_token = create_access_token({"sub": owner.username}, expires_delta=timedelta(seconds=-30))
    expired = {"Authorization": f"Bearer {expired_token}"}
    with patch(
        "backend.app.api.routes.slicer_loaded_spools.printer_manager.get_status",
        return_value=SimpleNamespace(connected=True, raw_data={}),
    ) as read_status:
        for headers, code in [({}, 401), ({"X-API-Key": "wrong"}, 401), (denied, 403), (revoked, 401), (expired, 401)]:
            response = await async_client.get(URL, headers=headers)
            assert response.status_code == code, response.text
        read_status.assert_not_called()
        response = await async_client.get(URL, headers=allowed)
        assert response.status_code == 200, response.text
        assert [p["id"] for p in response.json()["printers"]] == [visible.id]
        read_status.assert_called_once_with(visible.id)
        response = await async_client.get(URL, headers=jwt)
        assert response.status_code == 200, response.text
        assert {p["id"] for p in response.json()["printers"]} == {visible.id, owner_only.id}
