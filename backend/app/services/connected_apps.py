"""Persistent identity-code bindings and lifecycle cleanup for connected apps."""

import hashlib
import secrets

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.auth_ephemeral import AuthEphemeralToken, TokenType
from backend.app.models.connected_app import ConnectedApp, ConnectedAppGrant


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def configuration_digest(app: ConnectedApp) -> str:
    return digest(app.redirect_uri + "\0" + app.client_secret_hash)


def new_credentials() -> tuple[str, str]:
    return f"poa_{secrets.token_hex(12)}", f"pos_{secrets.token_urlsafe(32)}"


async def invalidate_codes(db: AsyncSession, app_id: int) -> None:
    await db.execute(
        delete(AuthEphemeralToken).where(
            AuthEphemeralToken.token_type == TokenType.CONNECT_CODE,
            AuthEphemeralToken.provider_id == app_id,
        )
    )


async def cleanup_user(db: AsyncSession, user_id: int) -> None:
    """Explicit cleanup also works with SQLite foreign-key enforcement disabled."""
    # Exchange/lifecycle operations lock app -> code/grant -> user. Acquire the
    # same app locks first, in stable order across concurrent user deletions.
    # Include third-party apps whose grants/codes will be deleted, not only apps
    # created by this user. Missing app rows still get dependent-row cleanup.
    app_ids = (
        await db.scalars(
            select(ConnectedApp.id)
            .where(
                or_(
                    ConnectedApp.created_by_id == user_id,
                    ConnectedApp.id.in_(select(ConnectedAppGrant.app_id).where(ConnectedAppGrant.user_id == user_id)),
                    ConnectedApp.id.in_(
                        select(AuthEphemeralToken.provider_id).where(
                            AuthEphemeralToken.token_type == TokenType.CONNECT_CODE,
                            AuthEphemeralToken.challenge_id.like(f"{user_id}:%"),
                        )
                    ),
                )
            )
            .order_by(ConnectedApp.id)
        )
    ).all()
    for app_id in app_ids:
        # A no-op write provides the existing lock semantics on SQLite and PG.
        await db.execute(update(ConnectedApp).where(ConnectedApp.id == app_id).values(id=ConnectedApp.id))
    await db.execute(update(ConnectedApp).where(ConnectedApp.created_by_id == user_id).values(created_by_id=None))
    await db.execute(delete(ConnectedAppGrant).where(ConnectedAppGrant.user_id == user_id))
    await db.execute(
        delete(AuthEphemeralToken).where(
            AuthEphemeralToken.token_type == TokenType.CONNECT_CODE,
            AuthEphemeralToken.challenge_id.like(f"{user_id}:%"),
        )
    )
