"""Inventory maintenance must not pretend that a spool was used for printing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.spoolman import SpoolmanClient


@pytest.mark.asyncio
async def test_weight_location_and_extra_updates_do_not_stamp_last_used():
    client = SpoolmanClient("http://localhost:7912")
    response = MagicMock()
    response.json.return_value = {"id": 42}
    with patch.object(client, "_request_spool", AsyncMock(return_value=response)) as request:
        await client.update_spool(42, remaining_weight=75, location="Shelf", extra={"test": "value"})
    payload = request.call_args.kwargs["json_body"]
    assert payload == {"remaining_weight": 75, "location": "Shelf", "extra": {"test": "value"}}
