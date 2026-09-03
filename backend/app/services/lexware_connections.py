"""Shared lifecycle guards used by synchronization and original-file downloads."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core import database, encryption
from backend.app.models.lexware import LexwareConnection
from backend.app.services.lexware_client import LexwareClient, LexwareError


def encrypt_api_key(value: str) -> str:
    if not value or len(value) > 4096 or any(c.isspace() for c in value):
        raise LexwareError("Invalid Lexware API key")
    try:
        result = encryption.mfa_encrypt(value)
    except Exception:
        raise LexwareError("Secure API key storage is unavailable") from None
    if not result.startswith("fernet:"):
        raise LexwareError("Secure API key storage is unavailable")
    return result


def decrypt_api_key(connection: LexwareConnection) -> str:
    if not connection.encrypted_api_key or not connection.encrypted_api_key.startswith("fernet:"):
        raise LexwareError("Lexware connection has no encrypted API key")
    try:
        return encryption.mfa_decrypt(connection.encrypted_api_key)
    except Exception:
        raise LexwareError("Lexware API key cannot be decrypted; reconnect the integration") from None


async def test_api_key(value: str) -> dict:
    async with LexwareClient(value) as client:
        profile = await client.get_json("/v1/profile")
    try:
        organization_id = str(UUID(profile["organizationId"]))
        company_name = profile["companyName"]
        if not isinstance(company_name, str) or not company_name.strip() or len(company_name) > 255:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise LexwareError("Lexware returned an invalid organization profile") from None
    return {"organization_id": organization_id, "company_name": company_name}


async def lock_connection(db: AsyncSession, connection_id: int) -> LexwareConnection:
    # A no-op UPDATE acquires SQLite's writer lock and a PostgreSQL row lock
    # before reading the current generation or any import target.
    found = await db.scalar(
        update(LexwareConnection)
        .where(LexwareConnection.id == connection_id)
        .values(version=LexwareConnection.version)
        .returning(LexwareConnection.id)
    )
    if found is None:
        raise LexwareError("Lexware connection not found", 404)
    return await db.scalar(
        select(LexwareConnection).where(LexwareConnection.id == connection_id).execution_options(populate_existing=True)
    )


async def check_connection_generation(connection_id: int, version: int) -> None:
    async with database.async_session() as db:
        valid = await db.scalar(
            select(LexwareConnection.id).where(
                LexwareConnection.id == connection_id,
                LexwareConnection.version == version,
                LexwareConnection.enabled.is_(True),
                LexwareConnection.encrypted_api_key.is_not(None),
            )
        )
        if valid is None:
            raise LexwareError("Lexware connection changed or was disconnected")
