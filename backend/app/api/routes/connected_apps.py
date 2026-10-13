"""PrintOps identity consent and S256 code exchange; no API access token is issued."""

import base64
import functools
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import get_current_user, get_password_hash, is_auth_enabled, security, verify_password
from backend.app.core.database import get_db
from backend.app.models.auth_ephemeral import AuthEphemeralToken, AuthRateLimitEvent, EventType, TokenType
from backend.app.models.connected_app import ConnectedApp, ConnectedAppGrant
from backend.app.models.user import User
from backend.app.schemas.connected_app import (
    ConnectAuthorizeInfo,
    ConnectAuthorizeRequest,
    ConnectAuthorizeResponse,
    ConnectedAppCreate,
    ConnectedAppResponse,
    ConnectedAppSecretResponse,
    ConnectedAppUpdate,
    ConnectedUser,
    ConnectTokenRequest,
    ConnectTokenResponse,
)
from backend.app.services.connected_apps import configuration_digest, digest, invalidate_codes, new_credentials

router = APIRouter(prefix="/connect", tags=["connected-apps"])


async def require_signed_in_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    if not await is_auth_enabled(db):
        raise HTTPException(409, "auth_disabled")
    return await get_current_user(credentials)


async def require_manager(user: User = Depends(require_signed_in_user)) -> User:
    if not user.has_permission("settings:update"):
        raise HTTPException(403, "Missing required permissions: settings:update")
    return user


async def app_by_id(db: AsyncSession, app_id: int) -> ConnectedApp:
    # Serialize lifecycle mutations and issuance on both SQLite and PostgreSQL.
    result = await db.execute(
        update(ConnectedApp).where(ConnectedApp.id == app_id).values(id=ConnectedApp.id).returning(ConnectedApp)
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(404, "Connected app not found")
    return app


def with_secret(app: ConnectedApp, secret: str) -> ConnectedAppSecretResponse:
    return ConnectedAppSecretResponse(**ConnectedAppResponse.model_validate(app).model_dump(), client_secret=secret)


@router.get("/apps", response_model=list[ConnectedAppResponse])
async def list_apps(db: AsyncSession = Depends(get_db), _: User = Depends(require_manager)):
    return (await db.execute(select(ConnectedApp).order_by(ConnectedApp.created_at.desc()))).scalars().all()


@router.post("/apps", response_model=ConnectedAppSecretResponse)
async def create_app(
    data: ConnectedAppCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_manager),
):
    client_id, secret = new_credentials()
    app = ConnectedApp(
        name=data.name,
        redirect_uri=data.redirect_uri,
        client_id=client_id,
        client_secret_hash=get_password_hash(secret),
        created_by_id=user.id,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    response.headers["Cache-Control"] = "no-store"
    return with_secret(app, secret)


@router.patch("/apps/{app_id}", response_model=ConnectedAppResponse)
async def update_app(
    app_id: int, data: ConnectedAppUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(require_manager)
):
    app = await app_by_id(db, app_id)
    if data.redirect_uri is not None and data.redirect_uri != app.redirect_uri:
        await invalidate_codes(db, app.id)
        await db.execute(delete(ConnectedAppGrant).where(ConnectedAppGrant.app_id == app.id))
    if data.enabled is False:
        await invalidate_codes(db, app.id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(app, field, value)
    await db.commit()
    await db.refresh(app)
    return app


@router.post("/apps/{app_id}/rotate-secret", response_model=ConnectedAppSecretResponse)
async def rotate_secret(
    app_id: int, response: Response, db: AsyncSession = Depends(get_db), _: User = Depends(require_manager)
):
    app = await app_by_id(db, app_id)
    _, secret = new_credentials()
    app.client_secret_hash = get_password_hash(secret)
    await invalidate_codes(db, app.id)
    await db.commit()
    await db.refresh(app)
    response.headers["Cache-Control"] = "no-store"
    return with_secret(app, secret)


@router.delete("/apps/{app_id}")
async def delete_app(app_id: int, db: AsyncSession = Depends(get_db), _: User = Depends(require_manager)):
    app = await app_by_id(db, app_id)
    await invalidate_codes(db, app.id)
    await db.execute(delete(ConnectedAppGrant).where(ConnectedAppGrant.app_id == app.id))
    await db.delete(app)
    await db.commit()
    return {"message": "Connected app deleted"}


async def app_for_authorize(db: AsyncSession, client_id: str, redirect_uri: str, *, lock: bool = False):
    statement = (
        update(ConnectedApp).values(id=ConnectedApp.id).returning(ConnectedApp) if lock else select(ConnectedApp)
    ).where(ConnectedApp.client_id == client_id)
    app = (await db.execute(statement)).scalar_one_or_none()
    if app is None or not app.enabled or app.redirect_uri != redirect_uri:
        raise HTTPException(400, "Unknown app, app disabled, or callback URL does not match its registration")
    return app


@router.get("/authorize/info", response_model=ConnectAuthorizeInfo)
async def authorize_info(
    response: Response,
    client_id: str = Query(..., max_length=64),
    redirect_uri: str = Query(..., max_length=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_signed_in_user),
):
    app = await app_for_authorize(db, client_id, redirect_uri)
    grant = (
        await db.execute(
            select(ConnectedAppGrant.id).where(ConnectedAppGrant.app_id == app.id, ConnectedAppGrant.user_id == user.id)
        )
    ).scalar_one_or_none()
    response.headers["Cache-Control"] = "no-store"
    return ConnectAuthorizeInfo(
        app_name=app.name, username=user.username, redirect_uri=app.redirect_uri, already_granted=grant is not None
    )


@router.post("/authorize", response_model=ConnectAuthorizeResponse)
async def authorize(
    data: ConnectAuthorizeRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_signed_in_user),
):
    app = await app_for_authorize(db, data.client_id, data.redirect_uri, lock=True)
    # Recheck the immutable identity after acquiring the app write lock.
    live = (
        await db.execute(
            select(User).where(User.id == user.id, User.connected_identity == user.connected_identity).with_for_update()
        )
    ).scalar_one_or_none()
    if live is None or not live.is_active or not live.connected_identity:
        raise HTTPException(403, "User account is disabled")
    now = datetime.now(timezone.utc)
    await db.execute(
        delete(AuthEphemeralToken).where(
            AuthEphemeralToken.token_type == TokenType.CONNECT_CODE, AuthEphemeralToken.expires_at <= now
        )
    )
    granted = (
        await db.execute(
            select(ConnectedAppGrant.id).where(ConnectedAppGrant.app_id == app.id, ConnectedAppGrant.user_id == live.id)
        )
    ).scalar_one_or_none()
    if granted is None:
        db.add(ConnectedAppGrant(app_id=app.id, user_id=live.id))
    code = secrets.token_urlsafe(32)
    db.add(
        AuthEphemeralToken.new_connect_code(
            code_hash=digest(code),
            username=live.username,
            user_id=live.id,
            identity_nonce=live.connected_identity,
            app_id=app.id,
            code_challenge=data.code_challenge,
            configuration_digest=configuration_digest(app),
            expires_at=now + timedelta(seconds=60),
        )
    )
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    return ConnectAuthorizeResponse(code=code, redirect_uri=app.redirect_uri)


@functools.cache
def dummy_hash() -> str:
    return get_password_hash(secrets.token_urlsafe(32))


@router.post("/token", response_model=ConnectTokenResponse)
async def exchange_code(
    request: Request, response: Response, data: ConnectTokenRequest, db: AsyncSession = Depends(get_db)
):
    from backend.app.api.routes.auth import _get_client_ip
    from backend.app.api.routes.mfa import check_rate_limit

    client_ip = _get_client_ip(request)
    for key, event in ((data.client_id, EventType.CONNECT_TOKEN_CLIENT), (client_ip, EventType.CONNECT_TOKEN_IP)):
        await check_rate_limit(db, key, event_type=event, max_attempts=20)
    if not await is_auth_enabled(db):
        raise HTTPException(400, {"error": "auth_disabled"})

    async def fail(status: int, error: str):
        db.add_all(
            [
                AuthRateLimitEvent(username=data.client_id.lower(), event_type=EventType.CONNECT_TOKEN_CLIENT),
                AuthRateLimitEvent(username=client_ip.lower(), event_type=EventType.CONNECT_TOKEN_IP),
            ]
        )
        # Commit spent codes and both failure buckets together before raising.
        await db.commit()
        return HTTPException(status, {"error": error})

    app = (
        await db.execute(
            update(ConnectedApp)
            .where(ConnectedApp.client_id == data.client_id)
            .values(id=ConnectedApp.id)
            .returning(ConnectedApp)
        )
    ).scalar_one_or_none()
    secret_ok = verify_password(data.client_secret, app.client_secret_hash if app else dummy_hash())
    if app is None or not secret_ok or not app.enabled:
        raise await fail(401, "invalid_client")
    now = datetime.now(timezone.utc)
    consumed = await db.execute(
        delete(AuthEphemeralToken)
        .where(
            AuthEphemeralToken.token == digest(data.code),
            AuthEphemeralToken.token_type == TokenType.CONNECT_CODE,
            AuthEphemeralToken.provider_id == app.id,
        )
        .returning(AuthEphemeralToken)
    )
    token = consumed.scalar_one_or_none()
    if token is None or token.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise await fail(400, "invalid_grant")
    challenge = base64.urlsafe_b64encode(bytes.fromhex(digest(data.code_verifier))).rstrip(b"=").decode()
    if (
        data.redirect_uri != app.redirect_uri
        or not hmac.compare_digest(token.code_verifier or "", configuration_digest(app))
        or not hmac.compare_digest(token.nonce or "", challenge)
    ):
        raise await fail(400, "invalid_grant")
    user_id, separator, identity_nonce = (token.challenge_id or "").partition(":")
    if not separator or not user_id.isdigit() or not identity_nonce:
        raise await fail(400, "invalid_grant")
    user = (
        await db.execute(
            select(User).where(User.id == int(user_id), User.connected_identity == identity_nonce).with_for_update()
        )
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise await fail(400, "invalid_grant")
    identity = ConnectedUser(
        sub=user.connected_identity,
        id=user.id,
        username=user.username,
        email=user.email,
        is_admin=user.is_admin,
        groups=sorted(g.name for g in user.groups),
        permissions=sorted(user.get_permissions()),
    )
    app.last_used_at = now.replace(tzinfo=None)
    await db.execute(
        delete(AuthRateLimitEvent).where(
            AuthRateLimitEvent.username == data.client_id.lower(),
            AuthRateLimitEvent.event_type == EventType.CONNECT_TOKEN_CLIENT,
        )
    )
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    return ConnectTokenResponse(user=identity, issued_at=now)
