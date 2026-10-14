"""App messages must retain key ownership, delivery policy and database quotas."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.auth import generate_api_key
from backend.app.core.database import Base
from backend.app.models.api_key import APIKey
from backend.app.models.notification import NotificationDigestQueue, NotificationLog, NotificationProvider
from backend.app.models.user import User
from backend.app.services.notification_service import notification_service
from backend.tests.conftest import async_client as base_async_client, test_engine as model_engine
from backend.tests.integration.test_api_key_cloud_access import _setup_auth_with_admin


@pytest.fixture
async def test_engine(model_engine, tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'messages.db'}", connect_args={"timeout": 30})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def async_client(base_async_client, test_engine):
    # Production get_db commits after yield; the shared in-memory fixture omits
    # that boundary. File-backed API tests must model it faithfully.
    from backend.app.core.database import get_db
    from backend.app.main import app

    sessions = async_sessionmaker(test_engine, expire_on_commit=False)

    async def get_request_db():
        async with sessions() as db:
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    app.dependency_overrides[get_db] = get_request_db
    yield base_async_client


@pytest.fixture
async def transport(monkeypatch):
    requests = []

    async def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:

        async def get_client():
            return client

        monkeypatch.setattr(notification_service, "_get_client", get_client)
        yield requests


async def setup(client, **flags):
    token = await _setup_auth_with_admin(client)
    admin = {"Authorization": f"Bearer {token}"}
    result = await client.post(
        "/api/v1/api-keys/",
        headers=admin,
        json={"name": "App", "can_send_notifications": True, "can_read_status": False, **flags},
    )
    assert result.status_code == 200, result.text
    provider = await client.post(
        "/api/v1/notifications/",
        headers=admin,
        json={
            "name": "App channel",
            "provider_type": "telegram",
            "on_app_message": True,
            "config": {"bot_token": "FAKE", "chat_id": "123"},
        },
    )
    assert provider.status_code == 200, provider.text
    return admin, result.json(), provider.json()


@pytest.mark.parametrize("method,path", [("post", "/app-message"), ("get", "/app-message/channels")])
async def test_no_anonymous_access_when_auth_disabled(async_client, method, path):
    response = await async_client.request(
        method, "/api/v1/notifications" + path, **({"json": {"title": "a", "message": "b"}} if method == "post" else {})
    )
    assert response.status_code == 401


@pytest.mark.parametrize("header", ["X-API-Key", "Authorization"])
async def test_scoped_send_is_plain_text_logged_and_channels_are_private(async_client, db_session, transport, header):
    admin, key, provider = await setup(async_client)
    headers = {header: key["key"] if header == "X-API-Key" else "Bearer " + key["key"]}
    channels = await async_client.get("/api/v1/notifications/app-message/channels", headers=headers)
    assert channels.status_code == 200, channels.text
    assert channels.json() == [{"id": provider["id"], "name": "App channel", "provider_type": "telegram"}]
    response = await async_client.post(
        "/api/v1/notifications/app-message",
        headers=headers,
        json={"title": "*[Title](tg://user?id=1)", "message": "a_b <b>x</b> `code` @everyone"},
    )
    assert response.status_code == 200, response.text
    payload = json.loads(transport[0].content)
    assert "parse_mode" not in payload
    assert payload["text"] == "*[Title](tg://user?id=1)\na_b <b>x</b> `code` @everyone"
    logs = list(await db_session.scalars(select(NotificationLog)))
    assert [(log.event_type, log.success) for log in logs] == [("app_message", True)]
    assert response.json()["channels"] == 1
    assert key["can_send_notifications"] is True
    assert provider["on_app_message"] is True
    assert (await async_client.get("/api/v1/notifications/", headers=headers)).status_code == 403
    assert (
        await async_client.post("/api/v1/notifications/app-message", headers=admin, json={"title": "a", "message": "b"})
    ).status_code == 401


@pytest.mark.parametrize(
    "change,expected",
    [
        ("scope", 403),
        ("ownerless", 403),
        ("generation", 403),
        ("disabled", 401),
        ("expired", 401),
        ("inactive", 401),
        ("deleted", 401),
    ],
)
async def test_current_key_and_owner_required(async_client, db_session, transport, change, expected):
    _, key, _ = await setup(async_client)
    row = await db_session.get(APIKey, key["id"])
    owner = await db_session.get(User, row.user_id)
    if change == "scope":
        row.can_send_notifications = False
    if change == "ownerless":
        row.user_id = None
    if change == "generation":
        owner.connected_identity = "a" * 32
    if change == "disabled":
        row.enabled = False
    if change == "expired":
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    if change == "inactive":
        owner.is_active = False
    if change == "deleted":
        await db_session.delete(row)
    await db_session.commit()
    response = await async_client.post(
        "/api/v1/notifications/app-message", headers={"X-API-Key": key["key"]}, json={"title": "a", "message": "b"}
    )
    assert response.status_code == expected, response.text
    assert not transport


async def test_persistent_atomic_quota_and_expiry(async_client, test_engine, transport, monkeypatch):
    _, key, _ = await setup(async_client)

    async def send():
        return await async_client.post(
            "/api/v1/notifications/app-message",
            headers={"X-API-Key": key["key"]},
            json={"title": "Quota", "message": "Test"},
        )

    responses = await asyncio.gather(*(send() for _ in range(25)))
    assert sorted(r.status_code for r in responses) == [200] * 20 + [429] * 5
    assert len(transport) == 20
    await test_engine.dispose()  # New connections cannot reset persistent quota.
    assert (await send()).status_code == 429
    from backend.app.services import app_messages

    now = app_messages.time.time()
    monkeypatch.setattr(app_messages.time, "time", lambda: now + 61)
    assert (await send()).status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "x" * 121, "message": "a"},
        {"title": "a", "message": "x" * 2001},
        {"title": "  ", "message": "a"},
        {"title": "a", "message": "b", "url": "javascript:alert(1)"},
        {"title": "a", "message": "b", "channel_ids": list(range(51))},
    ],
)
async def test_invalid_input_cannot_dispatch(async_client, transport, payload):
    _, key, _ = await setup(async_client)
    response = await async_client.post(
        "/api/v1/notifications/app-message", headers={"X-API-Key": key["key"]}, json=payload
    )
    assert response.status_code == 422
    assert not transport


async def test_owner_id_reuse_cannot_inherit_old_notification_scope(async_client, db_session, transport):
    _, key, _ = await setup(async_client)
    row = await db_session.get(APIKey, key["id"])
    owner_id = row.user_id
    await db_session.execute(delete(User).where(User.id == owner_id))
    await db_session.commit()
    replacement = User(username="replacement", is_active=True)
    db_session.add(replacement)
    await db_session.commit()
    assert replacement.id == owner_id
    assert await db_session.get(APIKey, key["id"]) is not None  # Legacy SQLite without FK cascades.
    response = await async_client.post(
        "/api/v1/notifications/app-message", headers={"X-API-Key": key["key"]}, json={"title": "a", "message": "b"}
    )
    assert response.status_code == 403
    assert not transport


async def test_flags_roundtrip_and_auth_disabled_does_not_bypass_key(async_client, db_session, transport):
    from backend.app.core.auth import invalidate_auth_enabled_cache
    from backend.app.models.settings import Settings

    admin, key, provider = await setup(async_client, can_send_notifications=False)
    default = await async_client.post(
        "/api/v1/notifications/",
        headers=admin,
        json={"name": "Not opted in", "provider_type": "telegram", "config": {"bot_token": "FAKE", "chat_id": "123"}},
    )
    assert default.json()["on_app_message"] is False
    assert key["can_send_notifications"] is False
    patched = await async_client.patch(
        f"/api/v1/api-keys/{key['id']}", headers=admin, json={"can_send_notifications": True}
    )
    assert patched.json()["can_send_notifications"] is True
    auth_setting = await db_session.scalar(select(Settings).where(Settings.key == "auth_enabled"))
    auth_setting.value = "false"
    await db_session.commit()
    invalidate_auth_enabled_cache()
    headers = {"X-API-Key": key["key"]}
    channels = await async_client.get("/api/v1/notifications/app-message/channels", headers=headers)
    assert [p["id"] for p in channels.json()] == [provider["id"]]
    assert (
        await async_client.post(
            "/api/v1/notifications/app-message", headers=headers, json={"title": "a", "message": "b"}
        )
    ).status_code == 200
    assert (
        await async_client.post("/api/v1/api-keys/", json={"name": "Anonymous grant", "can_send_notifications": True})
    ).status_code == 400


async def test_printer_provider_filters_and_explicit_selection(async_client, db_session, transport):
    from backend.app.models.printer import Printer

    admin, key, provider = await setup(async_client, printer_ids=[1, 2])
    owner = await db_session.get(User, key["user_id"])
    owner.allowed_printer_ids = [1, 3]
    db_session.add_all(
        [
            Printer(id=i, name=f"Printer {i}", serial_number=f"S{i}", ip_address="127.0.0.1", access_code="fake")
            for i in (1, 2, 3)
        ]
    )
    for i in (1, 2, 3):
        db_session.add(
            NotificationProvider(
                name=f"P{i}",
                provider_type="telegram",
                config='{"bot_token":"FAKE","chat_id":"1"}',
                on_app_message=True,
                printer_id=i,
            )
        )
    await db_session.commit()
    headers = {"X-API-Key": key["key"]}
    channels = await async_client.get("/api/v1/notifications/app-message/channels?printer_id=1", headers=headers)
    assert [p["name"] for p in channels.json()] == ["App channel", "P1"]
    for payload in ({}, {"printer_id": 2}, {"printer_id": 3}, {"printer_id": 1, "channel_ids": [999]}):
        response = await async_client.post(
            "/api/v1/notifications/app-message", headers=headers, json={"title": "a", "message": "b", **payload}
        )
        assert response.status_code == 403
    response = await async_client.post(
        "/api/v1/notifications/app-message",
        headers=headers,
        json={"title": "a", "message": "b", "printer_id": 1, "channel_ids": [provider["id"]]},
    )
    assert response.status_code == 200
    assert len(transport) == 1
    await async_client.patch(f"/api/v1/notifications/{provider['id']}", headers=admin, json={"on_app_message": False})
    response = await async_client.post(
        "/api/v1/notifications/app-message",
        headers=headers,
        json={"title": "a", "message": "b", "printer_id": 1, "channel_ids": [provider["id"]]},
    )
    assert response.status_code == 403


async def test_quiet_hours_digest_and_no_write_lock_through_transport(
    async_client, db_session, test_engine, monkeypatch
):
    admin, key, provider = await setup(async_client)
    await async_client.patch(
        f"/api/v1/notifications/{provider['id']}",
        headers=admin,
        json={
            "daily_digest_enabled": True,
            "daily_digest_time": "08:00",
            "quiet_hours_enabled": True,
            "quiet_hours_start": "00:00",
            "quiet_hours_end": "23:59",
        },
    )
    monkeypatch.setattr(notification_service, "_is_in_quiet_hours", lambda _: True)
    headers = {"X-API-Key": key["key"]}
    response = await async_client.post(
        "/api/v1/notifications/app-message", headers=headers, json={"title": "a_*", "message": "b"}
    )
    assert response.status_code == 200
    entries = list(await db_session.scalars(select(NotificationDigestQueue)))
    assert len(entries) == 1
    assert entries[0].event_type == "app_message"
    assert (await db_session.scalar(select(NotificationLog))).success is True
    await db_session.commit()
    monkeypatch.setattr(notification_service, "_is_in_quiet_hours", lambda _: False)
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)

    async def fake_transport(request):
        async def unrelated_write():
            async with sessions() as session:
                session.add(User(username="unrelated-writer"))
                await session.commit()

        await asyncio.wait_for(unrelated_write(), timeout=2)
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(fake_transport)) as client:

        async def get_client():
            return client

        monkeypatch.setattr(notification_service, "_get_client", get_client)
        response = await async_client.post(
            "/api/v1/notifications/app-message", headers=headers, json={"title": "a", "message": "b"}
        )
    assert response.status_code == 200
    assert await db_session.scalar(select(User).where(User.username == "unrelated-writer")) is not None


@pytest.mark.parametrize(
    "provider_type,config",
    [
        ("discord", {"webhook_url": "https://discord.com/api/webhooks/fake"}),
        ("webhook", {"webhook_url": "https://notify.example.com/hook", "payload_format": "slack"}),
    ],
)
async def test_markup_transports_cannot_inject_mentions(async_client, transport, provider_type, config):
    admin, key, provider = await setup(async_client)
    await async_client.patch(
        f"/api/v1/notifications/{provider['id']}",
        headers=admin,
        json={"provider_type": provider_type, "config": config},
    )
    response = await async_client.post(
        "/api/v1/notifications/app-message",
        headers={"X-API-Key": key["key"]},
        json={"title": "*Title*", "message": "<@123> @everyone **body**"},
    )
    assert response.status_code == 200
    payload = json.loads(transport[0].content)
    if provider_type == "discord":
        assert payload["allowed_mentions"] == {"parse": []}
        assert payload["embeds"][0]["description"] == "&lt;@123&gt; @everyone \\*\\*body\\*\\*"
    else:
        assert payload["mrkdwn"] is False
        assert payload["blocks"][0]["text"]["type"] == "plain_text"


async def test_channel_fanout_is_bounded(async_client, db_session, transport):
    _, key, provider = await setup(async_client)
    for index in range(50):
        db_session.add(
            NotificationProvider(name=f"Extra {index}", provider_type="telegram", config="{}", on_app_message=True)
        )
    await db_session.commit()
    headers = {"X-API-Key": key["key"]}
    response = await async_client.post(
        "/api/v1/notifications/app-message", headers=headers, json={"title": "a", "message": "b"}
    )
    assert response.status_code == 400
    assert not transport
    response = await async_client.post(
        "/api/v1/notifications/app-message",
        headers=headers,
        json={"title": "a", "message": "b", "channel_ids": [provider["id"]]},
    )
    assert response.status_code == 200
    assert len(transport) == 1


async def test_revocation_cleans_quota_even_without_sqlite_foreign_keys(async_client, db_session, transport):
    from backend.app.models.api_key import AppMessageQuota

    admin, key, _ = await setup(async_client)
    await async_client.post(
        "/api/v1/notifications/app-message", headers={"X-API-Key": key["key"]}, json={"title": "a", "message": "b"}
    )
    assert await db_session.scalar(select(AppMessageQuota)) is not None
    response = await async_client.delete(f"/api/v1/api-keys/{key['id']}", headers=admin)
    assert response.status_code == 200
    assert await db_session.scalar(select(AppMessageQuota)) is None


async def test_app_opt_in_cannot_be_set_to_null(async_client):
    admin, _, provider = await setup(async_client)
    response = await async_client.patch(
        f"/api/v1/notifications/{provider['id']}", headers=admin, json={"on_app_message": None}
    )
    assert response.status_code == 422
