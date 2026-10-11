"""Bounded ownership of heater targets set by queue preheating.

A durable intent is written before heating. Unknown/offline recovery retains
that intent and prevents automated power cuts until rollback can be verified.
"""

import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from backend.app.core.config import settings

logger = logging.getLogger(__name__)
_ACTIVE = frozenset({"PREPARE", "SLICING", "RUNNING", "PAUSE"})
_IDLE = frozenset({"IDLE", "FINISH", "FAILED"})
_current: ContextVar["PreheatLease | None"] = ContextVar("preheat_lease", default=None)


class _PlateClearRequired(Exception):
    """A newer completed print requires acknowledgment before publication."""


@dataclass
class PreheatLease:
    owner: "PreheatOwnership"
    printer_id: int
    item_id: int
    manager: object
    task: asyncio.Task | None = None
    targets: dict[str, int] = field(default_factory=dict)
    revisions: dict[str, int] = field(default_factory=dict)
    client: object = None
    expires_at: float = 0
    published: bool = False
    monitor: asyncio.Task | None = None
    recovered: bool = False
    purpose: str = "dispatch"
    interrupted: bool = False

    def activate(self, lifetime: float) -> None:
        existing = self.owner.leases.get(self.printer_id)
        if (
            self.owner.blocks_power_off(self.printer_id) and existing is not self
        ) or self.printer_id in self.owner.power_off_in_progress:
            raise RuntimeError("Printer already has preheat ownership")
        prior_expiry = self.expires_at
        # Absolute cap also bounds malformed/unexpected settings and retry budgets.
        self.expires_at = time.time() + min(max(lifetime, 1), 24 * 3600)
        self.owner.leases[self.printer_id] = self
        try:
            self.owner.save(self)
        except OSError:
            if existing is self:
                self.expires_at = prior_expiry
            else:
                self.owner.leases.pop(self.printer_id, None)
                self.expires_at = 0
            raise
        if self.purpose == "handoff":
            self.purpose = "dispatch"
        if self.monitor is None or self.monitor.done():
            self.monitor = asyncio.create_task(self.owner.watch(self), name=f"preheat-owner-{self.item_id}")

    def command(self, client, heater: str, target: int) -> bool:
        self.client = client
        state = self.manager.get_status(self.printer_id)
        if state is None or getattr(state, "state", None) in _ACTIVE:
            return False
        if self.purpose == "keep_warm" and (
            state.state != "FINISH" or (state.temperatures or {}).get(f"{heater}_target") != 0
        ):
            return False
        if (state.temperatures or {}).get(f"{heater}_target") == target:
            return True  # An existing heater session is not ours to stop.
        self.targets[heater] = target
        self.owner.save(self)  # Record even a command whose delivery becomes uncertain.
        sent = getattr(client, f"set_{heater}_temperature")(target)
        if sent:
            # Bed telemetry can lag the command. Cache our target just as the
            # chamber setter does, so immediate upload failures can roll back.
            state = self.manager.get_status(self.printer_id)
            if state is not None and isinstance(state.temperatures, dict):
                state.temperatures[f"{heater}_target"] = float(target)
            revisions = getattr(client, "_heater_command_revisions", {})
            if isinstance(revisions, dict):
                self.revisions[heater] = revisions.get(heater, 0)
        else:
            self.targets.pop(heater, None)
            self.owner.save(self)
        return bool(sent)

    def dispatched(self) -> None:
        if self.owner.leases.get(self.printer_id) is not self:
            return
        self.published = True
        # Publish is not proof of printing. Keep ownership through both start
        # watchdog phases, then roll back if firmware never confirms a start.
        self.expires_at = min(self.expires_at, time.time() + 300)
        try:
            self.owner.save(self)
        except OSError as exc:
            logger.warning("Cannot persist preheat dispatch handoff intent for printer %s: %s", self.printer_id, exc)


class PreheatOwnership:
    def __init__(self, directory: Path | None = None, session_factory=None):
        self.directory = directory
        self.session_factory = session_factory
        self.leases: dict[int, PreheatLease] = {}
        self.poll_seconds = 3.0
        self.power_off_in_progress: set[int] = set()

    def path(self, printer_id: int) -> Path:
        root = self.directory if self.directory is not None else settings.base_dir / "preheat-ownership"
        return root / f"{printer_id}.json"

    def save(self, lease: PreheatLease) -> None:
        path = self.path(lease.printer_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "printer_id": lease.printer_id,
                "item_id": lease.item_id,
                "targets": lease.targets,
                "expires_at": lease.expires_at,
            }
        )
        temporary = path.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(path)
            if os.name != "nt":
                directory_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)

    @contextmanager
    def power_off_window(self, printer_id: int | None):
        if printer_id is not None:
            self.power_off_in_progress.add(printer_id)
        try:
            yield
        finally:
            if printer_id is not None:
                self.power_off_in_progress.discard(printer_id)

    def blocks_power_off(self, printer_id: int | None) -> bool:
        if printer_id is None:
            return False
        try:
            return printer_id in self.leases or self.path(printer_id).exists()
        except OSError:
            return True  # Unknown ownership must never authorize a power cut.

    def forget(self, lease: PreheatLease) -> None:
        existing = self.leases.get(lease.printer_id)
        if existing is not None and existing is not lease:
            return
        try:
            self.path(lease.printer_id).unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Cannot clear preheat ownership for printer %s: %s", lease.printer_id, exc)
            return
        self.leases.pop(lease.printer_id, None)
        if lease.monitor and lease.monitor is not asyncio.current_task():
            lease.monitor.cancel()

    def rollback(self, lease: PreheatLease) -> bool:
        state = lease.manager.get_status(lease.printer_id)
        if state is None or getattr(state, "state", None) not in _ACTIVE | _IDLE:
            return False
        if state.state in _ACTIVE:
            self.forget(lease)  # Firmware, not the queue row/MQTT publish, owns heating now.
            return True
        client = lease.manager.get_client(lease.printer_id)
        if client is None or getattr(state, "connected", True) is False:
            return False
        if not lease.recovered and lease.client is not None and client is not lease.client:
            lease.recovered = True  # A new MQTT session cannot prove old command ownership.
        for heater, target in list(lease.targets.items()):
            # Recheck immediately before every command: a print can start or a
            # person can change one target while the other heater is stopped.
            current = lease.manager.get_status(lease.printer_id)
            if current is None or getattr(current, "state", None) not in _IDLE:
                return False
            actual = (current.temperatures or {}).get(f"{heater}_target")
            revisions = getattr(client, "_heater_command_revisions", {})
            overridden = isinstance(revisions, dict) and revisions.get(heater, 0) != lease.revisions.get(heater, 0)
            if not lease.recovered and overridden:
                lease.targets.pop(heater)
                continue
            if actual is None:
                return False
            if actual != target and (lease.recovered or actual != 0):
                lease.targets.pop(heater)  # Manual/firmware target superseded ours.
                continue
            if lease.recovered:
                # Same numeric target after restart cannot establish ownership
                # of a user's new heating session. Keep the safety interlock.
                return False
            try:
                if not getattr(client, f"set_{heater}_temperature")(0):
                    return False
            except Exception as exc:
                logger.warning("Preheat rollback failed for printer %s/%s: %s", lease.printer_id, heater, exc)
                return False
            lease.targets.pop(heater)
        self.forget(lease)
        return True

    @asynccontextmanager
    async def dispatch(self, item, manager, db=None):
        lease = self.leases.get(item.printer_id)
        if lease and lease.purpose == "keep_warm" and lease.item_id == item.id and lease.expires_at > time.time():
            lease.purpose = "handoff"
            lease.task = asyncio.current_task()
        else:
            lease = PreheatLease(self, item.printer_id, item.id, manager, asyncio.current_task())
        token = _current.set(lease)
        try:
            yield lease
        except _PlateClearRequired:
            # A complete firmware print may have occurred between monitor polls.
            # Its heater targets cannot still be claimed by our earlier preheat.
            lease.recovered = True
            self.forget(lease)
            await self.defer_interrupted(lease, db)
        except asyncio.CancelledError:
            if not lease.interrupted:
                raise
            await self.defer_interrupted(lease, db)
        finally:
            _current.reset(token)
            if self.leases.get(lease.printer_id) is lease and not lease.published:
                self.rollback(lease)

    @staticmethod
    def guard_plate_clear(printer_id, required, manager) -> None:
        if required and manager.is_awaiting_plate_clear(printer_id):
            raise _PlateClearRequired

    def release_undispatched(self, item_id: int) -> None:
        for lease in list(self.leases.values()):
            if lease.item_id == item_id and lease.purpose == "keep_warm":
                self.rollback(lease)

    def release_skipped_preheat(self) -> None:
        if (lease := current_preheat_lease()) and lease.purpose == "handoff":
            self.rollback(lease)

    def can_adopt(self, item) -> bool:
        lease = self.leases.get(item.printer_id)
        if not (
            lease
            and not lease.recovered
            and lease.purpose == "keep_warm"
            and lease.item_id == item.id
            and lease.expires_at > time.time()
        ):
            return False
        client = lease.manager.get_client(lease.printer_id)
        state = lease.manager.get_status(lease.printer_id)
        revisions = getattr(client, "_heater_command_revisions", {})
        return bool(
            client is lease.client
            and state is not None
            and getattr(state, "connected", False)
            and state.state in _IDLE
            and isinstance(revisions, dict)
            and all(
                revisions.get(heater, 0) == lease.revisions.get(heater, 0)
                and (state.temperatures or {}).get(f"{heater}_target") == target
                for heater, target in lease.targets.items()
            )
        )

    async def item_status(self, lease: PreheatLease) -> str | None:
        from backend.app.core.database import async_session
        from backend.app.models.print_queue import PrintQueueItem

        async with (self.session_factory or async_session)() as db:
            item = await db.get(PrintQueueItem, lease.item_id)
            return item.status if item else None

    async def fail_expired_dispatch(self, lease: PreheatLease) -> None:
        from sqlalchemy import update

        from backend.app.core.database import async_session
        from backend.app.models.print_queue import PrintQueueItem

        async with (self.session_factory or async_session)() as db:
            await db.execute(
                update(PrintQueueItem)
                .where(PrintQueueItem.id == lease.item_id, PrintQueueItem.status == "pending")
                .values(
                    status="failed",
                    error_message="Preheat dispatch safety deadline expired",
                    completed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

    async def defer_interrupted(self, lease: PreheatLease, db=None) -> None:
        """Revert an optimistic CAS whose print command was never published."""
        from sqlalchemy import update

        from backend.app.core.database import async_session
        from backend.app.models.print_queue import PrintQueueItem

        if db is None:
            async with (self.session_factory or async_session)() as session:
                await self.defer_interrupted(lease, session)
            return
        await db.rollback()
        await db.execute(
            update(PrintQueueItem)
            .where(
                PrintQueueItem.id == lease.item_id,
                PrintQueueItem.printer_id == lease.printer_id,
                PrintQueueItem.status.in_(("pending", "printing")),
            )
            .values(status="pending", started_at=None, dispatching_at=None)
        )
        await db.commit()
        logger.info("Queue item %s deferred before command publication", lease.item_id)

    async def watch(self, lease: PreheatLease) -> None:
        try:
            while self.leases.get(lease.printer_id) is lease:
                # Event timeout avoids patched scheduler sleeps and busy loops.
                try:
                    await asyncio.wait_for(asyncio.Event().wait(), timeout=self.poll_seconds)
                except TimeoutError:
                    pass
                state = lease.manager.get_status(lease.printer_id)
                if state is not None and getattr(state, "state", None) in _ACTIVE:
                    if not lease.published and lease.task and not lease.task.done():
                        lease.interrupted = True
                        lease.task.cancel()
                    self.forget(lease)
                    return
                published_before_read = lease.published
                try:
                    status = await self.item_status(lease)
                    ended = status not in ("pending", "printing") or (published_before_read and status == "pending")
                except Exception as exc:
                    logger.warning("Cannot verify preheat queue item %s: %s", lease.item_id, exc)
                    ended = False
                expired = time.time() >= lease.expires_at
                if (
                    expired
                    and not ended
                    and not lease.published
                    and not lease.recovered
                    and lease.purpose != "keep_warm"
                ):
                    try:
                        await self.fail_expired_dispatch(lease)
                    except Exception as exc:
                        logger.warning("Cannot fail expired preheat item %s: %s", lease.item_id, exc)
                if ended or expired:
                    if not lease.published and lease.task and not lease.task.done():
                        lease.task.cancel()
                    if self.rollback(lease):
                        return
        except asyncio.CancelledError:
            pass

    async def recover(self, manager) -> None:
        root = self.path(0).parent
        if not root.exists():
            return
        for path in root.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                printer_id = int(data["printer_id"])
                if path != self.path(printer_id) or printer_id in self.leases:
                    continue
                targets = data["targets"]
                if not isinstance(targets, dict) or any(
                    key not in ("bed", "chamber") or not isinstance(value, int) or value <= 0
                    for key, value in targets.items()
                ):
                    raise ValueError("invalid heater targets")
                lease = PreheatLease(
                    self,
                    printer_id,
                    int(data["item_id"]),
                    manager,
                    targets=targets,
                    expires_at=0,
                    recovered=True,
                )
                self.leases[printer_id] = lease
                if not self.rollback(lease):
                    logger.warning(
                        "Unresolved preheat ownership on printer %s; automatic power-off remains blocked", printer_id
                    )
                    lease.monitor = asyncio.create_task(self.watch(lease), name=f"preheat-recovery-{printer_id}")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                logger.warning("Cannot recover preheat record %s: %s; power-off remains blocked", path.name, exc)

    def stop(self) -> None:
        for lease in list(self.leases.values()):
            if lease.task and not lease.task.done() and not lease.published:
                lease.task.cancel()
            self.rollback(lease)
            if lease.monitor:
                lease.monitor.cancel()


def current_preheat_lease() -> PreheatLease | None:
    return _current.get()


preheat_ownership = PreheatOwnership()
