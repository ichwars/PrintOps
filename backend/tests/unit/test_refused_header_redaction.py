import logging
import sys
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import select

from backend.app.core.logging_filters import SensitiveLogRedactFilter
from backend.app.core.response_redaction import RefusedHeaderResponseMask
from backend.app.models.notification import NotificationLog
from backend.app.services.notification_service import NotificationService

ERROR = 'Illegal header value b"Bearer fixture-token\t"'
REDACTED = "Illegal header value [REDACTED]"


def test_refused_header_is_redacted_in_log_arguments_and_chained_tracebacks():
    try:
        try:
            raise httpx.LocalProtocolError(ERROR)
        except httpx.LocalProtocolError as exc:
            raise RuntimeError("Provider test failed") from exc
    except RuntimeError:
        record = logging.LogRecord("provider", logging.ERROR, "", 0, "Connection error: %s", (ERROR,), sys.exc_info())

    assert SensitiveLogRedactFilter().filter(record)
    logged = logging.Formatter().format(record)
    assert "fixture-token" not in logged
    assert logged.count(REDACTED) == 2
    assert "RuntimeError: Provider test failed" in logged


@pytest.mark.asyncio
async def test_refused_header_is_redacted_in_json_and_across_stream_chunks():
    app = FastAPI()
    app.add_middleware(RefusedHeaderResponseMask)

    @app.get("/json")
    def structured_error():
        return JSONResponse({"error": ERROR, "status": "failed"}, media_type="application/problem+json")

    @app.get("/stream")
    def chunked_error():
        return StreamingResponse(
            iter([b'{"error":"Illegal hea', rb"der value b\"Bearer fixture-token\t\"", b'","status":"failed"}']),
            media_type="application/json",
        )

    @app.get("/text")
    def plain_text():
        return PlainTextResponse(ERROR)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/json")
        assert int(response.headers["content-length"]) == len(response.content)
        assert response.json() == {"error": REDACTED, "status": "failed"}
        assert (await client.get("/stream")).json() == {"error": REDACTED, "status": "failed"}
        assert (await client.get("/text")).text == ERROR


@pytest.mark.asyncio
async def test_notification_failure_is_redacted_in_response_and_storage(
    db_session, notification_provider_factory, monkeypatch
):
    service = NotificationService()
    provider = await notification_provider_factory()
    monkeypatch.setattr(service, "_send_ntfy", AsyncMock(return_value=(False, ERROR)))
    assert await service.send_test_notification("ntfy", {}) == (False, REDACTED)

    await service._send_to_providers([provider], "Test title", "Test body", db_session, event_type="print_complete")
    await db_session.refresh(provider)
    logged_error = await db_session.scalar(select(NotificationLog.error_message))
    assert provider.last_error == REDACTED
    assert logged_error == REDACTED
