"""Tests for the CSRF handshake on Bambu Cloud TOTP sign-in."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.services.bambu_cloud import BambuCloudService


def _response(status: int, body: str) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.text = body
    response.json.return_value = json.loads(body) if body else {}
    response.cookies = {}
    return response


def _service(*, csrf_token: str | None = "csrf-abc123", region: str = "global") -> BambuCloudService:
    service = BambuCloudService(region=region)
    client = MagicMock()
    client.get = AsyncMock(return_value=_response(204, ""))
    client.post = AsyncMock(return_value=_response(200, '{"accessToken": "tok"}'))
    jar = MagicMock()
    jar.get.return_value = csrf_token
    client.cookies = jar
    service._client = client
    return service


@pytest.mark.asyncio
async def test_totp_fetches_csrf_token_before_posting_code():
    service = _service()

    result = await service.verify_totp("tfa-key", "123456")

    assert result["success"] is True
    service._client.get.assert_awaited_once()
    assert service._client.get.await_args.args[0] == "https://bambulab.com/api/csrf"


@pytest.mark.asyncio
async def test_totp_echoes_cookie_in_x_bbl_csrf_token_header():
    service = _service(csrf_token="csrf-abc123")

    await service.verify_totp("tfa-key", "123456")

    headers = service._client.post.await_args.kwargs["headers"]
    assert headers["x-bbl-csrf-token"] == "csrf-abc123"


@pytest.mark.asyncio
async def test_totp_uses_china_origin_for_china_region():
    service = _service(region="china")

    await service.verify_totp("tfa-key", "123456")

    assert service._client.get.await_args.args[0] == "https://bambulab.cn/api/csrf"
    assert service._client.post.await_args.args[0] == "https://bambulab.cn/api/sign-in/tfa"


@pytest.mark.asyncio
async def test_totp_does_not_post_code_without_csrf_token():
    service = _service(csrf_token=None)

    result = await service.verify_totp("tfa-key", "123456")

    assert result["success"] is False
    assert "security token" in result["message"]
    service._client.post.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["missing_cookie", "missing_header"])
async def test_totp_csrf_rejection_says_code_was_not_checked(reason):
    service = _service()
    service._client.post = AsyncMock(
        return_value=_response(403, json.dumps({"error": f"CSRF error: {reason}", "reason": reason}))
    )

    result = await service.verify_totp("tfa-key", "123456")

    assert result["success"] is False
    assert "before checking your code" in result["message"]
    assert "Invalid" not in result["message"]


@pytest.mark.asyncio
async def test_totp_wrong_code_still_reports_bambu_message():
    service = _service()
    service._client.post = AsyncMock(return_value=_response(400, '{"code":5,"error":"Login failed"}'))

    result = await service.verify_totp("tfa-key", "000000")

    assert result["success"] is False
    assert result["message"] == "Login failed"
