"""Issue and validate the browser credential for the dashboard WebSocket."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

from fastapi import HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth_issuers import bind_api_key_issuer, bind_user_issuer, load_api_key_issuer, load_user_issuer
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.auth_ephemeral import AuthEphemeralToken, TokenType
from backend.app.models.user import User

WEBSOCKET_TOKEN_EXPIRE_MINUTES = 60
WS_CLOSE_UNAUTHORIZED = 4401
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebSocketAccess:
    authenticated: bool
    printer_ids: frozenset[int] | None = None
    username: str | None = None
    user_id: int | None = None
    api_key_id: int | None = None
    api_key_fingerprint: str | None = field(default=None, repr=False)
    api_key_token_expires_at: datetime | None = None
    issuer_jti: str | None = field(default=None, repr=False)

    def allows_printer(self, printer_id: int | None) -> bool:
        return printer_id is None or self.printer_ids is None or printer_id in self.printer_ids


async def create_websocket_token(request: Request, user: User | None, api_key: APIKey | None) -> str:
    from backend.app.core import auth

    now = datetime.now(timezone.utc)
    token = token_urlsafe(24)
    row = AuthEphemeralToken(
        token=token, token_type=TokenType.WEBSOCKET, expires_at=now + timedelta(minutes=WEBSOCKET_TOKEN_EXPIRE_MINUTES)
    )
    async with auth.async_session() as db:
        if user is not None:
            bind_user_issuer(row, request, user)
        elif api_key is not None:
            bind_api_key_issuer(row, api_key)
        elif await auth.is_auth_enabled(db):
            raise HTTPException(401, "Valid issuing session required")
        await db.execute(
            delete(AuthEphemeralToken).where(
                AuthEphemeralToken.token_type == TokenType.WEBSOCKET, AuthEphemeralToken.expires_at <= now
            )
        )
        db.add(row)
        await db.commit()
    return token


async def _key_access(
    db: AsyncSession, key_id: int, fingerprint: str | None, expires_at: datetime | None
) -> WebSocketAccess | None:
    if expires_at is None:
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        return None
    issuer = await load_api_key_issuer(db, key_id, fingerprint)
    if issuer is None:
        return None
    key, owner = issuer
    if not key.can_read_status:
        return None
    cloud_owner = owner if key.can_access_cloud else None
    return WebSocketAccess(
        authenticated=True,
        printer_ids=None if key.printer_ids is None else frozenset(key.printer_ids),
        username=cloud_owner.username if cloud_owner is not None else None,
        user_id=cloud_owner.id if cloud_owner is not None else None,
        api_key_id=key.id,
        api_key_fingerprint=fingerprint,
        api_key_token_expires_at=expires_at,
    )


async def _token_access(db: AsyncSession, token: str) -> WebSocketAccess | None:
    from backend.app.core import auth

    row = await db.scalar(
        select(AuthEphemeralToken).where(
            AuthEphemeralToken.token == token,
            AuthEphemeralToken.token_type == TokenType.WEBSOCKET,
            AuthEphemeralToken.expires_at > datetime.now(timezone.utc),
        )
    )
    if row is None:
        return None
    if row.provider_id is not None:
        return await _key_access(db, row.provider_id, row.nonce, row.expires_at)
    if row.username:
        user = await load_user_issuer(db, row)
        if user is None or not user.has_permission(Permission.WEBSOCKET_CONNECT.value):
            return None
        allowed = auth.allowed_printer_ids_for_user(user)
        return WebSocketAccess(
            authenticated=True,
            printer_ids=None if allowed is None else frozenset(allowed),
            username=user.username,
            user_id=user.id,
            issuer_jti=row.issuer_jti,
        )
    return None if await auth.is_auth_enabled(db) else WebSocketAccess(authenticated=False)


async def read_websocket_access(token: str | None, previous: WebSocketAccess | None = None) -> WebSocketAccess | None:
    """Resolve current rights, refusing access if the auth state cannot be read."""
    from backend.app.core import auth

    try:
        async with asyncio.timeout(5), auth.async_session() as db:
            if not await auth.is_auth_enabled(db):
                return WebSocketAccess(authenticated=False)
            if previous is not None and previous.api_key_id is not None:
                # An accepted key connection can survive a restore that predates
                # its child token. Its original key fingerprint and expiry still apply.
                return await _key_access(
                    db, previous.api_key_id, previous.api_key_fingerprint, previous.api_key_token_expires_at
                )
            return await _token_access(db, token) if token else None
    except (SQLAlchemyError, TimeoutError, OSError, ValueError, TypeError) as error:
        logger.warning("WebSocket authorization unavailable: %s", type(error).__name__)
        return None


async def verify_websocket_token(token: str) -> str | None:
    """Return the username for owner-targeted events, or an empty key principal."""
    from backend.app.core import auth

    async with auth.async_session() as db:
        access = await _token_access(db, token)
        return None if access is None else access.username or ""
