"""Lifecycle helpers for authorized FTPS download responses."""

from collections.abc import AsyncIterator

import anyio
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse


async def first_download_chunk(request: Request, stream: AsyncIterator[bytes]) -> bytes | None:
    """Prime errors before HTTP headers, cancelling FTP on an early disconnect."""
    first = None
    error = None
    client_disconnected = False
    async with anyio.create_task_group() as group:

        async def disconnected() -> None:
            nonlocal client_disconnected
            while (await request.receive())["type"] != "http.disconnect":
                pass
            client_disconnected = True
            group.cancel_scope.cancel()

        group.start_soon(disconnected)
        try:
            first = await anext(stream)
        except StopAsyncIteration:
            pass
        except Exception as exc:
            error = exc
        finally:
            group.cancel_scope.cancel()
    if client_disconnected:
        raise HTTPException(499, "Download cancelled")
    if error is not None:
        raise error
    return first


class PrinterFileStreamingResponse(StreamingResponse):
    """Always close the FTPS source, including HTTP send failures/disconnects."""

    def __init__(self, stream: AsyncIterator[bytes], first: bytes, **kwargs):
        self._ftp_stream = stream

        async def body() -> AsyncIterator[bytes]:
            yield first
            async for chunk in stream:
                yield chunk

        super().__init__(body(), **kwargs)

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self._ftp_stream.aclose()
