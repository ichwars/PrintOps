"""Validate TOTP time-window replay at the sign-in entry point."""

import time
from datetime import datetime

import pyotp
import pytest
from httpx import AsyncClient

from backend.tests.integration.test_mfa_api import _login_get_pre_auth_token, _setup_totp_user


@pytest.mark.integration
async def test_future_window_code_cannot_be_replayed_in_its_own_window(async_client: AsyncClient, monkeypatch):
    from backend.app.api.routes import mfa as mfa_routes

    username, password = "replayfuture", "replayfuture1"
    _token, secret = await _setup_totp_user(async_client, username, password)
    totp = pyotp.TOTP(secret)
    next_window = (int(time.time()) // totp.interval + 1) * totp.interval

    class Clock(datetime):
        frozen_at = next_window - 1

        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(cls.frozen_at, tz=tz)

    monkeypatch.setattr(mfa_routes, "datetime", Clock)
    code = totp.at(next_window)
    first = await _login_get_pre_auth_token(async_client, username, password)
    accepted = await async_client.post(
        "/api/v1/auth/2fa/verify",
        json={"pre_auth_token": first, "method": "totp", "code": code},
    )
    assert accepted.status_code == 200

    Clock.frozen_at = next_window + 1
    second = await _login_get_pre_auth_token(async_client, username, password)
    rejected = await async_client.post(
        "/api/v1/auth/2fa/verify",
        json={"pre_auth_token": second, "method": "totp", "code": code},
    )
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "TOTP code already used"
