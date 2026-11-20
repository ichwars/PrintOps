from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app.services.print_completion_identity import completion_belongs_to_queue_item


@pytest.mark.parametrize(("echo", "expected"), [("gear.3mf", True), ("gear.gcode.3mf", True), ("other.3mf", False)])
async def test_resumed_subtask_echo_matches_archive_filename(echo, expected):
    db = AsyncMock()
    db.get.return_value = SimpleNamespace(id=4, filename="gear.gcode.3mf", print_name="gear", subtask_id=None)
    item = SimpleNamespace(id=3, archive_id=4)
    assert await completion_belongs_to_queue_item(db, item, {"subtask_name": echo}, event_archive_id=None) is expected
