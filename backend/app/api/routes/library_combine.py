"""Library mesh combination."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.library import LibraryFile, LibraryFolder
from backend.app.models.user import User
from backend.app.schemas.library import CombineFilesRequest, FileUploadResponse
from backend.app.utils.filename import InvalidFilenameError


async def combine_files(
    request: CombineFilesRequest, db: AsyncSession, current_user: User | None, read_auth: tuple[User | None, bool]
):
    """Create one bounded source 3MF with shared meshes and positioned copies."""
    from backend.app.api.routes import library
    from backend.app.services.mesh_combine import CombinePart, MeshCombineError, combine_parts_to_3mf

    filename = request.filename.strip()
    if not filename:
        raise HTTPException(400, "Filename cannot be empty")
    if not filename.lower().endswith(".3mf"):
        filename += ".3mf"
    try:
        library.validate_print_filename(filename)
    except InvalidFilenameError as exc:
        raise HTTPException(400, str(exc)) from exc
    if request.folder_id is not None:
        folder = (
            await db.execute(select(LibraryFolder).where(LibraryFolder.id == request.folder_id))
        ).scalar_one_or_none()
        if folder is None:
            raise HTTPException(404, "Folder not found")
        # Enforce readonly/writability/collision guards before expensive work.
        library._resolve_upload_destination(folder, filename)

    copies: dict[int, int] = {}
    for item in request.items:
        copies[item.file_id] = copies.get(item.file_id, 0) + item.copies
    rows = (await db.execute(LibraryFile.active().where(LibraryFile.id.in_(copies)))).scalars().all()
    by_id = {row.id: row for row in rows}
    user, can_read_all = read_auth
    sources = [library._ensure_library_file_visible(by_id.get(file_id), user, can_read_all) for file_id in copies]
    parts = []
    for source in sources:
        if not source.filename.lower().endswith(".stl"):
            raise HTTPException(400, f"Only STL files can be combined: {source.filename}")
        path = library._resolve_source_disk_path(source)
        if path is None or not path.is_file():
            raise HTTPException(404, f"Source file missing on disk: {source.filename}")
        parts.append(CombinePart(source.filename, path, copies[source.id]))
    try:
        content = await library.asyncio.to_thread(combine_parts_to_3mf, parts)
    except MeshCombineError as exc:
        raise HTTPException(400, str(exc)) from exc
    row, _existing = await library.save_3mf_bytes_to_library(
        db,
        file_bytes=content,
        filename=filename,
        folder_id=request.folder_id,
        source_type="combined",
        owner_id=current_user.id if current_user else None,
    )
    row.file_metadata = {**(row.file_metadata or {}), "object_count": sum(copies.values())}
    await db.commit()
    return FileUploadResponse(
        id=row.id,
        filename=row.filename,
        file_type=row.file_type,
        file_size=row.file_size,
        thumbnail_path=row.thumbnail_path,
        metadata=row.file_metadata,
    )
