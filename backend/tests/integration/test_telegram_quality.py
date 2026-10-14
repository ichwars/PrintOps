"""Real run, permission and persisted reaction state; only Telegram transport is fake."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.app.models.archive import PrintArchive
from backend.app.models.notification import NotificationProvider
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.settings import Settings
from backend.app.models.user import User
from backend.app.services import telegram_quality as quality


@pytest.fixture
async def context(db_session):
    db = db_session
    user = User(username="operator", role="admin", groups=[])
    db.add_all([user, Settings(key="auth_enabled", value="true")])
    await db.flush()
    archive = PrintArchive(
        filename="parts.3mf", file_path="/none", file_size=1, status="completed", quantity=7, created_by_id=user.id
    )
    provider = NotificationProvider(
        name="Telegram",
        provider_type="telegram",
        config=json.dumps({"bot_token": "123:fake", "chat_id": "-100"}),
        enabled=True,
    )
    db.add_all([archive, provider])
    await db.flush()
    run = PrintLogEntry(
        archive_id=archive.id,
        status="completed",
        quantity=7,
        confirm_requested=True,
        confirm_prompted_at=datetime.now(timezone.utc).replace(tzinfo=None),
        confirm_token_hash="a" * 64,
        confirm_token_expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=48),
    )
    db.add(run)
    await db.commit()
    config = await quality.configure(db, provider, True, [{"actor_id": 42, "user_id": user.id}])
    await quality.bind_message(db, provider, {"chat_id": -100, "message_id": 12}, archive.id, run.id)
    await db.commit()
    return db, user, archive, run, provider, config


def reaction(emoji="👍", **changes):
    event = {
        "chat": {"id": -100},
        "message_id": 12,
        "user": {"id": 42},
        "date": int(datetime.now(timezone.utc).timestamp()),
        "old_reaction": [],
        "new_reaction": [{"type": "emoji", "emoji": emoji}],
    }
    event.update(changes)
    return {"update_id": 1, "message_reaction": event}


@pytest.mark.parametrize("emoji,good,reject", [("👍", 7, 0), ("👎", 0, 7)])
async def test_valid_exact_parts_first_answer(context, emoji, good, reject):
    db, user, archive, run, provider, config = context
    assert await quality.apply_reaction(db, config.id, reaction(emoji))
    await db.commit()
    assert (run.good_quantity, run.reject_quantity, archive.user_verdict) == (
        good,
        reject,
        "good" if good else "reject",
    )
    assert not await quality.apply_reaction(db, config.id, reaction("👎" if good else "👍"))
    assert (run.good_quantity, run.reject_quantity) == (good, reject)


@pytest.mark.parametrize(
    "change",
    [
        "unknown_actor",
        "anonymous",
        "count_only",
        "chat",
        "message",
        "provider",
        "disabled",
        "auth_off",
        "inactive",
        "permission",
        "owner",
        "printer",
        "archive_printer",
        "expired",
        "mixed",
        "quantity",
        "new_run",
        "reused_archive",
        "token",
        "removed",
        "both",
        "custom",
    ],
)
async def test_denied_without_mutation(context, change):
    db, user, archive, run, provider, config = context
    event = reaction()
    item = event["message_reaction"]
    if change == "unknown_actor":
        item["user"]["id"] = 43
    elif change == "anonymous":
        item.pop("user")
        item["actor_chat"] = {"id": 42}
    elif change == "count_only":
        event = {"update_id": 1, "message_reaction_count": item}
    elif change == "chat":
        item["chat"]["id"] = -101
    elif change == "message":
        item["message_id"] = 13
    elif change == "provider":
        provider.provider_type = "webhook"
    elif change == "disabled":
        config.enabled = False
    elif change == "auth_off":
        (await db.scalar(select(Settings).where(Settings.key == "auth_enabled"))).value = "false"
    elif change == "inactive":
        user.is_active = False
    elif change == "permission":
        user.role = "user"
    elif change == "owner":
        from backend.app.core.permissions import Permission
        from backend.app.models.group import Group

        user.role = "user"
        user.groups = [Group(name="own", permissions=[Permission.ARCHIVES_UPDATE_OWN.value])]
        archive.created_by_id = None
    elif change == "printer":
        run.printer_id = 999
        user.allowed_printer_ids = []
    elif change == "archive_printer":
        archive.printer_id = 999
        user.allowed_printer_ids = []
    elif change == "expired":
        run.confirm_token_expires_at = datetime(2000, 1, 1)
    elif change == "mixed":
        run.good_quantity = 4
        run.reject_quantity = 3
        run.user_verdict = "mixed"
    elif change == "quantity":
        run.quantity = 8
    elif change == "new_run":
        db.add(PrintLogEntry(archive_id=archive.id, status="completed", quantity=7))
    elif change == "reused_archive":
        archive.status = "printing"
    elif change == "token":
        run.confirm_token_hash = "b" * 64
    elif change == "removed":
        item["new_reaction"] = []
    elif change == "both":
        item["new_reaction"].append({"type": "emoji", "emoji": "👎"})
    elif change == "custom":
        item["new_reaction"] = [{"type": "custom_emoji", "emoji": "👍"}]
    await db.commit()
    assert not await quality.apply_reaction(db, config.id, event)
    await db.refresh(run)
    assert run.good_quantity == (4 if change == "mixed" else None)


async def test_deleted_highest_user_id_never_rebinds(context):
    db, user, archive, run, provider, config = context
    old_id, identity = user.id, user.connected_identity
    await db.delete(user)
    await db.commit()
    replacement = User(username="replacement", role="admin", groups=[])
    db.add(replacement)
    await db.commit()
    assert replacement.id == old_id
    assert replacement.connected_identity != identity
    assert not await quality.apply_reaction(db, config.id, reaction())
    assert run.good_quantity is None


@pytest.mark.parametrize("message_id", [0, -1, True, "12", None])
async def test_only_positive_concrete_sent_message(context, message_id):
    db, user, archive, run, provider, config = context
    assert not await quality.bind_message(db, provider, {"chat_id": -100, "message_id": message_id}, archive.id, run.id)


async def test_own_scope_generation_and_mapping_removal(context):
    from backend.app.core.permissions import Permission
    from backend.app.models.group import Group
    from backend.app.models.telegram_quality import TelegramQualityMessage

    db, user, archive, run, provider, config = context
    user.role = "user"
    user.groups = [Group(name="inspect-own", permissions=[Permission.ARCHIVES_UPDATE_OWN.value])]
    binding = await db.scalar(select(TelegramQualityMessage))
    assert binding.owner_identity == archive.created_by_identity == user.connected_identity
    await db.commit()
    await quality.configure(db, provider, False, [])
    await db.commit()
    assert not await quality.apply_reaction(db, config.id, reaction())
    await quality.configure(db, provider, True, [{"actor_id": 42, "user_id": user.id}])
    await db.commit()
    assert not await quality.apply_reaction(db, config.id, reaction())
    assert await quality.bind_message(db, provider, {"message_id": 13, "chat_id": -100}, archive.id, run.id)
    await db.commit()
    assert await quality.apply_reaction(db, config.id, reaction(message_id=13))


async def test_historical_and_uncommitted_prompt_cannot_bind(context):
    db, user, archive, run, provider, config = context
    for field in ["confirm_token_hash", "confirm_prompted_at"]:
        previous = getattr(run, field)
        setattr(run, field, None)
        await db.commit()
        assert not await quality.bind_message(db, provider, {"message_id": 13, "chat_id": -100}, archive.id, run.id)
        setattr(run, field, previous)
    await db.commit()
    assert not await quality.bind_message(db, provider, {"message_id": 13, "chat_id": -100}, archive.id, run.id + 1)


async def test_no_commerce_side_effects(context):
    from backend.app.core.database import Base

    db, user, archive, run, provider, config = context
    protected = [
        table
        for name, table in Base.metadata.tables.items()
        if any(part in name for part in ("stock", "inventory", "delivery", "shipment", "invoice", "customer_order"))
    ]
    before = {table.name: (await db.execute(select(table))).all() for table in protected}
    assert await quality.apply_reaction(db, config.id, reaction("👎"))
    assert before == {table.name: (await db.execute(select(table))).all() for table in protected}


async def test_actual_prompt_delivery_policy(context, monkeypatch):
    from unittest.mock import AsyncMock

    import httpx
    from sqlalchemy import delete

    from backend.app.models.notification import NotificationDigestQueue, NotificationLog
    from backend.app.models.telegram_quality import TelegramQualityMessage
    from backend.app.services.notification_service import NotificationService

    db, user, archive, run, provider, config = context
    await db.execute(delete(TelegramQualityMessage))
    provider.daily_digest_enabled = True
    provider.daily_digest_time = "08:00"
    await db.commit()
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 88, "chat": {"id": -100}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        service = NotificationService()
        monkeypatch.setattr(service, "_get_client", AsyncMock(return_value=client))
        await service.on_print_confirm_request(
            1,
            "Printer",
            db,
            print_name="Seven parts",
            confirm_url="https://printops.test/archives?confirm=1",
            outcome_urls={"good": "https://printops.test/good", "reject": "https://printops.test/reject"},
            archive_id=archive.id,
            run_id=run.id,
        )
        binding = await db.scalar(select(TelegramQualityMessage))
        assert binding.message_id == 88 and binding.quantity == 7
        assert await db.scalar(select(NotificationLog.id))
        assert await db.scalar(select(NotificationDigestQueue.id))
        provider.quiet_hours_enabled = True
        provider.quiet_hours_start = "00:00"
        provider.quiet_hours_end = "23:59"
        await db.commit()
        await service.on_print_confirm_request(
            1,
            "Printer",
            db,
            print_name="Quiet",
            confirm_url="https://printops.test/",
            outcome_urls={},
            archive_id=archive.id,
            run_id=run.id,
        )
    assert len(requests) == 1
    assert "_telegram_quality_context" not in requests[0].content.decode()


async def test_settings_change_during_send_cannot_issue_new_binding(context, monkeypatch):
    from unittest.mock import AsyncMock

    import httpx

    from backend.app.models.telegram_quality import TelegramQualityMessage
    from backend.app.services.notification_service import NotificationService

    db, user, archive, run, provider, config = context

    async def handle(request):
        await quality.invalidate_provider(db, provider.id)
        await db.commit()
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 99, "chat": {"id": -100}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        service = NotificationService()
        monkeypatch.setattr(service, "_get_client", AsyncMock(return_value=client))
        await service.on_print_confirm_request(
            1,
            "Printer",
            db,
            print_name="parts",
            confirm_url="https://printops.test/",
            outcome_urls={},
            archive_id=archive.id,
            run_id=run.id,
        )
    assert await db.scalar(select(TelegramQualityMessage.id)) is None


async def test_same_second_owner_can_confirm(context):
    from backend.app.core.permissions import Permission
    from backend.app.models.group import Group

    db, user, archive, run, provider, config = context
    assert archive.created_by_identity == user.connected_identity
    archive.created_at = user.created_at  # Deterministic same-second timestamp metadata.
    user.role = "user"
    user.groups = [Group(name="same-second-owner", permissions=[Permission.ARCHIVES_UPDATE_OWN.value])]
    await db.commit()
    assert await quality.apply_reaction(db, config.id, reaction())
