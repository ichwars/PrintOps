"""Three-day capabilities for one immutable notification image.

These credentials are deliberately separate from user media and camera tokens.
The local JPEG copy is private; only its digest-bound capability can retrieve it.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.models.archive import PrintArchive
from backend.app.models.auth_ephemeral import AuthEphemeralToken, TokenType
from backend.app.utils.archive_paths import archive_dir
from backend.app.utils.safe_path import PathTraversalError, safe_join_under

PHOTO_LIFETIME = timedelta(days=3)
MAX_PHOTO_BYTES = 10_000_000
MAX_ATTACHMENT_BYTES = 2_500_000
_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{43}")
_FILENAME_RE = re.compile(r"[a-f0-9]{32}\.jpg")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _directory() -> Path:
    return safe_join_under(settings.base_dir, "notification_photos", http=False)


def _path(filename: str | None) -> Path | None:
    if not filename or not _FILENAME_RE.fullmatch(filename):
        return None
    try:
        return safe_join_under(_directory(), filename, http=False)
    except PathTraversalError:
        return None


def _read_photo(path: Path) -> bytes | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_PHOTO_BYTES:
            return None
        # Bound the read itself, including files growing between stat and read.
        with path.open("rb") as stream:
            data = stream.read(MAX_PHOTO_BYTES + 1)
        if len(data) > MAX_PHOTO_BYTES or not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
            return None
        return data
    except OSError:
        return None


async def external_photo_base(db: AsyncSession) -> str | None:
    from backend.app.api.routes.settings import get_setting

    base = (await get_setting(db, "external_url") or "").rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return None
    return base


async def create_notification_photo_url(db: AsyncSession, data: bytes, *, archive_id: int | None = None) -> str | None:
    """Publish only these bytes; commit before an external provider can fetch them."""
    base = await external_photo_base(db)
    if (
        not base
        or not data
        or len(data) > MAX_PHOTO_BYTES
        or not data.startswith(b"\xff\xd8")
        or not data.endswith(b"\xff\xd9")
    ):
        return None
    expired = list(
        (
            await db.scalars(
                select(AuthEphemeralToken).where(
                    AuthEphemeralToken.token_type == TokenType.NOTIFICATION_PHOTO,
                    AuthEphemeralToken.expires_at <= _now(),
                )
            )
        ).all()
    )
    await db.execute(
        delete(AuthEphemeralToken).where(
            AuthEphemeralToken.token_type == TokenType.NOTIFICATION_PHOTO,
            AuthEphemeralToken.expires_at <= _now(),
        )
    )
    for grant in expired:
        old = _path(grant.nonce)
        if old:
            try:
                await asyncio.to_thread(old.unlink, missing_ok=True)
            except OSError:
                pass  # Expired files stay inaccessible even if cleanup cannot unlink.
    try:
        directory = _directory()
    except PathTraversalError:
        return None
    await asyncio.to_thread(directory.mkdir, mode=0o700, parents=True, exist_ok=True)
    filename = secrets.token_hex(16) + ".jpg"
    path = _path(filename)
    if path is None:
        return None
    token = secrets.token_urlsafe(32)
    await asyncio.to_thread(path.write_bytes, data)
    await asyncio.to_thread(path.chmod, 0o600)
    db.add(
        AuthEphemeralToken(
            token=hashlib.sha256(token.encode()).hexdigest(),
            token_type=TokenType.NOTIFICATION_PHOTO,
            nonce=filename,
            code_verifier=hashlib.sha256(data).hexdigest(),
            challenge_id=str(archive_id) if archive_id is not None else None,
            expires_at=_now() + PHOTO_LIFETIME,
        )
    )
    try:
        await db.commit()
    except Exception:
        await asyncio.to_thread(path.unlink, missing_ok=True)
        raise
    return f"{base}/api/v1/notifications/photos/{token}"


async def resolve_notification_photo(db: AsyncSession, token: str) -> bytes | None:
    if not _TOKEN_RE.fullmatch(token):
        return None
    grant = await db.scalar(
        select(AuthEphemeralToken).where(
            AuthEphemeralToken.token_type == TokenType.NOTIFICATION_PHOTO,
            AuthEphemeralToken.token == hashlib.sha256(token.encode()).hexdigest(),
            AuthEphemeralToken.expires_at > _now(),
        )
    )
    if grant is None:
        return None
    if grant.challenge_id is not None:
        if not grant.challenge_id.isdigit():
            return None
        archive = await db.get(PrintArchive, int(grant.challenge_id))
        if archive is None or archive.deleted_at is not None:
            return None
    path = _path(grant.nonce)
    data = await asyncio.to_thread(_read_photo, path) if path else None
    if data is None or not secrets.compare_digest(hashlib.sha256(data).hexdigest(), grant.code_verifier or ""):
        return None
    return data


async def finish_photo_for_notification(
    db: AsyncSession, archive: PrintArchive, filename: str
) -> tuple[str | None, bytes | None]:
    """Preserve finish-photo templates/CID, using a narrow link with auth enabled."""
    from backend.app.core.auth import is_auth_enabled

    if not filename or Path(filename).name != filename or "\\" in filename:
        return None, None
    try:
        root = safe_join_under(settings.base_dir, str(archive_dir(archive).relative_to(settings.base_dir)), http=False)
        path = safe_join_under(root / "photos", filename, http=False)
    except (PathTraversalError, ValueError):
        return None, None
    data = await asyncio.to_thread(_read_photo, path)
    if data is None:
        return None, None
    try:
        auth_enabled = await is_auth_enabled(db)
    except Exception:
        auth_enabled = True
    base = await external_photo_base(db)
    url = (
        await create_notification_photo_url(db, data, archive_id=archive.id)
        if auth_enabled
        else f"{base or ''}/api/v1/archives/{archive.id}/photos/{filename}"
    )
    return url, data if len(data) <= MAX_ATTACHMENT_BYTES else None
