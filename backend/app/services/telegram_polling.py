"""One durable, fenced polling owner per Telegram bot. Never changes webhooks."""

import asyncio
import logging
import secrets
from datetime import timedelta

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from backend.app.models.telegram_quality import TelegramPollState, TelegramQualityConfig
from backend.app.services.telegram_quality import active_config, apply_reaction, now, provider_config

logger = logging.getLogger(__name__)
LEASE = timedelta(seconds=60)


async def claim(sessions, bot, owner):
    async with sessions() as db:
        if await db.get(TelegramPollState, bot) is None:
            db.add(TelegramPollState(bot_id=bot))
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()  # Another worker initialized it.
        result = await db.execute(
            update(TelegramPollState)
            .where(
                TelegramPollState.bot_id == bot,
                or_(TelegramPollState.lease_until.is_(None), TelegramPollState.lease_until <= now()),
            )
            .values(lease_owner=owner, lease_until=now() + LEASE)
        )
        await db.commit()
        return result.rowcount == 1


async def fence(db, bot, owner):
    # Acquires the row write lock until the decision/cursor transaction commits.
    result = await db.execute(
        update(TelegramPollState)
        .where(
            TelegramPollState.bot_id == bot,
            TelegramPollState.lease_owner == owner,
            TelegramPollState.lease_until > now(),
        )
        .values(lease_until=now() + LEASE)
    )
    return result.rowcount == 1


async def poll_once(sessions, client, config_id):
    async with sessions() as db:
        match = await active_config(db, config_id)
        if not match:
            return False
        config, provider = match
        bot, token = config.bot_id, provider_config(provider)["bot_token"].strip()
    owner = secrets.token_hex(16)
    if not await claim(sessions, bot, owner):
        return False
    status = "transport_error"
    try:
        url = f"https://api.telegram.org/bot{token}/"
        webhook = await client.post(url + "getWebhookInfo", json={}, timeout=10)
        webhook.raise_for_status()
        info = webhook.json()
        if not info.get("ok") or not isinstance(info.get("result"), dict):
            return False
        if info["result"].get("url"):
            status = "webhook_conflict"
            return False
        async with sessions() as db:
            state = await db.get(TelegramPollState, bot)
            payload = {"allowed_updates": ["message_reaction"], "timeout": 0, "limit": 100}
            if state.cursor is not None and state.last_update_at and state.last_update_at > now() - timedelta(days=6):
                payload["offset"] = state.cursor + 1
        # Only committed cursors reach Telegram's acknowledgement boundary.
        response = await client.post(url + "getUpdates", json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        if not result.get("ok") or not isinstance(result.get("result"), list):
            return False
        for event in result["result"]:
            if not isinstance(event, dict) or type(event.get("update_id")) is not int or event["update_id"] < 0:
                continue
            async with sessions() as db:
                state = await db.get(TelegramPollState, bot)
                if (
                    state.cursor is not None
                    and state.last_update_at
                    and state.last_update_at > now() - timedelta(days=6)
                    and event["update_id"] <= state.cursor
                ):
                    await db.commit()
                    continue

                async def commit_decision(state=state, event=event):
                    if not await fence(db, bot, owner):
                        await db.rollback()
                        raise ValueError("Polling lease lost")
                    state.cursor, state.last_update_at = event["update_id"], now()
                    await db.commit()

                applied = await apply_reaction(
                    db, config_id, event, commit=commit_decision, guard=lambda: fence(db, bot, owner)
                )
                if not applied:
                    await commit_decision()
        status = "polling"
        return True
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        # Never log HTTP exception text: it contains bot tokens and webhook URLs.
        return False
    finally:
        async with sessions() as db:
            await db.execute(
                update(TelegramPollState)
                .where(
                    TelegramPollState.bot_id == bot,
                    TelegramPollState.lease_owner == owner,
                )
                .values(
                    lease_owner=None,
                    lease_until=None if status == "polling" else now() + timedelta(minutes=5),
                    status=status,
                )
            )
            await db.commit()


async def run_polling(sessions):
    async with httpx.AsyncClient() as client:
        while True:
            try:
                async with sessions() as db:
                    ids = list(
                        (
                            await db.scalars(
                                select(TelegramQualityConfig.id).where(TelegramQualityConfig.enabled.is_(True))
                            )
                        ).all()
                    )
                for config_id in ids:
                    await poll_once(sessions, client, config_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Telegram quality polling unavailable")
            await asyncio.sleep(5)


_task = None


def start():
    global _task
    from backend.app.core.database import async_session

    if _task is None or _task.done():
        _task = asyncio.create_task(run_polling(async_session))


async def stop():
    global _task
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
