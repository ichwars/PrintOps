"""Access and storage for library folders carried by project exports."""

from pathlib import Path, PurePosixPath
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes.library import get_library_dir, get_library_files_dir, to_absolute_path, to_relative_path
from backend.app.core.permissions import Permission
from backend.app.core.row_visibility import RowVisibility, library_read_criteria
from backend.app.models.library import LibraryFile, LibraryFolder
from backend.app.utils.library_files import classify_file_type
from backend.app.utils.safe_path import safe_join_under


async def link_imported_folder(
    db: AsyncSession, name: str, project_id: int, visibility: RowVisibility
) -> LibraryFolder:
    if visibility.can_access_owner(None, Permission.LIBRARY_UPDATE_ALL, Permission.LIBRARY_UPDATE_OWN):
        folder = await db.scalar(
            select(LibraryFolder)
            .where(
                LibraryFolder.name == name,
                LibraryFolder.parent_id.is_(None),
                LibraryFolder.is_external.is_(False),
            )
            .order_by(LibraryFolder.id)
            .limit(1)
            .with_for_update()
        )
        if folder is not None:
            folder.project_id = project_id
            return folder
    folder = LibraryFolder(name=name, project_id=project_id)
    db.add(folder)
    await db.flush()
    return folder


def add_imported_files(
    db: AsyncSession,
    folder: LibraryFolder,
    zip_files: dict[str, bytes],
    created_by_id: int | None,
    written_paths: list[Path],
) -> None:
    prefix = f"files/{folder.name}/"
    for zip_path, content in zip_files.items():
        if not zip_path.startswith(prefix) or zip_path.endswith("/"):
            continue
        filename = zip_path.removeprefix(prefix)
        parts = PurePosixPath(filename).parts
        folder_path = safe_join_under(get_library_dir(), folder.name)
        safe_join_under(folder_path, *parts)
        if ".thumbnails" in parts:
            continue
        suffix = PurePosixPath(filename).suffix
        path = safe_join_under(get_library_files_dir(), f"{uuid4().hex}{suffix}")
        with path.open("xb") as output:
            written_paths.append(path)
            output.write(content)
        db.add(
            LibraryFile(
                folder_id=folder.id,
                filename=filename,
                file_path=to_relative_path(path),
                file_type=classify_file_type(filename, path),
                file_size=len(content),
                created_by_id=created_by_id,
                is_external=False,
            )
        )


def _resolve_stored_file(stored_path: str | None) -> Path | None:
    try:
        path = to_absolute_path(stored_path)
        if path is None or path.is_file() or Path(stored_path).is_absolute():
            return path
        # Older project ZIP imports used paths relative to the library directory.
        return safe_join_under(get_library_dir(), stored_path, http=False)
    except ValueError:
        return None


async def export_linked_library(
    db: AsyncSession, project_id: int, visibility: RowVisibility
) -> tuple[list[dict], list[tuple[Path, str]]]:
    read_all = visibility.can_access_owner(None, Permission.LIBRARY_READ_ALL, Permission.LIBRARY_READ_OWN)
    if not read_all and (
        visibility.user is None
        or not visibility.can_access_owner(visibility.user.id, Permission.LIBRARY_READ_ALL, Permission.LIBRARY_READ_OWN)
    ):
        return [], []
    folders = await db.scalars(
        select(LibraryFolder).where(LibraryFolder.project_id == project_id).order_by(LibraryFolder.name)
    )
    folders_export = []
    files_to_include = []
    for folder in folders:
        files = list(
            await db.scalars(
                LibraryFile.active()
                .where(LibraryFile.folder_id == folder.id, *library_read_criteria(visibility))
                .order_by(LibraryFile.filename)
            )
        )
        if not read_all and not files:
            continue
        folders_export.append(
            {
                "name": folder.name,
                "files": [{"filename": f.filename, "file_type": f.file_type, "notes": f.notes} for f in files],
            }
        )
        for file in files:
            for stored_path, zip_name in (
                (file.file_path, f"files/{folder.name}/{file.filename}"),
                (file.thumbnail_path, f"files/{folder.name}/.thumbnails/{file.filename}.png"),
            ):
                path = _resolve_stored_file(stored_path)
                if path is not None and path.is_file() and ".." not in PurePosixPath(zip_name.replace("\\", "/")).parts:
                    files_to_include.append((path, zip_name))
    return folders_export, files_to_include
