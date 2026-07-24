"""Security regressions for Git provider connection testing."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.app.api.routes.github_backup import test_connection as route_test_connection
from backend.app.schemas.github_backup import GitHubTestConnectionRequest, ProviderType


@pytest.mark.asyncio
async def test_connection_consumes_secret_from_request_body_model():
    request = GitHubTestConnectionRequest(
        repo_url="https://github.com/test/repo",
        token="ghp_secret",
        provider=ProviderType.GITHUB,
    )
    result = {
        "success": True,
        "message": "Connection successful",
        "repo_name": "test/repo",
        "permissions": {"push": True},
        "is_private": True,
    }

    with patch(
        "backend.app.api.routes.github_backup.github_backup_service.test_connection",
        new=AsyncMock(return_value=result),
    ) as mocked:
        response = await route_test_connection(request, None)

    mocked.assert_awaited_once_with(
        "https://github.com/test/repo",
        "ghp_secret",
        provider=ProviderType.GITHUB,
    )
    assert response.success is True
