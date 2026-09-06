"""Idempotently complete file-less print archives when their 3MF arrives later."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.websocket import ws_manager
from backend.app.models.active_print_session import ActivePrintSession
from backend.app.models.archive import PrintArchive
from backend.app.services.archive import ArchiveService
from backend.app.services.threemf_identity import (
    candidate_3mf_conflict,
    expected_plate_from_paths,
    normalized_model_name,
)

logger = logging.getLogger(__name__)
_recovery_locks: dict[int, asyncio.Lock] = {}


def fallback_print_name(filename: str | None, subtask_name: str | None) -> str:
    """Return the best display identity available without a 3MF."""
    raw = subtask_name or filename
    if not raw:
        return "Unknown Print"
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    for suffix in (".gcode.3mf", ".gcode", ".3mf"):
        if name.casefold().endswith(suffix):
            return name[: -len(suffix)]
    return name


def fallback_print_time(data: dict) -> int | None:
    """Recover the printer's remaining-time estimate for a file-less row."""
    remaining = data.get("remaining_time")
    if isinstance(remaining, (int, float)) and not isinstance(remaining, bool) and remaining > 0:
        return int(remaining)
    raw_data = data.get("raw_data")
    remaining_minutes = raw_data.get("mc_remaining_time") if isinstance(raw_data, dict) else None
    if isinstance(remaining_minutes, (int, float)) and not isinstance(remaining_minutes, bool):
        return int(remaining_minutes * 60) if remaining_minutes > 0 else None
    return None


def _archive_identity_names(archive: PrintArchive) -> tuple[str | None, ...]:
    extra = archive.extra_data or {}
    print_data = extra.get("_print_data") if isinstance(extra.get("_print_data"), dict) else {}
    return (
        archive.filename,
        archive.print_name,
        extra.get("original_subtask"),
        print_data.get("filename"),
        print_data.get("subtask_name"),
    )


def _identity_matches(archive: PrintArchive, candidate_name: str) -> bool:
    candidate = normalized_model_name(candidate_name)
    if candidate is None:
        return False
    return candidate in {
        normalized
        for value in _archive_identity_names(archive)
        if isinstance(value, str) and (normalized := normalized_model_name(value)) is not None
    }


async def try_recover_fallback_archive(
    db: AsyncSession,
    printer_id: int,
    candidate_name: str,
    candidate_path: Path,
) -> PrintArchive | None:
    """Complete the matching fallback row, or return ``None`` safely.

    Positive contradictions reject the candidate. Missing plate or mapping
    evidence remains unknown and never gets invented.
    """
    lock = _recovery_locks.setdefault(printer_id, asyncio.Lock())
    async with lock:
        result = await db.execute(
            select(PrintArchive)
            .where(
                PrintArchive.printer_id == printer_id,
                PrintArchive.status == "printing",
                PrintArchive.deleted_at.is_(None),
                PrintArchive.file_path == "",
            )
            .order_by(PrintArchive.created_at.desc(), PrintArchive.id.desc())
        )
        matches = [archive for archive in result.scalars().all() if _identity_matches(archive, candidate_name)]
        if len(matches) != 1:
            if len(matches) > 1:
                logger.warning(
                    "Fallback recovery for printer %s is ambiguous across archives %s",
                    printer_id,
                    [archive.id for archive in matches],
                )
            return None

        archive = matches[0]
        session = await db.get(ActivePrintSession, printer_id)
        stored_print_data = (archive.extra_data or {}).get("_print_data") or {}
        if not isinstance(stored_print_data, dict):
            stored_print_data = {}
        expected_plate = session.plate_id if session is not None else None
        if expected_plate is None:
            expected_plate = expected_plate_from_paths(
                stored_print_data.get("filename"),
                archive.filename,
            )
        ams_mapping = (
            session.ams_mapping
            if session is not None and session.ams_mapping is not None
            else stored_print_data.get("ams_mapping")
        )

        conflict = candidate_3mf_conflict(
            candidate_path,
            expected_plate=expected_plate,
            ams_mapping=ams_mapping,
        )
        if conflict:
            logger.warning(
                "Rejected 3MF %s for fallback archive %s: %s",
                candidate_path,
                archive.id,
                conflict,
            )
            return None

        recovered = await ArchiveService(db).archive_print(
            printer_id=printer_id,
            source_file=candidate_path,
            print_data=stored_print_data,
            original_filename=Path(candidate_name).name,
            plate_id=expected_plate,
            update_archive_id=archive.id,
        )
        if recovered is not None:
            logger.info("Completed fallback archive %s from later 3MF %s", archive.id, candidate_path)
            try:
                await ws_manager.send_archive_updated({"id": archive.id, "file_recovered": True})
            except Exception as exc:
                logger.warning("Could not broadcast recovered archive %s: %s", archive.id, exc)
        return recovered


def _cached_3mf_filename(raw_name: str) -> str | None:
    """Return a safe, extension-bearing archive name for a cache alias."""
    name = raw_name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name:
        return None
    lower = name.casefold()
    if lower.endswith((".gcode.3mf", ".3mf")):
        return name
    if lower.endswith(".gcode"):
        return f"{name}.3mf"
    return f"{name}.gcode.3mf"


async def recover_cached_fallback_archive(printer_id: int, data: dict) -> PrintArchive | None:
    """Offer print-start cache bytes to recovery before completion evicts them."""
    from backend.app.core.database import async_session
    from backend.app.services.bambu_ftp import get_cached_3mf

    try:
        names = [data.get("subtask_name"), data.get("filename")]
        attempted_paths: set[Path] = set()
        for raw_name in names:
            if not isinstance(raw_name, str) or not raw_name:
                continue
            candidate_name = _cached_3mf_filename(raw_name)
            if candidate_name is None:
                continue
            basename = raw_name.replace("\\", "/").rsplit("/", 1)[-1]
            for lookup_name in dict.fromkeys((raw_name, basename, candidate_name)):
                candidate = get_cached_3mf(printer_id, lookup_name)
                if candidate is None or candidate in attempted_paths:
                    continue
                attempted_paths.add(candidate)
                async with async_session() as db:
                    recovered = await try_recover_fallback_archive(db, printer_id, candidate_name, candidate)
                    if recovered is not None:
                        return recovered
    except Exception as exc:
        logger.warning("Fallback archive recovery from cache failed: %s", exc)
    return None
