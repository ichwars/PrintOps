"""Filament notes use the dispatched mapping and the active run's printer scope."""

import json
from datetime import timedelta
from unittest.mock import patch

import pytest

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.group import Group
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.settings import Settings
from backend.app.models.user import User
from backend.app.services.bambu_mqtt import PrinterState
from backend.app.services.queue_dispatch_state import defer_dispatch, fail_dispatch

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

SUBSTITUTION = {"slot_id": 1, "type": "PLA", "wanted": "#FFFFFF", "got": "#FF0000", "tray": 0}


async def test_dispatch_notes_decode_and_clear_after_failed_send_or_deferral(
    async_client, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id)
    job = PrintQueueItem(
        printer_id=printer.id, archive_id=archive.id, status="printing", color_substitutions=json.dumps([SUBSTITUTION])
    )
    malformed = PrintQueueItem(
        printer_id=printer.id, archive_id=archive.id, status="pending", color_substitutions='{"slot_id": 1}'
    )
    db_session.add_all([job, malformed])
    await db_session.commit()

    async def response(item):
        reply = await async_client.get(f"/api/v1/queue/{item.id}")
        assert reply.status_code == 200, reply.text
        return reply.json()

    assert (await response(job))["color_substitutions"] == [SUBSTITUTION]
    assert (await response(malformed))["color_substitutions"] is None
    await defer_dispatch(db_session, job)
    assert (await response(job))["color_substitutions"] is None
    await db_session.refresh(job)
    job.status = "printing"
    job.color_substitutions = json.dumps([SUBSTITUTION])
    await db_session.commit()
    assert await fail_dispatch(db_session, job, "MQTT start failed")
    assert (await response(job))["color_substitutions"] is None


async def test_running_backup_chain_is_bound_to_queue_run_and_printer_scope(
    async_client, db_session, printer_factory, archive_factory
):
    printer, hidden = await printer_factory(), await printer_factory()
    archive = await archive_factory(printer.id, status="printing")
    job = PrintQueueItem(printer_id=printer.id, archive_id=archive.id, status="printing", ams_mapping="[2, 3]")
    user = User(
        username="status-reader",
        allowed_printer_ids=[printer.id],
        groups=[Group(name="Status", permissions=[Permission.PRINTERS_READ.value])],
    )
    db_session.add_all([job, user, Settings(key="auth_enabled", value="true")])
    await db_session.flush()
    key, key_hash, prefix = generate_api_key()
    denied_key, denied_hash, denied_prefix = generate_api_key()
    revoked_key, revoked_hash, revoked_prefix = generate_api_key()
    run = PrintLogEntry(
        archive_id=archive.id, queue_item_id=job.id, printer_id=printer.id, status="printing", subtask_id="fresh"
    )
    db_session.add_all(
        [
            run,
            APIKey(
                name="Status",
                key_hash=key_hash,
                key_prefix=prefix,
                user_id=user.id,
                printer_ids=[printer.id, hidden.id],
            ),
            APIKey(name="Denied", key_hash=denied_hash, key_prefix=denied_prefix, can_read_status=False),
            APIKey(name="Revoked", key_hash=revoked_hash, key_prefix=revoked_prefix, enabled=False),
        ]
    )
    await db_session.commit()
    expired = create_access_token({"sub": user.username}, expires_delta=timedelta(seconds=-30))
    status = PrinterState(connected=True, state="RUNNING", subtask_id="fresh")
    status.tray_change_log = [[2, 0], (1, 40), (3, 70), (1, 90), (0, 120), (255, 122)]
    url = f"/api/v1/printers/{printer.id}/status"
    with patch("backend.app.api.routes.printers.printer_manager") as manager:
        manager.get_status.return_value = status
        manager.get_drying_targets.return_value = {}
        manager.is_awaiting_plate_clear.return_value = False
        for headers, code in (
            ({}, 401),
            ({"X-API-Key": "invalid"}, 401),
            ({"X-API-Key": denied_key}, 403),
            ({"X-API-Key": revoked_key}, 401),
            ({"Authorization": f"Bearer {expired}"}, 401),
        ):
            denied = await async_client.get(url, headers=headers)
            assert denied.status_code == code, denied.text
        forbidden = await async_client.get(f"/api/v1/printers/{hidden.id}/status", headers={"X-API-Key": key})
        assert forbidden.status_code == 404
        manager.get_status.assert_not_called()
        reply = await async_client.get(url, headers={"X-API-Key": key})
        assert reply.status_code == 200, reply.text
        assert reply.json()["current_backup_trays"] == {"2": 0}
        status.subtask_id = "another-print"
        reply = await async_client.get(url, headers={"X-API-Key": key})
        assert reply.status_code == 200 and reply.json()["current_backup_trays"] == {}, reply.text
