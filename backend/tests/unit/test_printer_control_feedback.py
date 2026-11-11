"""Stop attribution and long printer probes use only the evidence they have."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.api.routes import printers_controls as controls, printers_status as status_routes

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "state,marked",
    [
        ("IDLE", False),
        ("FINISH", False),
        ("FAILED", False),
        ("RUNNING", True),
        ("PAUSE", True),
        ("unknown", True),
        (None, True),
    ],
)
@pytest.mark.parametrize("channel", ["local", "cloud"])
async def test_a_stop_on_a_known_idle_printer_does_not_mark_a_later_failure_as_cancelled(state, marked, channel):
    async def send(printer_id, *, local_send, **kwargs):
        if channel == "local":
            assert local_send(SimpleNamespace(stop_print=lambda: True))
        return {"success": True, "control_channel": channel}

    with (
        patch.object(controls, "_send_print_command_with_cloud_fallback", send),
        patch.object(controls, "printer_manager") as manager,
        patch("backend.app.main.mark_printer_stopped_by_user") as mark,
    ):
        manager.get_status.return_value = SimpleNamespace(state=state) if state is not None else None
        response = await controls.stop_print(1, current_user=None, cloud_owner=None, db=MagicMock())
    assert response["success"] is True
    assert mark.called is marked


async def test_diagnostic_releases_the_read_session_before_waiting_on_network():
    printer = SimpleNamespace(ip_address="192.0.2.1")
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.execute.return_value.scalar_one_or_none.return_value = printer
    db.close = AsyncMock()

    async def probe(*args, **kwargs):
        db.close.assert_awaited_once()
        return {"printer": "mock"}

    with patch.object(status_routes, "run_connection_diagnostic", probe):
        assert await status_routes.diagnose_printer(1, db=db) == {"printer": "mock"}


async def test_object_reload_releases_db_and_never_uses_printer_filename_for_local_path(tmp_path):
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.execute.return_value.scalar_one_or_none.return_value = SimpleNamespace(
        ip_address="192.0.2.1", access_code="test", model="P1S"
    )
    db.close = AsyncMock()
    client = MagicMock()
    client.state = SimpleNamespace(
        subtask_name="../../outside", printable_objects={}, skipped_objects=[], state="RUNNING"
    )
    called = []

    async def download(ip, code, remote, local, **kwargs):
        db.close.assert_awaited_once()
        assert local.resolve().is_relative_to((tmp_path / "temp").resolve())
        assert "outside" not in local.name
        called.append(local)
        return False

    with (
        patch.object(controls, "printer_manager") as manager,
        patch.object(controls, "settings", SimpleNamespace(archive_dir=tmp_path)),
        patch("backend.app.services.bambu_ftp.download_file_try_paths_async", download),
    ):
        manager.get_client.return_value = client
        result = await controls.get_printable_objects(1, reload=True, db=db)
    assert result["total"] == 0
    assert len(called) == 1
