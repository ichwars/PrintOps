from unittest.mock import AsyncMock

import httpx
import pytest

from backend.app.services import log_reader
from backend.app.services.rest_smart_plug import RESTSmartPlugService

_LEGACY_LOG = (
    "2026-11-10 20:30:45,123 INFO [backend.app.services.rest_smart_plug] "
    "Turned ON plug via POST http://user:fixture-userinfo@plug.example.test:1234/fixture-path?auth_key=fixture-query\n"
    "2026-11-10 20:31:45,123 WARNING [backend.app.services.rest_smart_plug] "
    "REST smart plug at http://plug.example.test/fixture-path: headers JSON: fixture-header\n"
    "  Request failed at http://plug.example.test/fixture-traceback\n"
    "2026-11-10 20:32:45,123 INFO [httpx] "
    'HTTP Request: GET https://plug.example.test/webhook/fixture-hook "HTTP/1.1 200 OK"\n'
    "2026-11-10 20:33:45,123 ERROR [backend.app.services.notification_service] "
    "Failed with Illegal header value b'Bearer fixture-refused'\n"
)


def test_historical_plug_credentials_are_removed_before_log_search_or_export(monkeypatch, tmp_path):
    monkeypatch.setattr(log_reader.settings, "log_dir", tmp_path)
    (tmp_path / "printops.log").write_text(_LEGACY_LOG)
    entries, total = log_reader.read_log_entries()

    assert total == 5
    assert len(entries) == 4
    assert all("fixture-" not in entry.message for entry in entries)
    assert len(log_reader.read_log_entries(search="fixture-path")[0]) == 0
    assert len(log_reader.read_log_entries(search="Turned ON")[0]) == 1

    bundle_log = log_reader.sanitize_log_content(_LEGACY_LOG)
    assert "fixture-" not in bundle_log
    assert "http://[HOST]:1234/[REDACTED]" in bundle_log
    assert "Illegal header value [REDACTED]" in bundle_log
    assert len(bundle_log.splitlines()) == total


@pytest.mark.asyncio
async def test_rest_connection_error_does_not_quote_headers_or_urls(monkeypatch):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.request.side_effect = httpx.LocalProtocolError("Illegal header value b'Bearer fixture-secret'")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: client)

    result = await RESTSmartPlugService().test_connection("http://plug.example.test/fixture-webhook")
    assert result == {"success": False, "error": "Connection failed (LocalProtocolError)"}
