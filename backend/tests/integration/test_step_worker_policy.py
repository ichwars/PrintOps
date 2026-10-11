"""Only the successful local STEP worker script receives the native glue policy."""

import pytest
from starlette.requests import Request
from starlette.responses import Response

from backend.app.main import security_headers_middleware


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path,status,mime,method,allowed",
    [
        ("/assets/stepPreview.worker-abc123.js", 200, "application/javascript", "GET", True),
        ("/assets/stepPreview.worker-abc123.js", 200, "text/javascript; charset=utf-8", "GET", True),
        ("/assets/stepPreview.worker-abc123.js", 404, "application/javascript", "GET", False),
        ("/assets/stepPreview.worker-abc123.js", 200, "text/html", "GET", False),
        ("/assets/stepPreview.worker-abc123.js", 200, "application/javascript", "POST", False),
        ("/assets/other-abc123.js", 200, "application/javascript", "GET", False),
        ("/assets/prefixstepPreview.worker-abc123.js", 200, "application/javascript", "GET", False),
        ("/assets/stepPreview.worker-abc123.js/extra", 200, "application/javascript", "GET", False),
        ("/", 200, "text/html", "GET", False),
    ],
)
async def test_worker_policy_is_scoped_to_the_exact_javascript_asset(path, status, mime, method, allowed):
    request = Request(
        {"type": "http", "path": path, "method": method, "scheme": "http", "server": ("test", 80), "headers": []}
    )

    async def next_response(_request):
        return Response("", status_code=status, headers={"content-type": mime})

    response = await security_headers_middleware(request, next_response)
    policy = response.headers["Content-Security-Policy"]
    assert ("'unsafe-eval'" in policy) is allowed
    if allowed:
        assert "connect-src 'none'" in policy
        assert "worker-src 'none'" in policy
        assert "default-src 'none'" in policy
    else:
        assert "connect-src 'self'" in policy
        assert "nonce-" in policy
