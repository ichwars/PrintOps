import html
from unittest.mock import AsyncMock, Mock

import pytest

from backend.app.models.notification_template import NotificationTemplate
from backend.app.schemas.notification_template import EVENT_VARIABLES, SAMPLE_DATA
from backend.tests.integration.test_advanced_auth_api import _setup_admin, _setup_smtp_and_advanced_auth

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_creating_a_user_keeps_the_password_out_of_editable_text_and_urls(async_client, db_session, monkeypatch):
    token = await _setup_admin(async_client, "welcomeadmin", "AdminPass1!")
    await _setup_smtp_and_advanced_auth(async_client, token)
    db_session.add(
        NotificationTemplate(
            event_type="user_created",
            name="Welcome Email",
            title_template="Welcome {password}",
            body_template="Open https://example.test/activate?password={password}\n<em>{username}</em>",
            is_default=False,
        )
    )
    await db_session.commit()
    password = 'fixture<>&"Password1!'
    login_url = 'https://printops.example.test/login?a=1&b="2"'
    monkeypatch.setattr("backend.app.api.routes.users.generate_secure_password", lambda: password)
    monkeypatch.setattr("backend.app.api.routes.users.get_external_login_url", AsyncMock(return_value=login_url))
    send = Mock()
    monkeypatch.setattr("backend.app.api.routes.users.send_email", send)

    response = await async_client.post(
        "/api/v1/users/",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "new-user", "email": "new-user@example.test", "role": "user"},
    )

    assert response.status_code == 201
    send.assert_called_once()
    _, recipient, subject, text_body, html_body = send.call_args.args
    assert recipient == "new-user@example.test"
    assert subject == "Welcome "
    template_text, login_details = text_body.split("\n\n")
    assert template_text == "Open https://example.test/activate?password=\n<em>new-user</em>"
    assert login_details == f"Username: new-user\nPassword: {password}"
    assert html_body.count(html.escape(password)) == 1
    assert f'href="{html.escape(login_url)}"' in html_body
    assert "&lt;em&gt;new-user&lt;/em&gt;" in html_body
    assert "password" not in EVENT_VARIABLES["user_created"]
    assert "password" not in SAMPLE_DATA["user_created"]
