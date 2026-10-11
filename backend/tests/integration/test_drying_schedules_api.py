from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.app.models.drying_schedule import DryingSchedule, DryingScheduleRun

PLAN = {
    "ams_id": 0,
    "local_time": "06:30",
    "timezone": "Europe/Berlin",
    "filament": "PLA",
    "temperature": 45,
    "duration_hours": 4,
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("local_time", "24:00"),
        ("local_time", "6:30"),
        ("timezone", "Mars/Invalid"),
        ("timezone", "../etc/passwd"),
        ("ams_id", -1),
        ("ams_id", 136),
        ("ams_id", True),
        ("temperature", 44),
        ("temperature", 86),
        ("temperature", "45"),
        ("duration_hours", 0),
        ("duration_hours", 25),
        ("duration_hours", 1.5),
        ("filament", "  "),
        ("filament", "PLA\nSTART"),
        ("enabled", "true"),
        ("rotate_tray", 1),
        ("extra", "ignored"),
    ],
)
async def test_invalid_schedule_config_is_rejected(async_client, printer_factory, field, value):
    printer = await printer_factory(model="P2S")
    response = await async_client.post(f"/api/v1/printers/{printer.id}/drying/schedules", json={**PLAN, field: value})
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,connected,expected", [("ams", True, "unsupported_ams"), ("n3f", False, "offline"), ("n3f", True, None)]
)
async def test_enabled_plan_requires_actual_supported_fresh_hardware(
    async_client, printer_factory, kind, connected, expected
):
    from backend.tests.unit.services.test_scheduled_drying import fresh_state

    printer = await printer_factory(model="P2S")
    state = fresh_state(datetime.now(timezone.utc), kind=kind)
    state.connected = connected
    with patch("backend.app.api.routes.drying_schedules.printer_manager.get_status", return_value=state):
        response = await async_client.post(
            f"/api/v1/printers/{printer.id}/drying/schedules", json={**PLAN, "enabled": True}
        )
    assert response.status_code == (409 if expected else 201)
    if expected:
        assert response.json()["detail"]["code"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,suffix", [("GET", ""), ("POST", ""), ("PUT", "/1"), ("DELETE", "/1"), ("POST", "/runs/1/resolve")]
)
async def test_schedule_authentication_is_required(async_client, db_session, method, suffix):
    from backend.app.models.settings import Settings

    db_session.add(Settings(key="auth_enabled", value="true"))
    await db_session.commit()
    response = await async_client.request(method, f"/api/v1/printers/1/drying/schedules{suffix}", json=PLAN)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_viewer_can_read_but_cannot_modify_and_user_printer_scope_is_enforced(
    async_client, db_session, printer_factory
):
    from backend.app.core.auth import create_access_token
    from backend.app.models.group import Group
    from backend.app.models.settings import Settings
    from backend.app.models.user import User

    printer = await printer_factory(model="P2S")
    other = await printer_factory(model="P2S")
    group = Group(name="Drying viewer", permissions=["printers:read"])
    user = User(username="drying-viewer", groups=[group], allowed_printer_ids=[printer.id])
    db_session.add_all([user, Settings(key="auth_enabled", value="true")])
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}
    path = f"/api/v1/printers/{printer.id}/drying/schedules"
    assert (await async_client.get(path, headers=headers)).status_code == 200
    assert (await async_client.post(path, json=PLAN, headers=headers)).status_code == 403
    assert (await async_client.get(f"/api/v1/printers/{other.id}/drying/schedules", headers=headers)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("bearer", [False, True])
async def test_scoped_api_key_cannot_read_or_schedule_another_printer(
    async_client, db_session, printer_factory, bearer
):
    from backend.app.core.auth import generate_api_key
    from backend.app.models.api_key import APIKey
    from backend.app.models.settings import Settings

    printer = await printer_factory(model="P2S")
    full, hashed, prefix = generate_api_key()
    db_session.add_all(
        [
            Settings(key="auth_enabled", value="true"),
            APIKey(
                name="scoped",
                key_hash=hashed,
                key_prefix=prefix,
                can_control_printer=True,
                can_read_status=True,
                printer_ids=[printer.id + 1],
            ),
        ]
    )
    await db_session.commit()
    headers = {"Authorization": f"Bearer {full}"} if bearer else {"X-API-Key": full}
    path = f"/api/v1/printers/{printer.id}/drying/schedules"
    for method, suffix in [("GET", ""), ("POST", ""), ("PUT", "/1"), ("DELETE", "/1"), ("POST", "/runs/1/resolve")]:
        assert (await async_client.request(method, path + suffix, json=PLAN, headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_resolve_requires_observation_after_publication_and_sends_no_command(
    async_client, printer_factory, db_session
):
    from datetime import timedelta

    from backend.app.services.drying_telemetry import DryingObservation
    from backend.tests.unit.services.test_scheduled_drying import fresh_state

    printer = await printer_factory(model="P2S")
    plan = DryingSchedule(printer_id=printer.id, **PLAN)
    db_session.add(plan)
    await db_session.flush()
    now = datetime.now(timezone.utc)
    run = DryingScheduleRun(
        schedule_id=plan.id,
        printer_id=printer.id,
        active_printer_id=printer.id,
        ams_id=0,
        occurrence_day=now.date().isoformat(),
        due_at=now.replace(tzinfo=None),
        claimed_at=(now - timedelta(seconds=20)).replace(tzinfo=None),
        publication_at=(now - timedelta(seconds=10)).replace(tzinfo=None),
        status="uncertain",
    )
    db_session.add(run)
    await db_session.commit()
    state = fresh_state(now)
    path = f"/api/v1/printers/{printer.id}/drying/schedules/runs/{run.id}/resolve"
    with patch("backend.app.api.routes.drying_schedules.printer_manager") as manager:
        manager.get_status.return_value = state
        state.drying_telemetry.units[0] = DryingObservation(
            0, (now - timedelta(seconds=15)).timestamp(), "n3f", True, False
        )
        assert (await async_client.post(path)).status_code == 409
        state.drying_telemetry.units[0] = DryingObservation(0, now.timestamp(), "n3f", True, False)
        result = await async_client.post(path)
        assert result.status_code == 200
        assert result.json()["status"] == "resolved"
        assert result.json()["active_printer_id"] is None
        manager.send_drying_command.assert_not_called()


@pytest.mark.asyncio
async def test_new_daily_plan_is_persisted_disabled_by_default(async_client, printer_factory):
    printer = await printer_factory(model="P2S")
    response = await async_client.post(
        f"/api/v1/printers/{printer.id}/drying/schedules",
        json={
            "ams_id": 0,
            "local_time": "06:30",
            "timezone": "Europe/Berlin",
            "filament": "PLA",
            "temperature": 45,
            "duration_hours": 4,
        },
    )
    assert response.status_code == 201
    plan = response.json()
    assert plan["enabled"] is False
    assert plan["timezone"] == "Europe/Berlin"
    listed = await async_client.get(f"/api/v1/printers/{printer.id}/drying/schedules")
    assert [item["id"] for item in listed.json()["schedules"]] == [plan["id"]]


@pytest.mark.asyncio
async def test_manual_filament_load_cannot_conflict_with_a_durable_owner(async_client, printer_factory, db_session):
    printer = await printer_factory(model="P2S")
    plan = DryingSchedule(
        printer_id=printer.id,
        ams_id=0,
        local_time="06:30",
        timezone="UTC",
        filament="PLA",
        temperature=45,
        duration_hours=4,
        enabled=False,
    )
    db_session.add(plan)
    await db_session.flush()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(
        DryingScheduleRun(
            schedule_id=plan.id,
            printer_id=printer.id,
            active_printer_id=printer.id,
            ams_id=0,
            occurrence_day=now.date().isoformat(),
            due_at=now,
            claimed_at=now,
            status="uncertain",
            reason="publish_uncertain",
        )
    )
    await db_session.commit()
    client = MagicMock()
    with patch("backend.app.api.routes.printers.printer_manager.get_client", return_value=client):
        response = await async_client.post(f"/api/v1/printers/{printer.id}/ams/load?tray_id=0")
    assert response.status_code == 409
    client.ams_load_filament.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted", [True, False])
async def test_manual_command_invalidates_previous_idle_and_stopped_observations(
    async_client, printer_factory, accepted
):
    from backend.tests.unit.services.test_scheduled_drying import fresh_state

    printer = await printer_factory(model="P2S")
    state = fresh_state(datetime.now(timezone.utc))
    client = MagicMock()
    client.ams_load_filament.return_value = accepted
    with (
        patch("backend.app.api.routes.printers.printer_manager.get_client", return_value=client),
        patch("backend.app.services.printer_manager.printer_manager.get_status", return_value=state),
    ):
        response = await async_client.post(f"/api/v1/printers/{printer.id}/ams/load?tray_id=0")
    assert response.status_code == (200 if accepted else 500)
    client.ams_load_filament.assert_called_once_with(0)
    assert state.drying_telemetry.idle_observed_at == 0
    assert state.drying_telemetry.units == {}
