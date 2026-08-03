"""Bambu Cloud credential hand-off across auth enable/disable."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes.cloud import CLOUD_EMAIL_KEY, CLOUD_REGION_KEY, CLOUD_TOKEN_KEY, get_stored_token
from backend.app.core.auth import get_password_hash
from backend.app.models.settings import Settings
from backend.app.models.user import User


async def _seed_global_token(db: AsyncSession, token: str = "tok-global", region: str = "china") -> None:
    db.add(Settings(key=CLOUD_TOKEN_KEY, value=token))
    db.add(Settings(key=CLOUD_EMAIL_KEY, value="owner@example.com"))
    db.add(Settings(key=CLOUD_REGION_KEY, value=region))
    await db.commit()


async def _global_rows(db: AsyncSession) -> dict[str, str]:
    rows = (
        (
            await db.execute(
                select(Settings).where(Settings.key.in_([CLOUD_TOKEN_KEY, CLOUD_EMAIL_KEY, CLOUD_REGION_KEY]))
            )
        )
        .scalars()
        .all()
    )
    return {row.key: row.value for row in rows}


async def _make_admin(db: AsyncSession, username: str) -> User:
    user = User(
        username=username,
        password_hash=get_password_hash("AdminPass1!"),
        role="admin",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _admin_bearer(async_client: AsyncClient) -> str:
    await async_client.post(
        "/api/v1/auth/setup",
        json={"auth_enabled": True, "admin_username": "admin", "admin_password": "AdminPass1!"},
    )
    login = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "AdminPass1!"},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


@pytest.mark.asyncio
async def test_setup_migrates_global_token_to_created_admin(async_client: AsyncClient, db_session: AsyncSession):
    await _seed_global_token(db_session)

    response = await async_client.post(
        "/api/v1/auth/setup",
        json={"auth_enabled": True, "admin_username": "admin", "admin_password": "AdminPass1!"},
    )
    assert response.status_code == 200, response.text

    admin = (await db_session.execute(select(User).where(User.role == "admin"))).scalar_one()
    token, email, region = await get_stored_token(db_session, admin)
    assert (token, email, region) == ("tok-global", "owner@example.com", "china")
    assert await _global_rows(db_session) == {}


@pytest.mark.asyncio
async def test_setup_migrates_to_sole_existing_admin(async_client: AsyncClient, db_session: AsyncSession):
    admin = await _make_admin(db_session, "solo")
    await _seed_global_token(db_session, token="tok-solo")

    response = await async_client.post("/api/v1/auth/setup", json={"auth_enabled": True})
    assert response.status_code == 200, response.text

    await db_session.refresh(admin)
    token, _, _ = await get_stored_token(db_session, admin)
    assert token == "tok-solo"
    assert await _global_rows(db_session) == {}


@pytest.mark.asyncio
async def test_setup_refuses_to_guess_when_multiple_admins(async_client: AsyncClient, db_session: AsyncSession):
    admin_a = await _make_admin(db_session, "admin_a")
    admin_b = await _make_admin(db_session, "admin_b")
    await _seed_global_token(db_session, token="tok-ambiguous")

    response = await async_client.post("/api/v1/auth/setup", json={"auth_enabled": True})
    assert response.status_code == 200, response.text

    await db_session.refresh(admin_a)
    await db_session.refresh(admin_b)
    assert admin_a.cloud_token is None
    assert admin_b.cloud_token is None
    assert (await _global_rows(db_session))[CLOUD_TOKEN_KEY] == "tok-ambiguous"


@pytest.mark.asyncio
async def test_disable_auth_migrates_admin_token_to_global(async_client: AsyncClient, db_session: AsyncSession):
    bearer = await _admin_bearer(async_client)
    admin = (await db_session.execute(select(User).where(User.role == "admin"))).scalar_one()
    admin.cloud_token = "tok-user"
    admin.cloud_email = "user@example.com"
    admin.cloud_region = "china"
    await db_session.commit()

    response = await async_client.post("/api/v1/auth/disable", headers={"Authorization": f"Bearer {bearer}"})
    assert response.status_code == 200, response.text

    rows = await _global_rows(db_session)
    assert rows[CLOUD_TOKEN_KEY] == "tok-user"
    assert rows[CLOUD_EMAIL_KEY] == "user@example.com"
    assert rows[CLOUD_REGION_KEY] == "china"

    await db_session.refresh(admin)
    assert admin.cloud_token is None
