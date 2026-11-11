import html
from unittest.mock import AsyncMock, Mock

import pytest

from backend.app.models.notification_template import NotificationTemplate
from backend.app.schemas.notification_template import EVENT_VARIABLES, SAMPLE_DATA
from backend.tests.integration.test_advanced_auth_api import _setup_admin, _setup_smtp_and_advanced_auth

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.mark.parametrize("admin_reset", [False, True], ids=["self-service", "administrator"])
async def test_password_reset_routes_append_the_link_outside_editable_text(
    async_client, db_session, monkeypatch, admin_reset
):
    token = await _setup_admin(async_client, "resetadmin", "AdminPass1!")
    headers = {"Authorization": f"Bearer {token}"}
    await _setup_smtp_and_advanced_auth(async_client, token)
    db_session.add(
        NotificationTemplate(
            event_type="password_reset",
            name="Password Reset",
            title_template="Reset for {username}{reset_url}",
            body_template="Our own wording.\nhttps://elsewhere.example.test/?next={reset_url}\n{password}{login_url}",
            is_default=False,
        )
    )
    await db_session.commit()
    monkeypatch.setattr("backend.app.api.routes.users.send_email", Mock())
    created = await async_client.post(
        "/api/v1/users/",
        headers=headers,
        json={"username": "reset-user", "email": "reset-user@example.test", "role": "user"},
    )
    assert created.status_code == 201

    base_url = "https://printops.example.test/?a=1&b=2"
    monkeypatch.setattr("backend.app.api.routes.auth.get_external_login_url", AsyncMock(return_value=base_url))
    send = Mock()
    monkeypatch.setattr("backend.app.api.routes.auth.send_email", send)
    if admin_reset:
        response = await async_client.post(
            "/api/v1/auth/reset-password", headers=headers, json={"user_id": created.json()["id"]}
        )
    else:
        response = await async_client.post("/api/v1/auth/forgot-password", json={"email": "reset-user@example.test"})

    assert response.status_code == 200
    send.assert_called_once()
    _, recipient, subject, text_body, html_body = send.call_args.args
    assert recipient == "reset-user@example.test"
    assert subject == "Reset for reset-user"
    template_text, link = text_body.split("\n\n")
    assert template_text == "Our own wording.\nhttps://elsewhere.example.test/?next="
    assert link.startswith(f"{base_url}#reset_token=")
    assert text_body.count("#reset_token=") == 1
    assert f'href="{html.escape(link)}"' in html_body
    assert not {"password", "login_url", "reset_url"}.intersection(EVENT_VARIABLES["password_reset"])
    assert not {"password", "login_url", "reset_url"}.intersection(SAMPLE_DATA["password_reset"])
