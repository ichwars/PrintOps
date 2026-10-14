"""A browser preference must not follow a reused SQLite numeric user ID."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.api.routes.auth import _api_key_to_user_response
from backend.app.api.routes.mfa import _user_to_response as mfa_response
from backend.app.models import connected_app  # noqa: F401 — register deletion cleanup tables
from backend.app.models.user import User


@pytest.mark.asyncio
async def test_public_subject_survives_login_but_not_user_recreation(async_client, db_session):
    await async_client.post(
        "/api/v1/auth/setup",
        json={
            "auth_enabled": True,
            "admin_username": "subjectadmin",
            "admin_password": "AdminPass1!",
        },
    )
    admin = await async_client.post(
        "/api/v1/auth/login",
        json={
            "username": "subjectadmin",
            "password": "AdminPass1!",
        },
    )
    headers = {"Authorization": f"Bearer {admin.json()['access_token']}"}

    async def create_and_login():
        created = await async_client.post(
            "/api/v1/users/",
            headers=headers,
            json={
                "username": "recreated",
                "password": "Password123!",
                "role": "user",
            },
        )
        assert created.status_code in (200, 201), created.text
        login = await async_client.post(
            "/api/v1/auth/login",
            json={
                "username": "recreated",
                "password": "Password123!",
            },
        )
        assert login.status_code == 200, login.text
        account = login.json()["user"]
        assert account.get("sub"), "ordinary auth responses need a nonreused public preference subject"
        assert account["sub"] == created.json()["sub"]
        me = await async_client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {login.json()['access_token']}",
            },
        )
        assert me.status_code == 200
        assert me.json()["sub"] == account["sub"]
        assert account["username"] == "recreated"
        assert account["role"] == "user"
        assert isinstance(account["permissions"], list)
        result = await db_session.execute(
            select(User).options(selectinload(User.groups)).where(User.id == account["id"])
        )
        model = result.scalar_one()
        assert account["sub"] == model.connected_identity
        assert mfa_response(model).model_dump()["sub"] == account["sub"]
        return account

    original = await create_and_login()
    deleted = await async_client.delete(f"/api/v1/users/{original['id']}", headers=headers)
    assert deleted.status_code == 204, deleted.text
    db_session.expunge_all()
    replacement = await create_and_login()
    assert replacement["id"] == original["id"], "fixture must exercise actual SQLite ID reuse"
    assert replacement["sub"] != original["sub"]


def test_synthetic_api_key_identity_does_not_claim_a_durable_user_subject():
    from datetime import datetime, timezone
    from types import SimpleNamespace

    response = _api_key_to_user_response(SimpleNamespace(key_prefix="test", created_at=datetime.now(timezone.utc)))
    assert response.model_dump().get("sub") is None
    assert response.id == 0
