"""Tests for the Bark notification provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.notification_service import NotificationService


def _client_returning(status_code: int, json_body=None, text: str = ""):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    if json_body is None:
        response.json = MagicMock(side_effect=ValueError("not json"))
    else:
        response.json = MagicMock(return_value=json_body)
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    return client


@pytest.mark.asyncio
async def test_send_bark_success_default_server():
    service = NotificationService()
    client = _client_returning(200, {"code": 200, "message": "success"})

    with patch.object(service, "_get_client", new_callable=AsyncMock) as get_client:
        get_client.return_value = client
        success, _ = await service._send_bark({"device_key": "abc123"}, "Title", "Body")

    assert success is True
    call_args = client.post.call_args
    assert call_args.args[0] == "https://api.day.app/push"
    assert call_args.kwargs["json"] == {"device_key": "abc123", "title": "Title", "body": "Body"}


@pytest.mark.asyncio
async def test_send_bark_options_and_custom_server():
    service = NotificationService()
    client = _client_returning(200, {"code": 200})

    with patch.object(service, "_get_client", new_callable=AsyncMock) as get_client:
        get_client.return_value = client
        success, _ = await service._send_bark(
            {
                "device_key": "abc123",
                "server": "https://bark.example.com/",
                "group": "PrintOps",
                "sound": "minuet",
                "level": "timeSensitive",
            },
            "Title",
            "Body",
        )

    assert success is True
    call_args = client.post.call_args
    assert call_args.args[0] == "https://bark.example.com/push"
    assert call_args.kwargs["json"]["group"] == "PrintOps"
    assert call_args.kwargs["json"]["sound"] == "minuet"
    assert call_args.kwargs["json"]["level"] == "timeSensitive"


@pytest.mark.asyncio
async def test_send_bark_reports_json_error_inside_http_200():
    service = NotificationService()
    client = _client_returning(200, {"code": 400, "message": "bad device key"})

    with patch.object(service, "_get_client", new_callable=AsyncMock) as get_client:
        get_client.return_value = client
        success, message = await service._send_bark({"device_key": "abc123"}, "Title", "Body")

    assert success is False
    assert "bad device key" in message


@pytest.mark.asyncio
async def test_send_bark_requires_device_key():
    service = NotificationService()
    success, message = await service._send_bark({}, "Title", "Body")

    assert success is False
    assert "Device key" in message
