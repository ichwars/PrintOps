"""Isolated imports and startup logging must work outside the full test registry."""

import os
import subprocess
import sys
import textwrap

import pytest


def isolated(code, tmp_path, **environment):
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        env={**os.environ, "DATA_DIR": str(tmp_path), "LOG_TO_FILE": "false", **environment},
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_standalone_registry_resolves_telegram_run_foreign_key(tmp_path):
    isolated(
        """
        from sqlalchemy import create_engine
        from backend.app.models.spool_k_profile import SpoolKProfile
        from backend.app.api.routes.settings import _import_sqlite_to_postgres
        from backend.app.core.database import Base
        Base.metadata.create_all(create_engine('sqlite:///:memory:'))
        assert 'print_log_entries' in Base.metadata.tables
        """,
        tmp_path,
    )


@pytest.mark.parametrize("debug", ["true", "false"])
def test_startup_http_logging_never_exposes_telegram_credentials(tmp_path, debug):
    isolated(
        """
        import asyncio, io, logging
        import httpx
        from backend.app import main
        from backend.app.services.notification_telegram import send_telegram

        output = io.StringIO()
        handler = logging.StreamHandler(output)
        handler.setLevel(logging.DEBUG)
        logging.getLogger().addHandler(handler)
        # Capture application debug as well; do not override library policy.
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger('backend.test').debug('nonsecret diagnostic')
        token = '123:synthetic-runtime-secret'
        requests = []

        async def exercise():
            for status in (200, 409):
                def respond(request):
                    requests.append((request.url.path.rsplit('/', 1)[-1], status))
                    return httpx.Response(status, json={'ok': status == 200, 'result': {}})
                async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                    # Actual HTTPX records for both polling endpoints, including failure.
                    for method in ('getWebhookInfo', 'getUpdates'):
                        response = await client.post(f'https://api.telegram.org/bot{token}/{method}')
                        try:
                            response.raise_for_status()
                        except httpx.HTTPError:
                            pass
                    class Sender:
                        async def _get_client(self):
                            return client
                    for image in (None, b'fake-photo'):
                        await send_telegram(Sender(), {'bot_token': token, 'chat_id': '-100'}, 'test', image)
        asyncio.run(exercise())
        from backend.app.api.routes.support import _apply_log_level
        for enabled in (True, False):
            _apply_log_level(enabled)
            assert logging.getLogger('httpx').getEffectiveLevel() >= logging.WARNING
            assert logging.getLogger('httpcore.http11').getEffectiveLevel() >= logging.WARNING
            asyncio.run(exercise())
        assert len(requests) == 24
        assert 'nonsecret diagnostic' in output.getvalue()
        assert token not in output.getvalue(), output.getvalue()
        assert logging.getLogger('httpcore.http11').getEffectiveLevel() >= logging.WARNING
        """,
        tmp_path,
        DEBUG=debug,
    )
