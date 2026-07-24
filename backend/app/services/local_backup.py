"""Scheduled local backup service.

Creates ZIP snapshots of the full PrintOps data (database + data directories)
on a configurable schedule with retention management.
"""

import asyncio
import json
import logging
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone, tzinfo
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from backend.app.core.config import settings as app_settings
from backend.app.core.database import async_session
from backend.app.models.settings import Settings

logger = logging.getLogger(__name__)


def _ruleset_manifest() -> dict:
    """Return the small, stable ruleset receipt stored with every full backup."""
    from backend.app.services.einvoice.validator import pinned_rule_versions

    versions = pinned_rule_versions()
    return {
        "schema_version": 1,
        "en16931": {"version": versions["en16931"]},
        "xrechnung": {"version": "3.0.2", "bundle_date": "2026-01-31"},
        "zugferd": {
            "version": versions["zugferd"],
            "factur_x_version": versions["factur_x"],
        },
    }


def stage_document_evidence(staging_dir: Path, data_dir: Path) -> None:
    """Stage external document evidence next to the database backup.

    Relational configuration, snapshots, audit events, reservations and receipts
    live in ``printops.db``. Assets, final PDFs, raw validation reports and e-invoice
    XML remain external and are copied with a canonical integrity manifest.
    """
    evidence_roots = {
        "document-artifacts": "einvoice",
        "document-layout-assets": "layout_asset",
        "document-render-artifacts": "rendered_pdf",
        "document-validation-reports": "validation_report",
    }
    entries: list[dict] = []
    for directory, evidence_type in evidence_roots.items():
        source_root = data_dir / directory
        target_root = staging_dir / directory
        if not source_root.is_dir():
            continue
        shutil.copytree(source_root, target_root, dirs_exist_ok=True)
        for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
            relative = source.relative_to(data_dir).as_posix()
            content = source.read_bytes()
            entry = {
                "path": relative,
                "type": evidence_type,
                "sha256": sha256(content).hexdigest(),
                "size": len(content),
                "business_profile_id": None,
                "document_id": None,
                "database_id": None,
                "database_sha256": None,
                "integrity_status": "valid",
            }
            entries.append(entry)

    backup_db = staging_dir / "printops.db"
    if backup_db.is_file():
        connection = sqlite3.connect(str(backup_db))
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            metadata: dict[str, tuple[int | None, int | None, int | None, str | None]] = {}
            if "document_artifacts" in tables:
                for artifact_id, document_id, storage_path, expected_hash in connection.execute(
                    "SELECT id, document_id, storage_path, sha256 FROM document_artifacts "
                    "WHERE storage_path IS NOT NULL"
                ):
                    metadata[str(storage_path).replace("\\", "/")] = (
                        None,
                        document_id,
                        artifact_id,
                        expected_hash,
                    )
            if "document_layout_assets" in tables:
                for asset_id, profile_id, storage_key, expected_hash in connection.execute(
                    "SELECT id, business_profile_id, storage_key, sha256 FROM document_layout_assets"
                ):
                    metadata[str(storage_key).replace("\\", "/")] = (
                        profile_id,
                        None,
                        asset_id,
                        expected_hash,
                    )
            for entry in entries:
                profile_id, document_id, database_id, database_sha256 = metadata.get(
                    entry["path"],
                    (None, None, None, None),
                )
                entry.update(
                    business_profile_id=profile_id,
                    document_id=document_id,
                    database_id=database_id,
                    database_sha256=database_sha256,
                    integrity_status=(
                        "valid"
                        if database_sha256 is None or database_sha256 == entry["sha256"]
                        else "invalid"
                    ),
                )
        finally:
            connection.close()

    evidence_dir = staging_dir / "document-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "ruleset-manifest.json").write_text(
        json.dumps(_ruleset_manifest(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (evidence_dir / "document-layout-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "integrity_status": (
                    "valid"
                    if all(entry["integrity_status"] == "valid" for entry in entries)
                    else "invalid"
                ),
                "file_count": len(entries),
                "counts_by_type": {
                    evidence_type: sum(entry["type"] == evidence_type for entry in entries)
                    for evidence_type in sorted({entry["type"] for entry in entries})
                },
                "files": entries,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def verify_restored_document_artifacts(
    backup_root: Path,
    backup_db: Path,
    *,
    destination_root: Path | None = None,
) -> list[dict]:
    """Verify artifact bytes before restore and downgrade broken evidence.

    Older backups may predate the document tables and remain restorable. For a
    document-aware backup, every external artifact is hash checked. A missing,
    unsafe or corrupt artifact is recorded in its validation report and can never
    remain marked ``valid`` after restore.
    """
    issues: list[dict] = []
    root = backup_root.resolve()
    evidence_manifest = backup_root / "document-evidence" / "document-layout-manifest.json"
    if evidence_manifest.is_file():
        payload = json.loads(evidence_manifest.read_text(encoding="utf-8"))
        for entry in payload.get("files", []):
            relative = Path(str(entry.get("path") or ""))
            candidate = (backup_root / relative).resolve()
            code = None
            actual_hash = None
            if relative.is_absolute() or not candidate.is_relative_to(root):
                code = "manifest_path_unsafe"
            elif not candidate.is_file():
                code = "manifest_file_missing"
            else:
                content = candidate.read_bytes()
                actual_hash = sha256(content).hexdigest()
                if actual_hash != entry.get("sha256") or len(content) != entry.get("size"):
                    code = "manifest_hash_mismatch"
                elif entry.get("database_sha256") and actual_hash != entry["database_sha256"]:
                    code = "manifest_database_hash_mismatch"
                elif destination_root is not None:
                    destination_base = destination_root.resolve()
                    destination = (destination_base / relative).resolve()
                    if destination.is_relative_to(destination_base) and destination.is_file():
                        destination_hash = sha256(destination.read_bytes()).hexdigest()
                        if destination_hash != actual_hash:
                            code = "restore_destination_conflict"
            if code:
                issues.append(
                    {
                        "artifact_id": entry.get("database_id"),
                        "code": code,
                        "storage_path": entry.get("path"),
                        "expected_sha256": entry.get("sha256"),
                        "actual_sha256": actual_hash,
                        "evidence_type": entry.get("type"),
                    }
                )
    connection = sqlite3.connect(str(backup_db))
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        for issue in list(issues):
            database_id = issue.get("artifact_id")
            if issue.get("evidence_type") == "layout_asset" and database_id is not None and "document_layout_assets" in tables:
                connection.execute(
                    "UPDATE document_layout_assets SET preflight_status = 'invalid', preflight_report = ? WHERE id = ?",
                    (json.dumps({"restore_integrity": issue}, ensure_ascii=False), database_id),
                )
            elif database_id is not None and "document_artifacts" in tables:
                row = connection.execute(
                    "SELECT validation_report FROM document_artifacts WHERE id = ?",
                    (database_id,),
                ).fetchone()
                if row is not None:
                    try:
                        report = json.loads(row[0]) if isinstance(row[0], str) else dict(row[0] or {})
                    except (TypeError, ValueError):
                        report = {}
                    report.update(valid=False, restore_integrity=issue)
                    connection.execute(
                        "UPDATE document_artifacts SET validation_status = 'invalid', validation_report = ? WHERE id = ?",
                        (json.dumps(report, ensure_ascii=False), database_id),
                    )
        if any(item.get("evidence_type") == "validation_report" for item in issues) and "document_artifacts" in tables:
            connection.execute(
                "UPDATE document_artifacts SET validation_status = 'invalid' WHERE kind = 'pdf'"
            )
        if "document_artifacts" not in tables:
            connection.commit()
            return issues
        rows = connection.execute(
            "SELECT id, storage_path, content, sha256, validation_report "
            "FROM document_artifacts ORDER BY id"
        ).fetchall()
        for artifact_id, storage_path, content, expected_hash, raw_report in rows:
            code = None
            actual_hash = None
            if storage_path:
                candidate = (backup_root / storage_path).resolve()
                if not candidate.is_relative_to(root):
                    code = "artifact_path_unsafe"
                elif not candidate.is_file():
                    code = "artifact_file_missing"
                else:
                    actual_hash = sha256(candidate.read_bytes()).hexdigest()
                    if actual_hash != expected_hash:
                        code = "artifact_hash_mismatch"
            elif content is not None:
                actual_hash = sha256(content).hexdigest()
                if actual_hash != expected_hash:
                    code = "artifact_hash_mismatch"
            else:
                code = "artifact_content_missing"

            if code is None:
                continue
            issue = {
                "artifact_id": artifact_id,
                "code": code,
                "storage_path": storage_path,
                "expected_sha256": expected_hash,
                "actual_sha256": actual_hash,
            }
            issues.append(issue)
            try:
                report = json.loads(raw_report) if isinstance(raw_report, str) else dict(raw_report or {})
            except (TypeError, ValueError):
                report = {}
            report["valid"] = False
            report["restore_integrity"] = issue
            connection.execute(
                "UPDATE document_artifacts SET validation_status = 'invalid', validation_report = ? WHERE id = ?",
                (json.dumps(report, ensure_ascii=False), artifact_id),
            )
        connection.commit()
    finally:
        connection.close()
    return issues


def restore_document_evidence_files(
    backup_root: Path,
    destination_root: Path,
    issues: list[dict],
) -> dict:
    """Atomically restore manifest files without overwriting different evidence."""
    manifest_path = backup_root / "document-evidence" / "document-layout-manifest.json"
    if not manifest_path.is_file():
        return {
            "status": "legacy",
            "total": 0,
            "restored": 0,
            "unchanged": 0,
            "conflicts": 0,
            "invalid": len(issues),
        }

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    backup_base = backup_root.resolve()
    destination_base = destination_root.resolve()
    restored = 0
    unchanged = 0
    conflicts = 0

    def write_atomically(target: Path, content: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".restore-", dir=target.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    for entry in manifest.get("files", []):
        relative = Path(str(entry.get("path") or ""))
        source = (backup_base / relative).resolve()
        destination = (destination_base / relative).resolve()
        if (
            relative.is_absolute()
            or not source.is_relative_to(backup_base)
            or not destination.is_relative_to(destination_base)
            or not source.is_file()
        ):
            continue
        content = source.read_bytes()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_file():
            if sha256(destination.read_bytes()).hexdigest() == sha256(content).hexdigest():
                unchanged += 1
                continue
            conflicts += 1
            conflict_target = (
                destination_base
                / "document-restore-conflicts"
                / sha256(content).hexdigest()
                / relative.name
            )
            if not conflict_target.exists():
                write_atomically(conflict_target, content)
            continue
        write_atomically(destination, content)
        restored += 1

    invalid = len(issues)
    return {
        "status": "invalid" if invalid else "valid",
        "total": len(manifest.get("files", [])),
        "restored": restored,
        "unchanged": unchanged,
        "conflicts": conflicts,
        "invalid": invalid,
        "counts_by_type": manifest.get("counts_by_type", {}),
    }


def _local_zone() -> tzinfo:
    """Resolve the local timezone for scheduled-backup HH:MM interpretation.

    Uses the container's ``TZ`` env var (the same value the support package
    surfaces); falls back to UTC when unset or unrecognised so a missing TZ
    keeps the legacy behaviour rather than crashing. See #1602 follow-up.

    On Windows the embedded Python in our installer doesn't carry an IANA
    tz database, so ``ZoneInfo(...)`` — including ``ZoneInfo("UTC")`` —
    raises ``ZoneInfoNotFoundError`` unless the ``tzdata`` PyPI package is
    installed. requirements.txt now pins ``tzdata`` on win32, but to keep
    this resilient on installs that haven't refreshed deps we fall through
    to the stdlib ``datetime.timezone.utc`` as a last resort; it satisfies
    every ``astimezone`` / ``str()`` call site without needing the IANA DB.
    """
    tz_name = os.environ.get("TZ", "").strip()
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            logger.warning("Unrecognised TZ env value %r, scheduling in UTC", tz_name)
    try:
        return ZoneInfo("UTC")
    except ZoneInfoNotFoundError:
        return timezone.utc


SCHEDULE_INTERVALS = {
    "hourly": 3600,
    "daily": 86400,
    "weekly": 604800,
}


def _default_backup_dir() -> Path:
    return app_settings.base_dir / "backups"


class LocalBackupService:
    """Manages scheduled local backup snapshots with retention."""

    def __init__(self):
        self._scheduler_task: asyncio.Task | None = None
        self._check_interval = 60
        self._running: bool = False
        self._last_backup_at: str | None = None
        self._last_status: str | None = None
        self._last_message: str | None = None
        self._next_run: datetime | None = None

    async def start_scheduler(self):
        """Start the background scheduler loop."""
        if self._scheduler_task is not None:
            return
        logger.info("Starting local backup scheduler")
        # Seed next_run from settings so the first check has a target
        await self._seed_next_run()
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

    def stop_scheduler(self):
        """Stop the scheduler."""
        if self._scheduler_task:
            self._scheduler_task.cancel()
            self._scheduler_task = None
            logger.info("Stopped local backup scheduler")

    async def _scheduler_loop(self):
        """Main scheduler loop — checks for due backups every minute."""
        while True:
            try:
                await asyncio.sleep(self._check_interval)
                await self._check_scheduled_backup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in local backup scheduler: %s", e)
                await asyncio.sleep(60)

    async def _seed_next_run(self):
        """Load settings and calculate initial next_run."""
        try:
            settings = await self._load_settings()
            if settings.get("enabled"):
                self._next_run = self._calculate_next_run(
                    settings.get("schedule", "daily"),
                    settings.get("time", "03:00"),
                )
        except Exception as e:
            logger.debug("Could not seed local backup next_run: %s", e)

    async def _load_settings(self) -> dict:
        """Read local backup settings from the DB."""
        async with async_session() as db:
            keys = [
                "local_backup_enabled",
                "local_backup_schedule",
                "local_backup_time",
                "local_backup_retention",
                "local_backup_path",
            ]
            result = await db.execute(select(Settings).where(Settings.key.in_(keys)))
            rows = {r.key: r.value for r in result.scalars().all()}
        return {
            "enabled": rows.get("local_backup_enabled", "false").lower() == "true",
            "schedule": rows.get("local_backup_schedule", "daily"),
            "time": rows.get("local_backup_time", "03:00"),
            "retention": int(rows.get("local_backup_retention", "5")),
            "path": rows.get("local_backup_path", ""),
        }

    async def _check_scheduled_backup(self):
        """Check if a scheduled backup is due and run it."""
        settings = await self._load_settings()
        if not settings["enabled"]:
            self._next_run = None
            return

        now = datetime.now(timezone.utc)

        # If no next_run set, schedule one
        if self._next_run is None:
            self._next_run = self._calculate_next_run(settings["schedule"], settings["time"])
            return

        if self._next_run <= now:
            logger.info("Running scheduled local backup")
            await self.run_backup(settings)
            self._next_run = self._calculate_next_run(settings["schedule"], settings["time"])

    def _calculate_next_run(self, schedule_type: str, time_str: str = "03:00") -> datetime:
        """Calculate the next scheduled run time.

        For hourly: next full hour (timezone-agnostic).
        For daily/weekly: next occurrence of the configured HH:MM, interpreted
        in the container's local timezone (TZ env var, UTC fallback). Returns
        a UTC-aware datetime for storage / comparison against ``now``.
        """
        now_utc = datetime.now(timezone.utc)

        if schedule_type == "hourly":
            # Next full hour
            next_run = now_utc.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            return next_run

        # Parse HH:MM time
        try:
            parts = time_str.strip().split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        except (ValueError, IndexError):
            hour, minute = 3, 0

        local_tz = _local_zone()
        now_local = now_utc.astimezone(local_tz)
        # Next occurrence of HH:MM local time, today or tomorrow.
        # ``fold=0`` resolves the ambiguous wall-clock window at DST fall-back
        # to the earlier instance (consistent with cron's behaviour). On the
        # spring-forward gap the synthesized local time will normalise to the
        # next valid instant when converted to UTC.
        next_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0, fold=0)
        if next_local <= now_local:
            next_local += timedelta(days=1)

        if schedule_type == "weekly":
            next_local += timedelta(weeks=1)

        return next_local.astimezone(timezone.utc)

    def _resolve_backup_dir(self, path_setting: str) -> Path:
        """Resolve the backup output directory from settings."""
        if path_setting.strip():
            return Path(path_setting.strip())
        return _default_backup_dir()

    async def run_backup(self, settings: dict | None = None) -> dict:
        """Run a backup now. Returns {success, message, filename}."""
        if self._running:
            return {"success": False, "message": "Backup already in progress"}

        self._running = True
        try:
            if settings is None:
                settings = await self._load_settings()

            backup_dir = self._resolve_backup_dir(settings["path"])
            backup_dir.mkdir(parents=True, exist_ok=True)

            from backend.app.api.routes.settings import create_backup_zip

            zip_path, filename = await create_backup_zip(output_path=backup_dir)

            # Prune old backups
            retention = max(1, settings["retention"])
            self._prune_backups(backup_dir, retention)

            self._last_backup_at = datetime.now(timezone.utc).isoformat()
            self._last_status = "success"
            self._last_message = filename
            logger.info("Local backup created: %s", zip_path)
            return {"success": True, "message": "Backup created", "filename": filename}

        except Exception as e:
            self._last_backup_at = datetime.now(timezone.utc).isoformat()
            self._last_status = "failed"
            self._last_message = str(e)
            logger.error("Local backup failed: %s", e, exc_info=True)
            return {"success": False, "message": f"Backup failed: {e}"}
        finally:
            self._running = False

    def _prune_backups(self, backup_dir: Path, retention: int):
        """Delete oldest backups exceeding the retention count."""
        backups = sorted(
            backup_dir.glob("printops-backup-*.zip"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_backup in backups[retention:]:
            try:
                old_backup.unlink()
                logger.info("Pruned old backup: %s", old_backup.name)
            except OSError as e:
                logger.warning("Could not delete old backup %s: %s", old_backup.name, e)

    def get_status(self) -> dict:
        """Return current scheduler status."""
        return {
            "is_running": self._running,
            "last_backup_at": self._last_backup_at,
            "last_status": self._last_status,
            "last_message": self._last_message,
            "next_run": self._next_run.isoformat() if self._next_run else None,
        }

    def resolve_backup_file(self, path_setting: str, filename: str) -> Path | None:
        """Resolve a backup filename to a full path, with safety checks."""
        if "/" in filename or "\\" in filename or ".." in filename:
            return None
        if not filename.startswith("printops-backup-") or not filename.endswith(".zip"):
            return None
        backup_dir = self._resolve_backup_dir(path_setting)
        target = (
            backup_dir / filename
        )  # SEC-PATH-OK: filename rejected above on /, \\, .., plus startswith "printops-backup-" + endswith ".zip" gate
        if not target.exists():
            return None
        return target

    def list_backups(self, path_setting: str) -> list[dict]:
        """List backup ZIP files in the backup directory."""
        backup_dir = self._resolve_backup_dir(path_setting)
        if not backup_dir.exists():
            return []

        backups = []
        for f in sorted(backup_dir.glob("printops-backup-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
            stat = f.stat()
            backups.append(
                {
                    "filename": f.name,
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                }
            )
        return backups

    def delete_backup(self, path_setting: str, filename: str) -> dict:
        """Delete a specific backup file. Returns {success, message}."""
        # Path traversal protection
        if "/" in filename or "\\" in filename or ".." in filename:
            return {"success": False, "message": "Invalid filename"}

        backup_dir = self._resolve_backup_dir(path_setting)
        target = (
            backup_dir / filename
        )  # SEC-PATH-OK: filename rejected above on /, \\, .., plus startswith "printops-backup-" + endswith ".zip" gate below

        if not target.exists():
            return {"success": False, "message": "Backup not found"}
        if not target.name.startswith("printops-backup-") or not target.name.endswith(".zip"):
            return {"success": False, "message": "Invalid backup file"}

        try:
            target.unlink()
            return {"success": True, "message": "Backup deleted"}
        except OSError as e:
            return {"success": False, "message": f"Could not delete: {e}"}


local_backup_service = LocalBackupService()
