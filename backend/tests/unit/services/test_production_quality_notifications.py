"""Capabilities occur only in supported action buttons, never reusable API auth."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.app.models.notification import NotificationProvider
from backend.app.services.notification_service import NotificationService


@pytest.mark.parametrize(
    "provider_type,photo", [("ntfy", False), ("ntfy", True), ("telegram", False), ("telegram", True)]
)
async def test_confirmation_actions_use_post_or_marked_button_but_not_message_body(monkeypatch, provider_type, photo):
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        service = NotificationService()
        monkeypatch.setattr(service, "_get_client", AsyncMock(return_value=client))
        provider = NotificationProvider(
            name="Quality",
            provider_type=provider_type,
            config=json.dumps({"server": "https://ntfy.sh", "topic": "quality", "bot_token": "test", "chat_id": "1"}),
            quiet_hours_enabled=False,
        )
        token = "capability-secret"
        urls = {
            verdict: f"https://printops.example/api/v1/archives/outcome-link/{token}/{verdict}"
            for verdict in ("good", "reject")
        }
        result = await service._send_to_provider(
            provider,
            "Quality confirmation",
            "Inspect at https://printops.example/archives?confirm=7",
            image_data=b"photo" if photo else None,
            event_type="print_confirm_request",
            variables={"_outcome_urls": urls},
        )
        assert result[0] is True
        request = requests[0]
        if provider_type == "ntfy":
            assert token not in request.content.decode()
            assert "method=POST" in request.headers["Actions"]
            assert "clear=true" in request.headers["Actions"]
            assert urls["good"] in request.headers["Actions"]
            assert token not in request.headers.get("Message", "")
        elif not photo:
            payload = json.loads(request.content)
            assert token not in payload["text"]
            assert payload["reply_markup"]["inline_keyboard"][0][0]["url"] == urls["good"] + "?tap=1"
        else:
            body = request.content.decode()
            assert urls["good"] + "?tap=1" in body
            caption = body.split('name="caption"')[1].split("\r\n\r\n", 1)[1].split("\r\n--")[0]
            assert token not in caption


async def test_other_notification_provider_does_not_receive_action_capabilities(monkeypatch):
    service = NotificationService()
    send = AsyncMock(return_value=(True, "sent"))
    monkeypatch.setattr(service, "_send_webhook", send)
    provider = NotificationProvider(name="Webhook", provider_type="webhook", config="{}", quiet_hours_enabled=False)
    await service._send_to_provider(
        provider,
        "Quality",
        "Inspect in the app",
        variables={"confirm_url": "/archives?confirm=1", "_outcome_urls": {"good": "secret"}},
    )
    assert send.call_args.kwargs["variables"] == {"confirm_url": "/archives?confirm=1"}


async def test_telegram_send_captures_only_concrete_delivery(monkeypatch):
    from backend.app.services.notification_telegram import send_telegram

    sent = {}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"ok": True, "result": {"message_id": 81, "chat": {"id": -100}}})
        )
    ) as client:
        service = NotificationService()
        monkeypatch.setattr(service, "_get_client", AsyncMock(return_value=client))
        assert (
            await send_telegram(service, {"bot_token": "123:fake", "chat_id": "-100"}, "quality", sent_message=sent)
        )[0]
    assert sent == {"message_id": 81, "chat_id": -100}
