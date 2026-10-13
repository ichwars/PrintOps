"""Connected application boundary tests: real ASGI auth and committed SQLite transactions."""

import asyncio
import base64
import hashlib
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, event, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.sql.dml import Update

from backend.app.core import auth
from backend.app.core.database import Base, get_db
from backend.app.models.auth_ephemeral import AuthEphemeralToken, AuthRateLimitEvent
from backend.app.models.group import Group
from backend.app.models.settings import Settings
from backend.app.models.user import User

CALLBACK = "http://localhost:8123/callback?existing=yes"
VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
PREFIX = "/api/v1/connect"


@pytest.fixture
async def connected(tmp_path, monkeypatch, test_engine, request):
    from backend.app.main import app

    postgres = getattr(request, "param", "sqlite") == "postgres"
    admin_engine = None
    if postgres:
        url = os.environ.get("PRINTOPS_POSTGRES_TEST_URL")
        if not url:
            pytest.skip("live PostgreSQL test URL not configured")
        schema = f"connected_{uuid4().hex}"
        admin_engine = create_async_engine(url)
        async with admin_engine.begin() as conn:
            await conn.execute(text(f"CREATE SCHEMA {schema}"))
        engine = create_async_engine(
            url,
            connect_args={
                "server_settings": {
                    "search_path": schema,
                    "statement_timeout": "8000",
                }
            },
        )
    else:
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/connect.db")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if not postgres:
            assert (await conn.execute(text("PRAGMA foreign_keys"))).scalar() == 0
    async with sessions() as db:
        db.add(Settings(key="auth_enabled", value="true"))
        db.add_all([User(id=101, username="admin", role="admin"), User(id=102, username="person", role="user")])
        await db.commit()

    async def get_test_db():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = get_test_db
    monkeypatch.setattr(auth, "async_session", sessions)
    monkeypatch.setattr("backend.app.main.async_session", sessions)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, sessions
    app.dependency_overrides.clear()
    await engine.dispose()
    if admin_engine:
        async with admin_engine.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        await admin_engine.dispose()


def headers(username="admin"):
    return {"Authorization": f"Bearer {auth.create_access_token({'sub': username})}"}


async def create(client):
    response = await client.post(
        f"{PREFIX}/apps", headers=headers(), json={"name": "Workshop", "redirect_uri": CALLBACK}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def issue(client, app, **changes):
    data = {
        "client_id": app["client_id"],
        "redirect_uri": CALLBACK,
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
    }
    data.update(changes)
    return await client.post(f"{PREFIX}/authorize", headers=headers("person"), json=data)


async def redeem(client, app, code, **changes):
    data = {
        "grant_type": "authorization_code",
        "client_id": app["client_id"],
        "client_secret": app["client_secret"],
        "code": code,
        "redirect_uri": CALLBACK,
        "code_verifier": VERIFIER,
    }
    data.update(changes)
    return await client.post(f"{PREFIX}/token", json=data)


async def test_identity_only_single_use_and_hashed_credentials(connected):
    client, sessions = connected
    app = await create(client)
    assert app["client_id"].startswith("poa_") and app["client_secret"].startswith("pos_")
    listing = await client.get(f"{PREFIX}/apps", headers=headers())
    assert "client_secret" not in listing.text
    async with sessions() as db:
        row = (await db.execute(text("SELECT client_secret_hash FROM connected_apps"))).scalar_one()
        assert row != app["client_secret"] and auth.verify_password(app["client_secret"], row)
    issued = await issue(client, app)
    assert issued.status_code == 200
    code = issued.json()["code"]
    async with sessions() as db:
        token = (await db.execute(select(AuthEphemeralToken))).scalar_one()
        assert token.token == hashlib.sha256(code.encode()).hexdigest()
        assert 58 <= (token.expires_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds() <= 60
    result = await redeem(client, app, code)
    assert result.status_code == 200, result.text
    assert set(result.json()) == {"user", "issued_at"}
    identity = result.json()["user"]
    assert len(identity.pop("sub")) == 32
    assert identity == {
        "id": 102,
        "username": "person",
        "email": None,
        "is_admin": False,
        "groups": [],
        "permissions": [],
    }
    assert (await redeem(client, app, code)).status_code == 400


@pytest.mark.parametrize(
    "change", [{"redirect_uri": CALLBACK + "/"}, {"code_challenge": "x"}, {"code_challenge_method": "plain"}]
)
async def test_invalid_consent_request_never_issues_code(connected, change):
    client, sessions = connected
    app = await create(client)
    assert (await issue(client, app, **change)).status_code in (400, 422)
    async with sessions() as db:
        assert (await db.execute(select(AuthEphemeralToken))).first() is None


@pytest.mark.parametrize("change", [{"redirect_uri": CALLBACK + "/"}, {"code_verifier": "a" * 43}])
async def test_bad_exchange_consumes_code(connected, change):
    client, _ = connected
    app = await create(client)
    code = (await issue(client, app)).json()["code"]
    assert (await redeem(client, app, code, **change)).status_code == 400
    assert (await redeem(client, app, code)).status_code == 400


async def test_expiry_concurrent_redemption_and_concurrent_consent(connected):
    client, sessions = connected
    app = await create(client)
    issued = await asyncio.gather(issue(client, app), issue(client, app))
    assert [r.status_code for r in issued] == [200, 200]
    results = await asyncio.gather(*(redeem(client, app, issued[0].json()["code"]) for _ in range(2)))
    assert sorted(r.status_code for r in results) == [200, 400]
    async with sessions() as db:
        await db.execute(
            update(AuthEphemeralToken).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        await db.commit()
        assert (await db.execute(text("SELECT count(*) FROM connected_app_grants"))).scalar() == 1
    assert (await redeem(client, app, issued[1].json()["code"])).status_code == 400


@pytest.mark.parametrize("action", ["disable", "callback", "rotate", "delete"])
async def test_app_lifecycle_invalidates_pending_codes(connected, action):
    client, sessions = connected
    app = await create(client)
    code = (await issue(client, app)).json()["code"]
    path = f"{PREFIX}/apps/{app['id']}"
    if action == "rotate":
        rotated = await client.post(path + "/rotate-secret", headers=headers())
        assert rotated.status_code == 200
        app = rotated.json()
    elif action == "delete":
        assert (await client.delete(path, headers=headers())).status_code == 200
        app = await create(client)  # SQLite may reuse the app id.
    else:
        change = {"enabled": False} if action == "disable" else {"redirect_uri": CALLBACK + "&new=1"}
        assert (await client.patch(path, headers=headers(), json=change)).status_code == 200
        assert (
            await client.patch(path, headers=headers(), json={"enabled": True, "redirect_uri": CALLBACK})
        ).status_code == 200
    assert (await redeem(client, app, code)).status_code == 400
    async with sessions() as db:
        assert (
            await db.execute(select(AuthEphemeralToken).where(AuthEphemeralToken.token_type == "connect_code"))
        ).first() is None


async def test_live_identity_uses_id_and_current_permissions(connected):
    client, sessions = connected
    app = await create(client)
    original = (await redeem(client, app, (await issue(client, app)).json()["code"])).json()["user"]
    code = (await issue(client, app)).json()["code"]
    async with sessions() as db:
        person = await db.get(User, 102)
        person.username = "renamed"
        person.email = "new@example.test"
        person.groups.append(Group(name="Operators", permissions=["printers:read"]))
        db.add(User(id=103, username="person", role="admin"))
        await db.commit()
    response = await redeem(client, app, code)
    assert response.status_code == 200
    identity = response.json()["user"]
    assert identity.pop("sub") == original["sub"]
    assert identity == {
        "id": 102,
        "username": "renamed",
        "email": "new@example.test",
        "is_admin": False,
        "groups": ["Operators"],
        "permissions": ["printers:read"],
    }


async def test_user_deletion_cleans_grants_codes_and_app_owner_without_foreign_keys(connected):
    client, sessions = connected
    app = await create(client)
    code = (await issue(client, app)).json()["code"]
    response = await client.delete("/api/v1/users/102", headers=headers())
    assert response.status_code == 204, response.text
    async with sessions() as db:
        assert (await db.execute(text("SELECT count(*) FROM connected_app_grants"))).scalar() == 0
        assert (
            await db.execute(select(AuthEphemeralToken).where(AuthEphemeralToken.token_type == "connect_code"))
        ).first() is None
        db.add(User(id=102, username="person", role="admin"))
        await db.commit()
    assert (await redeem(client, app, code)).status_code == 400


async def test_disabled_auth_and_inactive_user_fail_closed(connected):
    client, sessions = connected
    app = await create(client)
    code = (await issue(client, app)).json()["code"]
    async with sessions() as db:
        await db.execute(update(User).where(User.id == 102).values(is_active=False))
        await db.commit()
    assert (await issue(client, app)).status_code == 401
    assert (await redeem(client, app, code)).status_code == 400
    async with sessions() as db:
        await db.execute(update(Settings).where(Settings.key == "auth_enabled").values(value="false"))
        await db.commit()
    auth.invalidate_auth_enabled_cache()
    assert (await issue(client, app)).status_code == 409
    assert (await redeem(client, app, "code")).json()["detail"]["error"] == "auth_disabled"


async def test_real_auth_permission_and_api_key_gates(connected):
    from backend.app.models.api_key import APIKey

    client, sessions = connected
    app = await create(client)
    key, key_hash, key_prefix = auth.generate_api_key()
    async with sessions() as db:
        db.add(APIKey(name="test", key_hash=key_hash, key_prefix=key_prefix, user_id=101))
        await db.commit()
    params = {"client_id": app["client_id"], "redirect_uri": CALLBACK}
    for key_headers in ({"X-API-Key": key}, {"Authorization": f"Bearer {key}"}):
        assert (await client.get(f"{PREFIX}/authorize/info", params=params, headers=key_headers)).status_code == 401
        assert (await client.get(f"{PREFIX}/apps", headers=key_headers)).status_code in (401, 403)
    assert (await client.get(f"{PREFIX}/apps", headers=headers("person"))).status_code == 403
    assert (await client.get(f"{PREFIX}/authorize/info", params=params)).status_code == 401
    assert (await client.get(f"{PREFIX}/authorize/info", params=params, headers=headers("person"))).status_code == 200
    params["redirect_uri"] += "/"
    assert (await client.get(f"{PREFIX}/authorize/info", params=params, headers=headers("person"))).status_code == 400


@pytest.mark.parametrize("bucket", ["connect_token_client", "connect_token_ip"])
async def test_persistent_failed_exchange_limits(connected, bucket):
    client, sessions = connected
    app = await create(client)
    assert (await redeem(client, app, "wrong", client_secret="wrong")).status_code == 401
    async with sessions() as db:
        events = (await db.execute(select(AuthRateLimitEvent))).scalars().all()
        assert {e.event_type for e in events} == {"connect_token_client", "connect_token_ip"}
        key = app["client_id"] if bucket.endswith("client") else "127.0.0.1"
        db.add_all([AuthRateLimitEvent(username=key, event_type=bucket) for _ in range(19)])
        await db.commit()
    assert (await redeem(client, app, "wrong")).status_code == 429


async def test_consent_frame_headers_only_allow_same_origin(connected):
    client, _ = connected
    consent = await client.get("/connect/authorize")
    ordinary = await client.get("/settings")
    assert "frame-ancestors 'self';" in consent.headers["content-security-policy"]
    assert "frame-ancestors 'none';" in ordinary.headers["content-security-policy"]


async def test_issuance_and_rotation_serialize_real_transactions(connected, monkeypatch):
    from backend.app.api.routes import connected_apps

    client, _ = connected
    app = await create(client)
    acquired = asyncio.Event()
    release = asyncio.Event()
    real_lookup = connected_apps.app_for_authorize

    async def paused_lookup(*args, **kwargs):
        result = await real_lookup(*args, **kwargs)
        if kwargs.get("lock"):
            acquired.set()
            await release.wait()
        return result

    monkeypatch.setattr(connected_apps, "app_for_authorize", paused_lookup)
    issuing = asyncio.create_task(issue(client, app))
    await asyncio.wait_for(acquired.wait(), 5)
    rotating = asyncio.create_task(client.post(f"{PREFIX}/apps/{app['id']}/rotate-secret", headers=headers()))
    try:
        await asyncio.sleep(0.05)
        assert not rotating.done(), "Rotation must wait for the issuing transaction's app lock"
    finally:
        release.set()
    issued, rotated = await asyncio.gather(issuing, rotating)
    assert issued.status_code == rotated.status_code == 200
    assert (await redeem(client, rotated.json(), issued.json()["code"])).status_code == 400


async def test_generation_binding_rejects_stale_snapshot_insert_after_rotation(connected):
    from backend.app.models.connected_app import ConnectedApp
    from backend.app.services.connected_apps import configuration_digest

    client, sessions = connected
    app = await create(client)
    async with sessions() as db:
        stale_digest = configuration_digest(await db.get(ConnectedApp, app["id"]))
        identity_nonce = (await db.get(User, 102)).connected_identity
    rotated = (await client.post(f"{PREFIX}/apps/{app['id']}/rotate-secret", headers=headers())).json()
    async with sessions() as db:
        db.add(
            AuthEphemeralToken.new_connect_code(
                code_hash=hashlib.sha256(b"stale-snapshot").hexdigest(),
                username="person",
                user_id=102,
                app_id=app["id"],
                code_challenge=CHALLENGE,
                configuration_digest=stale_digest,
                identity_nonce=identity_nonce,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
            )
        )
        await db.commit()
    assert (await redeem(client, rotated, "stale-snapshot")).status_code == 400


@pytest.mark.parametrize(
    "uri",
    [
        "https://good.test/cb#fragment",
        "https://user:pass@good.test/cb",
        "//good.test/cb",
        "javascript:alert(1)",
        " https://good.test/cb",
        "https://good.test/\\evil",
    ],
)
async def test_reject_unsafe_registration(connected, uri):
    client, _ = connected
    response = await client.post(f"{PREFIX}/apps", headers=headers(), json={"name": "App", "redirect_uri": uri})
    assert response.status_code == 422


async def test_foreign_client_cannot_consume_code_and_old_secret_fails(connected):
    client, _ = connected
    app = await create(client)
    other = await create(client)
    code = (await issue(client, app)).json()["code"]
    assert (await redeem(client, other, code)).status_code == 400
    assert (await redeem(client, app, code)).status_code == 200
    await client.post(f"{PREFIX}/apps/{app['id']}/rotate-secret", headers=headers())
    assert (await redeem(client, app, "unused")).status_code == 401


def test_additive_schema_and_atomic_sql_compile_for_postgres_and_sqlite():
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateTable

    from backend.app.models.connected_app import ConnectedApp, ConnectedAppGrant

    for dialect in (postgresql.dialect(), sqlite.dialect()):
        for model in (ConnectedApp, ConnectedAppGrant):
            sql = str(CreateTable(model.__table__).compile(dialect=dialect))
            assert "CREATE TABLE" in sql and "FOREIGN KEY" in sql
        consume = delete(AuthEphemeralToken).where(AuthEphemeralToken.token == "digest").returning(AuthEphemeralToken)
        assert "RETURNING" in str(consume.compile(dialect=dialect))
        locking = update(ConnectedApp).values(id=ConnectedApp.id).returning(ConnectedApp)
        assert "RETURNING" in str(locking.compile(dialect=dialect))


async def test_paused_consent_cannot_switch_to_recreated_highest_user_id(connected, monkeypatch):
    from backend.app.api.routes import connected_apps

    client, sessions = connected
    app = await create(client)
    authenticated = asyncio.Event()
    release = asyncio.Event()
    real_get_user = connected_apps.get_current_user

    async def paused_user(credentials):
        user = await real_get_user(credentials)
        if user.id == 102:
            authenticated.set()
            await release.wait()
        return user

    monkeypatch.setattr(connected_apps, "get_current_user", paused_user)
    issuing = asyncio.create_task(issue(client, app))
    await asyncio.wait_for(authenticated.wait(), 5)
    try:
        assert (await client.delete("/api/v1/users/102", headers=headers())).status_code == 204
        async with sessions() as db:
            recreated = User(username="person", role="admin")
            db.add(recreated)
            await db.commit()
            assert recreated.id == 102  # actual SQLite rowid reuse, not a forced identifier
    finally:
        release.set()
    result = await issuing
    assert result.status_code == 403


async def test_legacy_identity_migration_is_additive_and_idempotent(tmp_path):
    from backend.app.core.connected_identity_migration import migrate_connected_identity

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/legacy.db")
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(100))"))
            await conn.execute(text("INSERT INTO users VALUES (1, 'one'), (2, 'two')"))
            await migrate_connected_identity(conn)
            original = (
                await conn.execute(text("SELECT id, username, connected_identity FROM users ORDER BY id"))
            ).all()
            assert original[0][:2] == (1, "one") and original[1][:2] == (2, "two")
            assert len(original[0][2]) == len(original[1][2]) == 32
            assert original[0][2] != original[1][2]
            await migrate_connected_identity(conn)
            assert (
                await conn.execute(text("SELECT id, username, connected_identity FROM users ORDER BY id"))
            ).all() == original
    finally:
        await engine.dispose()


async def test_stale_identity_code_cannot_redeem_as_reused_user_id(connected):
    client, sessions = connected
    app = await create(client)
    code = (await issue(client, app)).json()["code"]
    # Simulate a code surviving cleanup; generation binding must independently fail closed.
    async with sessions() as db:
        await db.execute(delete(User).where(User.id == 102))
        await db.commit()
        replacement = User(username="person", role="admin")
        db.add(replacement)
        await db.commit()
        assert replacement.id == 102
    assert (await redeem(client, app, code)).status_code == 400


async def test_deleting_app_creator_nulls_ownership_without_foreign_keys(connected):
    client, sessions = connected
    async with sessions() as db:
        person = await db.get(User, 102)
        person.groups.append(Group(name="Application managers", permissions=["settings:update"]))
        await db.commit()
    response = await client.post(
        f"{PREFIX}/apps", headers=headers("person"), json={"name": "Delegated", "redirect_uri": CALLBACK}
    )
    assert response.status_code == 200
    assert (await client.delete("/api/v1/users/102", headers=headers())).status_code == 204
    async with sessions() as db:
        assert (await db.execute(text("SELECT created_by_id FROM connected_apps"))).scalar_one() is None


async def test_public_subject_survives_rename_but_not_deleted_id_reuse(connected):
    client, sessions = connected
    app = await create(client)
    first = (await redeem(client, app, (await issue(client, app)).json()["code"])).json()["user"]
    assert "sub" in first, "External accounts need a nonreused subject, not a reusable numeric ID"
    assert len(first["sub"]) == 32
    assert (await client.delete("/api/v1/users/102", headers=headers())).status_code == 204
    async with sessions() as db:
        replacement = User(username="person", role="user")
        db.add(replacement)
        await db.commit()
        assert replacement.id == 102
    second = (await redeem(client, app, (await issue(client, app)).json()["code"])).json()["user"]
    assert first["id"] == second["id"] and first["username"] == second["username"]
    assert first["sub"] != second["sub"]


@pytest.mark.parametrize("verifier", ["short", "", "!" * 43, "é" * 43, "v" * 129])
async def test_malformed_verifier_consumes_code_and_persists_failures(connected, verifier):
    client, sessions = connected
    app = await create(client)
    code = (await issue(client, app)).json()["code"]
    response = await redeem(client, app, code, code_verifier=verifier)
    assert response.status_code == 400, response.text
    assert response.json() == {"detail": {"error": "invalid_grant"}}
    async with sessions() as db:
        assert (await db.execute(select(AuthEphemeralToken))).scalars().all() == []
        events = (await db.execute(select(AuthRateLimitEvent))).scalars().all()
        assert sorted(event.event_type for event in events) == ["connect_token_client", "connect_token_ip"]
    assert (await redeem(client, app, code)).status_code == 400
    async with sessions() as db:
        assert len((await db.execute(select(AuthRateLimitEvent))).scalars().all()) == 4


async def test_malformed_verifier_does_not_consume_foreign_or_unauthenticated_code(connected):
    client, _ = connected
    app = await create(client)
    other = await create(client)
    code = (await issue(client, app)).json()["code"]
    assert (await redeem(client, other, code, code_verifier="short")).status_code == 400
    assert (await redeem(client, app, code, client_secret="incorrect", code_verifier="short")).status_code == 401
    assert (await redeem(client, app, code)).status_code == 200


async def test_verifier_request_input_is_bounded(connected):
    client, _ = connected
    app = await create(client)
    code = (await issue(client, app)).json()["code"]
    assert (await redeem(client, app, code, code_verifier="v" * 1025)).status_code == 422
    assert (await redeem(client, app, code)).status_code == 200


async def test_user_cleanup_locks_apps_before_dependent_rows(connected):
    from backend.app.models.connected_app import ConnectedApp, ConnectedAppGrant
    from backend.app.services.connected_apps import cleanup_user

    client, sessions = connected
    apps = [await create(client), await create(client), await create(client)]
    for app in apps:
        await issue(client, app)
    async with sessions() as db:
        await db.execute(update(ConnectedApp).where(ConnectedApp.id == apps[0]["id"]).values(created_by_id=102))
        # Exercise creator-only, grant-only, and code-only app selection separately.
        await db.execute(delete(ConnectedAppGrant).where(ConnectedAppGrant.app_id.in_([apps[0]["id"], apps[2]["id"]])))
        await db.execute(
            delete(AuthEphemeralToken).where(AuthEphemeralToken.provider_id.in_([apps[0]["id"], apps[1]["id"]]))
        )
        await db.commit()
    dangling = await create(client)
    await issue(client, dangling)
    unrelated = await create(client)
    async with sessions() as db:
        await db.execute(delete(ConnectedApp).where(ConnectedApp.id == dangling["id"]))
        await db.commit()  # Leave orphan grants/codes deliberately (SQLite FK off).
    statements = []

    def record(_conn, _cursor, statement, parameters, _context, _many):
        if statement.startswith(
            ("UPDATE connected_apps", "DELETE FROM connected_app_grants", "DELETE FROM auth_ephemeral_tokens")
        ):
            statements.append((statement, parameters))

    engine = sessions.kw["bind"]
    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        async with sessions() as db:
            await cleanup_user(db, 102)
            await db.commit()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
    first_delete = next(i for i, (sql, _) in enumerate(statements) if sql.startswith("DELETE"))
    assert first_delete > 0, "Cleanup must lock apps before deleting their grants or codes"
    assert all(sql.startswith("UPDATE connected_apps") for sql, _ in statements[:first_delete])
    locked_ids = [args[-1] for sql, args in statements[:first_delete] if "SET id=" in sql]
    assert locked_ids == sorted(app["id"] for app in apps), "Lock every app in deterministic ID order"
    async with sessions() as db:
        assert (await db.execute(select(ConnectedAppGrant))).scalars().all() == []
        assert (await db.execute(select(AuthEphemeralToken))).scalars().all() == []
        owners = {app.id: app.created_by_id for app in (await db.execute(select(ConnectedApp))).scalars()}
        assert owners == {apps[0]["id"]: None, apps[1]["id"]: 101, apps[2]["id"]: 101, unrelated["id"]: 101}


@pytest.mark.parametrize("connected", ["sqlite", "postgres"], indirect=True)
async def test_user_deletion_and_exchange_do_not_deadlock(connected, monkeypatch):
    from backend.app.models.connected_app import ConnectedApp, ConnectedAppGrant
    from backend.app.services.connected_apps import cleanup_user

    client, sessions = connected
    app = await create(client)
    code = (await issue(client, app)).json()["code"]
    async with sessions() as db:
        await db.execute(update(ConnectedApp).where(ConnectedApp.id == app["id"]).values(created_by_id=102))
        await db.commit()
    acquired, release, deletion_waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_execute = AsyncSession.execute
    async with sessions() as deleting_db:

        async def execute(db, statement, *args, **kwargs):
            app_update = isinstance(statement, Update) and statement.table.name == "connected_apps"
            if app_update and db is deleting_db:
                deletion_waiting.set()
            result = await original_execute(db, statement, *args, **kwargs)
            if app_update and db is not deleting_db and not acquired.is_set():
                acquired.set()
                await release.wait()
            return result

        monkeypatch.setattr(AsyncSession, "execute", execute)

        async def remove_user():
            await cleanup_user(deleting_db, 102)
            await deleting_db.delete(await deleting_db.get(User, 102))
            await deleting_db.commit()

        exchanging = asyncio.create_task(redeem(client, app, code))
        await asyncio.wait_for(acquired.wait(), 5)
        deleting = asyncio.create_task(remove_user())
        try:
            # On the broken order PG has already locked the code before it waits
            # for the app; releasing exchange then completes the deadlock cycle.
            await asyncio.wait_for(deletion_waiting.wait(), 5)
        finally:
            release.set()
        results = await asyncio.wait_for(asyncio.gather(exchanging, deleting, return_exceptions=True), 12)
        assert not any(isinstance(result, BaseException) for result in results), repr(results)
        assert results[0].status_code == 200
    assert (await redeem(client, app, code)).status_code == 400
    async with sessions() as db:
        assert await db.get(User, 102) is None
        assert (await db.execute(select(ConnectedAppGrant))).scalars().all() == []
        assert (await db.execute(select(AuthEphemeralToken))).scalars().all() == []
        assert (await db.get(ConnectedApp, app["id"])).created_by_id is None
