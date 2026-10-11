"""Filtered reorder requests preserve the slots of omitted and protected jobs."""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import Update, select, update

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.group import Group
from backend.app.models.print_batch import PrintBatch
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.models.settings import Settings
from backend.app.models.user import User
from backend.app.schemas.print_queue import PrintQueueReorderItem
from backend.app.services.queue_position import reorder_queue_positions

ENDPOINT = "/api/v1/queue/reorder"


@pytest.fixture
def queue_row(db_session):
    async def create(**kwargs):
        row = PrintQueueItem(status="pending", **kwargs)
        db_session.add(row)
        await db_session.commit()
        await db_session.refresh(row)
        return row

    return create


@pytest.fixture
def reorder_user(db_session):
    async def create(permission=Permission.QUEUE_UPDATE_ALL, **kwargs):
        group = Group(name="Reorder permission", permissions=[permission.value])
        user = User(username="reorder-user", groups=[group], **kwargs)
        db_session.add_all([Settings(key="auth_enabled", value="true"), user])
        await db_session.commit()
        return user, {"Authorization": f"Bearer {create_access_token({'sub': user.username})}"}

    return create


async def _pending(db_session):
    return (
        (
            await db_session.execute(
                select(PrintQueueItem)
                .where(PrintQueueItem.status == "pending")
                .order_by(PrintQueueItem.position, PrintQueueItem.id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )


async def _printers(db_session):
    printers = [
        Printer(name=name, ip_address=f"192.0.2.{index}", serial_number=name, access_code="12345678", model="P1S")
        for index, name in enumerate(("Allowed", "Hidden"), 1)
    ]
    db_session.add_all(printers)
    await db_session.commit()
    return printers


@pytest.mark.asyncio
@pytest.mark.parametrize("positions", [(1, 2, 3, 4, 5), (3, 7, 11, 19, 23)])
async def test_location_filtered_reorder_reuses_global_slots(async_client, db_session, queue_row, positions):
    rows = [
        await queue_row(position=position, target_location="visible" if index % 2 else "hidden")
        for index, position in enumerate(positions)
    ]

    response = await async_client.post(
        ENDPOINT, json={"items": [{"id": rows[3].id, "position": 1}, {"id": rows[1].id, "position": 2}]}
    )

    assert response.status_code == 200, response.text
    pending = await _pending(db_session)
    assert [row.id for row in pending] == [rows[0].id, rows[3].id, rows[2].id, rows[1].id, rows[4].id]
    assert [row.position for row in pending] == list(positions)
    assert len({row.position for row in pending}) == len(pending)


@pytest.mark.asyncio
async def test_owner_filtered_batch_reorder_keeps_omitted_jobs_and_attribution(
    async_client, db_session, queue_row, reorder_user
):
    user, headers = await reorder_user()
    other = User(username="other-owner")
    batch = PrintBatch(name="Own batch", quantity=2, created_by_id=user.id)
    db_session.add_all([other, batch])
    await db_session.commit()
    first = await queue_row(position=1, created_by_id=user.id, batch_id=batch.id, plate_id=2)
    hidden = await queue_row(position=2, created_by_id=other.id)
    last = await queue_row(position=3, created_by_id=user.id, batch_id=batch.id, plate_id=5)

    response = await async_client.post(
        ENDPOINT, headers=headers, json={"items": [{"id": last.id, "position": 1}, {"id": first.id, "position": 2}]}
    )

    assert response.status_code == 200, response.text
    pending = await _pending(db_session)
    assert [(row.id, row.position) for row in pending] == [(last.id, 1), (hidden.id, 2), (first.id, 3)]
    assert [(row.batch_id, row.plate_id, row.created_by_id) for row in (pending[0], pending[2])] == [
        (batch.id, 5, user.id),
        (batch.id, 2, user.id),
    ]
    assert pending[1].created_by_id == other.id


@pytest.mark.asyncio
async def test_printer_scoped_user_cannot_move_hidden_job(async_client, db_session, queue_row, reorder_user):
    allowed, blocked = await _printers(db_session)
    _, headers = await reorder_user(allowed_printer_ids=[allowed.id])
    first = await queue_row(position=1, printer_id=allowed.id)
    hidden = await queue_row(position=2, printer_id=blocked.id)
    last = await queue_row(position=3, printer_id=allowed.id)

    response = await async_client.post(
        ENDPOINT,
        headers=headers,
        json={
            "items": [{"id": hidden.id, "position": 1}, {"id": last.id, "position": 2}, {"id": first.id, "position": 3}]
        },
    )

    assert response.status_code == 200, response.text
    assert [(row.id, row.position) for row in await _pending(db_session)] == [
        (last.id, 1),
        (hidden.id, 2),
        (first.id, 3),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("credential", ["header", "bearer"])
async def test_api_key_printer_scope_keeps_foreign_slots(async_client, db_session, queue_row, reorder_user, credential):
    allowed, blocked = await _printers(db_session)
    user, _ = await reorder_user()
    raw, key_hash, prefix = generate_api_key()
    db_session.add(
        APIKey(name="Scoped queue", user_id=user.id, key_hash=key_hash, key_prefix=prefix, printer_ids=[allowed.id])
    )
    await db_session.commit()
    first = await queue_row(position=1, printer_id=allowed.id)
    hidden = await queue_row(position=2, printer_id=blocked.id)
    last = await queue_row(position=3, printer_id=allowed.id)
    headers = {"X-API-Key": raw} if credential == "header" else {"Authorization": f"Bearer {raw}"}

    response = await async_client.post(
        ENDPOINT,
        headers=headers,
        json={
            "items": [{"id": hidden.id, "position": 1}, {"id": last.id, "position": 2}, {"id": first.id, "position": 3}]
        },
    )

    assert response.status_code == 200, response.text
    assert [(row.id, row.position) for row in await _pending(db_session)] == [
        (last.id, 1),
        (hidden.id, 2),
        (first.id, 3),
    ]


@pytest.mark.asyncio
async def test_dispatching_and_completed_jobs_stay_unchanged(async_client, db_session, queue_row):
    first = await queue_row(position=1)
    dispatching = await queue_row(position=2, dispatching_at=datetime.now(timezone.utc))
    last = await queue_row(position=3)
    completed = PrintQueueItem(position=4, status="completed")
    db_session.add(completed)
    await db_session.commit()

    response = await async_client.post(
        ENDPOINT,
        json={
            "items": [
                {"id": dispatching.id, "position": 1},
                {"id": last.id, "position": 2},
                {"id": first.id, "position": 3},
                {"id": completed.id, "position": 4},
                {"id": 99999, "position": 5},
            ]
        },
    )

    assert response.status_code == 200, response.text
    assert [(row.id, row.position) for row in await _pending(db_session)] == [
        (last.id, 1),
        (dispatching.id, 2),
        (first.id, 3),
    ]
    await db_session.refresh(completed)
    assert completed.position == 4


@pytest.mark.asyncio
async def test_duplicate_ids_are_rejected_without_partial_updates(async_client, db_session, queue_row):
    first = await queue_row(position=1)
    second = await queue_row(position=2)

    response = await async_client.post(
        ENDPOINT, json={"items": [{"id": first.id, "position": 1}, {"id": first.id, "position": 2}]}
    )

    assert response.status_code == 422
    assert [(row.id, row.position) for row in await _pending(db_session)] == [(first.id, 1), (second.id, 2)]


@pytest.mark.asyncio
async def test_duplicate_payload_positions_remain_rejected(async_client, db_session, queue_row):
    rows = [await queue_row(position=index) for index in (1, 2)]

    response = await async_client.post(ENDPOINT, json={"items": [{"id": row.id, "position": 1} for row in rows]})

    assert response.status_code == 422
    assert [row.position for row in await _pending(db_session)] == [1, 2]


@pytest.mark.asyncio
async def test_full_reorder_uses_requested_order_and_unique_global_ranks(async_client, db_session, queue_row):
    rows = [await queue_row(position=index) for index in (1, 1, 3)]

    response = await async_client.post(
        ENDPOINT,
        json={
            "items": [
                {"id": rows[0].id, "position": 30},
                {"id": rows[1].id, "position": 10},
                {"id": rows[2].id, "position": 20},
            ]
        },
    )

    assert response.status_code == 200, response.text
    assert [(row.id, row.position) for row in await _pending(db_session)] == [
        (rows[1].id, 1),
        (rows[2].id, 2),
        (rows[0].id, 3),
    ]


@pytest.mark.asyncio
async def test_own_only_permission_does_not_gain_global_reorder(async_client, db_session, queue_row, reorder_user):
    user, headers = await reorder_user(permission=Permission.QUEUE_UPDATE_OWN)
    rows = [await queue_row(position=index, created_by_id=user.id) for index in (1, 2)]

    response = await async_client.post(
        ENDPOINT,
        headers=headers,
        json={"items": [{"id": row.id, "position": 3 - index} for index, row in enumerate(rows, 1)]},
    )

    assert response.status_code == 403
    assert [row.position for row in await _pending(db_session)] == [1, 2]


@pytest.mark.asyncio
async def test_late_dispatch_claim_rolls_back_every_position_change(db_session, queue_row, monkeypatch):
    first = await queue_row(position=1)
    last = await queue_row(position=2)
    original_execute = db_session.execute
    writes = 0

    async def execute(statement, *args, **kwargs):
        nonlocal writes
        if isinstance(statement, Update):
            writes += 1
            if writes == 2:
                # SQLite has no FOR UPDATE: claim the next row after the first
                # position was already written, before its guarded update.
                await original_execute(
                    update(PrintQueueItem)
                    .where(PrintQueueItem.id == first.id)
                    .values(dispatching_at=datetime.now(timezone.utc))
                )
        return await original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", execute)

    with pytest.raises(HTTPException) as error:
        await reorder_queue_positions(
            db_session,
            [PrintQueueReorderItem(id=last.id, position=1), PrintQueueReorderItem(id=first.id, position=2)],
            None,
            None,
        )

    assert error.value.status_code == 409
    assert [row.position for row in await _pending(db_session)] == [1, 2]
