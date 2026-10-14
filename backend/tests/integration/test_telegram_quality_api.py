"""HTTP administration uses real authenticated users and persisted mappings."""

import json

import pytest
from sqlalchemy import select

from backend.app.models.notification import NotificationProvider
from backend.app.models.telegram_quality import TelegramQualityConfig
from backend.app.models.user import User
from backend.tests.integration.test_api_key_cloud_access import _setup_auth_with_admin


async def test_unauthenticated_configuration_denied_even_auth_off(async_client, db_session):
    provider = NotificationProvider(name="T", provider_type="telegram", config="{}")
    db_session.add(provider)
    await db_session.commit()
    response = await async_client.put(
        f"/api/v1/notifications/{provider.id}/telegram-quality",
        json={"enabled": True, "actors": [{"actor_id": 42, "user_id": 1}]},
    )
    assert response.status_code in {401, 403}
    assert await db_session.scalar(select(TelegramQualityConfig.id)) is None


async def test_admin_roundtrip_mapping_removal_and_strict_input(async_client, db_session):
    token = await _setup_auth_with_admin(async_client)
    user = await db_session.scalar(select(User).where(User.username == "cloudadmin"))
    provider = NotificationProvider(
        name="T", provider_type="telegram", config=json.dumps({"bot_token": "123:fake", "chat_id": "-100"})
    )
    db_session.add(provider)
    await db_session.commit()
    url = f"/api/v1/notifications/{provider.id}/telegram-quality"
    headers = {"Authorization": f"Bearer {token}"}
    assert (await async_client.get(url, headers=headers)).json()["enabled"] is False
    for actor in [True, "42", 0, -1, 2**53]:
        response = await async_client.put(
            url, headers=headers, json={"enabled": True, "actors": [{"actor_id": actor, "user_id": user.id}]}
        )
        assert response.status_code == 422
    for invalid_user in [True, "1", 0, -1, 2**31, 2**63]:
        invalid = await async_client.put(
            url, headers=headers, json={"enabled": True, "actors": [{"actor_id": 42, "user_id": invalid_user}]}
        )
        assert invalid.status_code == 422
    response = await async_client.put(
        url, headers=headers, json={"enabled": True, "actors": [{"actor_id": 42, "user_id": user.id}]}
    )
    assert response.status_code == 200, response.text
    config = await db_session.scalar(select(TelegramQualityConfig))
    assert config.actors[0]["identity"] == user.connected_identity
    assert "identity" not in response.text
    response = await async_client.put(url, headers=headers, json={"enabled": False, "actors": []})
    assert response.status_code == 200 and response.json()["actors"] == []
    user.role = "user"
    user.groups = []
    await db_session.commit()
    assert (await async_client.get(url, headers=headers)).status_code == 403


async def test_provider_edits_and_recycled_provider_id_revoke_messages(async_client, db_session):
    from datetime import datetime, timedelta

    from backend.app.models.archive import PrintArchive
    from backend.app.models.print_log import PrintLogEntry
    from backend.app.models.telegram_quality import TelegramQualityMessage
    from backend.app.services.telegram_quality import bind_message

    token = await _setup_auth_with_admin(async_client)
    headers = {"Authorization": f"Bearer {token}"}
    user = await db_session.scalar(select(User).where(User.username == "cloudadmin"))
    provider = NotificationProvider(
        name="T",
        provider_type="telegram",
        config=json.dumps({"bot_token": "123:secret-never-return", "chat_id": "-100"}),
    )
    archive = PrintArchive(filename="parts", file_path="/none", file_size=1, status="completed")
    db_session.add_all([provider, archive])
    await db_session.flush()
    run = PrintLogEntry(
        archive_id=archive.id,
        status="completed",
        quantity=1,
        confirm_requested=True,
        confirm_prompted_at=datetime.utcnow(),
        confirm_token_hash="a" * 64,
        confirm_token_expires_at=datetime.utcnow() + timedelta(hours=48),
    )
    db_session.add(run)
    await db_session.commit()
    url = f"/api/v1/notifications/{provider.id}"
    response = await async_client.put(
        url + "/telegram-quality",
        headers=headers,
        json={"enabled": True, "actors": [{"actor_id": 42, "user_id": user.id}]},
    )
    assert response.status_code == 200
    assert "secret-never-return" not in response.text and "bot_token" not in response.text
    assert await bind_message(db_session, provider, {"message_id": 12, "chat_id": -100}, archive.id, run.id)
    await db_session.commit()
    assert (await async_client.patch(url, headers=headers, json={"printer_id": None})).status_code == 200
    assert await db_session.scalar(select(TelegramQualityMessage.id)) is None
    assert (await async_client.delete(url, headers=headers)).status_code == 200
    assert await db_session.scalar(select(TelegramQualityConfig.id)) is None
    replacement = NotificationProvider(name="replacement", provider_type="telegram", config=provider.config)
    db_session.expunge(provider)
    db_session.add(replacement)
    await db_session.commit()
    assert url.endswith("/" + str(replacement.id)), "Exercise SQLite highest-ID reuse"
    response = await async_client.get(url + "/telegram-quality", headers=headers)
    assert response.status_code == 200 and response.json()["enabled"] is False
    assert response.json()["actors"] == []
