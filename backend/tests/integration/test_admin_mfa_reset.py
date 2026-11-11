import pytest

from backend.app.api.routes.settings import get_setting, set_setting
from backend.app.models.user import User
from backend.tests.integration.test_mfa_api import _auth_header, _norm_pw, _setup_and_login


async def test_admin_mfa_reset_requires_authentication_even_when_it_is_disabled(async_client, db_session):
    user = User(username="reset-target")
    db_session.add(user)
    await db_session.flush()
    key = f"user_{user.id}_email_2fa_enabled"
    await set_setting(db_session, key, "true")
    await db_session.commit()

    denied = await async_client.delete(f"/api/v1/auth/2fa/admin/{user.id}")
    assert denied.status_code == 404
    assert await get_setting(db_session, key) == "true"


@pytest.mark.parametrize("email_enabled", [True, False])
async def test_admin_reset_reports_active_mfa_and_requires_own_password(async_client, db_session, email_enabled):
    password = "Fixture-admin-123!"
    token = await _setup_and_login(async_client, "adminreset", password)
    headers = _auth_header(token)
    created = await async_client.post(
        "/api/v1/users/", headers=headers, json={"username": "reset-target", "password": "Fixturetarget1!"}
    )
    assert created.status_code in (200, 201)
    user_id = created.json()["id"]
    if email_enabled:
        await set_setting(db_session, f"user_{user_id}_email_2fa_enabled", "true")
        await db_session.commit()

    route = f"/api/v1/auth/2fa/admin/{user_id}"
    denied = await async_client.request("DELETE", route, headers=headers, json={"admin_password": "wrong fixture"})
    assert denied.status_code == 401
    done = await async_client.request("DELETE", route, headers=headers, json={"admin_password": _norm_pw(password)})
    assert done.status_code == 200
    assert done.json()["had_2fa"] is email_enabled
