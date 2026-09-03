"""Bounded database originals: included in ordinary DB backups, never regenerated."""

from hashlib import sha256

from defusedxml import ElementTree
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from backend.app.models.lexware import LexwareConnection
from backend.app.models.lexware_documents import LexwareDocument, LexwareOriginal
from backend.app.services.lexware_client import LexwareClient, LexwareError
from backend.app.services.lexware_connections import check_connection_generation, decrypt_api_key
from backend.app.services.lexware_documents import file_ids, file_sources

MAX_ORIGINAL_BYTES = 10 * 1024 * 1024
MEDIA_SUFFIXES = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
    "application/xml": "xml",
    "text/xml": "xml",
}


def validate_original(content: bytes, media_type: str) -> None:
    if not content or len(content) > MAX_ORIGINAL_BYTES:
        raise LexwareError("Lexware original is empty or exceeds the 10 MiB cache limit")
    if media_type not in MEDIA_SUFFIXES:
        raise LexwareError("Unsupported Lexware original file type")
    signatures = {"application/pdf": b"%PDF-", "image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}
    if media_type in signatures and not content.startswith(signatures[media_type]):
        raise LexwareError("Lexware original content does not match its file type")
    if media_type in {"application/xml", "text/xml"}:
        try:
            ElementTree.fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)
        except Exception:
            raise LexwareError("Lexware original contains invalid or unsafe XML") from None


async def _cached(db: AsyncSession, document_id: int, file_id: str) -> LexwareOriginal | None:
    return await db.scalar(
        select(LexwareOriginal)
        .where(
            LexwareOriginal.document_id == document_id,
            LexwareOriginal.file_id == file_id,
        )
        .options(undefer(LexwareOriginal.content))
    )


async def get_original(
    db: AsyncSession, document: LexwareDocument, connection: LexwareConnection, file_id: str
) -> LexwareOriginal:
    cached = await _cached(db, document.id, file_id)
    if cached is not None:
        if len(cached.content) != cached.size_bytes or sha256(cached.content).hexdigest() != cached.sha256:
            raise HTTPException(409, "Cached Lexware original failed integrity validation")
        return cached
    if file_id not in file_ids(document.payload):
        raise HTTPException(404, "Lexware original file was not found")
    if not connection.enabled or not connection.encrypted_api_key:
        raise HTTPException(409, "Reconnect Lexware to fetch an uncached original")
    key = decrypt_api_key(connection)
    connection_id, generation = connection.id, connection.version
    document_id, version_hash = document.id, document.version_hash
    path = file_sources(document.payload)[file_id]
    # End even the read transaction before any HTTP. Do not carry ORM attributes across rollback.
    await db.rollback()

    async def before_request():
        await check_connection_generation(connection_id, generation)

    async with LexwareClient(key, before_request=before_request) as client:
        content, media_type, _filename = await client.get_file(path)
    validate_original(content, media_type)
    # A conditional no-op UPDATE takes the DB write lock and checks the generation atomically.
    # Disconnect waits for this short transaction, or wins first and makes the predicate fail.
    result = await db.execute(
        update(LexwareConnection)
        .where(
            LexwareConnection.id == connection_id,
            LexwareConnection.version == generation,
            LexwareConnection.enabled.is_(True),
            LexwareConnection.encrypted_api_key.is_not(None),
        )
        .values(version=LexwareConnection.version)
    )
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(409, "Lexware connection changed during original download")
    current = await db.scalar(
        select(LexwareDocument).where(LexwareDocument.id == document_id).execution_options(populate_existing=True)
    )
    if current is None or current.version_hash != version_hash or file_id not in file_ids(current.payload):
        await db.rollback()
        raise HTTPException(409, "Lexware document changed during original download; reload it")
    cached = await _cached(db, document_id, file_id)
    if cached is None:
        cached = LexwareOriginal(
            document_id=document_id,
            file_id=file_id,
            source_path=path,
            filename=f"lexware-{file_id}.{MEDIA_SUFFIXES[media_type]}",
            media_type=media_type,
            content=content,
            size_bytes=len(content),
            sha256=sha256(content).hexdigest(),
        )
        db.add(cached)
    await db.commit()
    await db.refresh(cached, attribute_names=["content", "cached_at"])
    return cached
