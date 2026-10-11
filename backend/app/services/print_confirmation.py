"""Inspection of a single print run, without stock or delivery side effects."""

import asyncio
import hashlib
import secrets
import weakref
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.archive import PrintArchive
from backend.app.models.commerce import CustomerOrder
from backend.app.models.print_batch import PrintBatchPlate
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.print_queue import PrintQueueItem

_locks: weakref.WeakValueDictionary[int, asyncio.Lock] = weakref.WeakValueDictionary()
TOKEN_LIFETIME = timedelta(hours=48)


class OutcomeConflict(ValueError):
    pass


@asynccontextmanager
async def outcome_lock(db: AsyncSession, archive_id: int, run_id: int | None = None):
    lock = _locks.get(archive_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[archive_id] = lock
    async with lock:
        if db.get_bind().dialect.name == "postgresql":
            await db.execute(text("SELECT pg_advisory_xact_lock(1898, :id)"), {"id": archive_id})
            # The ordinary print-start callback updates this same row. A row lock
            # makes a concurrent start reset quality after our commit, rather
            # than letting a stale inspection overwrite the active run's mirror.
            await db.execute(select(PrintArchive.id).where(PrintArchive.id == archive_id).with_for_update())
        from backend.app.services.print_batch import batch_dispatch_lock

        run = await db.get(PrintLogEntry, run_id) if run_id is not None else await latest_run(db, archive_id)
        batch_id = (
            await db.scalar(select(PrintQueueItem.batch_id).where(PrintQueueItem.id == run.queue_item_id))
            if run and run.queue_item_id
            else None
        )
        if batch_id is None:
            yield
        else:
            # Hold this through the caller's commit. Dispatch must observe the
            # new inspection before deciding how many replacement runs are owed.
            async with batch_dispatch_lock(db, batch_id):
                yield


async def initialize_queue_outcome(db: AsyncSession, item: PrintQueueItem, archive: PrintArchive) -> None:
    """Flag only newly dispatched production; historical rows retain legacy behavior."""
    production = False
    if item.batch_id is not None:
        production = bool(
            await db.scalar(select(PrintBatchPlate.id).where(PrintBatchPlate.batch_id == item.batch_id).limit(1))
        )
    if item.project_id is not None:
        production = production or bool(
            await db.scalar(select(CustomerOrder.id).where(CustomerOrder.project_id == item.project_id).limit(1))
        )
    # Production requires inspection even when a caller omitted the optional toggle.
    item.confirm_outcome = bool(item.confirm_outcome or production)
    archive.confirm_requested = item.confirm_outcome
    if item.expected_parts is None:
        item.expected_parts = max(1, archive.quantity or 1)
    archive.quantity = item.expected_parts


def reset_current_outcome(archive: PrintArchive) -> None:
    """Reprints clear the display mirror, never the earlier run's quality record."""
    for field in ("user_verdict", "good_quantity", "reject_quantity", "user_verdict_source", "user_verdict_at"):
        setattr(archive, field, None)


async def latest_run(db: AsyncSession, archive_id: int) -> PrintLogEntry | None:
    return await db.scalar(
        select(PrintLogEntry).where(PrintLogEntry.archive_id == archive_id).order_by(PrintLogEntry.id.desc()).limit(1)
    )


def run_matches_archive(run: PrintLogEntry, archive: PrintArchive) -> bool:
    # A reused archive already starting its next run must not accept the old link.
    if archive.status != "completed" or run.status != "completed" or archive.deleted_at is not None:
        return False
    if archive.started_at is not None:
        if run.started_at is None:
            return False
        return run.started_at.replace(tzinfo=None) == archive.started_at.replace(tzinfo=None)
    return True


async def record_outcome(
    db: AsyncSession,
    archive: PrintArchive,
    *,
    run_id: int,
    good_quantity: int,
    reject_quantity: int,
    source: str,
    failure_reason: str | None = None,
    token_hash: str | None = None,
    historical: bool = False,
) -> PrintLogEntry:
    """Write an inspection atomically; notification capabilities are first-answer-only.

    Caller holds outcome_lock and commits before releasing it. Authenticated
    operators can correct a run by submitting its explicit id. Historical
    inspections update only that log row unless it is still the current run.
    """
    current = await latest_run(db, archive.id)
    run = await db.get(PrintLogEntry, run_id) if historical else current
    if run is None or run.archive_id != archive.id or run.id != run_id or run.status != "completed":
        raise OutcomeConflict("This print has changed; reload the current run before confirming")
    is_current = current is not None and run.id == current.id and run_matches_archive(run, archive)
    if not historical and not is_current:
        raise OutcomeConflict("This print has changed; reload the current run before confirming")
    if good_quantity < 0 or reject_quantity < 0 or good_quantity + reject_quantity != run.quantity:
        raise OutcomeConflict(f"Good and rejected quantities must total the intended {run.quantity} parts")
    verdict = "good" if reject_quantity == 0 else "reject" if good_quantity == 0 else "mixed"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    current_archive = select(PrintArchive.id).where(
        PrintArchive.id == archive.id,
        PrintArchive.deleted_at.is_(None),
    )
    conditions = [
        PrintLogEntry.id == run.id,
        PrintLogEntry.archive_id == archive.id,
        PrintLogEntry.status == "completed",
    ]
    if not historical:
        current_archive = current_archive.where(PrintArchive.status == "completed")
        if run.started_at is not None:
            current_archive = current_archive.where(PrintArchive.started_at == run.started_at)
        newest_id = select(func.max(PrintLogEntry.id)).where(PrintLogEntry.archive_id == archive.id).scalar_subquery()
        conditions.append(PrintLogEntry.id == newest_id)
    conditions.append(current_archive.exists())
    if token_hash is not None:
        conditions.extend(
            [
                PrintLogEntry.confirm_requested.is_(True),
                PrintLogEntry.confirm_token_hash == token_hash,
                PrintLogEntry.confirm_token_used_at.is_(None),
                PrintLogEntry.confirm_token_expires_at > now,
                PrintLogEntry.good_quantity.is_(None),
            ]
        )
    values = {
        "good_quantity": good_quantity,
        "reject_quantity": reject_quantity,
        "user_verdict": verdict,
        "user_verdict_source": source,
        "user_verdict_at": now,
        "confirm_token_used_at": now,
    }
    if failure_reason is not None:
        values["failure_reason"] = failure_reason
    result = await db.execute(update(PrintLogEntry).where(*conditions).values(**values))
    if result.rowcount != 1:
        raise OutcomeConflict("This confirmation link was already answered or has expired")
    await db.refresh(run)
    if is_current:
        for field in ("user_verdict", "good_quantity", "reject_quantity", "user_verdict_source", "user_verdict_at"):
            setattr(archive, field, getattr(run, field))
        if failure_reason is not None:
            archive.failure_reason = failure_reason
    await db.flush()
    if run.queue_item_id is not None:
        from backend.app.services.print_batch import refresh_batch_status_for_item

        await refresh_batch_status_for_item(db, run.queue_item_id)
    return run


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_confirmation_token(db: AsyncSession, archive: PrintArchive, *, run_id: int | None = None) -> str | None:
    run = await latest_run(db, archive.id)
    if run_id is not None and (run is None or run.id != run_id):
        return None
    if not run or not run.confirm_requested or run.good_quantity is not None or not run_matches_archive(run, archive):
        return None
    if run.confirm_token_hash is not None and run.confirm_token_expires_at is not None:
        if run.confirm_token_expires_at.replace(tzinfo=None) > datetime.now(timezone.utc).replace(tzinfo=None):
            return None  # Duplicate completion callback must not retire sent buttons.
    token = secrets.token_urlsafe(32)
    run.confirm_token_hash = token_digest(token)
    run.confirm_token_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + TOKEN_LIFETIME
    run.confirm_token_used_at = None
    await db.flush()
    return token


async def find_token_run(db: AsyncSession, token: str) -> tuple[PrintArchive, PrintLogEntry] | None:
    # Bound invalid-input work and do an indexed digest lookup. Tokens never grant
    # access to archive files, ownership changes, API scopes, stock or shipment.
    if len(token) != 43 or not all(c.isalnum() or c in "-_" for c in token):
        return None
    run = await db.scalar(select(PrintLogEntry).where(PrintLogEntry.confirm_token_hash == token_digest(token)))
    if not run or run.archive_id is None or not run.confirm_requested:
        return None
    archive = await db.get(PrintArchive, run.archive_id)
    current = await latest_run(db, run.archive_id)
    if not archive or not current or current.id != run.id or not run_matches_archive(run, archive):
        return None
    expiry = run.confirm_token_expires_at
    if expiry is None or expiry.replace(tzinfo=None) <= datetime.now(timezone.utc).replace(tzinfo=None):
        return None
    return archive, run


async def confirmed_production(db: AsyncSession, project_id: int, *, printer_ids: list[int] | None = None) -> dict:
    """Separate project production progress; never marks an order delivered."""
    conditions = [PrintLogEntry.project_id == project_id, PrintLogEntry.status == "completed"]
    if printer_ids is not None:
        conditions.append(PrintLogEntry.printer_id.in_(printer_ids))
    good, reject, pending = (
        await db.execute(
            select(
                func.coalesce(func.sum(PrintLogEntry.good_quantity), 0),
                func.coalesce(func.sum(PrintLogEntry.reject_quantity), 0),
                func.count(PrintLogEntry.id).filter(
                    PrintLogEntry.confirm_requested.is_(True), PrintLogEntry.good_quantity.is_(None)
                ),
            ).where(*conditions)
        )
    ).one()
    return {"good_quantity": int(good), "reject_quantity": int(reject), "unconfirmed_runs": int(pending)}


async def send_outcome_confirmation_hint(db: AsyncSession, archive_id: int, run_id: int, printer_id: int) -> bool:
    """Ask the owner about this completed run, even while its archive is reused.

    This carries no capability. The dialog's historical-run endpoint still
    checks current ownership, printer scope, and update permission on submit.
    """
    from backend.app.core.auth import is_auth_enabled, user_can_access_printer
    from backend.app.core.websocket import ws_manager
    from backend.app.models.user import User

    archive = await db.get(PrintArchive, archive_id, populate_existing=True)
    run = await db.get(PrintLogEntry, run_id)
    if (
        archive is None or archive.deleted_at is not None or run is None or run.archive_id != archive_id
        or run.printer_id != printer_id or run.status != "completed" or not run.confirm_requested
        or run.good_quantity is not None
    ):
        return False
    if await is_auth_enabled(db):
        # Ownerless prints remain available to authorized admins through the
        # archive UI; never fan their private metadata out to every connection.
        if archive.created_by_id is None:
            return False
        owner = await db.get(User, archive.created_by_id)
        if (
            owner is None or not owner.is_active or not user_can_access_printer(owner, printer_id)
            or not user_can_access_printer(owner, archive.printer_id)
        ):
            return False
    await ws_manager.broadcast_to_user(archive.created_by_id, {
        "type": "print_confirm_request", "printer_id": printer_id,
        "data": {"archive_id": archive_id, "run_id": run.id,
                 "print_name": run.print_name or archive.print_name or archive.filename},
    })
    return True


async def dispatch_outcome_confirmation(
    db: AsyncSession, archive_id: int, printer_id: int, printer_name: str,
    *, run_id: int | None = None, notify_user: bool = True,
) -> bool:
    """Prompt this run once; only the matching current run receives public actions."""
    from backend.app.api.routes.settings import get_setting
    from backend.app.services.notification_service import notification_service

    async with outcome_lock(db, archive_id, run_id):
        # Provider awaits may leave this session holding the previous mirror.
        archive = await db.get(PrintArchive, archive_id, populate_existing=True)
        if archive is None or archive.deleted_at is not None:
            return False
        current = await latest_run(db, archive_id)
        run = await db.get(PrintLogEntry, run_id, populate_existing=True) if run_id is not None else current
        if (
            run is None or run.archive_id != archive_id or run.printer_id != printer_id
            or run.status != "completed" or not run.confirm_requested or run.good_quantity is not None
            or run.confirm_prompted_at is not None
        ):
            return False
        is_current = current is not None and current.id == run.id and run_matches_archive(run, archive)
        token = None
        if is_current:
            token = await issue_confirmation_token(db, archive, run_id=run.id)
            if token is None:
                return False  # Keep already-sent current-run buttons valid.
        elif run_id is None:
            return False  # Historical requests require the concrete completed run.
        # Claim external prompting atomically, independently of token issuance.
        # Historical prompts never manufacture or reuse a public capability.
        live_archive = select(PrintArchive.id).where(
            PrintArchive.id == archive_id, PrintArchive.deleted_at.is_(None),
        )
        if is_current:
            live_archive = live_archive.where(PrintArchive.status == "completed")
            if run.started_at is not None:
                live_archive = live_archive.where(PrintArchive.started_at == run.started_at)
        claimed = await db.execute(update(PrintLogEntry).where(
            PrintLogEntry.id == run.id, PrintLogEntry.archive_id == archive_id,
            PrintLogEntry.printer_id == printer_id, PrintLogEntry.status == "completed",
            PrintLogEntry.confirm_requested.is_(True), PrintLogEntry.good_quantity.is_(None),
            PrintLogEntry.confirm_prompted_at.is_(None), live_archive.exists(),
        ).values(confirm_prompted_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        if claimed.rowcount != 1:
            await db.rollback()
            return False
        payload = {"archive_id": archive_id, "run_id": run.id,
                   "print_name": run.print_name or archive.print_name or archive.filename}
        await db.commit()
    if notify_user:
        await send_outcome_confirmation_hint(db, archive_id, payload["run_id"], printer_id)
    base = (await get_setting(db, "external_url") or "").rstrip("/")
    urls = {}
    if token is not None and base.startswith(("https://", "http://")):
        urls = {verdict: f"{base}/api/v1/archives/outcome-link/{token}/{verdict}" for verdict in ("good", "reject")}
    await notification_service.on_print_confirm_request(
        printer_id,
        printer_name,
        db,
        print_name=payload["print_name"],
        confirm_url=f"{base}/archives?confirm={archive_id}&confirm_run={payload['run_id']}",
        outcome_urls=urls,
    )
    return True
