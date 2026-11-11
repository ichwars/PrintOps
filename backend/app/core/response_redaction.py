"""Mask refused HTTP header values in outgoing JSON, including older records."""

import re

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REFUSED_HEADER_JSON = re.compile(rb'(Illegal header (?:value|name) )(?:[^"\\]|\\.)*', re.IGNORECASE)


class RefusedHeaderResponseMask:
    """Redact HTTP client errors without altering downloads or non-JSON streams."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start: Message | None = None
        chunks: list[bytes] = []

        async def masking_send(message: Message) -> None:
            nonlocal start
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=message["headers"])
                media_type = headers.get("content-type", "").partition(";")[0].strip().lower()
                encoding = headers.get("content-encoding", "identity")
                if (media_type == "application/json" or media_type.endswith("+json")) and encoding == "identity":
                    start = message
                    return
            if start is None:
                await send(message)
                return
            if message["type"] != "http.response.body":
                await send(start)
                start = None
                await send(message)
                return

            chunk = message.get("body", b"")
            if message.get("more_body", False):
                chunks.append(chunk)
                return
            original = b"".join([*chunks, chunk]) if chunks else chunk
            body = _REFUSED_HEADER_JSON.sub(rb"\1[REDACTED]", original)
            headers = MutableHeaders(raw=start["headers"])
            if body != original and "content-length" in headers:
                headers["content-length"] = str(len(body))
            await send(start)
            start = None
            await send({**message, "body": body})

        await self.app(scope, receive, masking_send)
