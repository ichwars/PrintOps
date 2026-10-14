"""Add lookup/retention indexes to existing reaction bindings without rewriting data."""

from sqlalchemy import inspect

from backend.app.models.telegram_quality import TelegramQualityMessage


async def migrate_telegram_quality_indexes(conn):
    if await conn.run_sync(lambda sync: inspect(sync).has_table("telegram_quality_messages")):
        for index in TelegramQualityMessage.__table__.indexes:
            await conn.run_sync(lambda sync, index=index: index.create(sync, checkfirst=True))
