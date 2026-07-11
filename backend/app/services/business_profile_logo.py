from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Literal
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

MAX_LOGO_BYTES = 2 * 1024 * 1024
LogoMediaType = Literal["image/png", "image/jpeg"]
_FORMAT_MEDIA_TYPES: dict[str, LogoMediaType] = {"PNG": "image/png", "JPEG": "image/jpeg"}
_MEDIA_EXTENSIONS: dict[LogoMediaType, str] = {"image/png": "png", "image/jpeg": "jpeg"}


class InvalidBusinessProfileLogo(ValueError):
    pass


def validate_logo(content: bytes, declared_media_type: str | None) -> LogoMediaType:
    if len(content) > MAX_LOGO_BYTES:
        raise InvalidBusinessProfileLogo("logo_too_large")
    try:
        with Image.open(BytesIO(content)) as image:
            detected_media_type = _FORMAT_MEDIA_TYPES.get(image.format or "")
            image.verify()
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        raise InvalidBusinessProfileLogo("invalid_logo_image") from exc
    if detected_media_type is None or declared_media_type not in {None, detected_media_type}:
        raise InvalidBusinessProfileLogo("invalid_logo_type")
    return detected_media_type


def logo_path(root: Path, *, profile_id: int, version: int, media_type: LogoMediaType) -> Path:
    return root / f"{profile_id}-{version}.{_MEDIA_EXTENSIONS[media_type]}"


def write_logo_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def remove_logo(path: Path) -> None:
    path.unlink(missing_ok=True)
