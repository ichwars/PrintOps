"""Upgrade compatibility and quota serialization on real database connections."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.app_message_migration import migrate_notification_options
from backend.app.core.database import Base, _safe_execute
from backend.app.models.api_key import APIKey, AppMessageQuota
from backend.app.models.notification import NotificationProvider
from backend.app.services.app_messages import consume_quota


@pytest.fixture(params=["sqlite", "postgresql"])
async def storage(request, tmp_path, test_engine):
    dialect = request.param
    dsn = (
        f"sqlite+aiosqlite:///{tmp_path / 'storage.db'}" if dialect == "sqlite" else os.getenv("F01_TEST_POSTGRES_DSN")
    )
    if not dsn:
        pytest.skip("F01_TEST_POSTGRES_DSN must point to an isolated disposable PostgreSQL database")
    schema = "o16_" + uuid4().hex
    admin = create_async_engine(dsn)
    if dialect == "postgresql":
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
    else:
        engine = admin
    try:
        async with engine.begin() as conn:
            # Register all models through test_engine, then create the app tables
            # and their referenced users/groups/printers in an isolated schema.
            await conn.run_sync(Base.metadata.create_all)
        yield engine, dsn
    finally:
        await engine.dispose()
        if dialect == "postgresql":
            async with admin.begin() as conn:
                await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin.dispose()


async def test_existing_rows_remain_opted_out_and_repeat_upgrade(storage):
    engine, _ = storage
    async with engine.begin() as conn:
        await conn.execute(APIKey.__table__.insert().values(id=1, name="Legacy", key_hash="fake", key_prefix="fake"))
        await conn.execute(
            NotificationProvider.__table__.insert().values(id=1, name="Legacy", provider_type="ntfy", config="{}")
        )
        for table, field in (
            ("api_keys", "can_send_notifications"),
            ("api_keys", "notification_owner_identity"),
            ("notification_providers", "on_app_message"),
        ):
            await conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {field}"))
        await migrate_notification_options(conn, _safe_execute)
        assert (await conn.execute(text("SELECT can_send_notifications FROM api_keys"))).scalar_one() in (False, 0)
        assert (await conn.execute(text("SELECT notification_owner_identity FROM api_keys"))).scalar_one() is None
        assert (await conn.execute(text("SELECT on_app_message FROM notification_providers"))).scalar_one() in (
            False,
            0,
        )
        await conn.execute(text("UPDATE api_keys SET can_send_notifications=TRUE"))
        await conn.execute(text("UPDATE notification_providers SET on_app_message=TRUE"))
        await migrate_notification_options(conn, _safe_execute)
        assert (await conn.execute(text("SELECT can_send_notifications FROM api_keys"))).scalar_one() in (True, 1)
        assert (await conn.execute(text("SELECT on_app_message FROM notification_providers"))).scalar_one() in (True, 1)


async def test_atomic_quota_across_connections_and_restart(storage):
    engine, _ = storage
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as db:
        key = APIKey(id=1, name="App", key_hash="isolated-fake-hash", key_prefix="fake")
        db.add(key)
        await db.commit()

    async def consume():
        async with sessions() as db:
            try:
                await consume_quota(db, key)
                return 200
            except HTTPException as exc:
                return exc.status_code

    results = await asyncio.gather(*(consume() for _ in range(40)))
    assert sorted(results) == [200] * 20 + [429] * 20
    await engine.dispose()
    assert await consume() == 429
    async with sessions() as db:
        quota = await db.scalar(select(AppMessageQuota))
        assert len(quota.timestamps) == 20


async def test_real_worker_processes_share_sqlite_quota(tmp_path, test_engine):
    dsn = f"sqlite+aiosqlite:///{tmp_path / 'workers.db'}"
    engine = create_async_engine(dsn)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            APIKey.__table__.insert().values(id=1, name="Workers", key_hash="worker-hash", key_prefix="fake")
        )
    script = """
import asyncio, sys
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.app.services.app_messages import consume_quota
async def main():
    engine = create_async_engine(sys.argv[1], connect_args={"timeout": 30})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    successes = 0
    for _ in range(15):
        async with sessions() as db:
            try:
                await consume_quota(db, SimpleNamespace(id=1, key_hash="worker-hash"))
                successes += 1
            except HTTPException as exc:
                assert exc.status_code == 429
    await engine.dispose()
    print(successes)
asyncio.run(main())
"""

    def run_worker():
        # CI invokes pytest from backend/; a fresh Python process does not inherit
        # pytest's sys.path additions. Resolve the package root from this file.
        try:
            return subprocess.run(
                [sys.executable, "-c", script, dsn],
                cwd=Path(__file__).resolve().parents[3],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            pytest.fail(
                f"Quota worker exited {exc.returncode}.\nstdout:\n{exc.stdout}\nstderr:\n{exc.stderr}",
                pytrace=False,
            )

    try:
        workers = await asyncio.gather(asyncio.to_thread(run_worker), asyncio.to_thread(run_worker))
        assert sum(int(result.stdout.strip()) for result in workers) == 20
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            with pytest.raises(HTTPException) as exc:
                await consume_quota(db, SimpleNamespace(id=1, key_hash="worker-hash"))
            assert exc.value.status_code == 429
    finally:
        await engine.dispose()
