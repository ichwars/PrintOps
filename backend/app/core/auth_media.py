"""Media-token lifecycle and scoped media authentication dependencies."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth_camera import StreamOpener, camera_request_access, camera_share_status
from backend.app.core.auth_issuers import bind_user_issuer, load_user_issuer
from backend.app.core.permissions import Permission
from backend.app.models.auth_ephemeral import AuthEphemeralToken, TokenType
from backend.app.models.user import User


async def create_media_token(request: Request, user: User | None) -> str:
    """Issue a reusable media credential bound to the issuing session."""
    from backend.app.core import auth

    now = datetime.now(timezone.utc)
    token = auth.secrets.token_urlsafe(24)
    row = AuthEphemeralToken(
        token=token, token_type=TokenType.MEDIA, expires_at=now + timedelta(minutes=auth.MEDIA_TOKEN_EXPIRE_MINUTES)
    )
    if user is not None:
        bind_user_issuer(row, request, user)
    async with auth.async_session() as db:
        if user is None and await auth.is_auth_enabled(db):
            raise HTTPException(401, "Valid issuing session required")
        await db.execute(
            delete(AuthEphemeralToken).where(
                AuthEphemeralToken.token_type == TokenType.MEDIA, AuthEphemeralToken.expires_at <= now
            )
        )
        db.add(row)
        await db.commit()
    return token


async def _get_media_token(db: AsyncSession, token: str) -> AuthEphemeralToken | None:
    return await db.scalar(
        select(AuthEphemeralToken).where(
            AuthEphemeralToken.token == token,
            AuthEphemeralToken.token_type == TokenType.MEDIA,
            AuthEphemeralToken.expires_at > datetime.now(timezone.utc),
        )
    )


async def verify_media_token(token: str) -> str | None:
    """Verify a media credential and return its current username."""
    from backend.app.core import auth

    async with auth.async_session() as db:
        row = await _get_media_token(db, token)
        if row is None:
            return None
        if not row.username:
            return None if await auth.is_auth_enabled(db) else ""
        user = await load_user_issuer(db, row)
        return user.username if user is not None else None


def require_camera_stream_token_if_auth_enabled():
    """Dependency that validates a camera stream token query param when auth is enabled.

    Used for camera stream/snapshot endpoints that are loaded via <img> tags
    which cannot send Authorization headers. The frontend obtains a token from
    POST /printers/camera/stream-token and appends it as ?token=xxx.
    Camera routes only; resource media uses the identified media token.
    """

    async def checker(printer_id: int, token: str | None = None) -> StreamOpener:
        access_status, opener = await camera_request_access(token, printer_id)
        if access_status == 403:
            raise HTTPException(status_code=403, detail="Printer access denied.")
        if opener is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Valid camera stream token required. Obtain one from POST /api/v1/printers/camera/stream-token",
            )
        return opener

    return checker


def require_camwall_token_if_auth_enabled():
    """Dependency that validates a Cam Wall token query param when auth is enabled."""
    from backend.app.core import auth

    async def checker(token: str | None = None) -> None:
        async with auth.async_session() as db:
            if not await auth.is_auth_enabled(db):
                return
        if not token or not await auth.verify_camwall_token(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Valid Cam Wall token required. Create one under Settings > API Keys with the 'Cam Wall' scope.",
            )

    return checker


def require_overlay_token_if_auth_enabled():
    """Validate the overlay grant and its owner's current printer scope."""
    from backend.app.core import auth

    async def checker(printer_id: int, token: str | None = None) -> None:
        from backend.app.services.long_lived_tokens import verify_token

        async with auth.async_session() as db:
            if not await auth.is_auth_enabled(db):
                return
            record = await verify_token(db, token or "", scope="overlay")
            if record is None:
                raise HTTPException(status_code=401, detail="Valid streaming overlay token required.")
            access = await camera_share_status(db, record, printer_id)
            if access != 200:
                raise HTTPException(status_code=access, detail="Printer access denied.")

    return checker


async def _user_from_media_token(token: str) -> User:
    """Resolve the ``User`` a media token was minted for, or raise 401 (#3025).

    Fail-closed on every miss: an unknown/expired token, an auth-disabled token (empty
    username -- see :func:`create_media_token`), a username no
    longer in the table, and a deactivated account all raise rather than fall
    through to an anonymous read. The 401 detail names the mint endpoint so a
    stale tab knows how to recover, and the frontend's error handler refreshes
    the token on the first failed <img> load.
    """
    from backend.app.core import auth

    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Valid media token required. Obtain one from POST /api/v1/auth/media-token",
    )
    async with auth.async_session() as db:
        row = await _get_media_token(db, token)
        user = await load_user_issuer(db, row) if row is not None else None
        if user is None:
            raise unauthorized
        return user


def require_media_token_permission(*permissions: str | Permission):
    """Media-route dependency for resources with no per-row ownership (#3025).

    Accepts either a ``?token=`` media token (the ``<img>`` case) or the
    ordinary ``Authorization`` / ``X-API-Key`` headers, so a ``fetch()`` or an
    API-keyed integration authenticates here exactly as it does on the
    resource's sibling routes. Requires ALL of ``permissions``, matching
    :func:`require_permission_if_auth_enabled`.

    Returns the resolved ``User``, or ``None`` when auth is disabled or the
    caller is an API key -- the same ``User | None`` contract the header-only
    dependency has, so handlers need no new branch.
    """
    from backend.app.core import auth

    perm_strings = [p.value if isinstance(p, Permission) else p for p in permissions]
    header_checker = auth.require_permission_if_auth_enabled(*permissions)

    async def checker(
        token: str | None = None,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(auth.security)] = None,
        x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> User | None:
        async with auth.async_session() as db:
            if not await auth.is_auth_enabled(db):
                return None  # Auth disabled, allow access
        if token:
            user = await auth._user_from_media_token(token)
            missing = [p for p in perm_strings if not user.has_permission(p)]
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required permissions: {', '.join(missing)}",
                )
            return user
        return await header_checker(credentials=credentials, x_api_key=x_api_key)

    return checker


def require_media_token_ownership(
    all_permission: str | Permission,
    own_permission: str | Permission,
    *,
    include_api_key: bool = False,
):
    """Check ownership using a media token when present, or header credentials."""
    from backend.app.core import auth

    all_perm = all_permission.value if isinstance(all_permission, Permission) else all_permission
    own_perm = own_permission.value if isinstance(own_permission, Permission) else own_permission
    header_checker = auth.require_ownership_permission(all_permission, own_permission, include_api_key=include_api_key)

    async def checker(
        token: str | None = None,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(auth.security)] = None,
        x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ):
        if not token:
            return await header_checker(credentials=credentials, x_api_key=x_api_key)
        async with auth.async_session() as db:
            auth_enabled = await auth.is_auth_enabled(db)
        user = await auth._user_from_media_token(token) if auth_enabled else None
        can_access_all = user is None or user.has_permission(all_perm)
        if not can_access_all and not user.has_permission(own_perm):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {own_perm} or {all_perm}",
            )
        return auth.OwnershipAccess(user, can_access_all) if include_api_key else (user, can_access_all)

    return checker


def require_media_token_printer_permission(permission: str | Permission):
    """Apply resource permission and user/API-key printer scopes to media."""
    from backend.app.core import auth

    media_checker = require_media_token_ownership(permission, permission, include_api_key=True)

    async def checker(printer_id: int, access=Depends(media_checker)) -> User | None:
        if not auth.user_can_access_printer(access.user, printer_id):
            raise HTTPException(404, "Printer not found")
        if access.api_key is not None:
            auth.check_printer_access(access.api_key, printer_id)
        return access.user

    return checker
