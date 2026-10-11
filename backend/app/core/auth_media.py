"""Media-token lifecycle and scoped media authentication dependencies."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import delete, select

from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.auth_ephemeral import AuthEphemeralToken, TokenType
from backend.app.models.user import User


async def create_media_token(username: str | None) -> str:
    """Issue a reusable media credential bound to a username and user id.

    An auth-disabled token has no principal and fails closed if auth is later
    enabled. API keys retain their own scopes through the header path instead.
    """
    from backend.app.core import auth

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=auth.MEDIA_TOKEN_EXPIRE_MINUTES)
    token = auth.secrets.token_urlsafe(24)
    async with auth.async_session() as db:
        # Prune expired tokens opportunistically (same shape as camera/websocket).
        await db.execute(
            delete(AuthEphemeralToken).where(
                AuthEphemeralToken.token_type == TokenType.MEDIA,
                AuthEphemeralToken.expires_at < now,
            )
        )
        user = await auth.get_user_by_username(db, username) if username else None
        db.add(
            AuthEphemeralToken(
                token=token,
                token_type=TokenType.MEDIA,
                username=username or "",
                nonce=str(user.id) if user is not None else None,
                expires_at=expires_at,
            )
        )
        await db.commit()
    return token


async def verify_media_token(token: str) -> str | None:
    """Verify a media token, returning the username it was minted for.

    Returns ``""`` for an auth-disabled token (no per-row identity) and
    ``None`` when the token is missing / expired / unknown. Not consumed --
    one token serves every image on a page.

    Deliberately narrower than :func:`verify_camera_stream_token`: no
    long-lived scope passes here. ``camera_stream`` / ``camwall`` / ``overlay``
    tokens are handed to kiosks, walls and Home Assistant to display *video*,
    and are anonymous by construction, so accepting one would reinstate the
    unowned read this token type exists to close (#3025). The inverse also
    holds -- see :func:`verify_camwall_token`, which refuses a camera-stream
    token for the same reason in the other direction.
    """
    from backend.app.core import auth

    now = datetime.now(timezone.utc)
    async with auth.async_session() as db:
        result = await db.execute(
            select(AuthEphemeralToken).where(
                AuthEphemeralToken.token == token,
                AuthEphemeralToken.token_type == TokenType.MEDIA,
                AuthEphemeralToken.expires_at > now,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return row.username or ""


def require_camera_stream_token_if_auth_enabled():
    """Dependency that validates a camera stream token query param when auth is enabled.

    Used for camera stream/snapshot endpoints that are loaded via <img> tags
    which cannot send Authorization headers. The frontend obtains a token from
    POST /printers/camera/stream-token and appends it as ?token=xxx.
    Camera routes only; resource media uses the identified media token.
    """
    from backend.app.core import auth

    async def checker(token: str | None = None) -> None:
        async with auth.async_session() as db:
            if not await auth.is_auth_enabled(db):
                return  # Auth disabled, allow access
        if not token or not await auth.verify_camera_stream_token(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Valid camera stream token required. Obtain one from POST /api/v1/printers/camera/stream-token",
            )

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
    """Dependency that validates a streaming-overlay token query param when auth is enabled."""
    from backend.app.core import auth

    async def checker(token: str | None = None) -> None:
        async with auth.async_session() as db:
            if not await auth.is_auth_enabled(db):
                return
        if not token or not await auth.verify_overlay_token(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Valid streaming overlay token required. Create one under Settings > API Keys with the 'Overlay' scope.",
            )

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
    username = await auth.verify_media_token(token)
    if not username:
        raise unauthorized
    async with auth.async_session() as db:
        user = await auth.get_user_by_username(db, username)
        row = await db.scalar(
            select(AuthEphemeralToken).where(
                AuthEphemeralToken.token == token,
                AuthEphemeralToken.token_type == TokenType.MEDIA,
            )
        )
    if (
        user is None
        or not user.is_active
        or row is None
        or row.nonce != str(user.id)
        or not auth._is_token_fresh(row.created_at.replace(tzinfo=timezone.utc).timestamp(), user)
    ):
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
):
    """Media-route dependency for ownership-scoped resources (#3025).

    The ownership counterpart of :func:`require_media_token_permission`, and
    the reason media tokens carry a principal at all: it returns the same
    ``(user, can_read_all)`` pair as :func:`require_ownership_permission`, so a
    thumbnail route can hand it straight to the ``_ensure_*_visible`` gate its
    header-authenticated siblings already use instead of serving any row to any
    token holder.

    Header callers are delegated to :func:`require_ownership_permission`
    unchanged -- including its API-key rule, where a key satisfying the ALL
    permission's scope flag gets ``can_read_all=True`` because keys have no
    per-row identity.
    """
    from backend.app.core import auth

    all_perm = all_permission.value if isinstance(all_permission, Permission) else all_permission
    own_perm = own_permission.value if isinstance(own_permission, Permission) else own_permission
    header_checker = auth.require_ownership_permission(all_permission, own_permission)

    async def checker(
        token: str | None = None,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(auth.security)] = None,
        x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> tuple[User | None, bool]:
        async with auth.async_session() as db:
            if not await auth.is_auth_enabled(db):
                return None, True  # Auth disabled, allow all
        if token:
            user = await auth._user_from_media_token(token)
            if user.has_permission(all_perm):
                return user, True
            if user.has_permission(own_perm):
                return user, False
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {own_perm} or {all_perm}",
            )
        return await header_checker(credentials=credentials, x_api_key=x_api_key)

    return checker


def require_media_token_printer_permission(permission: str | Permission):
    """Apply resource permission and user/API-key printer scopes to media."""
    from backend.app.core import auth

    media_checker = auth.require_media_token_permission(permission)

    async def checker(
        printer_id: int,
        user: User | None = Depends(media_checker),
        api_key: APIKey | None = Depends(auth.resolve_optional_api_key),
    ) -> User | None:
        if not auth.user_can_access_printer(user, printer_id):
            raise HTTPException(404, "Printer not found")
        if api_key is not None:
            auth.check_printer_access(api_key, printer_id)
        return user

    return checker
