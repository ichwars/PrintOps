"""Home Assistant settings select one database snapshot and apply environment overrides."""

import pytest

from backend.app.api.routes.settings import get_homeassistant_settings
from backend.app.models.settings import Settings

_DB_URL = "http://db-url:8123"
_DB_TOKEN = "fixture-db-token"
_ENV_URL = "http://supervisor/core"
_ENV_TOKEN = "fixture-env-token"


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    ("db_enabled", "env_url", "env_token", "expected_enabled"),
    [
        (True, None, None, True),
        (False, None, None, False),
        (False, _ENV_URL, _ENV_TOKEN, True),
        (True, _ENV_URL, _ENV_TOKEN, True),
        (False, _ENV_URL, None, False),
        (False, None, _ENV_TOKEN, False),
        (False, "", "", False),
    ],
)
async def test_homeassistant_settings_environment_precedence(
    db_session, monkeypatch, db_enabled, env_url, env_token, expected_enabled
):
    db_session.add_all(
        [
            Settings(key="ha_url", value=_DB_URL),
            Settings(key="ha_token", value=_DB_TOKEN),
            Settings(key="ha_enabled", value=str(db_enabled).lower()),
        ]
    )
    await db_session.flush()

    for name, value in (("HA_URL", env_url), ("HA_TOKEN", env_token)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)

    assert await get_homeassistant_settings(db_session) == {
        "ha_url": env_url or _DB_URL,
        "ha_token": env_token or _DB_TOKEN,
        "ha_enabled": expected_enabled,
        "ha_url_from_env": bool(env_url),
        "ha_token_from_env": bool(env_token),
        "ha_env_managed": bool(env_url and env_token),
    }
