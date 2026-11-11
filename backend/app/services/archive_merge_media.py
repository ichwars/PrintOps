"""Stage archive assets before committing the merge that references them."""

import errno
import os
import shutil
from pathlib import Path
from uuid import uuid4

from backend.app.core.config import settings
from backend.app.services.archive import ArchiveService
from backend.app.utils.archive_paths import archive_dir
from backend.app.utils.safe_path import assert_under, safe_join_under


class ArchiveMergeConflict(Exception):
    """A group needs user attention before it can be merged."""


def archive_folder(archive) -> Path:
    return assert_under(
        settings.archive_dir,
        archive_dir(archive, base_dir=settings.base_dir, archive_root=settings.archive_dir),
        http=False,
    )


def existing_asset(stored: str | None) -> Path | None:
    if not stored:
        return None
    path = safe_join_under(settings.base_dir, stored, http=False)
    return path if path.is_file() else None


def _relative(path: Path) -> str:
    return str(path.relative_to(settings.base_dir.resolve()))


class StagedArchiveMedia:
    """Files placed with new names and removed if the database write fails."""

    def __init__(self, survivor):
        self.folder = archive_folder(survivor)
        self.photos = safe_join_under(self.folder, "photos", http=False)
        self._placements: dict[tuple[Path, Path], Path] = {}
        self._created: list[Path] = []
        self._checks: list[tuple[Path, str]] = []
        self._equal_assets: list[tuple[Path, Path]] = []
        self._source_stats: dict[Path, os.stat_result] = {}

    def primary(self, archives) -> str:
        paths = [file for archive in archives if (file := existing_asset(archive.file_path))]
        if not paths:
            raise ArchiveMergeConflict("missing_file")
        self._checks.extend((path, archives[0].content_hash) for path in set(paths))
        return self._place(paths[0], self.folder)

    def choose_extra(self, archives, name: str) -> str | None:
        files = list(dict.fromkeys(path for archive in archives if (path := existing_asset(getattr(archive, name)))))
        if not files:
            if any(getattr(archive, name) for archive in archives):
                raise ArchiveMergeConflict("missing_file")
            return None
        self._equal_assets.extend((files[0], other) for other in files[1:])
        return self._place(files[0], self.folder)

    def copy_asset(self, value: str | None) -> str | None:
        if not value:
            return None
        source = existing_asset(value)
        if source is None:
            raise ArchiveMergeConflict("missing_file")
        return self._place(source, self.folder)

    def copy_photos(self, archive, names) -> list[str]:
        if not names:
            return []
        folder = safe_join_under(archive_folder(archive), "photos", http=False)
        result = []
        for name in names:
            if not isinstance(name, str) or name != Path(name).name:
                raise ArchiveMergeConflict("conflicting_files")
            source = safe_join_under(folder, name, http=False)
            if not source.is_file():
                raise ArchiveMergeConflict("missing_file")
            result.append(Path(self._place(source, self.photos)).name)
        return result

    def _place(self, source: Path, folder: Path) -> str:
        if source.parent == folder:
            return _relative(source)
        key = (source, folder)
        if key not in self._placements:
            target = safe_join_under(folder, f"merged-{uuid4().hex}{source.suffix}", http=False)
            self._placements[key] = target
        return _relative(self._placements[key])

    def write(self) -> None:
        sources = {source for source, _ in self._placements}
        sources.update(source for source, _ in self._checks)
        sources.update(source for pair in self._equal_assets for source in pair)
        self._source_stats = {source: source.stat() for source in sources}
        for source, digest in self._checks:
            if ArchiveService.compute_file_hash(source) != digest:
                raise ArchiveMergeConflict("conflicting_files")
        for first, second in self._equal_assets:
            if ArchiveService.compute_file_hash(first) != ArchiveService.compute_file_hash(second):
                raise ArchiveMergeConflict("conflicting_files")
        for (source, folder), target in self._placements.items():
            folder.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source, target)
                self._created.append(target)
            except OSError as error:
                if error.errno != errno.EXDEV:
                    raise
                with source.open("rb") as reader, target.open("xb") as writer:
                    self._created.append(target)
                    shutil.copyfileobj(reader, writer)

    def undo(self) -> None:
        for target in self._created:
            target.unlink(missing_ok=True)

    def retire(self, folder: Path) -> None:
        """Remove a source directory only when every asset was accounted for."""
        try:
            entries = list(folder.rglob("*"))
            files = [entry for entry in entries if not entry.is_dir()]
            if any(entry.is_symlink() for entry in entries):
                return
            for path in files:
                before = self._source_stats.get(path)
                after = path.stat()
                if before is None or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                ):
                    return
            for path in files:
                path.unlink(missing_ok=True)
            for directory in sorted(
                (path for path in entries if path.is_dir()), key=lambda path: len(path.parts), reverse=True
            ):
                directory.rmdir()
            folder.rmdir()
        except OSError:
            # The database already points to the copied assets. Concurrent
            # writers or filesystem errors can leave the old folder in place.
            return
