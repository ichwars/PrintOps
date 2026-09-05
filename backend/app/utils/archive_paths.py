"""Canonical on-disk paths for archives, including rows without a 3MF."""

from pathlib import Path

from backend.app.core.config import settings

FALLBACK_ARCHIVE_DIRNAME = "_fallback"


def archive_dir(
    archive: object,
    *,
    base_dir: Path | None = None,
    archive_root: Path | None = None,
) -> Path:
    """Return the directory owned by *archive*.

    Normal archives live beside their 3MF. A fallback row has no ``file_path``
    yet, so its stable primary key provides a safe directory inside
    ``settings.archive_dir``.
    """

    base_dir = base_dir or settings.base_dir
    archive_root = archive_root or settings.archive_dir
    file_path = getattr(archive, "file_path", "") or ""
    if file_path:
        return base_dir / Path(file_path).parent
    return archive_root / FALLBACK_ARCHIVE_DIRNAME / str(int(archive.id))
