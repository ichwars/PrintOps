"""Camera credentials and continued access to open video streams."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

from fastapi import HTTPException, Request
from fastapi.security.utils import get_authorization_scheme_param
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth_issuers import bind_api_key_issuer, bind_user_issuer, load_api_key_issuer, load_user_issuer
from backend.app.core.permissions import Permission
from backend.app.models.auth_ephemeral import AuthEphemeralToken, TokenType
from backend.app.models.long_lived_token import LongLivedToken
from backend.app.models.printer import Printer
from backend.app.models.user import User

CAMERA_STREAM_TOKEN_EXPIRE_MINUTES = 60


@dataclass(frozen=True)
class StreamOpener:
    token: str | None = field(default=None, repr=False)
    share_id: int | None = None
    share_owner_id: int | None = None
    share_scope: str | None = None
    share_hash: str | None = field(default=None, repr=False)


async def create_camera_stream_token(request: Request, user: User | None) -> str:
    """Mint a reusable credential bound to the authorized caller."""
    from backend.app.core import auth

    now = datetime.now(timezone.utc)
    row = AuthEphemeralToken(
        token=token_urlsafe(24),
        token_type=TokenType.CAMERA_STREAM,
        expires_at=now + timedelta(minutes=CAMERA_STREAM_TOKEN_EXPIRE_MINUTES),
    )
    async with auth.async_session() as db:
        if await auth.is_auth_enabled(db):
            scheme, credentials = get_authorization_scheme_param(request.headers.get("Authorization"))
            bearer = credentials if scheme.lower() == "bearer" else ""
            if user is not None:
                bind_user_issuer(row, request, user)
            else:
                key = None
                for candidate in (request.headers.get("X-API-Key"), bearer if bearer.startswith("bb_") else None):
                    if candidate and (key := await auth._validate_api_key(db, candidate)):
                        break
                if key is None:
                    raise HTTPException(401, "Valid camera issuer required")
                auth._check_apikey_permissions(key, [Permission.CAMERA_VIEW.value])
                bind_api_key_issuer(row, key)
        await db.execute(
            delete(AuthEphemeralToken).where(
                AuthEphemeralToken.token_type == TokenType.CAMERA_STREAM, AuthEphemeralToken.expires_at <= now
            )
        )
        token = row.token
        db.add(row)
        await db.commit()
        return token


def _printer_allowed(user: User, printer_id: int | None) -> bool:
    from backend.app.core import auth

    if printer_id is None:
        return auth.allowed_printer_ids_for_user(user) is None
    return auth.user_can_access_printer(user, printer_id)


async def _ephemeral_status(db: AsyncSession, row: AuthEphemeralToken, printer_id: int | None) -> int:
    from backend.app.core import auth

    if row.provider_id is not None:
        issuer = await load_api_key_issuer(db, row.provider_id, row.nonce)
        if issuer is None:
            return 401
        key, _ = issuer
        if not key.can_read_status or (key.printer_ids is not None and printer_id not in key.printer_ids):
            return 403
        return 200
    if not row.username:
        return 401 if await auth.is_auth_enabled(db) else 200

    user = await load_user_issuer(db, row)
    if user is None:
        return 401
    if not user.has_permission(Permission.CAMERA_VIEW.value) or not _printer_allowed(user, printer_id):
        return 403
    return 200


async def camera_share_status(db: AsyncSession, record: LongLivedToken, printer_id: int | None) -> int:
    owner = await db.get(User, record.user_id)
    if owner is None or not owner.is_active or record.created_at < owner.created_at:
        return 401
    # Overlay links use the owner's printer grants. Camera and Cam Wall
    # shares retain their existing appliance-wide scope.
    if not owner.has_permission(Permission.CAMERA_VIEW.value) or (
        record.scope == "overlay" and (printer_id is None or not _printer_allowed(owner, printer_id))
    ):
        return 403
    return 200


async def _get_ephemeral(db: AsyncSession, token: str) -> AuthEphemeralToken | None:
    return await db.scalar(
        select(AuthEphemeralToken).where(
            AuthEphemeralToken.token == token,
            AuthEphemeralToken.token_type == TokenType.CAMERA_STREAM,
            AuthEphemeralToken.expires_at > datetime.now(timezone.utc),
        )
    )


async def _token_access(db: AsyncSession, token: str, printer_id: int | None) -> tuple[int, StreamOpener | None]:
    from backend.app.services.long_lived_tokens import STREAM_SCOPES, verify_token

    row = await _get_ephemeral(db, token)
    if row is not None:
        status = await _ephemeral_status(db, row, printer_id)
        return status, StreamOpener(token=token) if status == 200 else None
    record = await verify_token(db, token, scope=STREAM_SCOPES)
    if record is None:
        return 401, None
    status = await camera_share_status(db, record, printer_id)
    if status != 200:
        return status, None
    return 200, StreamOpener(
        share_id=record.id, share_owner_id=record.user_id, share_scope=record.scope, share_hash=record.secret_hash
    )


async def camera_request_access(token: str | None, printer_id: int) -> tuple[int, StreamOpener | None]:
    from backend.app.core import auth

    async with auth.async_session() as db:
        if not await auth.is_auth_enabled(db):
            return 200, StreamOpener()
        return await _token_access(db, token, printer_id) if token else (401, None)


async def verify_camera_stream_token(token: str, printer_id: int | None = None) -> bool:
    from backend.app.core import auth

    async with auth.async_session() as db:
        status, _ = await _token_access(db, token, printer_id)
        return status == 200


async def stream_opener_still_allowed(opener: StreamOpener, printer_id: int) -> bool:
    """Check current permissions and revocation without rehashing share passwords."""
    from backend.app.core import auth
    from backend.app.services.long_lived_tokens import _is_expired

    async with auth.async_session() as db:
        if await db.get(Printer, printer_id) is None:
            return False
        if opener.token is not None:
            row = await _get_ephemeral(db, opener.token)
            return row is not None and await _ephemeral_status(db, row, printer_id) == 200
        if opener.share_id is None:
            return not await auth.is_auth_enabled(db)
        record = await db.get(LongLivedToken, opener.share_id)
        if (
            record is None
            or record.revoked_at is not None
            or record.user_id != opener.share_owner_id
            or record.scope != opener.share_scope
            or record.secret_hash != opener.share_hash
            or _is_expired(record, datetime.now(timezone.utc))
        ):
            return False
        return await camera_share_status(db, record, printer_id) == 200
