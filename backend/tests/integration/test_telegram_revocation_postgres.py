"""Real PostgreSQL transactions serialize reaction decisions with administrative revocation."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.database import Base
from backend.app.models.notification import NotificationProvider
from backend.app.services import telegram_quality as quality
from backend.tests.integration.test_telegram_quality import context, reaction


@pytest.fixture
async def db_session():
    dsn = os.environ.get("F01_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set F01_TEST_POSTGRES_DSN for isolated PostgreSQL transaction verification")
    schema = "o17_revoke_" + uuid4().hex
    admin = create_async_engine(dsn)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            yield db
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.mark.parametrize("remove_actor", [False, True])
async def test_revoke_cannot_return_before_inflight_reaction_commit(context, monkeypatch, remove_actor):
    db, user, archive, run, provider, config = context
    sessions = async_sessionmaker(db.bind, expire_on_commit=False)
    validated, release = asyncio.Event(), asyncio.Event()
    original = quality.active_config
    order = []

    async def pause_after_read(session, config_id):
        result = await original(session, config_id)
        validated.set()
        await release.wait()
        return result

    monkeypatch.setattr(quality, "active_config", pause_after_read)

    async def answer():
        async with sessions() as session:
            result = await quality.apply_reaction(session, config.id, reaction())
            order.append("reaction committed")
            return result

    async def revoke():
        async with sessions() as session:
            p = await session.get(NotificationProvider, provider.id)
            await quality.configure(
                session, p, remove_actor, [{"actor_id": 43 if remove_actor else 42, "user_id": user.id}]
            )
            await session.commit()
            order.append("revocation committed")

    answering = asyncio.create_task(answer())
    await asyncio.wait_for(validated.wait(), 5)
    revoking = asyncio.create_task(revoke())
    try:
        done, _ = await asyncio.wait([revoking], timeout=0.2)
        assert not done, "revocation returned while a previously validated reaction can still commit"
    finally:
        release.set()
        results = await asyncio.wait_for(asyncio.gather(answering, revoking), 5)
    assert results[0] is True
    assert order == ["reaction committed", "revocation committed"]


@pytest.mark.parametrize("remove_actor", [False, True])
async def test_revocation_winning_transaction_denies_stale_reaction(context, remove_actor):
    db, user, archive, run, provider, config = context
    sessions = async_sessionmaker(db.bind, expire_on_commit=False)
    async with sessions() as editor:
        p = await editor.get(NotificationProvider, provider.id)
        await quality.configure(editor, p, remove_actor, [{"actor_id": 43 if remove_actor else 42, "user_id": user.id}])

        async def answer():
            async with sessions() as session:
                result = await quality.apply_reaction(session, config.id, reaction())
                await session.commit()
                return result

        answering = asyncio.create_task(answer())
        try:
            done, _ = await asyncio.wait([answering], timeout=0.2)
            assert not done, "reaction bypassed an uncommitted revocation fence"
        finally:
            await editor.commit()
            result = await asyncio.wait_for(answering, 5)
    assert result is False
    await db.refresh(run)
    assert run.good_quantity is None
