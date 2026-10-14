"""Skip-object HTTP gates and MQTT state checks use inert software transports."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.models.api_key import APIKey
from backend.app.models.drying_schedule import DryingSchedule, DryingScheduleRun
from backend.app.models.group import Group
from backend.app.models.settings import Settings
from backend.app.models.user import User
from backend.app.services.bambu_mqtt import BambuMQTTClient


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,suffix,permission,other",
    [
        ("GET", "objects", "printers:read", "printers:control"),
        ("POST", "skip-objects", "printers:control", "printers:read"),
    ],
)
@pytest.mark.parametrize("granted", [False, True])
async def test_object_endpoints_keep_distinct_read_and_control_permissions(
    async_client, db_session, printer_factory, method, suffix, permission, other, granted
):
    printer = await printer_factory()
    group = Group(name="Object picker", permissions=[permission if granted else other])
    user = User(username="object-picker", groups=[group], allowed_printer_ids=[printer.id])
    db_session.add_all([user, Settings(key="auth_enabled", value="true")])
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}
    await assert_scoped_request(async_client, printer.id, method, suffix, headers, granted)


@pytest.mark.asyncio
@pytest.mark.parametrize("method,suffix", [("GET", "objects"), ("POST", "skip-objects")])
@pytest.mark.parametrize("scope", ["empty", "allowed", "denied", "unrestricted"])
async def test_object_endpoints_enforce_jwt_printer_scope(
    async_client, db_session, printer_factory, method, suffix, scope
):
    printer = await printer_factory()
    other = await printer_factory()
    scopes = {"empty": [], "allowed": [printer.id], "denied": [other.id], "unrestricted": None}
    group = Group(name="Scoped picker", permissions=["printers:read", "printers:control"])
    user = User(username="scoped-picker", groups=[group], allowed_printer_ids=scopes[scope])
    db_session.add_all([user, Settings(key="auth_enabled", value="true")])
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}
    await assert_scoped_request(async_client, printer.id, method, suffix, headers, scope in ("allowed", "unrestricted"))


@pytest.mark.asyncio
@pytest.mark.parametrize("method,suffix", [("GET", "objects"), ("POST", "skip-objects")])
@pytest.mark.parametrize("scope", ["empty", "allowed", "denied", "unrestricted"])
@pytest.mark.parametrize("bearer", [False, True])
async def test_object_endpoints_enforce_api_key_printer_scope(
    async_client, db_session, printer_factory, method, suffix, scope, bearer
):
    printer = await printer_factory()
    other = await printer_factory()
    scopes = {"empty": [], "allowed": [printer.id], "denied": [other.id], "unrestricted": None}
    full_key, key_hash, key_prefix = generate_api_key()
    db_session.add_all(
        [
            APIKey(
                name="object-key",
                key_hash=key_hash,
                key_prefix=key_prefix,
                can_control_printer=True,
                can_read_status=True,
                printer_ids=scopes[scope],
                enabled=True,
            ),
            Settings(key="auth_enabled", value="true"),
        ]
    )
    await db_session.commit()
    headers = {"Authorization": f"Bearer {full_key}"} if bearer else {"X-API-Key": full_key}
    await assert_scoped_request(async_client, printer.id, method, suffix, headers, scope in ("allowed", "unrestricted"))


async def assert_scoped_request(http_client, printer_id, method, suffix, headers, allowed):
    transport = MagicMock()
    transport.state.printable_objects = {100: {"name": "Part A", "x": None, "y": None}}
    transport.state.skipped_objects = []
    transport.state.state = "RUNNING"
    transport.state.printable_objects_bbox_all = None
    transport.skip_objects.return_value = True
    with patch(
        "backend.app.api.routes.printers_controls.printer_manager.get_client", return_value=transport
    ) as get_client:
        response = await http_client.request(
            method,
            f"/api/v1/printers/{printer_id}/print/{suffix}",
            headers=headers,
            **({"json": [100]} if method == "POST" else {}),
        )
    assert response.status_code == (200 if allowed else 403), response.text
    if allowed:
        if method == "POST":
            assert response.json()["skipped_objects"] == [100]
            transport.skip_objects.assert_called_once_with([100])
        else:
            assert response.json()["objects"] == [{"id": 100, "name": "Part A", "x": None, "y": None, "skipped": False}]
    else:
        get_client.assert_not_called()
        transport.skip_objects.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("principal", ["anonymous", "jwt-denied", "key-denied", "bearer-key-denied"])
async def test_skip_objects_checks_scope_before_durable_drying(async_client, db_session, printer_factory, principal):
    printer = await printer_factory(model="P2S")
    schedule = DryingSchedule(
        printer_id=printer.id,
        ams_id=0,
        local_time="06:30",
        timezone="UTC",
        filament="PLA",
        temperature=45,
        duration_hours=4,
        enabled=False,
    )
    db_session.add(schedule)
    await db_session.flush()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(
        DryingScheduleRun(
            schedule_id=schedule.id,
            printer_id=printer.id,
            active_printer_id=printer.id,
            ams_id=0,
            occurrence_day=now.date().isoformat(),
            due_at=now,
            claimed_at=now,
            status="uncertain",
        )
    )
    headers = {}
    if principal == "jwt-denied":
        group = Group(name="Denied picker", permissions=["printers:control"])
        user = User(username="denied-picker", groups=[group], allowed_printer_ids=[])
        db_session.add_all([user, Settings(key="auth_enabled", value="true")])
        headers = {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}
    elif principal != "anonymous":
        full_key, key_hash, key_prefix = generate_api_key()
        db_session.add_all(
            [
                APIKey(
                    name="denied-object-key",
                    key_hash=key_hash,
                    key_prefix=key_prefix,
                    can_control_printer=True,
                    printer_ids=[],
                    enabled=True,
                ),
                Settings(key="auth_enabled", value="true"),
            ]
        )
        headers = (
            {"Authorization": f"Bearer {full_key}"} if principal == "bearer-key-denied" else {"X-API-Key": full_key}
        )
    await db_session.commit()
    with patch("backend.app.api.routes.printers_controls.printer_manager.get_client") as get_client:
        response = await async_client.post(
            f"/api/v1/printers/{printer.id}/print/skip-objects", json=[100], headers=headers
        )
    assert response.status_code == (409 if principal == "anonymous" else 403), response.text
    if principal == "anonymous":
        assert "Scheduled drying owns this printer" in response.json()["detail"]
    get_client.assert_not_called()


@pytest.mark.parametrize(
    "state,connected,expected",
    [
        ("RUNNING", True, True),
        ("PAUSE", True, True),
        ("IDLE", True, False),
        ("RUNNING", False, False),
    ],
)
def test_skip_objects_mqtt_state_gate_uses_fake_transport(state, connected, expected):
    client = BambuMQTTClient("192.0.2.1", "software-fixture", "00000000")
    transport = MagicMock()
    client._client = transport
    client.state.connected = connected
    client.state.state = state
    assert client.skip_objects([100, 200]) is expected
    if expected:
        transport.publish.assert_called_once()
        payload = json.loads(transport.publish.call_args.args[1])
        assert payload["print"]["command"] == "skip_objects"
        assert payload["print"]["obj_list"] == [100, 200]
        assert client.state.skipped_objects == [100, 200]
    else:
        transport.publish.assert_not_called()
        assert client.state.skipped_objects == []
