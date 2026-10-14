"""Trusted Telegram actors may answer one current print run, once."""

import json
import re
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select, update

from backend.app.core.permissions import Permission
from backend.app.models.archive import PrintArchive
from backend.app.models.notification import NotificationProvider
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.settings import Settings
from backend.app.models.telegram_quality import TelegramQualityConfig, TelegramQualityMessage
from backend.app.models.user import User
from backend.app.services.print_confirmation import (
    OutcomeConflict,
    latest_run,
    outcome_lock,
    record_outcome,
    run_matches_archive,
)
from backend.app.services.quality_authorization import can_inspect_run


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def provider_config(provider):
    return json.loads(provider.config) if isinstance(provider.config, str) else provider.config


def bot_id(config):
    token = str(config.get("bot_token", "")).strip()
    prefix, separator, secret = token.partition(":")
    return (
        prefix
        if separator
        and secret
        and len(prefix) <= 16
        and prefix.isascii()
        and prefix.isdecimal()
        and 0 < int(prefix) < 2**52
        else None
    )


async def auth_enabled(db):
    # Read authoritative state, not the short-lived interactive-login cache.
    return (await db.scalar(select(Settings.value).where(Settings.key == "auth_enabled"))) == "true"


async def configure(db, provider, enabled, actors):
    if provider.provider_type != "telegram" or not await auth_enabled(db):
        raise HTTPException(409, "Telegram reactions require authentication and a Telegram provider")
    config = provider_config(provider)
    bot = bot_id(config)
    chat = str(config.get("chat_id", "")).strip()
    if not bot or not re.fullmatch(r"-?[1-9][0-9]{0,15}", chat) or abs(int(chat)) >= 2**52:
        raise HTTPException(422, "Use a bot token and numeric chat ID")
    if len(actors) > 100 or (enabled and not actors):
        raise HTTPException(422, "Configure between 1 and 100 trusted actors")
    bound, seen = [], set()
    existing = await db.scalar(select(TelegramQualityConfig).where(TelegramQualityConfig.provider_id == provider.id))
    for actor in actors:
        actor_id, user_id = actor.get("actor_id"), actor.get("user_id")
        if (
            type(actor_id) is not int
            or not 0 < actor_id < 2**52
            or type(user_id) is not int
            or not 0 < user_id < 2**31
            or actor_id in seen
        ):
            raise HTTPException(422, "Actor and user IDs must be positive integers; actors must be unique")
        user = await db.get(User, user_id, populate_existing=True)
        if not user or not user.is_active or not user.connected_identity:
            raise HTTPException(422, "Choose an active user")
        # An unchanged mapping must never silently adopt a replacement account.
        old = (
            next((a for a in existing.actors if a["actor_id"] == actor_id and a["user_id"] == user_id), None)
            if existing
            else None
        )
        if old and old["identity"] != user.connected_identity:
            raise HTTPException(409, "Remove the stale mapping before binding a replacement user")
        bound.append({"actor_id": actor_id, "user_id": user_id, "identity": user.connected_identity})
        seen.add(actor_id)
    duplicate = await db.scalar(
        select(TelegramQualityConfig.id).where(
            TelegramQualityConfig.bot_id == bot,
            TelegramQualityConfig.enabled.is_(True),
            TelegramQualityConfig.provider_id != provider.id,
        )
    )
    if enabled and duplicate:
        raise HTTPException(409, "This bot already has a reaction polling provider")
    if existing is None:
        existing = TelegramQualityConfig(provider_id=provider.id, bot_id=bot)
        db.add(existing)
    if existing.id and (existing.bot_id != bot or existing.enabled != enabled or existing.actors != bound):
        await invalidate_provider(db, provider.id)
    existing.bot_id, existing.enabled, existing.actors = bot, enabled, bound
    await db.flush()
    return existing


async def active_config(db, config_id):
    config = await db.get(TelegramQualityConfig, config_id, populate_existing=True)
    if not config or not config.enabled or not await auth_enabled(db):
        return None
    provider = await db.get(NotificationProvider, config.provider_id, populate_existing=True)
    if (
        not provider
        or not provider.enabled
        or provider.provider_type != "telegram"
        or not provider.on_print_confirm_request
    ):
        return None
    if bot_id(provider_config(provider)) != config.bot_id:
        return None
    return config, provider


async def bind_message(db, provider, sent, archive_id, run_id, *, expected_revision=None):
    if type(sent.get("message_id")) is not int or sent["message_id"] <= 0 or type(sent.get("chat_id")) is not int:
        return False
    config = await db.scalar(select(TelegramQualityConfig).where(TelegramQualityConfig.provider_id == provider.id))
    if not config or not await active_config(db, config.id):
        return False
    if expected_revision is not None and config.revision != expected_revision:
        return False
    # Fence issuance against settings edits in another process. This write lock
    # starts only after the network response and lasts through binding commit.
    fenced = await db.execute(
        update(TelegramQualityConfig)
        .where(
            TelegramQualityConfig.id == config.id,
            TelegramQualityConfig.revision == config.revision,
            TelegramQualityConfig.enabled.is_(True),
        )
        .values(revision=config.revision)
    )
    if fenced.rowcount != 1:
        return False
    if str(sent["chat_id"]) != str(provider_config(provider).get("chat_id", "")).strip():
        return False
    archive, run = await db.get(PrintArchive, archive_id), await latest_run(db, archive_id)
    if (
        not archive
        or not run
        or run.id != run_id
        or not run_matches_archive(run, archive)
        or not run.confirm_requested
        or not run.confirm_token_hash
        or run.confirm_prompted_at is None
        or not run.confirm_token_expires_at
        or run.good_quantity is not None
        or run.confirm_token_used_at
        or run.confirm_token_expires_at <= now()
    ):
        return False
    owner_identity = archive.created_by_identity
    db.add(
        TelegramQualityMessage(
            config_id=config.id,
            config_revision=config.revision,
            bot_id=config.bot_id,
            **sent,
            archive_id=archive_id,
            run_id=run_id,
            quantity=run.quantity,
            token_hash=run.confirm_token_hash,
            expires_at=run.confirm_token_expires_at,
            owner_id=archive.created_by_id,
            owner_identity=owner_identity,
        )
    )
    await db.flush()
    return True


async def apply_reaction(db, config_id, payload, *, commit=None, guard=None):
    """Caller commits inside the shared outcome lock; poller also commits its cursor."""
    event = payload.get("message_reaction")
    if not isinstance(event, dict) or event.get("actor_chat") or not isinstance(event.get("user"), dict):
        return False
    actor_id = event["user"].get("id")
    if type(actor_id) is not int or actor_id <= 0 or event["user"].get("is_bot"):
        return False
    reactions = event.get("new_reaction")
    if (
        not isinstance(reactions, list)
        or len(reactions) != 1
        or reactions[0] not in ({"type": "emoji", "emoji": "👍"}, {"type": "emoji", "emoji": "👎"})
    ):
        return False
    if not isinstance(event.get("chat"), dict):
        return False
    chat_id, message_id = event["chat"].get("id"), event.get("message_id")
    if type(chat_id) is not int or type(message_id) is not int or message_id <= 0:
        return False
    binding = await db.scalar(
        select(TelegramQualityMessage).where(
            TelegramQualityMessage.config_id == config_id,
            TelegramQualityMessage.chat_id == chat_id,
            TelegramQualityMessage.message_id == message_id,
        )
    )
    if not binding:
        return False
    # Lock config before archive/outcome, matching send and revocation order.
    # If revocation commits first, its revision makes this a no-op; otherwise
    # revocation cannot return until this decision and cursor have committed.
    fenced = await db.execute(
        update(TelegramQualityConfig)
        .where(
            TelegramQualityConfig.id == config_id,
            TelegramQualityConfig.revision == binding.config_revision,
            TelegramQualityConfig.enabled.is_(True),
        )
        .values(revision=binding.config_revision)
    )
    if fenced.rowcount != 1:
        return False
    async with outcome_lock(db, binding.archive_id, binding.run_id):
        if guard and not await guard():
            return False
        match = await active_config(db, config_id)
        if not match:
            return False
        config, provider = match
        if config.revision != binding.config_revision:
            return False
        if config.bot_id != binding.bot_id or str(chat_id) != str(provider_config(provider).get("chat_id", "")).strip():
            return False
        actor = next((a for a in config.actors if a["actor_id"] == actor_id), None)
        user = await db.get(User, actor["user_id"], populate_existing=True) if actor else None
        archive = await db.get(PrintArchive, binding.archive_id, populate_existing=True)
        run = await db.get(PrintLogEntry, binding.run_id, populate_existing=True)
        if (
            not user
            or not user.is_active
            or not user.connected_identity
            or user.connected_identity != actor["identity"]
        ):
            return False
        if (
            not archive
            or not run
            or run.quantity != binding.quantity
            or binding.expires_at <= now()
            or (provider.printer_id is not None and provider.printer_id != run.printer_id)
        ):
            return False
        can_all = user.has_permission(Permission.ARCHIVES_UPDATE_ALL.value)
        if not can_inspect_run(user, can_all, archive, run):
            return False
        if not can_all and not (
            user.has_permission(Permission.ARCHIVES_UPDATE_OWN.value)
            and archive.created_by_id == user.id == binding.owner_id
            and user.connected_identity == binding.owner_identity == archive.created_by_identity
        ):
            return False
        good = reactions[0]["emoji"] == "👍"
        try:
            await record_outcome(
                db,
                archive,
                run_id=run.id,
                token_hash=binding.token_hash,
                source="telegram",
                good_quantity=run.quantity if good else 0,
                reject_quantity=0 if good else run.quantity,
            )
        except OutcomeConflict:
            return False
        await db.delete(binding)
        await (commit() if commit else db.commit())
        return True


async def send_quality_prompt(service, db, provider, config, message, image_data, outcome_urls, context):
    from backend.app.services.notification_telegram import send_telegram

    settings = await db.scalar(select(TelegramQualityConfig).where(TelegramQualityConfig.provider_id == provider.id))
    revision = settings.revision if settings and await active_config(db, settings.id) else None
    sent = {}
    result = await send_telegram(service, config, message, image_data, outcome_urls, sent_message=sent)
    if result[0] and sent and revision is not None:
        await bind_message(db, provider, sent, *context, expected_revision=revision)
        await db.commit()
    return result


async def invalidate_provider(db, provider_id):
    configs = select(TelegramQualityConfig.id).where(TelegramQualityConfig.provider_id == provider_id)
    await db.execute(
        update(TelegramQualityConfig)
        .where(TelegramQualityConfig.provider_id == provider_id)
        .values(revision=secrets.token_hex(16))
    )
    await db.execute(delete(TelegramQualityMessage).where(TelegramQualityMessage.config_id.in_(configs)))
