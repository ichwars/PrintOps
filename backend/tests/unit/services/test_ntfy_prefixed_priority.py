"""Stored on_* priorities apply to bare event names sent by the dispatcher."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.services.notification_service import NotificationService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event, priorities, expected",
    [
        ("print_failed", {"on_print_failed": 5}, "5"),
        ("print_failed", {"print_failed": 2, "on_print_failed": 5}, "2"),
        ("on_print_failed", {"on_print_failed": 4}, "4"),
        ("print_failed", {"on_print_failed": 9}, None),
    ],
)
async def test_ntfy_priority_config_matches_dispatch_event(event, priorities, expected):
    service = NotificationService()
    response = MagicMock(status_code=200)
    client = AsyncMock()
    client.post.return_value = response
    service._get_client = AsyncMock(return_value=client)
    ok, _ = await service._send_ntfy(
        {"topic": "printops", "event_priorities": priorities}, "Title", "Body", event_type=event
    )
    assert ok
    assert client.post.call_args.kwargs["headers"].get("Priority") == expected
