"""Credential and destination writes are validated within one transaction."""

import asyncio
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from backend.app.api.routes import settings
from backend.app.core.config import settings as app_settings
from backend.app.models.settings import Settings
from backend.app.schemas.settings import AppSettingsUpdate
from backend.app.services.mqtt_relay import mqtt_relay


@pytest.mark.asyncio
@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
async def test_concurrent_mqtt_update_cannot_retarget_a_newly_saved_password(dialect, tmp_path, monkeypatch):
    if dialect == "postgresql":
        url = os.getenv("PRINTOPS_POSTGRES_TEST_URL")
        if not url:
            pytest.skip("Requires a disposable PostgreSQL server")
        schema = f"credential_edit_{uuid4().hex}"
    else:
        url = f"sqlite+aiosqlite:///{tmp_path / 'credential-edits.db'}"
        schema = None
    monkeypatch.setattr(app_settings, "database_url", url)
    monkeypatch.setattr(mqtt_relay, "configure", AsyncMock())
    engine = create_async_engine(url)
    try:
        if schema:
            async with engine.begin() as connection:
                await connection.execute(CreateSchema(schema))
        scoped = engine.execution_options(schema_translate_map={None: schema})
        async with scoped.begin() as connection:
            await connection.run_sync(Settings.__table__.create)
        sessions = async_sessionmaker(scoped, expire_on_commit=False)
        async with sessions() as first_session, sessions() as second_session:
            first_locked = asyncio.Event()
            second_started = asyncio.Event()
            finish_first = asyncio.Event()
            original_lock = settings.lock_settings_credentials

            async def pause_after_lock(db):
                if db is second_session:
                    second_started.set()
                await original_lock(db)
                if db is first_session:
                    first_locked.set()
                    await finish_first.wait()

            monkeypatch.setattr(settings, "lock_settings_credentials", pause_after_lock)
            first = asyncio.create_task(
                settings.update_settings(
                    AppSettingsUpdate(mqtt_broker="mqtt.local", mqtt_password="fixture-password"),
                    db=first_session,
                    current_user=None,
                )
            )
            second = None
            try:
                await asyncio.wait_for(first_locked.wait(), 5)
                second = asyncio.create_task(
                    settings.update_settings(
                        AppSettingsUpdate(mqtt_broker="foreign.local"),
                        db=second_session,
                        current_user=None,
                    )
                )
                await asyncio.wait_for(second_started.wait(), 5)
                completed, _ = await asyncio.wait({second}, timeout=0.05)
                assert not completed
                finish_first.set()
                await asyncio.wait_for(first, 5)
                with pytest.raises(HTTPException) as refused:
                    await asyncio.wait_for(second, 5)
                assert refused.value.status_code == 400
            finally:
                for task in (first, second):
                    if task is not None and not task.done():
                        task.cancel()
                await asyncio.gather(*(task for task in (first, second) if task is not None), return_exceptions=True)

        async with sessions() as reader:
            result = await reader.execute(select(Settings.key, Settings.value))
            assert dict(result.all()) == {"mqtt_broker": "mqtt.local", "mqtt_password": "fixture-password"}
    finally:
        if schema:
            async with engine.begin() as connection:
                await connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        await engine.dispose()
