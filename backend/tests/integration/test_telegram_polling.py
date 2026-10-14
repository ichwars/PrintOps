"""Polling uses real persisted leases/cursors and a fake Bot API only."""

import asyncio
import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.database import Base
from backend.app.models.telegram_quality import TelegramPollState
from backend.app.services import telegram_polling as polling
from backend.app.services.telegram_quality import now
from backend.tests.conftest import test_engine as model_engine
from backend.tests.integration.test_telegram_quality import context, reaction


@pytest.fixture
async def test_engine(model_engine, tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'telegram.db'}", connect_args={"timeout": 30})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


async def test_cursor_committed_before_ack_and_restart(context, test_engine):
    db, user, archive, run, provider, config = context
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    calls = []

    async def handle(request):
        method = request.url.path.rsplit("/", 1)[1]
        if method == "getWebhookInfo":
            return httpx.Response(200, json={"ok": True, "result": {"url": ""}})
        payload = json.loads(request.content)
        calls.append(payload)
        async with sessions() as check:
            state = await check.get(TelegramPollState, "123")
            if payload.get("offset") == 2:
                assert state.cursor == 1
                assert (await check.get(type(run), run.id)).good_quantity == 7
        return httpx.Response(200, json={"ok": True, "result": [reaction()] if len(calls) == 1 else []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        await polling.poll_once(sessions, client, config.id)
        await polling.poll_once(sessions, client, config.id)
    assert calls[0]["allowed_updates"] == ["message_reaction"]
    assert calls[1]["offset"] == 2
    await db.refresh(run)
    assert run.good_quantity == 7


async def test_active_lease_blocks_second_worker(context, test_engine):
    db, user, archive, run, provider, config = context
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    entered, release = asyncio.Event(), asyncio.Event()
    requests = []

    async def handle(request):
        requests.append(request.url.path)
        if request.url.path.endswith("getWebhookInfo"):
            entered.set()
            await release.wait()
            return httpx.Response(200, json={"ok": True, "result": {"url": ""}})
        return httpx.Response(200, json={"ok": True, "result": [reaction()]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        first = asyncio.create_task(polling.poll_once(sessions, client, config.id))
        await entered.wait()
        assert not await polling.poll_once(sessions, client, config.id)
        release.set()
        await first
    assert len(requests) == 2
    await db.refresh(run)
    assert run.good_quantity == 7


@pytest.mark.parametrize("conflict", ["webhook", "http409", "timeout"])
async def test_conflict_preserves_bot_configuration(context, test_engine, conflict, caplog):
    db, user, archive, run, provider, config = context
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    calls = []

    def handle(request):
        method = request.url.path.rsplit("/", 1)[1]
        calls.append(method)
        if conflict == "timeout":
            raise httpx.ReadTimeout("sensitive token 123:fake", request=request)
        if conflict == "http409":
            return httpx.Response(409, text="sensitive token 123:fake")
        return httpx.Response(200, json={"ok": True, "result": {"url": "https://external.example/secret"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        await polling.poll_once(sessions, client, config.id)
    state = await db.get(TelegramPollState, "123")
    assert state.status in {"webhook_conflict", "transport_error"}
    assert state.cursor is None and run.good_quantity is None
    assert calls == ["getWebhookInfo"]
    assert "123:fake" not in caplog.text and "external.example/secret" not in caplog.text


async def test_expired_lease_recovers_and_idle_cursor_omitted(context, test_engine):
    db, user, archive, run, provider, config = context
    db.add(
        TelegramPollState(
            bot_id="123",
            cursor=900,
            lease_owner="crashed",
            lease_until=now() - timedelta(seconds=1),
            last_update_at=now() - timedelta(days=8),
        )
    )
    await db.commit()
    calls = []

    def handle(request):
        if request.url.path.endswith("getWebhookInfo"):
            return httpx.Response(200, json={"ok": True, "result": {"url": ""}})
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True, "result": [reaction()]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        await polling.poll_once(async_sessionmaker(test_engine, expire_on_commit=False), client, config.id)
    assert "offset" not in calls[0]
    await db.refresh(run)
    assert run.good_quantity == 7


async def test_decision_and_cursor_rollback_together(context, test_engine):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    db, user, archive, run, provider, config = context
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    await db.execute(
        text(
            "CREATE TRIGGER fail_cursor BEFORE UPDATE ON telegram_poll_states WHEN NEW.cursor IS NOT NULL BEGIN SELECT RAISE(ABORT, 'test crash before cursor commit'); END"
        )
    )
    await db.commit()

    def handle(request):
        return httpx.Response(
            200,
            json={"ok": True, "result": {"url": ""} if request.url.path.endswith("getWebhookInfo") else [reaction()]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(IntegrityError):
            await polling.poll_once(sessions, client, config.id)
    await db.refresh(run)
    assert run.good_quantity is None
    state = await db.get(TelegramPollState, "123")
    assert state.cursor is None


async def test_expired_worker_cannot_apply_after_network_wait(context, test_engine):
    from sqlalchemy import update

    db, user, archive, run, provider, config = context
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)

    async def handle(request):
        if request.url.path.endswith("getWebhookInfo"):
            return httpx.Response(200, json={"ok": True, "result": {"url": ""}})
        async with sessions() as other:
            await other.execute(
                update(TelegramPollState).values(lease_owner="new-worker", lease_until=now() + timedelta(seconds=60))
            )
            await other.commit()
        return httpx.Response(200, json={"ok": True, "result": [reaction()]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        assert not await polling.poll_once(sessions, client, config.id)
    await db.refresh(run)
    assert run.good_quantity is None
    state = await db.get(TelegramPollState, "123")
    assert state.cursor is None and state.lease_owner == "new-worker"


async def test_two_reactions_share_first_answer_lock(context, test_engine):
    from backend.app.services.telegram_quality import apply_reaction

    db, user, archive, run, provider, config = context
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)

    async def answer(emoji):
        async with sessions() as session:
            return await apply_reaction(session, config.id, reaction(emoji))

    results = await asyncio.gather(answer("👍"), answer("👎"))
    assert sorted(results) == [False, True]
    await db.refresh(run)
    assert (run.good_quantity, run.reject_quantity) in [(7, 0), (0, 7)]


async def test_send_race_separate_database_sessions(context, test_engine, monkeypatch):
    from unittest.mock import AsyncMock

    from backend.app.models.telegram_quality import TelegramQualityMessage
    from backend.app.services.notification_service import NotificationService
    from backend.app.services.telegram_quality import invalidate_provider

    db, user, archive, run, provider, config = context
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)

    async def handle(request):
        # A separate transaction commits the edit while the sender awaits HTTP.
        async with sessions() as editor:
            await invalidate_provider(editor, provider.id)
            await editor.commit()
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
    async with sessions() as check:
        assert await check.scalar(select(TelegramQualityMessage.id)) is None
