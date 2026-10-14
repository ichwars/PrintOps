"""File-backed SQLite browser/Telegram races use the real inspection route and CAS."""

import asyncio
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.api.routes.archives_runs import confirm_production_outcome
from backend.app.core.database import Base
from backend.app.schemas.archive import OutcomeConfirmation
from backend.app.services import print_confirmation, telegram_quality
from backend.tests.integration.test_telegram_quality import context, reaction


@pytest.fixture(params=["DELETE", "WAL"])
async def db_session(tmp_path, request):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'inspection.db'}", connect_args={"timeout": 0.2})
    async with engine.begin() as conn:
        await conn.execute(text(f"PRAGMA journal_mode={request.param}"))
        await conn.run_sync(Base.metadata.create_all)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            yield db
    finally:
        await engine.dispose()


@pytest.mark.parametrize("first", ["browser", "telegram"])
async def test_browser_reaction_lock_order_preserves_mixed_inspection(context, monkeypatch, first):
    db, user, archive, run, provider, config = context
    sessions = async_sessionmaker(db.bind, expire_on_commit=False)
    first_locked, second_waiting = asyncio.Event(), asyncio.Event()
    original_lock = print_confirmation.outcome_lock
    original_record = print_confirmation.record_outcome

    async def pause_first_record(*args, **kwargs):
        first_locked.set()  # Real route/reaction already holds the outcome lock.
        await asyncio.wait_for(second_waiting.wait(), 3)
        return await original_record(*args, **kwargs)

    @asynccontextmanager
    async def observe_second_lock(*args, **kwargs):
        second_waiting.set()
        async with original_lock(*args, **kwargs):
            yield

    if first == "browser":
        monkeypatch.setattr(print_confirmation, "record_outcome", pause_first_record)
        monkeypatch.setattr(telegram_quality, "outcome_lock", observe_second_lock)
    else:
        monkeypatch.setattr(telegram_quality, "record_outcome", pause_first_record)
        monkeypatch.setattr(print_confirmation, "outcome_lock", observe_second_lock)

    async def browser():
        if first != "browser":
            await first_locked.wait()
        async with sessions() as session:
            return await confirm_production_outcome(
                archive.id,
                OutcomeConfirmation(run_id=run.id, good_quantity=5, reject_quantity=2),
                None,
                session,
                None,
                (user, True),
            )

    async def telegram():
        if first != "telegram":
            await first_locked.wait()
        async with sessions() as session:
            result = await telegram_quality.apply_reaction(session, config.id, reaction())
            await session.commit()
            return result

    results = await asyncio.wait_for(asyncio.gather(browser(), telegram(), return_exceptions=True), 5)
    assert not any(isinstance(result, Exception) for result in results), repr(results)
    assert results[0]["good_quantity"] == 5 and results[0]["reject_quantity"] == 2
    # Telegram is first-answer-only; authenticated browser corrections still work.
    assert results[1] is (first == "telegram")
    await db.refresh(run)
    assert (run.good_quantity, run.reject_quantity, run.user_verdict_source) == (5, 2, "dialog")
