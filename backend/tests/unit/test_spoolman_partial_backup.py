from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPartialUsageTraySplit:
    """A single-filament print that ran out and switched to the AMS backup
    spool before failing charges each spool its share, as a completed print
    and the built-in inventory do. All of it went to the tray that ran out."""

    @pytest.mark.asyncio
    async def test_the_partial_grams_are_split_at_the_tray_change(self):
        from backend.app.services.spoolman_tracking import _report_partial_usage

        tracking = SimpleNamespace(
            archive_id=99,
            filament_usage=[{"slot_id": 1, "used_g": 200.0}],
            layer_usage=None,
            filament_properties=None,
            ams_trays={"0": {"tray_uuid": "A" * 32}, "1": {"tray_uuid": "B" * 32}},
            slot_to_tray=[0],
            tray_remain_start=None,
        )
        spools = {"A" * 32: {"id": 7}, "B" * 32: {"id": 8}}
        client = AsyncMock()
        client.find_spool_by_tag = AsyncMock(side_effect=lambda tag, *a, **k: spools.get(tag))
        client.use_spool = AsyncMock()
        printer_manager = MagicMock()
        printer_manager.get_status.return_value = SimpleNamespace(
            raw_data={},
            layer_num=100,
            total_layers=200,
            tray_change_log=[(0, 1), (1, 51)],
        )

        with (
            patch("backend.app.api.routes.settings.get_setting", AsyncMock(return_value="true")),
            patch(
                "backend.app.services.spoolman_tracking._get_spoolman_client_with_fallback",
                AsyncMock(return_value=client),
            ),
            patch("backend.app.services.spoolman_tracking._get_printer_serial", AsyncMock(return_value="serial")),
            patch("backend.app.services.printer_manager.printer_manager", printer_manager),
        ):
            await _report_partial_usage(printer_id=1, tracking=tracking)

        charged = {call.args[0]: call.args[1] for call in client.use_spool.await_args_list}
        # 100 g by layer 100 of 200, the switch at layer 51: half each.
        assert charged == {7: 50.0, 8: 50.0}

    @pytest.mark.asyncio
    async def test_a_stop_layer_below_a_logged_switch_never_charges_more_than_was_used(self):
        """The stop layer estimated from progress (60) can trail the logged
        switch (80); the split must not exceed the partial grams."""
        from backend.app.services.spoolman_tracking import _report_partial_usage

        tracking = SimpleNamespace(
            archive_id=99,
            filament_usage=[{"slot_id": 1, "used_g": 200.0}],
            layer_usage=None,
            filament_properties=None,
            ams_trays={"0": {"tray_uuid": "A" * 32}, "1": {"tray_uuid": "B" * 32}},
            slot_to_tray=[0],
            tray_remain_start=None,
        )
        spools = {"A" * 32: {"id": 7}, "B" * 32: {"id": 8}}
        client = AsyncMock()
        client.find_spool_by_tag = AsyncMock(side_effect=lambda tag, *a, **k: spools.get(tag))
        client.use_spool = AsyncMock()
        printer_manager = MagicMock()
        printer_manager.get_status.return_value = SimpleNamespace(
            raw_data={}, layer_num=0, total_layers=200, tray_change_log=[(0, 0), (1, 80)]
        )

        with (
            patch("backend.app.api.routes.settings.get_setting", AsyncMock(return_value="true")),
            patch(
                "backend.app.services.spoolman_tracking._get_spoolman_client_with_fallback",
                AsyncMock(return_value=client),
            ),
            patch("backend.app.services.spoolman_tracking._get_printer_serial", AsyncMock(return_value="serial")),
            patch("backend.app.services.printer_manager.printer_manager", printer_manager),
        ):
            await _report_partial_usage(printer_id=1, tracking=tracking, last_progress=30)

        # Layer 60 of 200 from 30 %: 60 g used, never more.
        assert round(sum(call.args[1] for call in client.use_spool.await_args_list), 2) <= 60.0
