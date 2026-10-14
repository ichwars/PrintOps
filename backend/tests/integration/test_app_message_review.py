"""Review regressions at real API/digest boundaries, with offline provider consumers."""

import html
import json
import re
import smtplib
from datetime import datetime
from email import message_from_string
from urllib.parse import parse_qs

import httpx
import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.core import database
from backend.app.models.api_key import APIKey, AppMessageQuota
from backend.app.models.notification import NotificationDigestQueue, NotificationLog, NotificationProvider
from backend.app.models.user import User
from backend.app.services.notification_service import notification_service
from backend.tests.integration.test_app_messages import (  # noqa: F401
    async_client,
    base_async_client,
    model_engine,
    setup,
    test_engine,
)


def decoded_markdown(value):
    return html.unescape(re.sub(r"\\([\\`*_{}\[\]()#+.!|>~\-])", r"\1", value)).replace("@\u200b", "@")


@pytest.fixture
async def consumer(monkeypatch):
    calls, violations = [], []

    async def handle(request):
        if request.url.host == "api.pushover.net":
            payload = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
            if len(payload["message"]) > 1024:
                violations.append("Pushover message >1024 characters")
        else:
            payload = json.loads(request.content)
            if "embeds" in payload:
                for embed in payload["embeds"]:
                    if len(embed.get("title", "").encode("utf-16-le")) // 2 > 256:
                        violations.append("Discord title >256")
                    if len(embed["description"].encode("utf-16-le")) // 2 > 4096:
                        violations.append("Discord description >4096")
                if sum(len(e.get("title", "")) + len(e["description"]) for e in payload["embeds"]) > 6000:
                    violations.append("Discord aggregate >6000")
            for block in payload.get("blocks", []):
                if block["type"] == "section" and len(block["text"]["text"].encode("utf-16-le")) // 2 > 3000:
                    violations.append("Slack section >3000")
        calls.append(payload)
        return httpx.Response(400 if violations else 200, json={"ok": not violations})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:

        async def get_client():
            return client

        monkeypatch.setattr(notification_service, "_get_client", get_client)
        yield calls, violations


async def set_provider(db, provider_id, kind, config):
    provider = await db.get(NotificationProvider, provider_id)
    provider.provider_type = kind
    provider.config = json.dumps(config)
    await db.commit()
    return provider


async def send(client, key, title, message, **extra):
    response = await client.post(
        "/api/v1/notifications/app-message",
        headers={"X-API-Key": key["key"]},
        json={"title": title, "message": message, **extra},
    )
    assert response.status_code == 200, response.text


async def test_mattermost_fallback_cannot_interpret_mentions_or_markup(async_client, db_session, consumer):
    _, key, provider = await setup(async_client)
    await set_provider(
        db_session,
        provider["id"],
        "webhook",
        {
            "webhook_url": "https://chat.example.com/hooks/fake",
            "payload_format": "slack",
        },
    )
    title, body = "App & <tag>", "@channel @here @someone **bold** [link](https://evil.example) <!here>"
    await send(async_client, key, title, body)
    payload = consumer[0][0]
    fallback = payload["text"]
    assert not re.search(r"@(channel|here|someone)", fallback)
    assert "**bold**" not in fallback and "<tag>" not in fallback and "<!here>" not in fallback
    assert decoded_markdown(fallback) == title + "\n" + body
    assert payload["blocks"][0]["text"]["text"] == title + "\n" + body


@pytest.mark.parametrize(
    "title,body", [("&" * 120, "&" * 2000), ("😀" * 120, "**<&😀>" * 300)], ids=["entities", "unicode-markdown"]
)
async def test_discord_encoded_limits_preserve_all_content(async_client, db_session, consumer, title, body):
    _, key, provider = await setup(async_client)
    await set_provider(db_session, provider["id"], "discord", {"webhook_url": "https://discord.com/api/webhooks/fake"})
    url = "https://example.com/" + "x" * 450
    await send(async_client, key, title, body, url=url)
    body += "\n" + url
    calls, violations = consumer
    assert not violations
    assert all(p["allowed_mentions"] == {"parse": []} for p in calls)
    descriptions = "".join(decoded_markdown(e["description"]) for p in calls for e in p["embeds"])
    first_title = calls[0]["embeds"][0].get("title", "")
    assert (decoded_markdown(first_title) + "\n" if first_title else "") + descriptions == title + "\n" + body
    assert (await db_session.scalar(select(NotificationLog))).success is True


@pytest.mark.parametrize("count", [1, 30])
async def test_mixed_digest_is_complete_and_slack_valid(
    async_client, db_session, test_engine, monkeypatch, consumer, count
):
    _, _, provider_data = await setup(async_client)
    provider = await set_provider(
        db_session,
        provider_data["id"],
        "webhook",
        {
            "webhook_url": "https://chat.example.com/hooks/fake",
            "payload_format": "slack",
        },
    )
    provider.daily_digest_enabled = True
    for index in range(count):
        db_session.add(
            NotificationDigestQueue(
                provider_id=provider.id,
                event_type="app_message",
                title=f"{index:02d}" + "x" * 118,
                message=f"@channel **full body {index}**\nhttps://example.com/{index}",
                created_at=datetime(2026, 10, 14, 10, 20),
            )
        )
    db_session.add(
        NotificationDigestQueue(
            provider_id=provider.id,
            event_type="print_complete",
            title="Own print finished",
            message="Ordinary digest remains title-only",
            printer_name="Own printer",
            created_at=datetime(2026, 10, 14, 10, 21),
        )
    )
    await db_session.commit()
    monkeypatch.setattr(database, "async_session", async_sessionmaker(test_engine, expire_on_commit=False))
    await notification_service.send_digest(provider.id)
    calls, violations = consumer
    assert not violations
    rendered = "".join(b["text"]["text"] for p in calls for b in p["blocks"])
    assert "10:21 [Own printer] Own print finished" in rendered
    assert "Ordinary digest remains title-only" not in rendered
    for index in range(count):
        assert f"@channel **full body {index}**\nhttps://example.com/{index}" in rendered
    assert all("@channel" not in p["text"] for p in calls)
    log = await db_session.scalar(select(NotificationLog).where(NotificationLog.event_type == "daily_digest"))
    assert log.success is True
    assert not list(await db_session.scalars(select(NotificationDigestQueue)))


@pytest.mark.parametrize("kind", ["ntfy", "email"])
@pytest.mark.parametrize("separator", ["\n", "\r\n", "\t"])
async def test_header_titles_rejected_before_delivery_or_quota(async_client, db_session, monkeypatch, kind, separator):
    _, key, provider = await setup(async_client)
    config = (
        {"topic": "fake", "server": "https://ntfy.example.com"}
        if kind == "ntfy"
        else {
            "smtp_server": "smtp.example.com",
            "from_email": "from@example.com",
            "to_email": "to@example.com",
            "security": "none",
            "auth_enabled": "false",
        }
    )
    await set_provider(db_session, provider["id"], kind, config)
    reached = []

    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def sendmail(self, sender, recipients, message):
            reached.append(message_from_string(message))

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP", SMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", SMTP)

    async def handle(request):
        reached.append(request)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))

    async def get_client():
        return client

    monkeypatch.setattr(notification_service, "_get_client", get_client)
    response = await async_client.post(
        "/api/v1/notifications/app-message",
        headers={"X-API-Key": key["key"]},
        json={"title": "Header" + separator + "Bcc: injected@example.com", "message": "Body\nline 2"},
    )
    assert response.status_code == 422
    assert not reached
    assert not list(await db_session.scalars(select(AppMessageQuota)))
    # A valid single-line Unicode subject keeps the body multiline on both real
    # serializers; only the final SMTP/HTTP connections are replaced.
    await send(async_client, key, "App ä <title>", "Body\nline 2")
    assert len(reached) == 1
    if kind == "ntfy":
        assert dict(reached[0].headers.raw)[b"Title"] == "App ä <title>".encode()
        assert reached[0].content.decode() == "Body\nline 2"
    else:
        from email.header import decode_header, make_header

        assert str(make_header(decode_header(reached[0]["Subject"]))) == "[PrintOps] App ä <title>"
        assert reached[0].get_payload()[0].get_payload(decode=True).decode() == "Body\nline 2"
    assert (await db_session.scalar(select(NotificationLog))).success is True
    await client.aclose()


async def test_pushover_long_unicode_message_and_url_split_losslessly(async_client, db_session, consumer):
    _, key, provider = await setup(async_client)
    await set_provider(db_session, provider["id"], "pushover", {"user_key": "fake", "app_token": "fake"})
    body, url = "😀<&>" * 500, "https://example.com/" + "x" * 450
    await send(async_client, key, "App", body, url=url)
    calls, violations = consumer
    assert calls and not violations
    assert "".join(p["message"] for p in calls) == body + "\n" + url
    assert all(p.get("html") != "1" for p in calls)
    assert (await db_session.scalar(select(NotificationLog))).success is True


async def test_user_delete_removes_only_owned_quota_without_sqlite_foreign_keys(async_client, db_session):
    admin, key, _ = await setup(async_client)
    assert await db_session.scalar(text("PRAGMA foreign_keys")) == 0
    response = await async_client.post(
        "/api/v1/users/",
        headers=admin,
        json={
            "username": "quota-owner",
            "password": "Password123!",
            "role": "user",
        },
    )
    assert response.status_code in (200, 201), response.text
    owner_id = response.json()["id"]
    owned_key = APIKey(name="Owned", key_hash="owned-hash", key_prefix="owned", user_id=owner_id)
    db_session.add(owned_key)
    await db_session.flush()
    admin_key = await db_session.get(APIKey, key["id"])
    db_session.add_all(
        [
            AppMessageQuota(key_hash=owned_key.key_hash, key_id=owned_key.id, timestamps=[1]),
            AppMessageQuota(key_hash=admin_key.key_hash, key_id=admin_key.id, timestamps=[1]),
        ]
    )
    await db_session.commit()
    response = await async_client.delete(f"/api/v1/users/{owner_id}", headers=admin)
    assert response.status_code == 204, response.text
    remaining = list(await db_session.scalars(select(AppMessageQuota.key_id)))
    assert remaining == [admin_key.id]


@pytest.mark.parametrize("binding", ["unbound", "reused_owner"])
async def test_admin_cannot_grant_old_owner_keys(async_client, db_session, binding):
    admin, key, _ = await setup(async_client, can_send_notifications=False)
    row = await db_session.get(APIKey, key["id"])
    if binding == "unbound":
        row.notification_owner_identity = None
    else:
        owner = User(username="original", is_active=True)
        db_session.add(owner)
        await db_session.flush()
        row.user_id, row.notification_owner_identity = owner.id, owner.connected_identity
        old_id = owner.id
        await db_session.commit()
        await db_session.execute(delete(User).where(User.id == old_id))
        await db_session.commit()
        replacement = User(username="replacement", is_active=True)
        db_session.add(replacement)
        await db_session.flush()
        assert replacement.id == old_id
    await db_session.commit()
    response = await async_client.patch(
        f"/api/v1/api-keys/{key['id']}", headers=admin, json={"can_send_notifications": True}
    )
    assert response.status_code == 403, response.text
    await db_session.refresh(row)
    assert row.can_send_notifications is False


async def test_telegram_app_digest_keeps_full_bodies_within_message_limits(
    async_client,
    db_session,
    test_engine,
    monkeypatch,
    consumer,
):
    _, _, provider_data = await setup(async_client)
    provider = await db_session.get(NotificationProvider, provider_data["id"])
    provider.daily_digest_enabled = True
    bodies = [f"entry{index}:" + "😀<&>" * 499 for index in range(3)]
    for body in bodies:
        db_session.add(
            NotificationDigestQueue(
                provider_id=provider.id,
                event_type="app_message",
                title="App",
                message=body,
            )
        )
    await db_session.commit()
    monkeypatch.setattr(database, "async_session", async_sessionmaker(test_engine, expire_on_commit=False))
    await notification_service.send_digest(provider.id)
    payloads, violations = consumer
    assert not violations
    assert all(len(p["text"].encode("utf-16-le")) // 2 <= 4096 and "parse_mode" not in p for p in payloads)
    rendered = "".join(p["text"] for p in payloads)
    assert all(body in rendered for body in bodies)
    assert (await db_session.scalar(select(NotificationLog))).success is True


@pytest.mark.parametrize("kind", ["webhook", "discord", "pushover", "telegram"])
async def test_partial_digest_failure_is_logged_and_keeps_unsent_queue(
    async_client,
    db_session,
    test_engine,
    monkeypatch,
    kind,
):
    _, _, provider_data = await setup(async_client)
    configs = {
        "webhook": {"webhook_url": "https://chat.example.com/hooks/fake", "payload_format": "slack"},
        "discord": {"webhook_url": "https://discord.com/api/webhooks/fake"},
        "pushover": {"user_key": "fake", "app_token": "fake"},
        "telegram": {"bot_token": "fake", "chat_id": "123"},
    }
    provider = await set_provider(db_session, provider_data["id"], kind, configs[kind])
    provider.daily_digest_enabled = True
    for index in range(4):
        db_session.add(
            NotificationDigestQueue(
                provider_id=provider.id,
                event_type="app_message",
                title=f"App {index}",
                message="&" * 2000,
            )
        )
    db_session.add(
        NotificationDigestQueue(
            provider_id=provider.id,
            event_type="print_complete",
            title="Own print",
            message="Trusted summary",
        )
    )
    await db_session.commit()
    monkeypatch.setattr(database, "async_session", async_sessionmaker(test_engine, expire_on_commit=False))
    calls = []

    async def handle(request):
        calls.append(request)
        return httpx.Response(200 if len(calls) == 1 else 503, json={"ok": len(calls) == 1})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:

        async def get_client():
            return client

        monkeypatch.setattr(notification_service, "_get_client", get_client)
        await notification_service.send_digest(provider.id)
    log = await db_session.scalar(select(NotificationLog).where(NotificationLog.event_type == "daily_digest"))
    assert log.success is False
    assert len(calls) == 2  # Stop on rejection; do not silently send later chunks.
    assert len(list(await db_session.scalars(select(NotificationDigestQueue)))) == 5


async def test_ordinary_digest_keeps_existing_summary_format(
    async_client, db_session, test_engine, monkeypatch, consumer
):
    _, _, provider_data = await setup(async_client)
    provider = await set_provider(
        db_session,
        provider_data["id"],
        "webhook",
        {
            "webhook_url": "https://chat.example.com/hooks/fake",
            "payload_format": "slack",
        },
    )
    provider.daily_digest_enabled = True
    db_session.add(
        NotificationDigestQueue(
            provider_id=provider.id,
            event_type="print_complete",
            title="Own print",
            message="Not in existing summary",
            printer_name="Own printer",
            created_at=datetime(2026, 10, 14, 10, 21),
        )
    )
    await db_session.commit()
    monkeypatch.setattr(database, "async_session", async_sessionmaker(test_engine, expire_on_commit=False))
    await notification_service.send_digest(provider.id)
    assert consumer[0] == [
        {"text": "*Daily Digest - 1 Events*\n== Print Complete (1) ==\n  10:21 [Own printer] Own print\n"}
    ]
    assert (await db_session.scalar(select(NotificationLog))).success is True
    assert not list(await db_session.scalars(select(NotificationDigestQueue)))
