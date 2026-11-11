"""Scoped callers can manage only their notification providers and printer logs."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.models.api_key import APIKey
from backend.app.models.group import Group
from backend.app.models.notification import NotificationLog, NotificationProvider
from backend.app.models.user import User
from backend.app.services.notification_service import notification_service
from backend.app.utils.local_time import utcnow_naive
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def scoped_notifications(async_client, db_session, printer_factory):
    await _setup_admin(async_client)
    visible, hidden = await printer_factory(), await printer_factory()
    operator = User(
        username="notification_operator",
        allowed_printer_ids=[visible.id],
        groups=[
            Group(
                name="Scoped notifications",
                permissions=[
                    "notifications:read",
                    "notifications:create",
                    "notifications:update",
                    "notifications:delete",
                ],
            )
        ],
    )
    key, key_hash, prefix = generate_api_key()
    providers = [
        NotificationProvider(name=name, printer_id=printer_id, provider_type="ntfy", config="{}")
        for name, printer_id in (("Mine", visible.id), ("Hidden", hidden.id), ("Global", None))
    ]
    db_session.add_all(
        [operator, APIKey(name="Read notifications", key_hash=key_hash, key_prefix=prefix, printer_ids=[visible.id])]
        + providers
    )
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': operator.username})}"}
    return visible, hidden, providers, headers, {"X-API-Key": key}


async def test_only_assigned_providers_can_be_seen_tested_or_modified(async_client, scoped_notifications, monkeypatch):
    visible, hidden, (mine, other, global_provider), headers, key = scoped_notifications
    send_test = AsyncMock(return_value=(True, "Test result"))
    monkeypatch.setattr(notification_service, "send_test_notification", send_test)
    base = "/api/v1/notifications"
    for credentials in (headers, key):
        response = await async_client.get(f"{base}/", headers=credentials)
        assert response.status_code == 200
        assert [p["id"] for p in response.json()] == [mine.id]
        for provider in (other, global_provider):
            assert (await async_client.get(f"{base}/{provider.id}", headers=credentials)).status_code == 404

    for provider in (other, global_provider):
        for method, suffix, kwargs in (
            ("PATCH", "", {"json": {"name": "Denied"}}),
            ("POST", "/test", {}),
            ("DELETE", "", {}),
        ):
            response = await async_client.request(method, f"{base}/{provider.id}{suffix}", headers=headers, **kwargs)
            assert response.status_code == 404
    send_test.assert_not_called()
    for target, code in ((hidden.id, 404), (None, 400)):
        response = await async_client.patch(f"{base}/{mine.id}", headers=headers, json={"printer_id": target})
        assert response.status_code == code
        response = await async_client.post(
            f"{base}/",
            headers=headers,
            json={"name": "Denied", "printer_id": target, "provider_type": "ntfy", "config": {"topic": "test"}},
        )
        assert response.status_code == code

    updated = await async_client.patch(
        f"{base}/{mine.id}", headers=headers, json={"name": "Updated", "printer_id": visible.id}
    )
    assert updated.status_code == 200
    tested = await async_client.post(f"{base}/test-all", headers=headers)
    assert tested.status_code == 200
    assert [entry["provider_id"] for entry in tested.json()["results"]] == [mine.id]
    send_test.assert_awaited_once()


async def test_log_list_stats_and_deletion_follow_printer_scope(async_client, db_session, scoped_notifications):
    visible, hidden, (mine, other, global_provider), headers, key = scoped_notifications
    old = utcnow_naive() - timedelta(days=2)
    for provider, printer_id, printer_name, title in (
        (mine, visible.id, visible.name, "Own printer"),
        (global_provider, visible.id, visible.name, "Visible event, private destination"),
        (other, hidden.id, hidden.name, "Hidden printer"),
        (mine, None, None, "Own provider test"),
        (mine, None, "Deleted printer", "Old printer snapshot"),
        (global_provider, None, None, "Global provider test"),
    ):
        db_session.add(
            NotificationLog(
                provider_id=provider.id,
                printer_id=printer_id,
                printer_name=printer_name,
                title=title,
                message="Fixture",
                success=False,
                event_type="test",
                error_message="Private destination",
                created_at=old,
            )
        )
    await db_session.commit()

    base = "/api/v1/notifications/logs"
    for credentials in (headers, key):
        response = await async_client.get(base, headers=credentials)
        assert response.status_code == 200
        entries = {row["title"]: row for row in response.json()}
        assert set(entries) == {"Own printer", "Visible event, private destination", "Own provider test"}
        global_event = entries["Visible event, private destination"]
        assert global_event["provider_name"] is global_event["provider_type"] is global_event["error_message"] is None
        assert entries["Own printer"]["provider_name"] == mine.name
        response = await async_client.get(f"{base}/stats", headers=credentials)
        assert response.status_code == 200
        assert response.json()["total"] == 3
        assert response.json()["by_provider"] == {mine.name: 2, "Other": 1}

    cleared = await async_client.delete(base, headers=headers, params={"older_than_days": 1})
    assert cleared.status_code == 200
    assert cleared.json()["deleted"] == 2
    assert set(await db_session.scalars(select(NotificationLog.title))) == {
        "Hidden printer",
        "Own provider test",
        "Old printer snapshot",
        "Global provider test",
    }
