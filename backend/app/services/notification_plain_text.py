"""Transport-specific literal text for untrusted application content."""

import html
import re


def escape_markdown(value: str) -> str:
    # Also suppress raw HTML, mentions and automatic link syntax.
    value = html.escape(value, quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~\-])", r"\\\1", value)


def utf16_size(value: str) -> int:
    """Conservatively respect consumers that count UTF-16 code units."""
    return len(value.encode("utf-16-le")) // 2


def split_text(value: str, limit: int, encode=str, measure=utf16_size):
    """Split only between source codepoints, never inside an encoded escape/entity."""
    parts, size = [], 0
    for character in value:
        fragment = encode(character)
        width = measure(fragment)
        if size + width > limit and parts:
            yield "".join(parts)
            parts, size = [], 0
        parts.append(fragment)
        size += width
    if parts:
        yield "".join(parts)


def slack_app_payloads(title: str, message: str, image_url: str | None = None):
    for part in split_text(f"{title}\n{message}", 3000):
        # Mattermost ignores Slack's parse/mrkdwn/link_names flags. Escape its
        # fallback separately and break @mention tokens with a zero-width space.
        # Worst-case entity expansion is 5x: <=15000 < Mattermost's 16383 limit.
        payload = {
            "text": escape_markdown(part).replace("@", "@\u200b"),
            "mrkdwn": False,
            "parse": "none",
            "link_names": False,
            "blocks": [{"type": "section", "text": {"type": "plain_text", "text": part, "emoji": False}}],
        }

        if image_url:
            payload["blocks"].append({"type": "image", "image_url": image_url, "alt_text": "Printer camera snapshot"})
        yield payload


async def send_parts(send, parts) -> tuple[bool, str]:
    """Stop at the first rejection; report partial delivery instead of success."""
    for number, part in enumerate(parts, 1):
        success, detail = await send(part)
        if not success:
            return False, f"Part {number} failed (earlier parts may have been delivered): {detail}"
    return True, "Message sent successfully"
