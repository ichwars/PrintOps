"""Real ASGI dashboard sockets honor committed grants and printer restrictions."""

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest

from backend.app.api.routes import websocket
from backend.app.core.auth import generate_api_key
from backend.app.core.websocket import ws_manager
from backend.app.models.api_key import APIKey
from backend.tests.integration.test_long_lived_tokens_api import _create_user, _login, _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
def live_events(monkeypatch):
    monkeypatch.setattr(ws_manager, "_lock", asyncio.Lock())
    monkeypatch.setattr(ws_manager, "active_connections", [])
    monkeypatch.setattr(websocket.printer_manager, "get_all_statuses", lambda: {1: "first", 2: "second"})
    monkeypatch.setattr(websocket.printer_manager, "get_status", lambda pid: {1: "first", 2: "second"}.get(pid))
    monkeypatch.setattr(websocket, "printer_state_to_dict", lambda state, *_args: {"fixture": state})


@pytest.fixture
async def dashboard_key(db_session):
    secret, key_hash, prefix = generate_api_key()
    key = APIKey(name="Dashboard fixture", key_hash=key_hash, key_prefix=prefix, can_read_status=True, printer_ids=[1])
    db_session.add(key)
    await db_session.commit()
    return key, secret


@asynccontextmanager
async def open_socket(token):
    from backend.app.main import app

    requests = asyncio.Queue()
    replies = asyncio.Queue()
    scope = {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "scheme": "ws",
        "path": "/api/v1/ws",
        "query_string": urlencode({"token": token}).encode(),
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
        "headers": [],
        "subprotocols": [],
    }
    await requests.put({"type": "websocket.connect"})
    task = asyncio.create_task(app(scope, requests.get, replies.put))

    async def receive():
        return await asyncio.wait_for(replies.get(), timeout=4)

    async def send(data):
        await requests.put({"type": "websocket.receive", "text": json.dumps(data)})

    try:
        yield SimpleNamespace(receive=receive, send=send)
    finally:
        await requests.put({"type": "websocket.disconnect", "code": 1000})
        await asyncio.wait_for(task, timeout=4)


async def token_for(client, headers):
    response = await client.post("/api/v1/auth/ws-token", headers=headers)
    assert response.status_code == 200
    return response.json()["token"]


async def assert_status(socket, printer_id):
    message = await socket.receive()
    assert message["type"] == "websocket.send"
    data = json.loads(message["text"])
    assert data["type"] == "printer_status"
    assert data["printer_id"] == printer_id


async def assert_pong(socket):
    await socket.send({"type": "ping"})
    message = await socket.receive()
    assert message["type"] == "websocket.send"
    assert json.loads(message["text"]) == {"type": "pong"}


async def test_group_permission_and_printer_scope_update_open_dashboard(
    async_client, printer_factory, archive_factory, live_events
):
    first = await printer_factory()
    second = await printer_factory()
    assert (first.id, second.id) == (1, 2)
    visible_archive = await archive_factory(first.id)
    hidden_archive = await archive_factory(second.id)
    admin = {"Authorization": f"Bearer {await _setup_admin(async_client)}"}
    group = await async_client.post(
        "/api/v1/groups", headers=admin, json={"name": "Live viewers", "permissions": ["websocket:connect"]}
    )
    assert group.status_code == 201
    group_id = group.json()["id"]
    user_id = await _create_user(async_client, admin["Authorization"].removeprefix("Bearer "), "liveobserver")
    response = await async_client.patch(
        f"/api/v1/users/{user_id}",
        headers=admin,
        json={"group_ids": [group_id], "allowed_printer_ids": [first.id]},
    )
    assert response.status_code == 200
    viewer = {"Authorization": f"Bearer {await _login(async_client, 'liveobserver')}"}
    token = await token_for(async_client, viewer)

    async with open_socket(token) as socket:
        assert (await socket.receive())["type"] == "websocket.accept"
        await assert_status(socket, first.id)
        await socket.send({"type": "get_status", "printer_id": second.id})
        await assert_pong(socket)
        await ws_manager.broadcast({"type": "printer_status", "printer_id": second.id, "data": {}})
        await ws_manager.broadcast({"type": "printer_status", "printer_id": first.id, "data": {}})
        await assert_status(socket, first.id)
        await ws_manager.send_archive_created({"id": 7, "printer_id": second.id, "filename": "private"})
        await ws_manager.send_archive_updated({"id": hidden_archive.id, "cost": 5})
        await ws_manager.send_archive_updated({"id": -999, "cost": 5})
        await ws_manager.send_archive_updated({"id": visible_archive.id, "cost": 1})
        await ws_manager.broadcast({"type": "printer_status", "printer_id": first.id, "data": {}})
        assert json.loads((await socket.receive())["text"]) == {"type": "archive_updated"}
        await assert_status(socket, first.id)

        response = await async_client.patch(
            f"/api/v1/users/{user_id}", headers=admin, json={"allowed_printer_ids": [second.id]}
        )
        assert response.status_code == 200
        await ws_manager.broadcast({"type": "printer_status", "printer_id": first.id, "data": {}})
        await ws_manager.broadcast({"type": "printer_status", "printer_id": second.id, "data": {}})
        await assert_status(socket, second.id)
        await assert_pong(socket)

        response = await async_client.patch(f"/api/v1/groups/{group_id}", headers=admin, json={"permissions": []})
        assert response.status_code == 200
        closed = await socket.receive()
        assert closed["type"] == "websocket.close" and closed["code"] == 4401

    async with open_socket(token) as socket:
        assert (await socket.receive())["type"] == "websocket.close"


async def test_api_key_printer_scope_and_status_permission_track_committed_key_edits(
    async_client, printer_factory, live_events, dashboard_key
):
    await printer_factory()
    await printer_factory()
    admin = {"Authorization": f"Bearer {await _setup_admin(async_client)}"}
    key, secret = dashboard_key
    token = await token_for(async_client, {"X-API-Key": secret})
    async with open_socket(token) as socket:
        assert (await socket.receive())["type"] == "websocket.accept"
        await assert_status(socket, 1)
        await assert_pong(socket)
        response = await async_client.patch(f"/api/v1/api-keys/{key.id}", headers=admin, json={"printer_ids": [2]})
        assert response.status_code == 200
        await socket.send({"type": "get_status", "printer_id": 1})
        await socket.send({"type": "get_status", "printer_id": 2})
        await assert_status(socket, 2)
        response = await async_client.patch(
            f"/api/v1/api-keys/{key.id}", headers=admin, json={"can_read_status": False}
        )
        assert response.status_code == 200
        closed = await socket.receive()
        assert closed["type"] == "websocket.close" and closed["code"] == 4401


async def test_periodic_access_check_closes_idle_socket_without_a_write_route(
    async_client, db_session, live_events, dashboard_key, monkeypatch
):
    monkeypatch.setattr(websocket, "_ACCESS_RECHECK_SECONDS", 0.05)
    await _setup_admin(async_client)
    key, secret = dashboard_key
    token = await token_for(async_client, {"X-API-Key": secret})
    async with open_socket(token) as socket:
        assert (await socket.receive())["type"] == "websocket.accept"
        await assert_status(socket, 1)
        key.enabled = False
        await db_session.commit()
        closed = await socket.receive()
        assert closed["type"] == "websocket.close" and closed["code"] == 4401


async def test_logout_immediately_closes_only_that_sessions_socket(async_client, live_events):
    first = {"Authorization": f"Bearer {await _setup_admin(async_client)}"}
    login = await async_client.post("/api/v1/auth/login", json={"username": "tokenadmin", "password": "AdminPass1!"})
    assert login.status_code == 200
    second = {"Authorization": f"Bearer {login.json()['access_token']}"}
    first_token = await token_for(async_client, first)
    second_token = await token_for(async_client, second)
    async with open_socket(first_token) as first_socket, open_socket(second_token) as second_socket:
        for socket in (first_socket, second_socket):
            assert (await socket.receive())["type"] == "websocket.accept"
            await assert_status(socket, 1)
            await assert_status(socket, 2)
        assert (await async_client.post("/api/v1/auth/logout", headers=first)).status_code == 200
        closed = await first_socket.receive()
        assert closed["type"] == "websocket.close" and closed["code"] == 4401
        await assert_pong(second_socket)


@pytest.mark.parametrize("change", ["password", "rename", "deactivate", "two-factor"])
async def test_admin_session_changes_close_open_dashboards(async_client, live_events, change):
    admin_token = await _setup_admin(async_client)
    admin = {"Authorization": f"Bearer {admin_token}"}
    user_id = await _create_user(async_client, admin_token, "sessionviewer")
    viewer = {"Authorization": f"Bearer {await _login(async_client, 'sessionviewer')}"}
    token = await token_for(async_client, viewer)
    async with open_socket(token) as socket:
        assert (await socket.receive())["type"] == "websocket.accept"
        await assert_status(socket, 1)
        await assert_status(socket, 2)
        if change == "two-factor":
            response = await async_client.request(
                "DELETE", f"/api/v1/auth/2fa/admin/{user_id}", headers=admin, json={"admin_password": "AdminPass1!"}
            )
        else:
            payload = {
                "password": {"password": "ChangedPass1!"},
                "rename": {"username": "renamedviewer"},
                "deactivate": {"is_active": False},
            }[change]
            response = await async_client.patch(f"/api/v1/users/{user_id}", headers=admin, json=payload)
        assert response.status_code == 200
        closed = await socket.receive()
        assert closed["type"] == "websocket.close" and closed["code"] == 4401
    assert (await async_client.get("/api/v1/auth/me", headers=viewer)).status_code == 401
    async with open_socket(token) as socket:
        assert (await socket.receive())["type"] == "websocket.close"


async def test_enabling_auth_closes_anonymous_live_socket(async_client, live_events):
    async with open_socket("unused-before-auth") as socket:
        assert (await socket.receive())["type"] == "websocket.accept"
        await assert_status(socket, 1)
        await assert_status(socket, 2)
        await _setup_admin(async_client)
        closed = await socket.receive()
        assert closed["type"] == "websocket.close" and closed["code"] == 4401


async def test_restore_ends_user_sessions_and_rechecks_api_key_identity(
    async_client, db_session, test_engine, live_events, dashboard_key, monkeypatch
):
    from sqlalchemy import delete

    from backend.app.core import database
    from backend.app.core.auth_sessions import handle_restored_sessions
    from backend.app.models.auth_ephemeral import AuthEphemeralToken

    monkeypatch.setattr(database, "engine", test_engine)
    admin = {"Authorization": f"Bearer {await _setup_admin(async_client)}"}
    key, secret = dashboard_key
    user_token = await token_for(async_client, admin)
    key_token = await token_for(async_client, {"X-API-Key": secret})
    async with open_socket(user_token) as user_socket, open_socket(key_token) as key_socket:
        assert (await user_socket.receive())["type"] == "websocket.accept"
        await assert_status(user_socket, 1)
        await assert_status(user_socket, 2)
        assert (await key_socket.receive())["type"] == "websocket.accept"
        await assert_status(key_socket, 1)
        # The restored backup predates this socket's derived key token.
        await db_session.execute(delete(AuthEphemeralToken).where(AuthEphemeralToken.token == key_token))
        await db_session.commit()
        await handle_restored_sessions()
        closed = await user_socket.receive()
        assert closed["type"] == "websocket.close" and closed["code"] == 4401
        await assert_pong(key_socket)
        assert (await async_client.get("/api/v1/auth/me", headers=admin)).status_code == 401

        _, key.key_hash, key.key_prefix = generate_api_key()
        await db_session.commit()
        await handle_restored_sessions()
        closed = await key_socket.receive()
        assert closed["type"] == "websocket.close" and closed["code"] == 4401


async def test_auth_disabled_restore_keeps_open_dashboard_without_its_old_identity(
    async_client, db_session, test_engine, live_events, monkeypatch
):
    from sqlalchemy import select

    from backend.app.core import database
    from backend.app.core.auth_sessions import handle_restored_sessions
    from backend.app.models.settings import Settings

    monkeypatch.setattr(database, "engine", test_engine)
    admin = {"Authorization": f"Bearer {await _setup_admin(async_client)}"}
    token = await token_for(async_client, admin)
    async with open_socket(token) as socket:
        assert (await socket.receive())["type"] == "websocket.accept"
        await assert_status(socket, 1)
        await assert_status(socket, 2)

        setting = await db_session.scalar(select(Settings).where(Settings.key == "auth_enabled"))
        setting.value = "false"
        await db_session.commit()
        await handle_restored_sessions()
        await assert_pong(socket)
        access = ws_manager.active_connections[0].state.printops_live_access
        assert not access.authenticated and access.user_id is None


async def test_delete_key_closes_socket_and_old_tokens_cannot_follow_a_reused_id(
    async_client, db_session, live_events, dashboard_key
):
    from sqlalchemy import select

    from backend.app.core.auth_camera import camera_request_access
    from backend.app.models.auth_ephemeral import AuthEphemeralToken, TokenType

    admin = {"Authorization": f"Bearer {await _setup_admin(async_client)}"}
    key, secret = dashboard_key
    headers = {"X-API-Key": secret}
    ws_token = await token_for(async_client, headers)
    response = await async_client.post("/api/v1/printers/camera/stream-token", headers=headers)
    assert response.status_code == 200
    camera_token = response.json()["token"]
    assert (await camera_request_access(camera_token, 1))[0] == 200

    rows = (
        await db_session.scalars(
            select(AuthEphemeralToken).where(AuthEphemeralToken.token.in_([ws_token, camera_token]))
        )
    ).all()
    stale = [
        {
            "token": row.token,
            "token_type": row.token_type,
            "provider_id": row.provider_id,
            "nonce": row.nonce,
            "expires_at": row.expires_at,
        }
        for row in rows
    ]
    assert len(stale) == 2
    db_session.add(
        AuthEphemeralToken(
            token="unrelated-oidc-state",
            token_type=TokenType.OIDC_STATE,
            provider_id=key.id,
            expires_at=rows[0].expires_at,
        )
    )
    await db_session.commit()

    key_id = key.id
    async with open_socket(ws_token) as socket:
        assert (await socket.receive())["type"] == "websocket.accept"
        await assert_status(socket, 1)
        response = await async_client.delete(f"/api/v1/api-keys/{key_id}", headers=admin)
        assert response.status_code == 200
        closed = await socket.receive()
        assert closed["type"] == "websocket.close" and closed["code"] == 4401
    assert await db_session.scalar(select(APIKey.id).where(APIKey.id == key_id)) is None
    remaining = (await db_session.scalars(select(AuthEphemeralToken.token))).all()
    assert ws_token not in remaining and camera_token not in remaining
    assert "unrelated-oidc-state" in remaining

    db_session.expunge_all()
    replacement, key_hash, prefix = generate_api_key()
    db_session.add(
        APIKey(
            id=key_id, name="Restored key", key_hash=key_hash, key_prefix=prefix, can_read_status=True, printer_ids=[2]
        )
    )
    # Simulate a stale row that survived deletion or came from an old backup.
    db_session.add_all(AuthEphemeralToken(**fields) for fields in stale)
    await db_session.commit()
    assert (await camera_request_access(camera_token, 2))[0] == 401
    async with open_socket(ws_token) as socket:
        assert (await socket.receive())["type"] == "websocket.close"
    replacement_token = await token_for(async_client, {"X-API-Key": replacement})
    async with open_socket(replacement_token) as socket:
        assert (await socket.receive())["type"] == "websocket.accept"
        await assert_status(socket, 2)
        await assert_pong(socket)


async def test_startup_prunes_missing_credential_owners_without_deleting_oidc_or_revocations(
    async_client, db_session, test_engine, dashboard_key
):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from backend.app.core.auth_sessions import cleanup_orphan_ephemeral_tokens
    from backend.app.models.auth_ephemeral import AuthEphemeralToken, TokenType

    await _setup_admin(async_client)
    key, _ = dashboard_key
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=2)
    db_session.add_all(
        [
            AuthEphemeralToken(
                token="missing-key", token_type=TokenType.WEBSOCKET, provider_id=999, expires_at=expires_at
            ),
            AuthEphemeralToken(
                token="active-key", token_type=TokenType.CAMERA_STREAM, provider_id=key.id, expires_at=expires_at
            ),
            AuthEphemeralToken(
                token="missing-user", token_type=TokenType.MEDIA, username="missing", expires_at=expires_at
            ),
            AuthEphemeralToken(
                token="oidc-state", token_type=TokenType.OIDC_STATE, provider_id=999, expires_at=expires_at
            ),
            AuthEphemeralToken(
                token="revoked", token_type=TokenType.REVOKED_JTI, username="missing", expires_at=expires_at
            ),
        ]
    )
    await db_session.commit()
    async with test_engine.begin() as conn:
        await cleanup_orphan_ephemeral_tokens(conn)
    assert set(await db_session.scalars(select(AuthEphemeralToken.token))) == {"active-key", "oidc-state", "revoked"}


async def test_deleting_key_owner_closes_the_keys_socket_and_removes_its_token(
    async_client, db_session, live_events, dashboard_key
):
    from sqlalchemy import select

    from backend.app.models.auth_ephemeral import AuthEphemeralToken

    jwt = await _setup_admin(async_client)
    owner_id = await _create_user(async_client, jwt, "keyowner")
    key, secret = dashboard_key
    key.user_id = owner_id
    await db_session.commit()
    key_id = key.id
    token = await token_for(async_client, {"X-API-Key": secret})
    async with open_socket(token) as socket:
        assert (await socket.receive())["type"] == "websocket.accept"
        await assert_status(socket, 1)
        response = await async_client.delete(f"/api/v1/users/{owner_id}", headers={"Authorization": f"Bearer {jwt}"})
        assert response.status_code == 204
        closed = await socket.receive()
        assert closed["type"] == "websocket.close" and closed["code"] == 4401
    assert await db_session.scalar(select(AuthEphemeralToken.id).where(AuthEphemeralToken.token == token)) is None
    assert await db_session.scalar(select(APIKey.id).where(APIKey.id == key_id)) is None


async def test_recreated_username_never_accepts_the_previous_accounts_jwt(async_client):
    jwt = await _setup_admin(async_client)
    admin = {"Authorization": f"Bearer {jwt}"}
    old_id = await _create_user(async_client, jwt, "recreated")
    old_headers = {"Authorization": f"Bearer {await _login(async_client, 'recreated')}"}
    assert (await async_client.get("/api/v1/auth/me", headers=old_headers)).status_code == 200
    assert (await async_client.delete(f"/api/v1/users/{old_id}", headers=admin)).status_code == 204
    new_id = await _create_user(async_client, jwt, "Recreated")
    assert new_id > old_id
    assert (await async_client.get("/api/v1/auth/me", headers=old_headers)).status_code == 401
    new_headers = {"Authorization": f"Bearer {await _login(async_client, 'recreated')}"}
    assert (await async_client.get("/api/v1/auth/me", headers=new_headers)).json()["id"] == new_id


async def test_joining_socket_rejects_a_username_reassigned_during_handshake(
    async_client, db_session, live_events, monkeypatch
):
    from backend.app.core import websocket as manager
    from backend.app.models.user import User

    jwt = await _setup_admin(async_client)
    old_id = await _create_user(async_client, jwt, "original-viewer")
    old_headers = {"Authorization": f"Bearer {await _login(async_client, 'original-viewer')}"}
    token = await token_for(async_client, old_headers)
    stopped, resume = asyncio.Event(), asyncio.Event()
    validate = manager.read_websocket_access

    async def delayed_validation(token, previous=None):
        stopped.set()
        await resume.wait()
        return await validate(token, previous)

    monkeypatch.setattr(manager, "read_websocket_access", delayed_validation)
    async with open_socket(token) as socket:
        assert (await socket.receive())["type"] == "websocket.accept"
        await asyncio.wait_for(stopped.wait(), timeout=4)
        try:
            original = await db_session.get(User, old_id)
            original.username = "renamed-viewer"
            await db_session.flush()
            db_session.add(User(username="original-viewer", role="admin"))
            await db_session.commit()
        finally:
            resume.set()
        closed = await socket.receive()
        assert closed["type"] == "websocket.close" and closed["code"] == 4401
        assert not ws_manager.active_connections
