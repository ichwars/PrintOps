"""Synchronize external library trees without copying their files."""

from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.library import LibraryFile, LibraryFolder
from backend.app.models.settings import Settings


async def _external_folder_tree(db: AsyncSession, folder_id: int):
    all_folder_ids = [folder_id]
    child_result = await db.execute(
        select(LibraryFolder).where(
            LibraryFolder.is_external.is_(True),
            LibraryFolder.parent_id.isnot(None),
        )
    )
    all_child_folders = child_result.scalars().all()

    parent_to_children: dict[int, list] = {}
    for cf in all_child_folders:
        parent_to_children.setdefault(cf.parent_id, []).append(cf)

    queue = [folder_id]
    while queue:
        pid = queue.pop()
        for child in parent_to_children.get(pid, []):
            all_folder_ids.append(child.id)
            queue.append(child.id)
    return all_folder_ids, all_child_folders


def _external_folder_cache(
    ext_path: Path, folder_id: int, all_folder_ids: list[int], all_child_folders: list[LibraryFolder]
):
    folder_cache: dict[str, int] = {"": folder_id}
    for fid in all_folder_ids:
        if fid == folder_id:
            continue
        # Find the child folder object
        for cf in all_child_folders:
            if cf.id == fid and cf.external_path:
                try:
                    rel = Path(cf.external_path).relative_to(ext_path).as_posix()
                    if rel != ".":
                        folder_cache[rel] = cf.id
                except ValueError:
                    pass
    return folder_cache


async def scan_external_folder(folder_id: int, db: AsyncSession):
    """Sync an external folder to the database without copying files."""
    from backend.app.api.routes import library

    result = await db.execute(select(LibraryFolder).where(LibraryFolder.id == folder_id))
    folder = result.scalar_one_or_none()

    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if not folder.is_external or not folder.external_path:
        raise HTTPException(status_code=400, detail="Not an external folder")

    ext_path = Path(folder.external_path)
    if not ext_path.exists() or not ext_path.is_dir():
        raise HTTPException(status_code=400, detail=f"External path is not accessible: {folder.external_path}")

    all_folder_ids, all_child_folders = await _external_folder_tree(db, folder_id)

    existing_result = await db.execute(
        LibraryFile.active().where(
            LibraryFile.folder_id.in_(all_folder_ids),
            LibraryFile.is_external.is_(True),
        )
    )
    existing_files = {f.file_path: f for f in existing_result.scalars().all()}
    repair_key = f"_backfill_132_external_folder_{folder_id}"
    external_types_repaired = (
        await db.execute(select(Settings.id).where(Settings.key == repair_key))
    ).scalar_one_or_none() is not None

    folder_cache = _external_folder_cache(ext_path, folder_id, all_folder_ids, all_child_folders)

    # Scan the directory
    added = 0
    removed = 0
    found_paths: set[str] = set()
    seen_rel_dirs: set[str] = set()
    # Real on-disk mtime per visited folder id (#2680), applied after the walk.
    folder_mtimes: dict[int, datetime] = {}

    for dirpath, dirnames, filenames in library.os.walk(ext_path):
        # Filter hidden directories unless configured
        if not folder.external_show_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]

        rel_dir = Path(dirpath).relative_to(ext_path).as_posix()
        if rel_dir == ".":
            rel_dir = ""
        seen_rel_dirs.add(rel_dir)

        # Resolve or create subfolder chain for this directory
        if rel_dir and rel_dir not in folder_cache:
            parts = Path(rel_dir).parts
            current_path = ""
            current_parent = folder_id
            for part in parts:
                current_path = f"{current_path}/{part}".lstrip("/")
                if current_path in folder_cache:
                    current_parent = folder_cache[current_path]
                else:
                    existing_sub = await db.execute(
                        select(LibraryFolder).where(
                            LibraryFolder.name == part,
                            LibraryFolder.parent_id == current_parent,
                            LibraryFolder.is_external.is_(True),
                        )
                    )
                    existing_folder = existing_sub.scalar_one_or_none()
                    if existing_folder:
                        current_parent = existing_folder.id
                    else:
                        new_folder = LibraryFolder(
                            name=part,
                            parent_id=current_parent,
                            is_external=True,
                            external_path=str(
                                ext_path / current_path
                            ),  # SEC-PATH-OK: current_path built from Path(rel_dir).parts of an os.walk descent under ext_path
                            external_readonly=folder.external_readonly,
                            external_show_hidden=folder.external_show_hidden,
                        )
                        db.add(new_folder)
                        await db.flush()
                        current_parent = new_folder.id
                    folder_cache[current_path] = current_parent

        target_folder_id = folder_cache.get(rel_dir, folder_id)

        # Record this directory's own mtime (#2680). os.walk visits every
        # directory once, so this covers the root external folder and every
        # subfolder (existing or just created). Applied to the folder rows
        # after the walk completes.
        try:
            folder_mtimes[target_folder_id] = library._mtime_to_datetime(library.os.stat(dirpath).st_mtime)
        except OSError:
            pass

        for filename in filenames:
            # Skip hidden files unless configured
            if not folder.external_show_hidden and filename.startswith("."):
                continue

            filepath = (
                Path(dirpath) / filename
            )  # SEC-PATH-OK: dirpath + filename from os.walk(ext_path); filesystem-discovered, not user input
            ext = filepath.suffix.lower()

            # Check for compound extensions like .gcode.3mf
            if ext not in library._SCANNABLE_EXTENSIONS:
                # Check compound
                compound = "".join(filepath.suffixes[-2:]).lower() if len(filepath.suffixes) >= 2 else ""
                if compound not in library._SCANNABLE_EXTENSIONS:
                    continue

            # Resolve symlinks and ensure still under external_path
            try:
                real_path = filepath.resolve()
                real_path.relative_to(ext_path.resolve())
            except (ValueError, OSError):
                continue  # Symlink escapes the external dir

            try:
                stat = filepath.stat()
            except OSError:
                continue
            fs_mtime = library._mtime_to_datetime(stat.st_mtime)
            file_path_str = str(filepath)
            found_paths.add(file_path_str)

            if file_path_str in existing_files:
                tracked = existing_files[file_path_str]
                changed = tracked.file_size != stat.st_size or tracked.fs_modified_at != fs_mtime
                if not external_types_repaired or changed:
                    tracked.file_type = library.classify_file_type(filename, filepath)
                tracked.file_size = stat.st_size
                if tracked.fs_modified_at != fs_mtime:
                    tracked.fs_modified_at = fs_mtime
                continue

            file_type = library.classify_file_type(filename, filepath)

            # Extract thumbnail for 3mf files (including .gcode.3mf sliced
            # outputs — those are 3MF zips on disk and carry the same
            # thumbnail Metadata/plate_1.png the parser reads). Pre-#1600
            # the gate was `file_type == "3mf"` alone, so .gcode.3mf files
            # in external folders silently got no thumbnail.
            thumbnail_path = None
            file_metadata = None
            if file_type in ("3mf", "gcode.3mf"):
                try:
                    parser = library.ThreeMFParser(str(filepath))
                    raw_metadata = parser.parse()
                    if raw_metadata:
                        # Extract thumbnail before cleaning metadata
                        thumb_data = raw_metadata.get("_thumbnail_data")
                        thumbnail_ext = raw_metadata.get("_thumbnail_ext", ".png")
                        if thumb_data:
                            thumb_dir = library.get_library_thumbnails_dir()
                            thumb_filename = f"{library.uuid.uuid4().hex}{thumbnail_ext}"
                            thumb_full = (
                                thumb_dir / thumb_filename
                            )  # SEC-PATH-OK: thumb_filename = uuid.uuid4().hex + thumbnail_ext
                            thumb_full.write_bytes(thumb_data)
                            thumbnail_path = library.to_relative_path(thumb_full)

                        # Clean metadata - remove non-JSON-serializable data (bytes, etc.)
                        def clean_metadata(obj):
                            if isinstance(obj, dict):
                                return {
                                    k: clean_metadata(v)
                                    for k, v in obj.items()
                                    if not isinstance(v, bytes) and k not in ("_thumbnail_data", "_thumbnail_ext")
                                }
                            elif isinstance(obj, list):
                                return [clean_metadata(i) for i in obj if not isinstance(i, bytes)]
                            elif isinstance(obj, bytes):
                                return None
                            return obj

                        file_metadata = clean_metadata(raw_metadata)
                except Exception as e:
                    library.logger.debug("Failed to extract metadata from external 3mf %s: %s", filepath, e)

            # STL thumbnails are deferred to a background task spawned after
            # the scan's db.commit() — see _backfill_external_stl_thumbnails.
            # Doing them inline would block the HTTP request for minutes on a
            # large NAS mount (#1299).

            # Extract gcode thumbnail
            if file_type == "gcode" and thumbnail_path is None:
                thumb_data = library.extract_gcode_thumbnail(filepath)
                if thumb_data:
                    thumb_dir = library.get_library_thumbnails_dir()
                    thumb_filename = f"{library.uuid.uuid4().hex}.png"
                    thumb_full = thumb_dir / thumb_filename  # SEC-PATH-OK: thumb_filename = uuid.uuid4().hex + ".png"
                    thumb_full.write_bytes(thumb_data)
                    thumbnail_path = library.to_relative_path(thumb_full)

            # Create thumbnail for image files
            if ext.lower() in library.IMAGE_EXTENSIONS and thumbnail_path is None:
                thumbnail_path_str = library.create_image_thumbnail(filepath, library.get_library_thumbnails_dir())
                if thumbnail_path_str:
                    thumbnail_path = library.to_relative_path(Path(thumbnail_path_str))

            db_file = LibraryFile(
                folder_id=target_folder_id,
                is_external=True,
                filename=filename,
                file_path=file_path_str,
                file_type=file_type,
                file_size=stat.st_size,
                file_hash=None,  # Skip hashing external files for performance
                thumbnail_path=thumbnail_path,
                file_metadata=library._without_print_name(file_metadata),
                fs_modified_at=fs_mtime,
            )
            db.add(db_file)
            added += 1

    # Remove DB entries for files that no longer exist on disk
    for path_str, db_file in existing_files.items():
        if path_str not in found_paths:
            # Clean up thumbnail if we generated one
            if db_file.thumbnail_path:
                try:
                    abs_thumb = library.to_absolute_path(db_file.thumbnail_path)
                    if abs_thumb and abs_thumb.exists():
                        abs_thumb.unlink()
                except OSError:
                    pass
            await db.delete(db_file)
            library.remove_library_photos_dir(db_file.id)
            removed += 1

    # Remove empty subfolders whose directories no longer exist on disk
    # Process deepest-first by sorting on path depth (descending)
    subfolder_entries = [(rel, fid) for rel, fid in folder_cache.items() if rel and fid != folder_id]
    subfolder_entries.sort(key=lambda x: x[0].count("/"), reverse=True)
    for rel_path, sub_fid in subfolder_entries:
        if rel_path in seen_rel_dirs:
            continue  # Directory still exists on disk
        # Check if subfolder has any remaining files
        file_count_result = await db.execute(
            select(func.count(LibraryFile.id)).where(
                LibraryFile.folder_id == sub_fid,
                LibraryFile.deleted_at.is_(None),
            )
        )
        if (file_count_result.scalar() or 0) == 0:
            # Check if it has any remaining child folders
            child_count_result = await db.execute(
                select(func.count(LibraryFolder.id)).where(LibraryFolder.parent_id == sub_fid)
            )
            if (child_count_result.scalar() or 0) == 0:
                sub_folder_result = await db.execute(select(LibraryFolder).where(LibraryFolder.id == sub_fid))
                sub_folder_obj = sub_folder_result.scalar_one_or_none()
                if sub_folder_obj:
                    await db.delete(sub_folder_obj)
                    folder_mtimes.pop(sub_fid, None)

    # Persist each visited folder's real directory mtime (#2680). Fetched in one
    # trip; folders deleted by the cleanup above were dropped from folder_mtimes.
    if folder_mtimes:
        folders_result = await db.execute(select(LibraryFolder).where(LibraryFolder.id.in_(list(folder_mtimes.keys()))))
        for folder_obj in folders_result.scalars().all():
            new_mtime = folder_mtimes.get(folder_obj.id)
            if new_mtime is not None and folder_obj.fs_modified_at != new_mtime:
                folder_obj.fs_modified_at = new_mtime

    if not external_types_repaired:
        db.add(Settings(key=repair_key, value="true"))
    await db.commit()

    # Spawn STL thumbnail backfill in the background — the scan endpoint
    # returns immediately so the FE modal closes and subdirectories are
    # visible right away; thumbnails fill in over the following seconds /
    # minutes as the task processes each STL file. Survives FE refresh —
    # the task lives in the FastAPI event loop, not the request scope.
    # folder_cache.values() covers the root + every pre-existing subfolder
    # + every subfolder created during this scan. all_folder_ids on its own
    # would miss the newly-created ones (it's snapshotted before the walk).
    library.spawn_background_task(
        library._backfill_external_stl_thumbnails(list(set(folder_cache.values()))),
        name=f"stl-backfill-folder-{folder_id}",
    )

    return {"status": "success", "added": added, "removed": removed}
