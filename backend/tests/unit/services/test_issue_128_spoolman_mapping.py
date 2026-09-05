"""Spoolman must use authoritative tray telemetry before position (issue #128)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.spoolman_tracking import (
    _resolve_slot_to_tray_fallback,
    _single_slot_tray_from_state,
)

USAGE = [{"slot_id": 1, "used_g": 2.17, "type": "PLA+", "color": "#000000"}]
AMS = [
    {
        "id": 0,
        "tray": [
            {"id": 0, "tray_color": "888888FF", "tray_type": "PLA+"},
            {"id": 3, "tray_color": "111111FF", "tray_type": "PLA+"},
        ],
    }
]


def _state(*, changes=None, tray_now=255, last_loaded=-1, raw_data=None):
    return SimpleNamespace(
        tray_change_log=list(changes or []),
        tray_now=tray_now,
        last_loaded_tray=last_loaded,
        raw_data={} if raw_data is None else raw_data,
    )


def test_single_material_uses_print_tray_change_evidence():
    assert _single_slot_tray_from_state(_state(changes=[(3, 0)]), USAGE, 255) == (1, 3)


def test_single_material_falls_back_to_start_then_current_then_last_loaded():
    state = _state(tray_now=2, last_loaded=3)
    assert _single_slot_tray_from_state(state, USAGE, 1) == (1, 1)
    assert _single_slot_tray_from_state(state, USAGE, 255) == (1, 2)
    assert _single_slot_tray_from_state(_state(last_loaded=3), USAGE, 255) == (1, 3)


def test_multi_material_and_backup_split_decline_single_tray_guess():
    multi = [*USAGE, {"slot_id": 2, "used_g": 1.0, "color": "#FFFFFF"}]
    assert _single_slot_tray_from_state(_state(changes=[(3, 0)]), multi, 3) is None
    assert _single_slot_tray_from_state(_state(changes=[(0, 0), (3, 100)]), USAGE, 0) is None


def test_unloaded_255_is_not_treated_as_a_real_tray():
    assert _single_slot_tray_from_state(_state(tray_now=255, last_loaded=255), USAGE, 255) is None


def test_resolver_prefers_mqtt_then_color_then_single_tray_state():
    manager = MagicMock()
    with patch("backend.app.services.printer_manager.printer_manager", manager):
        manager.get_status.return_value = _state(raw_data={"mapping": [2], "ams": AMS}, changes=[(3, 0)])
        assert _resolve_slot_to_tray_fallback(1, USAGE, 255) == ([2], "mqtt")

        color_usage = [{**USAGE[0], "color": "#111111"}]
        manager.get_status.return_value = _state(raw_data={"ams": AMS}, changes=[(0, 0)])
        assert _resolve_slot_to_tray_fallback(1, color_usage, 255) == ([3], "color_match")

        manager.get_status.return_value = _state(raw_data={"ams": AMS}, changes=[(3, 0)])
        assert _resolve_slot_to_tray_fallback(1, USAGE, 255) == ([3], "tray_state")


def test_resolver_pads_only_to_the_used_slot():
    usage = [
        {"slot_id": 1, "used_g": 0.0, "color": "#AAAAAA"},
        {"slot_id": 3, "used_g": 2.17, "color": "#000000"},
    ]
    manager = MagicMock()
    manager.get_status.return_value = _state(changes=[(3, 0)])
    with patch("backend.app.services.printer_manager.printer_manager", manager):
        assert _resolve_slot_to_tray_fallback(1, usage, None) == ([-1, -1, 3], "tray_state")


class _AsyncSessionContext:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_exc):
        return False


def _tracking():
    return SimpleNamespace(
        filament_usage=list(USAGE),
        ams_trays={
            "0": {"tray_uuid": "TRAY0", "tag_uid": "", "tray_type": "PLA+"},
            "3": {"tray_uuid": "TRAY3", "tag_uid": "", "tray_type": "PLA+"},
        },
        slot_to_tray=None,
        tray_remain_start=None,
        layer_usage=None,
        filament_properties=None,
        tray_now_at_start=255,
    )


async def _report_with_state(state):
    from backend.app.services.spoolman_tracking import report_usage

    tracking = _tracking()
    result = MagicMock()
    result.scalar_one_or_none.return_value = tracking
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    client = AsyncMock()
    client.find_spool_by_tag = AsyncMock(
        side_effect=lambda tag: {
            "TRAY0": {"id": 41, "filament": {"color_hex": "888888"}},
            "TRAY3": {"id": 46, "filament": {"color_hex": "111111"}},
        }.get(tag)
    )
    manager = MagicMock()
    manager.get_status.return_value = state
    apply_colors = AsyncMock()

    with (
        patch("backend.app.services.spoolman_tracking.async_session", lambda: _AsyncSessionContext(db)),
        patch("backend.app.api.routes.settings.get_setting", AsyncMock(return_value="true")),
        patch(
            "backend.app.services.spoolman_tracking._get_spoolman_client_with_fallback",
            AsyncMock(return_value=client),
        ),
        patch("backend.app.services.spoolman_tracking._get_printer_serial", AsyncMock(return_value="SER")),
        patch(
            "backend.app.services.spoolman_tracking._resolve_spool_id_via_slot_assignment",
            AsyncMock(return_value=None),
        ),
        patch("backend.app.services.spoolman_tracking._apply_spool_colors_to_archive", apply_colors),
        patch("backend.app.services.spoolman_tracking._apply_spoolman_costs_to_archive", AsyncMock()),
        patch("backend.app.services.printer_manager.printer_manager", manager),
    ):
        await report_usage(printer_id=1, archive_id=12)

    return client, apply_colors


@pytest.mark.asyncio
async def test_report_charges_the_single_tray_named_by_the_printer():
    client, apply_colors = await _report_with_state(_state(changes=[(3, 0)], last_loaded=3, raw_data={"ams": AMS}))

    client.use_spool.assert_awaited_once_with(46, 2.17)
    apply_colors.assert_awaited_once()


@pytest.mark.asyncio
async def test_positional_guess_does_not_rewrite_archive_provenance():
    client, apply_colors = await _report_with_state(_state(raw_data={"ams": AMS}))

    client.use_spool.assert_awaited_once_with(41, 2.17)
    apply_colors.assert_not_awaited()
