"""Managed photo storage follows library IDs rather than source file locations."""

import logging
import shutil
import uuid
from pathlib import Path

from backend.app.core.config import settings
from backend.app.utils.safe_path import PathTraversalError, safe_join_under

logger = logging.getLogger(__name__)


def library_photos_dir(file_id: int) -> Path:
    return Path(settings.archive_dir) / "library" / "photos" / str(file_id)


def remove_library_photos_dir(file_id: int) -> None:
    path = library_photos_dir(file_id)
    if path.is_dir():
        try:
            shutil.rmtree(path)
        except OSError as exc:
            logger.warning("Failed to remove library photos %s: %s", file_id, exc)


def move_library_photos(file_id: int, photos: list[str], destination: Path) -> list[str]:
    moved = []
    failed = False
    for name in photos:
        try:
            source = safe_join_under(library_photos_dir(file_id), name, http=False)
            if not source.is_file():
                continue
            destination.mkdir(parents=True, exist_ok=True)
            target = safe_join_under(destination, name, http=False)
            if target.exists():
                name = f"{uuid.uuid4().hex}{source.suffix.lower()}"
                target = safe_join_under(destination, name, http=False)
            shutil.move(str(source), str(target))
            moved.append(name)
        except (OSError, PathTraversalError) as exc:
            failed = True
            logger.warning("Failed to move library photo for file %s: %s", file_id, exc)
    if not failed:
        remove_library_photos_dir(file_id)
    return moved
