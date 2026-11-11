"""Bind derived credentials to the user session or API key that issued them."""

from datetime import datetime, timezone
from hashlib import sha256

import jwt
from fastapi import HTTPException, Request
from fastapi.security.utils import get_authorization_scheme_param
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.api_key import APIKey
from backend.app.models.auth_ephemeral import AuthEphemeralToken
from backend.app.models.user import User


def bind_user_issuer(row: AuthEphemeralToken, request: Request, user: User) -> None:
    from backend.app.core import auth

    scheme, token = get_authorization_scheme_param(request.headers.get("Authorization"))
    if scheme.lower() != "bearer" or not user.connected_identity:
        raise HTTPException(401, "Valid issuing session required")
    try:
        claims = jwt.decode(
            token,
            auth.SECRET_KEY,
            algorithms=[auth.ALGORITHM],
            options={"require": ["sub", "iat", "exp", "jti"]},
        )
        if (
            claims["sub"].casefold() != user.username.casefold()
            or not claims["jti"]
            or not auth._is_token_fresh(claims["iat"], user)
        ):
            raise ValueError("Issuing session does not match the current account")
        expires_at = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    except (jwt.PyJWTError, ValueError, TypeError, AttributeError, OverflowError, OSError):
        raise HTTPException(401, "Valid issuing session required") from None

    row.username = user.username
    row.issuer_identity = user.connected_identity
    row.issuer_jti = claims["jti"]
    row.issuer_epoch = _login_epoch(user).isoformat()
    row.expires_at = min(row.expires_at, expires_at)


async def user_issuer_valid(db: AsyncSession, row: AuthEphemeralToken, user: User) -> bool:
    from backend.app.core import auth

    return (
        user.is_active
        and bool(row.issuer_jti)
        and bool(row.issuer_identity)
        and row.issuer_identity == user.connected_identity
        and row.issuer_epoch == _login_epoch(user).isoformat()
        and not await auth.is_jti_revoked(row.issuer_jti, db)
    )


async def load_user_issuer(db: AsyncSession, row: AuthEphemeralToken) -> User | None:
    from backend.app.core import auth

    if not row.username:
        return None
    user = await auth.get_user_by_username(db, row.username)
    return user if user is not None and await user_issuer_valid(db, row, user) else None


def bind_api_key_issuer(row: AuthEphemeralToken, key: APIKey) -> None:
    row.provider_id = key.id
    row.nonce = sha256(key.key_hash.encode()).hexdigest()


async def load_api_key_issuer(
    db: AsyncSession, api_key_id: int | None, fingerprint: str | None
) -> tuple[APIKey, User | None] | None:
    from backend.app.core import auth

    if api_key_id is None:
        return None
    key = await db.get(APIKey, api_key_id)
    if (
        key is None
        or not key.enabled
        or fingerprint != sha256(key.key_hash.encode()).hexdigest()
        or auth._api_key_expired(key, datetime.now(timezone.utc))
    ):
        return None
    owner = await db.get(User, key.user_id) if key.user_id is not None else None
    if key.user_id is not None and (owner is None or not owner.is_active):
        return None
    return key, owner


def _utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _login_epoch(user: User) -> datetime:
    created_at = _utc(user.created_at)
    return max(created_at, _utc(user.password_changed_at)) if user.password_changed_at is not None else created_at


def bind_login_step(row: AuthEphemeralToken, user: User) -> None:
    """Preserve the account and security state that authorized this login step."""
    row.username = user.username
    row.issuer_identity = user.connected_identity
    row.nonce = _login_epoch(user).isoformat()


async def load_login_step_user(db: AsyncSession, row: AuthEphemeralToken, *, for_update: bool = False) -> User | None:
    from backend.app.core import auth

    if not row.username:
        return None
    user = await auth.get_user_by_username(db, row.username, for_update=for_update)
    if user is None or not user.is_active:
        return None
    epoch = _login_epoch(user)
    if row.issuer_identity is None:
        # Short-lived login steps issued before this migration still carry an
        # issuance time. Once they expire, all new steps also bind the identity.
        return user if _utc(row.created_at) >= epoch else None
    if row.issuer_identity != user.connected_identity or row.nonce != epoch.isoformat():
        return None
    return user
