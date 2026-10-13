"""Real Orca builder and request ownership regressions from O02 review."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from backend.app.api.routes.orca_cloud import _build_authenticated_service, _load_credentials
from backend.app.core.auth import generate_api_key
from backend.app.models.api_key import APIKey
from backend.app.models.settings import Settings
from backend.app.models.slot_preset import SlotPresetMapping
from backend.app.models.spool import Spool
from backend.app.models.spool_k_profile import SpoolKProfile
from backend.app.models.user import User
from backend.app.services.orca_cloud import OrcaCloudAuthError, OrcaCloudService
from backend.app.services.orca_filament_lookup import lookup_orca_filament_id

ORCA_ID = "34d8f588-860b-5be1-bcbe-c0d46d96324b"


@pytest.mark.asyncio
@pytest.mark.parametrize("shared", [False, True])
@pytest.mark.parametrize("preserve", [False, True])
async def test_real_builder_refresh_failure_preserves_credentials_only_on_opt_out(db_session, shared, preserve):
    token, refresh = "oc_ext_owner", "oc_ext_rt_owner"
    expired = datetime.now(timezone.utc) - timedelta(hours=1)
    if shared:
        user = None
        db_session.add_all(
            [
                Settings(key="orca_cloud_token", value=token),
                Settings(key="orca_cloud_refresh_token", value=refresh),
                Settings(key="orca_cloud_expires_at", value=expired.isoformat()),
            ]
        )
    else:
        user = User(
            username="owner",
            role="admin",
            orca_cloud_token=token,
            orca_cloud_refresh_token=refresh,
            orca_cloud_expires_at=expired,
        )
        db_session.add(user)
    await db_session.commit()
    with (
        patch.object(OrcaCloudService, "refresh", AsyncMock(side_effect=OrcaCloudAuthError("rotation raced"))),
        pytest.raises(HTTPException, match="refresh failed"),
    ):
        await _build_authenticated_service(db_session, user, **({"clear_on_auth_failure": False} if preserve else {}))
    if user is not None:
        await db_session.refresh(user)
    creds = await _load_credentials(db_session, user)
    assert (creds.token, creds.refresh_token) == ((token, refresh) if preserve else (None, None))


@pytest.mark.asyncio
async def test_lookup_reaches_profile_using_real_authenticated_builder(db_session):
    user = User(
        username="owner",
        role="admin",
        orca_cloud_token="oc_ext_owner",
        orca_cloud_refresh_token="oc_ext_rt_owner",
        orca_cloud_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add(user)
    await db_session.commit()
    with patch.object(
        OrcaCloudService,
        "get_profile",
        AsyncMock(return_value={"name": "Mine PLA", "content": {"filament_id": "Pfc74047", "filament_type": ["PLA"]}}),
    ) as profile:
        found = await lookup_orca_filament_id(db_session, user, ORCA_ID)
    assert found.filament_id == "Pfc74047"
    profile.assert_awaited_once_with(ORCA_ID)


@pytest.mark.asyncio
async def test_local_realignment_records_identity_sent_and_retains_ui_preset_reference(
    async_client, db_session, printer_factory
):
    printer = await printer_factory(model="X1C")
    spool = Spool(material="PLA", label_weight=1000, slicer_filament=ORCA_ID, slicer_filament_name="Mine PLA")
    db_session.add(spool)
    await db_session.flush()
    db_session.add(
        SpoolKProfile(
            spool_id=spool.id,
            printer_id=printer.id,
            extruder=0,
            nozzle_diameter="0.4",
            k_value=0.025,
            cali_idx=5,
            setting_id="PFUSedbf16b803ff3e",
        )
    )
    await db_session.commit()
    state = MagicMock(
        nozzle_rack=[],
        kprofile_diameters=set(),
        nozzles=[MagicMock(nozzle_diameter="0.4")],
        ams_extruder_map={"0": 0},
        raw_data={"ams": {"ams": []}},
        kprofiles=[
            MagicMock(
                slot_id=5,
                extruder_id=0,
                nozzle_id="",
                nozzle_diameter="0.4",
                filament_id="P4d64437",
                setting_id="PFUSedbf16b803ff3e",
            )
        ],
    )
    mqtt = MagicMock()
    with patch("backend.app.services.printer_manager.printer_manager") as pm:
        pm.get_client.return_value = mqtt
        pm.get_model.return_value = "X1C"
        pm.get_status.return_value = state
        response = await async_client.post(
            "/api/v1/inventory/assignments",
            json={
                "spool_id": spool.id,
                "printer_id": printer.id,
                "ams_id": 0,
                "tray_id": 2,
            },
        )
    assert response.status_code == 200, response.text
    sent = mqtt.ams_set_filament_setting.call_args.kwargs
    assert (sent["tray_info_idx"], sent["setting_id"]) == ("P4d64437", "PFUSedbf16b803ff3e")
    mapping = (await db_session.execute(select(SlotPresetMapping))).scalar_one()
    # This is the identity compared by slotPresetDescribesTray in every slot UI.
    assert mapping.tray_info_idx == sent["tray_info_idx"]
    assert (mapping.preset_id, mapping.preset_source, mapping.preset_name) == (
        f"orca_{ORCA_ID}",
        "orca_cloud",
        "Mine PLA",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path, auth_enabled",
    [
        ("local", True),
        ("spoolman_assign", True),
        ("configure", True),
        ("spoolman_link", True),
        ("spoolman_link", False),
    ],
)
@pytest.mark.parametrize(
    "scope, header",
    [
        ("allowed", "X-API-Key"),
        ("allowed", "Authorization"),
        ("denied", "X-API-Key"),
        ("ownerless", "X-API-Key"),
        ("unpermitted", "X-API-Key"),
    ],
)
async def test_inventory_routes_use_only_cloud_scoped_key_owner_pairing(
    async_client, db_session, printer_factory, path, auth_enabled, scope, header
):
    owner = User(
        username="owner",
        role="user" if scope == "unpermitted" else "admin",
        orca_cloud_token="oc_ext_owner",
        orca_cloud_refresh_token="oc_ext_rt_owner",
        orca_cloud_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    other = User(username="other", role="admin", orca_cloud_token="oc_ext_other")
    db_session.add_all(
        [
            owner,
            other,
            Settings(key="auth_enabled", value="true" if auth_enabled else "false"),
            Settings(key="orca_cloud_token", value="oc_ext_global"),
            Settings(key="orca_cloud_expires_at", value=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()),
            Settings(key="spoolman_enabled", value="true"),
            Settings(key="spoolman_url", value="http://localhost:7912"),
        ]
    )
    await db_session.flush()
    full_key, key_hash, key_prefix = generate_api_key()
    db_session.add(
        APIKey(
            name="assignment key",
            key_hash=key_hash,
            key_prefix=key_prefix,
            user_id=None if scope == "ownerless" else owner.id,
            can_access_cloud=scope != "denied",
            can_manage_inventory=True,
            can_control_printer=True,
        )
    )
    spool = Spool(material="PLA", label_weight=1000, slicer_filament=ORCA_ID, slicer_filament_name="Mine PLA")
    db_session.add(spool)
    await db_session.commit()
    printer = await printer_factory(model="X1C")
    sm_spool = {
        "id": 10,
        "filament": {
            "id": 1,
            "name": "Mine PLA",
            "material": "PLA",
            "weight": 1000,
            "vendor": {"id": 1, "name": "Mine"},
        },
        "remaining_weight": 800,
        "extra": {"bambu_slicer_filament": json.dumps(ORCA_ID), "bambu_slicer_filament_name": json.dumps("Mine PLA")},
    }
    sm = MagicMock()
    sm.get_spool = AsyncMock(return_value=sm_spool)
    sm.get_spools = AsyncMock(return_value=[])
    sm.health_check = AsyncMock(return_value=True)
    sm.ensure_tag_extra_field = AsyncMock(return_value=True)
    sm.merge_spool_extra = AsyncMock(return_value=sm_spool)
    used_tokens = []

    async def get_profile(service, profile_id):
        assert profile_id == ORCA_ID
        used_tokens.append(service.access_token)
        return {"name": "Mine PLA", "content": {"filament_id": "Pfc74047", "filament_type": ["PLA"]}}

    mqtt = MagicMock()
    with (
        patch.object(OrcaCloudService, "get_profile", get_profile),
        patch("backend.app.services.printer_manager.printer_manager") as local_pm,
        patch("backend.app.api.routes.printers.printer_manager") as configure_pm,
        patch("backend.app.api.routes.spoolman.printer_manager") as link_pm,
        patch("backend.app.api.routes.spoolman_inventory.printer_manager") as assign_pm,
        patch("backend.app.api.routes.spoolman.get_spoolman_client", AsyncMock(return_value=sm)),
        patch("backend.app.api.routes.spoolman_inventory._get_client", AsyncMock(return_value=sm)),
    ):
        for pm in (local_pm, link_pm, assign_pm, configure_pm):
            pm.get_client.return_value = mqtt
            pm.get_model.return_value = "X1C"
            pm.get_status.return_value = None
        headers = {header: f"Bearer {full_key}" if header == "Authorization" else full_key}
        target = {"printer_id": printer.id, "ams_id": 0, "tray_id": 2}
        if path == "configure":
            response = await async_client.post(
                f"/api/v1/printers/{printer.id}/slots/0/2/configure",
                headers=headers,
                params={
                    "orca_profile_id": ORCA_ID,
                    "tray_info_idx": "",
                    "tray_type": "PLA",
                    "tray_sub_brands": "Mine PLA",
                    "tray_color": "FF0000FF",
                    "nozzle_temp_min": 190,
                    "nozzle_temp_max": 230,
                },
            )
        elif path == "local":
            response = await async_client.post(
                "/api/v1/inventory/assignments", json={**target, "spool_id": spool.id}, headers=headers
            )
        elif path == "spoolman_link":
            response = await async_client.post(
                "/api/v1/spoolman/spools/10/link", json={**target, "tray_uuid": "a" * 32}, headers=headers
            )
        else:
            response = await async_client.post(
                "/api/v1/spoolman/inventory/slot-assignments", json={**target, "spoolman_spool_id": 10}, headers=headers
            )
    if path == "spoolman_link" and auth_enabled:
        # FILAMENTS_UPDATE is deliberately administrative; O02 must not open it to keys.
        assert response.status_code == 403, response.text
        mqtt.ams_set_filament_setting.assert_not_called()
        assert used_tokens == []
        return
    assert response.status_code == 200, response.text
    expected = "Pfc74047" if scope == "allowed" else "GFL99"
    assert mqtt.ams_set_filament_setting.call_args.kwargs["tray_info_idx"] == expected
    assert used_tokens == (["oc_ext_owner"] if scope == "allowed" else [])
    if path == "configure":
        assert response.json()["tray_info_idx"] == expected
        return
    mapping = (await db_session.execute(select(SlotPresetMapping))).scalar_one()
    assert (mapping.preset_id, mapping.tray_info_idx) == (f"orca_{ORCA_ID}", expected)
