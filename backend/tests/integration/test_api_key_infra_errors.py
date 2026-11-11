"""Differentiate bad credentials and infrastructure failures at the API boundary."""

from datetime import datetime, timedelta, timezone

import pytest
from passlib.utils import MAX_PASSWORD_SIZE
from sqlalchemy import update

from backend.app.core.auth import generate_api_key
from backend.app.models.api_key import APIKey
from backend.tests.integration.test_kiosk_auth_recovery import fail_matching_statements
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


AUTH_ROUTE = "/api/v1/auth/me"
WEBHOOK_ROUTE = "/api/v1/webhook/printer/99999/status"


@pytest.mark.parametrize(("route", "accepted_status"), [(AUTH_ROUTE, 200), (WEBHOOK_ROUTE, 404)])
async def test_malformed_hash_does_not_hide_valid_key_with_same_prefix(
    async_client, db_session, caplog, route, accepted_status
):
    await _setup_admin(async_client)
    full_key, key_hash, prefix = generate_api_key()
    malformed = "unrecognized-fixture-hash"
    db_session.add_all(
        [
            APIKey(name="Malformed hash", key_prefix=prefix, key_hash=malformed),
            APIKey(name="Valid collision", key_prefix=prefix, key_hash=key_hash, can_read_status=True),
        ]
    )
    await db_session.commit()

    assert (await async_client.get(route, headers={"X-API-Key": full_key})).status_code == accepted_status
    assert "has an unreadable hash" in caplog.text
    assert malformed not in caplog.text
    assert full_key not in caplog.text

    unmatched = full_key[:8] + "wrong-secret"
    assert (await async_client.get(route, headers={"X-API-Key": unmatched})).status_code == 401

    caplog.clear()
    oversized = full_key[:8] + ("x" * MAX_PASSWORD_SIZE)
    assert (await async_client.get(route, headers={"X-API-Key": oversized})).status_code == 401
    assert "has an unreadable hash" not in caplog.text


@pytest.mark.parametrize(("route", "accepted_status"), [(AUTH_ROUTE, 200), (WEBHOOK_ROUTE, 404)])
async def test_usage_write_failure_with_failed_credential_recheck_returns_503(
    async_client,
    db_session,
    test_engine,
    caplog,
    route,
    accepted_status,
):
    await _setup_admin(async_client)
    full_key, key_hash, prefix = generate_api_key()
    db_session.add(APIKey(name="Retryable kiosk", key_prefix=prefix, key_hash=key_hash, can_read_status=True))
    await db_session.commit()

    def fails_write_and_recheck(statement):
        return statement.startswith("update api_keys set last_used") or (
            statement.startswith("select") and "api_keys.key_hash = ?" in statement
        )

    headers = {"X-API-Key": full_key}
    with fail_matching_statements(test_engine, fails_write_and_recheck) as failures:
        unavailable = await async_client.get(route, headers=headers)
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == "Authentication service temporarily unavailable"
    assert len(failures) == 2
    assert "API key validation unavailable" in caplog.text
    assert full_key not in caplog.text and key_hash not in caplog.text
    assert (await async_client.get(route, headers=headers)).status_code == accepted_status


async def test_webhook_expiry_and_lookup_failure_use_shared_check(async_client, db_session, test_engine):
    full_key, key_hash, prefix = generate_api_key()
    db_session.add(APIKey(name="Webhook", key_prefix=prefix, key_hash=key_hash, can_read_status=True))
    await db_session.commit()

    headers = {"Authorization": f"Bearer {full_key}"}
    assert (await async_client.get(WEBHOOK_ROUTE, headers=headers)).status_code == 404
    with fail_matching_statements(
        test_engine, lambda sql: sql.startswith("select") and "from api_keys" in sql
    ) as reads:
        response = await async_client.get(WEBHOOK_ROUTE, headers=headers)
    assert len(reads) == 1
    assert response.status_code == 503

    await db_session.execute(
        update(APIKey)
        .where(APIKey.key_prefix == prefix)
        .values(expires_at=datetime.now(timezone.utc) - timedelta(days=1))
    )
    await db_session.commit()
    response = await async_client.get(WEBHOOK_ROUTE, headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "API key has expired"
