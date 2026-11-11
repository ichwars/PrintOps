"""Recent printer cards use each printer's visible runs, including reprints."""

from datetime import datetime

import pytest
from sqlalchemy import update

from backend.app.core.auth import generate_api_key
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.user import User
from backend.tests.integration.test_media_tokens import _admin_token, _make_user

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]
URL = "/api/v1/archives/last-per-printer"


async def test_latest_print_is_scoped_to_the_physical_printer(
    async_client, db_session, printer_factory, archive_factory
):
    first, second, older = await printer_factory(), await printer_factory(), await printer_factory()
    shared = await archive_factory(second.id, with_run=False, print_name="Shared archive")
    legacy = await archive_factory(older.id, with_run=False, completed_at=datetime(2026, 11, 9))
    await archive_factory(first.id, with_run=False, status="printing", started_at=datetime(2026, 11, 12))
    run_first = PrintLogEntry(
        archive_id=shared.id,
        printer_id=first.id,
        status="completed",
        print_name="Previous run",
        completed_at=datetime(2026, 11, 10),
    )
    run_second = PrintLogEntry(
        archive_id=shared.id,
        printer_id=second.id,
        status="failed",
        print_name="Later reprint",
        completed_at=datetime(2026, 11, 11),
    )
    db_session.add_all([run_first, run_second])
    await db_session.commit()

    response = await async_client.get(URL)
    assert response.status_code == 200, response.text
    rows = {row["printer_id"]: row for row in response.json()}
    assert rows[first.id]["run_id"] == run_first.id
    assert rows[first.id]["print_name"] == "Previous run"
    assert rows[second.id]["run_id"] == run_second.id
    assert rows[older.id]["archive_id"] == legacy.id and rows[older.id]["run_id"] is None


async def test_a_printer_key_cannot_see_the_other_reprint(async_client, db_session, printer_factory, archive_factory):
    first, second = await printer_factory(), await printer_factory()
    shared = await archive_factory(second.id, with_run=False, print_name="Shared")
    admin = await _admin_token(async_client, "_recent_printer")
    _, user_id = await _make_user(
        async_client, admin, username="recent_printer_reader", permissions=[Permission.ARCHIVES_READ_ALL.value]
    )
    await db_session.execute(update(User).where(User.id == user_id).values(allowed_printer_ids=[first.id]))
    secret, key_hash, prefix = generate_api_key()
    db_session.add(
        APIKey(
            name="Recent print key",
            key_hash=key_hash,
            key_prefix=prefix,
            user_id=user_id,
            can_read_status=True,
            printer_ids=[first.id, second.id],
        )
    )
    db_session.add_all(
        [
            PrintLogEntry(archive_id=shared.id, printer_id=first.id, status="completed", print_name="Visible"),
            PrintLogEntry(archive_id=shared.id, printer_id=second.id, status="completed", print_name="Hidden"),
        ]
    )
    await db_session.commit()

    response = await async_client.get(URL, headers={"X-API-Key": secret})
    assert response.status_code == 200, response.text
    assert [(row["printer_id"], row["print_name"]) for row in response.json()] == [(first.id, "Visible")]
