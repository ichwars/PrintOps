"""Invalidate pending credentials when a user or restored database ends sessions."""

from collections.abc import Collection
from datetime import datetime, timezone

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from backend.app.models.api_key import APIKey, AppMessageQuota
from backend.app.models.auth_ephemeral import AuthEphemeralToken, AuthRateLimitEvent, TokenType
from backend.app.models.user import User

_KEY_TOKEN_TYPES = (TokenType.CAMERA_STREAM, TokenType.WEBSOCKET)
_USER_TOKEN_TYPES = (
    *_KEY_TOKEN_TYPES,
    TokenType.MEDIA,
    TokenType.CONNECT_CODE,
    TokenType.EMAIL_OTP_SETUP,
    TokenType.PRE_AUTH,
    TokenType.OIDC_EXCHANGE,
    TokenType.PASSWORD_RESET,
)


async def drop_pending_user_tokens(db: AsyncSession, username: str) -> None:
    await db.execute(
        delete(AuthEphemeralToken).where(
            func.lower(AuthEphemeralToken.username) == func.lower(username),
            AuthEphemeralToken.token_type.in_(_USER_TOKEN_TYPES),
        )
    )


async def _drop_api_key_tokens(db: AsyncSession, key_ids: Collection[int]) -> None:
    if key_ids:
        await db.execute(
            delete(AuthEphemeralToken).where(
                AuthEphemeralToken.token_type.in_(_KEY_TOKEN_TYPES),
                AuthEphemeralToken.provider_id.in_(key_ids),
            )
        )


async def drop_owned_key_tokens(db: AsyncSession, user_id: int) -> list[int]:
    key_ids = list(await db.scalars(select(APIKey.id).where(APIKey.user_id == user_id)))
    await _drop_api_key_tokens(db, key_ids)
    return key_ids


async def delete_api_key_and_tokens(db: AsyncSession, key: APIKey) -> None:
    await _drop_api_key_tokens(db, [key.id])
    await db.execute(delete(AppMessageQuota).where(AppMessageQuota.key_hash == key.key_hash))
    await db.delete(key)


async def cleanup_orphan_ephemeral_tokens(conn: AsyncConnection) -> None:
    await conn.execute(
        delete(AuthEphemeralToken).where(
            AuthEphemeralToken.token_type.in_(_KEY_TOKEN_TYPES),
            AuthEphemeralToken.provider_id.is_not(None),
            AuthEphemeralToken.provider_id.not_in(select(APIKey.id)),
        )
    )
    issuer_exists = (
        select(User.id)
        .where(
            func.lower(User.username) == func.lower(AuthEphemeralToken.username),
            or_(
                AuthEphemeralToken.issuer_identity.is_(None),
                AuthEphemeralToken.issuer_identity == User.connected_identity,
            ),
        )
        .correlate(AuthEphemeralToken)
        .exists()
    )
    await conn.execute(
        delete(AuthEphemeralToken).where(
            AuthEphemeralToken.token_type.in_(_USER_TOKEN_TYPES),
            AuthEphemeralToken.username.is_not(None),
            AuthEphemeralToken.username != "",
            or_(AuthEphemeralToken.token_type.not_in(_KEY_TOKEN_TYPES), AuthEphemeralToken.provider_id.is_(None)),
            ~issuer_exists,
        )
    )


async def drop_anonymous_live_tokens(db: AsyncSession) -> None:
    await db.execute(
        delete(AuthEphemeralToken).where(
            AuthEphemeralToken.token_type.in_((*_KEY_TOKEN_TYPES, TokenType.MEDIA)),
            or_(AuthEphemeralToken.username.is_(None), AuthEphemeralToken.username == ""),
            AuthEphemeralToken.provider_id.is_(None),
        )
    )


async def invalidate_all_sessions(conn: AsyncConnection) -> None:
    """Require fresh user JWTs and discard in-flight auth flows, retaining logout revocations."""
    await conn.execute(update(User).values(password_changed_at=datetime.now(timezone.utc), updated_at=User.updated_at))
    await conn.execute(delete(AuthEphemeralToken).where(AuthEphemeralToken.token_type != TokenType.REVOKED_JTI))
    await conn.execute(delete(AuthRateLimitEvent))


async def handle_restored_sessions() -> None:
    from backend.app.core import auth, database
    from backend.app.core.websocket import ws_manager

    async with database.engine.begin() as conn:
        await invalidate_all_sessions(conn)

    auth.invalidate_auth_enabled_cache()
    async with database.async_session() as db:
        auth_enabled = await auth.is_auth_enabled(db)
    await ws_manager.reconcile_restored_access(auth_enabled)
