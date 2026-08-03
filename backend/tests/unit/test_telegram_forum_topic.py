"""Tests for optional Telegram forum-topic delivery via message_thread_id."""

import httpx
import pytest

from backend.app.services.notification_service import NotificationService


class _CaptureClient:
    def __init__(self):
        self.is_closed = False
        self.calls: list[dict] = []

    async def post(self, url, data=None, files=None, json=None):
        self.calls.append({"url": url, "data": data, "files": files, "json": json})
        return httpx.Response(200, json={"ok": True, "result": {}})


@pytest.fixture
def service_with_capture():
    service = NotificationService()
    client = _CaptureClient()
    service._http_client = client
    return service, client


BASE_CONFIG = {"bot_token": "123456:AAbbCC", "chat_id": "-1002520100736"}
PNG = b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_thread_id_omitted_when_unset(service_with_capture):
    service, client = service_with_capture
    ok, _ = await service._send_telegram(BASE_CONFIG, "*T*\nbody")

    assert ok
    assert "message_thread_id" not in client.calls[0]["json"]


@pytest.mark.asyncio
async def test_sendmessage_carries_thread_id_as_int(service_with_capture):
    service, client = service_with_capture
    ok, _ = await service._send_telegram({**BASE_CONFIG, "message_thread_id": "25"}, "*T*\nbody")

    assert ok
    assert client.calls[0]["json"]["message_thread_id"] == 25
    assert isinstance(client.calls[0]["json"]["message_thread_id"], int)


@pytest.mark.asyncio
async def test_sendphoto_carries_thread_id(service_with_capture):
    service, client = service_with_capture
    ok, _ = await service._send_telegram({**BASE_CONFIG, "message_thread_id": "25"}, "*T*\nbody", image_data=PNG)

    assert ok
    assert client.calls[0]["url"].endswith("/sendPhoto")
    assert client.calls[0]["data"]["message_thread_id"] == 25


@pytest.mark.asyncio
async def test_non_numeric_thread_id_fails_without_sending(service_with_capture):
    service, client = service_with_capture
    ok, error = await service._send_telegram({**BASE_CONFIG, "message_thread_id": "General"}, "*T*\nbody")

    assert not ok
    assert "not a number" in error
    assert "AAbbCC" not in error
    assert client.calls == []
