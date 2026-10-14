"""Discord transport; literal app content is bounded after encoding."""

import json

from backend.app.services.notification_plain_text import escape_markdown, send_parts, split_text, utf16_size


async def send_discord(self, config, title, message, image_data=None, plain_text=False) -> tuple[bool, str]:
    webhook_url = config.get("webhook_url", "").strip()
    if not webhook_url:
        return False, "Webhook URL is required"
    if not (
        webhook_url.startswith("https://discord.com/api/webhooks/")
        or webhook_url.startswith("https://discordapp.com/api/webhooks/")
    ):
        return False, "Invalid Discord webhook URL"

    if plain_text:
        encoded_title = escape_markdown(title)
        if utf16_size(encoded_title) > 256:
            # A long encoded title becomes part of the description, without loss.
            message, encoded_title = f"{title}\n{message}", ""
        title = encoded_title
        descriptions = split_text(message, 4096, encode=escape_markdown)
    else:
        descriptions = [message]
    client = await self._get_client()

    async def send(description):
        # One embed per request: 256 + 4096 stays below the 6000 aggregate cap.
        embed = {"title": title, "description": description, "color": 0x00AE42}
        payload = {"embeds": [embed], **({"allowed_mentions": {"parse": []}} if plain_text else {})}
        if image_data:
            embed["image"] = {"url": "attachment://photo.jpg"}
            response = await client.post(
                webhook_url,
                data={"payload_json": json.dumps(payload)},
                files={"files[0]": ("photo.jpg", image_data, "image/jpeg")},
            )
        else:
            response = await client.post(webhook_url, json=payload)
        if response.status_code in (200, 204):
            return True, "Message sent successfully"
        return False, f"HTTP {response.status_code}: {response.text[:200]}"

    if plain_text:
        return await send_parts(send, descriptions)
    return await send(message)
