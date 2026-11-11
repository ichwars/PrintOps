"""Credential checks remain fail-closed when kiosk usage bookkeeping is unavailable."""

from contextlib import contextmanager
from sqlite3 import OperationalError as SQLiteOperationalError

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError

from backend.app.core.auth import generate_api_key
from backend.app.models.api_key import APIKey
from backend.app.models.user import User
from backend.tests.integration.test_long_lived_tokens_api import _create_user, _login, _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@contextmanager
def fail_matching_statements(engine, matches):
    attempts = []

    def fail(_connection, _cursor, statement, _parameters, _context, _many):
        if matches(statement.lower()):
            attempts.append(statement)
            raise OperationalError(None, None, SQLiteOperationalError("simulated database outage"))

    event.listen(engine.sync_engine, "before_cursor_execute", fail)
    try:
        yield attempts
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", fail)


async def test_kiosk_key_survives_unavailable_usage_write_but_requires_a_successful_read(
    async_client, db_session, test_engine
):
    admin = await _setup_admin(async_client)
    owner_id = await _create_user(async_client, admin, "kiosk_owner")
    full_key, key_hash, prefix = generate_api_key()
    db_session.add(
        APIKey(name="Kiosk", key_hash=key_hash, key_prefix=prefix, user_id=owner_id, enabled=True, can_read_status=True)
    )
    await db_session.commit()

    headers = {"X-API-Key": full_key}
    with fail_matching_statements(test_engine, lambda sql: sql.startswith("update api_keys set last_used")) as writes:
        for path in ("/api/v1/auth/me", "/api/v1/auth/me", "/api/v1/webhook/queue"):
            response = await async_client.get(path, headers=headers)
            assert response.status_code == 200
        assert len(writes) == 1

    with fail_matching_statements(test_engine, lambda sql: sql.startswith("select") and "from api_keys" in sql):
        response = await async_client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 503

    owner = await db_session.get(User, owner_id)
    owner.is_active = False
    await db_session.commit()
    assert (await async_client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    assert (await async_client.get("/api/v1/webhook/queue", headers=headers)).status_code == 401


async def test_camera_wall_stays_available_if_only_the_usage_write_fails(async_client, db_session, test_engine):
    admin = await _setup_admin(async_client)
    headers = {"Authorization": f"Bearer {admin}"}
    share = await async_client.post(
        "/api/v1/auth/tokens", headers=headers, json={"name": "Wall", "scope": "camwall", "expires_in_days": 1}
    )
    assert share.status_code == 201
    token = share.json()["token"]

    with fail_matching_statements(
        test_engine, lambda sql: sql.startswith("update long_lived_tokens set last_used_at")
    ) as writes:
        for _ in range(2):
            response = await async_client.get("/api/v1/camwall/printers", params={"token": token})
            assert response.status_code == 200
        assert len(writes) == 1

    owner = await db_session.scalar(select(User).where(User.role == "admin"))
    owner.is_active = False
    await db_session.commit()
    response = await async_client.get("/api/v1/camwall/printers", params={"token": token})
    assert response.status_code == 401
