"""The queue-reference updates must recheck state after concurrent dispatch."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.services.library_queue_references import (
    release_queue_references,
    repoint_siblings_at_archive,
)


def _rows(values):
    result = MagicMock()
    result.all.return_value = values
    return result


def _scalar_rows(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


@pytest.mark.asyncio
async def test_delete_cancellation_rechecks_waiting_state_in_update():
    db = AsyncMock()
    db.execute.side_effect = [
        _rows([(7, 3)]),
        _rows([(3, "benchy.3mf")]),
        SimpleNamespace(rowcount=0),
        SimpleNamespace(rowcount=1),
    ]

    assert await release_queue_references(db, [3]) == 0

    cancellation_sql = str(db.execute.await_args_list[2].args[0])
    assert "print_queue.status IN" in cancellation_sql
    assert "print_queue.archive_id IS NULL" in cancellation_sql
    assert "print_queue.library_file_id" in cancellation_sql


@pytest.mark.asyncio
async def test_sibling_repoint_rechecks_archive_and_status_in_update():
    db = AsyncMock()
    db.execute.side_effect = [
        _scalar_rows([8]),
        SimpleNamespace(rowcount=0),
        SimpleNamespace(rowcount=1),
    ]

    assert (
        await repoint_siblings_at_archive(
            db,
            consumed_library_file_id=3,
            archive_id=20,
            dispatched_item_id=7,
        )
        == 0
    )

    repoint_sql = str(db.execute.await_args_list[1].args[0])
    assert "print_queue.status IN" in repoint_sql
    assert "print_queue.archive_id IS NULL" in repoint_sql
    assert "print_queue.library_file_id" in repoint_sql
