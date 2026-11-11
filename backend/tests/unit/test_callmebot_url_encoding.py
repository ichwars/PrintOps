"""The CallMeBot transport encodes each query value independently."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.app.services.notification_service import NotificationService


@pytest.mark.asyncio
async def test_phone_message_and_key_arrive_as_typed():
    phone = "+49 151 123 456"
    apikey = "key+/&="
    message = "Grüße / Test? & Status = OK"

    def handler(request):
        assert request.url.host == "api.callmebot.com"
        assert request.url.path == "/whatsapp.php"
        assert dict(request.url.params) == {"phone": phone, "text": message, "apikey": apikey}
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = NotificationService()
        with patch.object(service, "_get_client", new=AsyncMock(return_value=client)):
            result = await service._send_callmebot({"phone": phone, "apikey": apikey}, message)
    assert result[0]
