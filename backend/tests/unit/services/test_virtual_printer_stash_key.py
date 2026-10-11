"""Virtual printer project_file option stashing and wake-up regressions."""

import pytest


class TestVPProjectFileStashKey:
    """Regression: `on_print_command` MUST stash slicer options under the
    FTP filename (`data["file"]`, with extension), NOT under `filename`
    (the slicer's `subtask_name`, bare).

    #1780 root cause (real bundle, 2026-06-21): BambuStudio sends
    `subtask_name = "Model_Name"` (bare) and `file = "Model_Name.gcode.3mf"`
    (with extension). `_add_to_print_queue` looks up the stash under
    `file_path.name` from the FTP receive side, which always has the
    extension. If the stash uses `subtask_name`, lookup misses → every
    captured slicer field (bed_leveling, flow_cali, vibration_cali,
    layer_inspect, timelapse, nozzle_mapping) silently falls back to
    settings defaults on every Bambu Studio "Send" upload.

    `filename` (subtask_name) must still flow to `_schedule_finish_release`
    untouched — push_status echoes it back as gcode_file / subtask_name and
    the slicer matches against its own local subtask_name there. So
    `on_print_command` keeps `filename` for state-feedback but derives the
    stash key from `data["file"]`.
    """

    @pytest.fixture
    def instance(self, tmp_path):
        from backend.app.services.virtual_printer.manager import VirtualPrinterInstance

        return VirtualPrinterInstance(
            vp_id=99,
            name="StashKeyTest",
            mode="queue",
            model="O1C2",
            access_code="12345678",
            serial_suffix="999999999",
            base_dir=tmp_path,
        )

    @pytest.mark.asyncio
    async def test_stash_key_uses_file_field_not_subtask_name(self, instance):
        """BambuStudio's real wire shape: `subtask_name` ≠ `file`.
        on_print_command must stash under `data["file"]` so the FTP-side
        `_add_to_print_queue` lookup matches.
        """
        # mqtt_server.py:_handle_publish hands the bare subtask_name as
        # `filename` and the full print_data body as `data`. The FTP filename
        # lives in `data["file"]`.
        await instance.on_print_command(
            "Filament_Track_Switch_Holder",  # subtask_name (bare)
            {
                "command": "project_file",
                "subtask_name": "Filament_Track_Switch_Holder",
                "file": "Filament_Track_Switch_Holder.gcode.3mf",
                "nozzle_mapping": [16, -1, -1, 1],
            },
        )

        # Stash MUST be under the FTP filename, not the bare subtask_name.
        # `_add_to_print_queue` does `_slicer_print_options.pop(file_path.name, None)`
        # where file_path.name == "Filament_Track_Switch_Holder.gcode.3mf".
        assert "Filament_Track_Switch_Holder.gcode.3mf" in instance._slicer_print_options
        assert "Filament_Track_Switch_Holder" not in instance._slicer_print_options
        # Body must carry nozzle_mapping verbatim.
        stashed = instance._slicer_print_options["Filament_Track_Switch_Holder.gcode.3mf"]
        assert stashed["nozzle_mapping"] == [16, -1, -1, 1]

    @pytest.mark.asyncio
    async def test_stash_key_falls_back_to_filename_when_file_absent(self, instance):
        """Defensive fallback: a slicer that omits the `file` field entirely
        (legacy / non-3MF) must fall back to `filename` (subtask_name), not
        leave the stash unkeyed."""
        await instance.on_print_command(
            "BareName",
            {
                "command": "project_file",
                "subtask_name": "BareName",
                # no "file" field
            },
        )

        assert "BareName" in instance._slicer_print_options

    @pytest.mark.asyncio
    async def test_stash_key_signals_event_under_file_key(self, instance):
        """`_add_to_print_queue` registers a wait-event under `file_path.name`
        when the slicer's project_file arrives late. on_print_command must
        signal THAT event (keyed by the FTP filename), not one keyed by
        subtask_name — else the waiter times out even though the stash is
        present and addressable."""
        import asyncio

        ftp_filename = "Filament_Track_Switch_Holder.gcode.3mf"
        event = asyncio.Event()
        instance._slicer_print_options_events[ftp_filename] = event

        await instance.on_print_command(
            "Filament_Track_Switch_Holder",  # bare subtask_name
            {
                "command": "project_file",
                "subtask_name": "Filament_Track_Switch_Holder",
                "file": ftp_filename,
            },
        )

        # Event keyed by FTP filename must fire even though on_print_command
        # was called with the bare subtask_name.
        assert event.is_set()
