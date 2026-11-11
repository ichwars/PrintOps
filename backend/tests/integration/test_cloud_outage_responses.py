import httpx
import pytest

from backend.app.api.routes import cloud as routes
from backend.app.services.bambu_cloud import BambuCloudService


@pytest.mark.parametrize("status, expected", [(401, 401), (403, 401), (503, 502), (None, 502)])
async def test_token_registration_distinguishes_invalid_token_and_outage(async_client, monkeypatch, status, expected):
    def response(request):
        if status is None:
            raise httpx.ConnectError("fixture connection refused", request=request)
        return httpx.Response(status, text="<html>fixture edge response</html>")

    def service(*args, **kwargs):
        client = BambuCloudService(*args, **kwargs)
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(response))
        client._owns_client = True
        return client

    monkeypatch.setattr(routes, "BambuCloudService", service)
    result = await async_client.post("/api/v1/cloud/token", json={"access_token": "fixture-cloud-token"})
    assert result.status_code == expected
    assert "fixture" not in result.text
