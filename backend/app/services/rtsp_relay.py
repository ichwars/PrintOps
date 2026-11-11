"""Relay RTSP replies without forwarding redirects to camera clients."""

import asyncio
import logging
import re

logger = logging.getLogger(__name__)

_CONTENT_LENGTH = re.compile(rb"^content-length:[ \t]*([0-9]{1,10})[ \t]*$", re.IGNORECASE)
_START_LINE = re.compile(
    rb"(?:RTSP/[0-9.]+[ \t]+[0-9]{3}(?:[ \t]+[^\r\n]*)?|[a-z_]+[ \t]+[^ \t\r\n]+[ \t]+RTSP/[0-9.]+)",
    re.IGNORECASE,
)


def _body_length(header: bytes) -> int | None:
    lengths = []
    for line in header.split(b"\r\n")[1:]:
        if b"\r" in line or b"\n" in line:
            return None
        name, _, _ = line.partition(b":")
        if name.strip().lower() == b"content-length":
            match = _CONTENT_LENGTH.fullmatch(line)
            if match is None:
                return None
            lengths.append(int(match[1]))
    if len(lengths) > 1:
        return None
    return lengths[0] if lengths else 0


def _is_redirect(first_line: bytes) -> bool:
    method, status_or_url, *_ = first_line.upper().split(None, 2)
    return method == b"REDIRECT" or (method.startswith(b"RTSP/") and status_or_url.startswith(b"3"))


async def forward_rtsp_responses(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Check each protocol header before forwarding it, including after RTP starts."""
    try:
        while first := await reader.read(1):
            if first == b"$":
                header = first + await reader.readexactly(3)
                length = int.from_bytes(header[2:], "big")
            else:
                header = first + await reader.readuntil(b"\r\n\r\n")
                first_line = header.split(b"\r\n", 1)[0]
                if _START_LINE.fullmatch(first_line) is None:
                    return
                if _is_redirect(first_line):
                    logger.warning("RTSP camera redirect rejected")
                    return
                length = _body_length(header)
                if length is None:
                    return

            writer.write(header)
            await writer.drain()
            while length:
                data = await reader.read(min(65536, length))
                if not data:
                    return
                writer.write(data)
                await writer.drain()
                length -= len(data)
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, OSError, RuntimeError):
        return
