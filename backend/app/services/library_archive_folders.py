"""Read folder summaries for archives and files visible to the caller."""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.row_visibility import RowVisibility, archive_read_criteria, library_read_criteria
from backend.app.models.archive import PrintArchive
from backend.app.models.library import LibraryFile, LibraryFolder
from backend.app.schemas.library import FolderResponse


async def read_archive_folders(
    db: AsyncSession, visibility: RowVisibility, archive_ids: list[int]
) -> dict[int, list[FolderResponse]]:
    folders: dict[int, list[FolderResponse]] = {archive_id: [] for archive_id in archive_ids}
    rows = (
        await db.execute(
            select(
                LibraryFolder,
                PrintArchive.print_name,
                func.count(LibraryFile.id),
                func.max(func.coalesce(LibraryFile.fs_modified_at, LibraryFile.updated_at)),
            )
            .join(PrintArchive, LibraryFolder.archive_id == PrintArchive.id)
            .outerjoin(
                LibraryFile,
                and_(
                    LibraryFile.folder_id == LibraryFolder.id,
                    LibraryFile.deleted_at.is_(None),
                    *library_read_criteria(visibility),
                ),
            )
            .where(PrintArchive.id.in_(archive_ids), *archive_read_criteria(visibility))
            .group_by(LibraryFolder.id, PrintArchive.print_name)
            .order_by(LibraryFolder.name, LibraryFolder.id)
        )
    ).all()
    for folder, archive_name, file_count, latest_file in rows:
        own_activity = folder.fs_modified_at or folder.updated_at
        latest_activity_at = max(own_activity, latest_file) if latest_file is not None else own_activity

        folders[folder.archive_id].append(
            FolderResponse(
                id=folder.id,
                name=folder.name,
                parent_id=folder.parent_id,
                project_id=folder.project_id,
                archive_id=folder.archive_id,
                project_name=None,
                archive_name=archive_name,
                is_external=folder.is_external,
                external_path=folder.external_path,
                external_readonly=folder.external_readonly,
                external_show_hidden=folder.external_show_hidden,
                file_count=file_count,
                latest_activity_at=latest_activity_at,
                created_at=folder.created_at,
                updated_at=folder.updated_at,
            )
        )

    return folders
