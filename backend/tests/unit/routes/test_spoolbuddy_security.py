"""Security regressions for SpoolBuddy remote configuration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.app.api.routes.spoolbuddy import queue_system_config_update
from backend.app.schemas.spoolbuddy import SystemConfigRequest


@pytest.mark.asyncio
async def test_remote_system_config_requires_https():
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace()
    db = AsyncMock()
    db.execute.return_value = result

    with pytest.raises(HTTPException) as exc_info:
        await queue_system_config_update(
            "sb-test",
            SystemConfigRequest(backend_url="http://192.168.1.100:8000"),
            db,
            None,
        )

    assert exc_info.value.status_code == 400
    assert "HTTPS is required" in str(exc_info.value.detail)
    db.commit.assert_not_awaited()
