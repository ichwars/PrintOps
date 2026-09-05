"""Remain-delta attribution must neither double-charge nor touch idle trays."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.services.spoolman_tracking import (
    _print_used_tray_keys,
    _report_remain_delta_for_slots,
)


def test_print_used_trays_combine_mapping_start_and_backup_transitions():
    state = SimpleNamespace(tray_change_log=[(2, 0), (3, 675)])

    assert _print_used_tray_keys([2], 2, state) == {(0, 2), (0, 3)}


@pytest.mark.asyncio
async def test_remain_delta_skips_idle_tray_even_when_its_percentage_fell():
    client = AsyncMock()
    client.get_spool.return_value = {"filament": {"weight": 1000}}
    resolve = AsyncMock(return_value=88)

    with patch(
        "backend.app.services.spoolman_tracking._resolve_spool_id_via_slot_assignment",
        resolve,
    ):
        updated = await _report_remain_delta_for_slots(
            client,
            printer_id=1,
            tray_remain_start={
                "0-0": {"remain": 90, "tray_uuid": "A"},
                "0-3": {"remain": 80, "tray_uuid": "B"},
            },
            current_lookup={
                "0-0": {"remain": 70, "tray_uuid": "A"},
                "0-3": {"remain": 75, "tray_uuid": "B"},
            },
            handled_global_tray_ids=set(),
            archive_id=12,
            print_used_keys={(0, 3)},
        )

    assert updated == 1
    resolve.assert_awaited_once_with(1, 0, 3)
    client.use_spool.assert_awaited_once_with(88, 50.0)


@pytest.mark.asyncio
async def test_handled_3mf_tray_is_not_charged_again_by_remain_delta():
    client = AsyncMock()

    updated = await _report_remain_delta_for_slots(
        client,
        printer_id=1,
        tray_remain_start={"0-3": {"remain": 80, "tray_uuid": "B"}},
        current_lookup={"0-3": {"remain": 75, "tray_uuid": "B"}},
        handled_global_tray_ids={3},
        archive_id=12,
        print_used_keys={(0, 3)},
    )

    assert updated == 0
    client.use_spool.assert_not_awaited()
