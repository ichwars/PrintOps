"""Telegram transport with explicit literal-text support for app content."""

import json
from typing import Any

from backend.app.services.notification_plain_text import send_parts, split_text, utf16_size


async def send_telegram(
    self,
    config: dict,
    message: str,
    image_data: bytes | None = None,
    outcome_urls: dict[str, str] | None = None,
    plain_text: bool = False,
) -> tuple[bool, str]:
    """Send notification via Telegram bot."""
    # App-containing digests include full bodies; keep each plain message within
    # Telegram's post-parse limit (caption limit for any photo attachment).
    limit = 1024 if image_data else 4096
    if plain_text and utf16_size(message) > limit:
        return await send_parts(
            lambda part: send_telegram(self, config, part, image_data, outcome_urls, plain_text=True),
            split_text(message, limit),
        )
    bot_token = config.get("bot_token", "").strip()
    chat_id = config.get("chat_id", "").strip()

    if not bot_token or not chat_id:
        return False, "Bot token and chat ID are required"

    keyboard = None
    if outcome_urls:
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "Good parts", "url": outcome_urls["good"] + "?tap=1"},
                    {"text": "Reject parts", "url": outcome_urls["reject"] + "?tap=1"},
                ]
            ]
        }

    thread_id_raw = str(config.get("message_thread_id") or "").strip()
    message_thread_id: int | None = None
    if thread_id_raw:
        try:
            message_thread_id = int(thread_id_raw)
        except ValueError:
            return False, f"Invalid message thread ID: {thread_id_raw!r} is not a number"

    # Escape underscores in the message body so Telegram Markdown
    # parsing doesn't break on job names like "A1_plate_8" or error
    # codes like "0300_0001".  The title is already wrapped in *bold*
    # markers, so only escape after the first newline.
    if not plain_text and "\n" in message:
        title_part, body_part = message.split("\n", 1)
        body_part = body_part.replace("_", "\\_")
        message = f"{title_part}\n{body_part}"

    client = await self._get_client()

    if image_data:
        # Use sendPhoto to attach the thumbnail with the caption
        url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
        form: dict[str, Any] = {
            "chat_id": chat_id,
            "caption": message,
            **({} if plain_text else {"parse_mode": "Markdown"}),
        }
        if keyboard:
            form["reply_markup"] = json.dumps(keyboard)
        if message_thread_id is not None:
            form["message_thread_id"] = message_thread_id
        response = await client.post(
            url,
            data=form,
            files={"photo": ("photo.jpg", image_data, "image/jpeg")},
        )
    else:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data: dict[str, Any] = {
            "chat_id": chat_id,
            "text": message,
            **({} if plain_text else {"parse_mode": "Markdown"}),
            **({"reply_markup": keyboard} if keyboard else {}),
        }
        if message_thread_id is not None:
            data["message_thread_id"] = message_thread_id
        response = await client.post(url, json=data)

    if response.status_code == 200:
        result = response.json()
        if result.get("ok"):
            return True, "Message sent successfully"
        else:
            return False, f"Telegram error: {result.get('description', 'Unknown error')}"
    else:
        return False, f"HTTP {response.status_code}: {response.text[:200]}"
