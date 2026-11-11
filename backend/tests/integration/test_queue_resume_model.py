"""A model's failure gate can be resumed only for permitted printers."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.print_queue import PrintQueueItem
from backend.tests.integration.test_queue_partial_reorder import reorder_user  # noqa: F401

pytestmark = pytest.mark.asyncio
ENDPOINT = "/api/v1/queue/model/x1c/resume"


@pytest.fixture
async def failed_printers(db_session, printer_factory):
    printers = [await printer_factory(model=model) for model in ("X1C", "X1C", "P1S")]
    for printer in printers:
        db_session.add(PrintQueueItem(printer_id=printer.id, status="failed", completed_at=datetime.now(timezone.utc)))
    await db_session.commit()
    return [printer.id for printer in printers]


async def _acknowledged(db_session):
    rows = (await db_session.scalars(select(PrintQueueItem).execution_options(populate_existing=True))).all()
    return {row.printer_id for row in rows if row.gate_acknowledged}


async def test_resumes_only_the_requested_model(async_client, db_session, failed_printers):
    response = await async_client.post(ENDPOINT)
    assert response.status_code == 200, response.text
    assert response.json() == {"acknowledged": 2, "printers": 2}
    assert await _acknowledged(db_session) == set(failed_printers[:2])


async def test_resumes_only_the_users_grants(async_client, db_session, failed_printers, reorder_user):  # noqa: F811
    _, headers = await reorder_user(allowed_printer_ids=[failed_printers[0]])
    response = await async_client.post(ENDPOINT, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"acknowledged": 1, "printers": 1}
    assert await _acknowledged(db_session) == {failed_printers[0]}


@pytest.mark.parametrize("allowed", [[], None])
async def test_api_key_scope_is_kept(async_client, db_session, failed_printers, reorder_user, allowed):  # noqa: F811
    user, _ = await reorder_user()
    raw, key_hash, prefix = generate_api_key()
    db_session.add(APIKey(name="Resume", user_id=user.id, key_hash=key_hash, key_prefix=prefix, printer_ids=allowed))
    await db_session.commit()
    response = await async_client.post(ENDPOINT, headers={"X-API-Key": raw})
    assert response.status_code == 200, response.text
    expected = set(failed_printers[:2]) if allowed is None else set()
    assert await _acknowledged(db_session) == expected
    assert response.json()["acknowledged"] == len(expected)


@pytest.mark.parametrize("kind", ["missing", "wrong", "expired", "permission", "revoked_key", "key_scope"])
async def test_denied_credentials_cannot_clear_gates(
    async_client,
    db_session,
    failed_printers,
    reorder_user,
    kind,  # noqa: F811
):
    user, headers = await reorder_user(
        permission=Permission.QUEUE_READ_ALL if kind == "permission" else Permission.QUEUE_UPDATE_ALL
    )
    expected_status = 403 if kind in ("permission", "key_scope") else 401
    if kind == "missing":
        headers = {}
    elif kind == "wrong":
        headers = {"Authorization": "Bearer invalid-test-token"}
    elif kind == "expired":
        headers = {
            "Authorization": f"Bearer {create_access_token({'sub': user.username}, expires_delta=timedelta(seconds=-1))}"
        }
    elif kind in ("revoked_key", "key_scope"):
        raw, key_hash, prefix = generate_api_key()
        db_session.add(
            APIKey(
                name="Denied resume",
                user_id=user.id,
                key_hash=key_hash,
                key_prefix=prefix,
                enabled=kind != "revoked_key",
                can_queue=kind != "key_scope",
            )
        )
        await db_session.commit()
        headers = {"X-API-Key": raw}
    response = await async_client.post(ENDPOINT, headers=headers)
    assert response.status_code == expected_status, response.text
    assert await _acknowledged(db_session) == set()


@pytest.mark.parametrize("key_uses_other_printer", [False, True])
async def test_owned_api_key_cannot_clear_gates_outside_its_owners_current_grants(
    async_client, db_session, failed_printers, reorder_user, key_uses_other_printer
):
    user, _ = await reorder_user(allowed_printer_ids=[failed_printers[0]])
    raw, key_hash, prefix = generate_api_key()
    key_scope = [failed_printers[1]] if key_uses_other_printer else None
    db_session.add(
        APIKey(name="Owner-scoped resume", user_id=user.id, key_hash=key_hash, key_prefix=prefix, printer_ids=key_scope)
    )
    await db_session.commit()
    response = await async_client.post(ENDPOINT, headers={"X-API-Key": raw})
    assert response.status_code == 200
    expected = set() if key_uses_other_printer else {failed_printers[0]}
    assert await _acknowledged(db_session) == expected
    assert response.json() == {"acknowledged": len(expected), "printers": len(expected)}
