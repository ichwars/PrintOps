"""File-backed SQLite grant/delete serialization, with actual separate connections."""

import asyncio
from contextvars import ContextVar
from unittest.mock import patch

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.database import Base, get_db
from backend.app.core.user_printer_scope import remove_printer_grants, validate_printer_grants
from backend.app.main import app
from backend.tests.integration.test_long_lived_tokens_api import _login
from backend.tests.integration.test_overlay_authorization_boundaries import mint

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]
_operation = ContextVar("overlay_scope_operation", default="")


@pytest.fixture(params=[False, True], ids=["legacy-select", "existing-read-snapshot"])
def explicit_reads(request):
    return request.param


@pytest.fixture
async def test_engine(test_engine, tmp_path):
    # Parent fixture registers all models. This engine uses a real file/pool,
    # so the concurrent requests cannot share a single in-memory connection.
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scope-race.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def pragmas(connection, _):
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture(autouse=True)
async def request_snapshots(async_client, explicit_reads):
    original = app.dependency_overrides[get_db]

    async def snapshot_db():
        async for db in original():
            # Establish an actual SQLite read transaction, not just SQLAlchemy's
            # logical autobegin. A concurrent writer can stale this WAL snapshot.
            await db.execute(text("BEGIN"))
            await db.execute(text("SELECT id FROM users LIMIT 1"))
            yield db

    if explicit_reads:
        app.dependency_overrides[get_db] = snapshot_db
    yield
    app.dependency_overrides[get_db] = original


async def labelled(label, request):
    token = _operation.set(label)
    try:
        return await request
    finally:
        _operation.reset(token)


def attempted(engine, label):
    ready = asyncio.Event()
    connections = set()

    def observe(conn, cursor, statement, parameters, context, executemany):
        if _operation.get() == label:
            connections.add(id(conn.connection.driver_connection))
            if statement.startswith("UPDATE printers SET") or statement.startswith("SELECT printers."):
                ready.set()

    event.listen(engine.sync_engine, "before_cursor_execute", observe)
    return ready, connections, observe


async def assert_waiting(task):
    # The scheduling barrier proves the second request reached its printer SQL.
    # A bounded wait distinguishes SQLite lock exclusion from completed writes.
    done, _ = await asyncio.wait({task}, timeout=0.5)
    assert not done, "A competing write finished while the first grant transaction was paused"


@pytest.mark.parametrize("operation", ["update", "create"])
async def test_validated_grant_excludes_delete_until_commit(
    async_client, printer_factory, db_session, test_engine, operation
):
    original = await printer_factory()
    printer_id = original.id
    uid, headers, params = await mint(async_client, [])
    validated, release = asyncio.Event(), asyncio.Event()
    grant_connections = set()

    async def hold(db, ids):
        await validate_printer_grants(db, ids)
        conn = await db.connection()
        grant_connections.add(await conn.run_sync(lambda connection: id(connection.connection.driver_connection)))
        validated.set()
        await release.wait()

    if operation == "update":
        request = async_client.patch(
            f"/api/v1/users/{uid}", headers=headers, json={"allowed_printer_ids": [printer_id]}
        )
    else:
        groups = (await async_client.get("/api/v1/groups/", headers=headers)).json()
        viewers = next(group["id"] for group in groups if group["name"] == "Viewers")
        request = async_client.post(
            "/api/v1/users/",
            headers=headers,
            json={
                "username": "racecreated",
                "password": "UserPass1!",
                "group_ids": [viewers],
                "allowed_printer_ids": [printer_id],
            },
        )
    delete_started, delete_connections, observer = attempted(test_engine, "delete")
    with (
        patch("backend.app.api.routes.users.validate_printer_grants", hold),
        patch("backend.app.api.routes.printers.printer_manager.disconnect_printer"),
    ):
        grant = asyncio.create_task(labelled("grant", request))
        deletion = None
        try:
            await asyncio.wait_for(validated.wait(), 5)
            deletion = asyncio.create_task(
                labelled("delete", async_client.delete(f"/api/v1/printers/{printer_id}", headers=headers))
            )
            await asyncio.wait_for(delete_started.wait(), 5)
            await assert_waiting(deletion)
        finally:
            release.set()
            granted = await asyncio.wait_for(grant, 5)
            deleted = await asyncio.wait_for(deletion, 5) if deletion else None
            event.remove(test_engine.sync_engine, "before_cursor_execute", observer)
    assert granted.status_code == (200 if operation == "update" else 201), granted.text
    assert deleted.status_code == 200, deleted.text
    assert grant_connections.isdisjoint(delete_connections)
    if operation == "create":
        uid = granted.json()["id"]
        owner = await _login(async_client, "racecreated")
        created_token = await async_client.post(
            "/api/v1/auth/tokens",
            headers={"Authorization": f"Bearer {owner}"},
            json={"name": "race", "scope": "overlay", "expires_in_days": 1},
        )
        assert created_token.status_code == 201
        params = {"token": created_token.json()["token"]}
    assert (await async_client.get(f"/api/v1/users/{uid}", headers=headers)).json()["allowed_printer_ids"] == []
    db_session.expunge(original)
    replacement = await printer_factory(name="Private replacement after concurrent deletion")
    assert replacement.id == printer_id
    assert (await async_client.get(f"/api/v1/printers/{printer_id}/overlay-status", params=params)).status_code == 403
    assert (await async_client.get(f"/api/v1/printers/{printer_id}/camera/stream", params=params)).status_code == 403


async def test_delete_excludes_stale_grant_and_revalidates_after_commit(
    async_client, printer_factory, db_session, test_engine
):
    original = await printer_factory()
    printer_id = original.id
    uid, headers, params = await mint(async_client, [])
    pruned, release = asyncio.Event(), asyncio.Event()

    async def hold(db, id_):
        await remove_printer_grants(db, id_)
        pruned.set()
        await release.wait()

    grant_started, _, observer = attempted(test_engine, "grant")
    with (
        patch("backend.app.core.user_printer_scope.remove_printer_grants", hold),
        patch("backend.app.api.routes.printers.printer_manager.disconnect_printer"),
    ):
        deletion = asyncio.create_task(
            labelled("delete", async_client.delete(f"/api/v1/printers/{printer_id}", headers=headers))
        )
        grant = None
        try:
            await asyncio.wait_for(pruned.wait(), 5)
            grant = asyncio.create_task(
                labelled(
                    "grant",
                    async_client.patch(
                        f"/api/v1/users/{uid}", headers=headers, json={"allowed_printer_ids": [printer_id]}
                    ),
                )
            )
            await asyncio.wait_for(grant_started.wait(), 5)
            await assert_waiting(grant)
        finally:
            release.set()
            deleted = await asyncio.wait_for(deletion, 5)
            granted = await asyncio.wait_for(grant, 5) if grant else None
            event.remove(test_engine.sync_engine, "before_cursor_execute", observer)
    assert deleted.status_code == 200, deleted.text
    assert granted.status_code == 400, granted.text
    db_session.expunge(original)
    replacement = await printer_factory(name="Private replacement after failed stale edit")
    assert replacement.id == printer_id
    assert (await async_client.get(f"/api/v1/printers/{printer_id}/overlay-status", params=params)).status_code == 403


async def test_writer_timeout_is_retryable_and_fresh_transaction_revalidates(test_engine, printer_factory):
    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from backend.app.core.user_printer_scope import prepare_printer_scope_write

    original = await printer_factory()
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as first, factory() as retry:
        await prepare_printer_scope_write(first)
        await retry.execute(text("PRAGMA busy_timeout=50"))
        with pytest.raises(HTTPException) as timeout:
            await prepare_printer_scope_write(retry)
        assert timeout.value.status_code == 409
        assert not retry.in_transaction()
        await first.execute(text("DELETE FROM printers WHERE id=:id"), {"id": original.id})
        await first.commit()
        await prepare_printer_scope_write(retry)
        with pytest.raises(HTTPException) as stale:
            await validate_printer_grants(retry, [original.id])
        assert stale.value.status_code == 400
        await retry.rollback()
