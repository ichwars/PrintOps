"""Scheduled snapshot refresh with an atomic, generation-checked publication."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update

from backend.app.core import database
from backend.app.models.lexware import LexwareConnection, LexwareResource
from backend.app.services.lexware_client import LexwareClient, LexwareError
from backend.app.services.lexware_connections import check_connection_generation, decrypt_api_key, lock_connection
from backend.app.services.lexware_imports import snapshot_hash

logger = logging.getLogger(__name__)


async def sync_connection(connection_id: int) -> None:
    async with database.async_session() as db:
        connection = await lock_connection(db, connection_id)
        if not connection.enabled or not connection.encrypted_api_key:
            return
        version = connection.version
        organization_id = connection.organization_id
        connection.sync_status = "running"
        connection.last_attempt_at = datetime.now(timezone.utc)
        connection.last_error = None
        await db.commit()

    async def guard():
        await check_connection_generation(connection_id, version)

    try:
        from backend.app.services.lexware_documents import fetch_vouchers, replace_vouchers

        key = decrypt_api_key(connection)
        async with LexwareClient(key, before_request=guard) as client:
            contacts = await client.list_pages("/v1/contacts", {"customer": "true"})
            articles = await client.list_pages("/v1/articles")
            vouchers = await fetch_vouchers(client)
        # Validate upstream identities before any write. Never trust a row from another organization.
        for row in contacts + articles:
            try:
                row["id"] = str(UUID(row["id"]))
            except (KeyError, ValueError, TypeError):
                raise LexwareError("Lexware returned an invalid resource identity") from None
            # Article list responses may omit organizationId. The fixed-origin
            # authenticated connection supplies ownership in that case.
            if row.get("organizationId") is not None and row["organizationId"] != organization_id:
                raise LexwareError("Lexware returned a resource from a different organization")
        async with database.async_session() as db:
            connection = await lock_connection(db, connection_id)
            if not connection.enabled or not connection.encrypted_api_key or connection.version != version:
                return
            now = datetime.now(timezone.utc)
            for kind, rows in (("contacts", contacts), ("articles", articles)):
                existing = {
                    r.external_id: r
                    for r in (
                        await db.scalars(
                            select(LexwareResource).where(
                                LexwareResource.connection_id == connection_id, LexwareResource.kind == kind
                            )
                        )
                    ).all()
                }
                for row in rows:
                    resource = existing.get(row["id"])
                    if resource is None:
                        resource = LexwareResource(connection_id=connection_id, kind=kind, external_id=row["id"])
                        db.add(resource)
                    resource.payload = row
                    resource.version_hash = snapshot_hash(row)
                    resource.updated_at = now
                # Missing records are retained without guessing deletion/archive state.
            await replace_vouchers(db, connection_id, vouchers)
            connection.sync_status = "success"
            connection.last_success_at = now
            connection.last_error = None
            await db.commit()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        message = (
            str(error)
            if isinstance(error, LexwareError)
            else "Lexware synchronization failed; previous data is unchanged"
        )
        async with database.async_session() as db:
            await db.execute(
                update(LexwareConnection)
                .where(
                    LexwareConnection.id == connection_id,
                    LexwareConnection.version == version,
                    LexwareConnection.enabled.is_(True),
                )
                .values(sync_status="error", last_error=message[:500])
            )
            await db.commit()
        logger.warning("Lexware synchronization %s failed (%s)", connection_id, type(error).__name__)


class LexwareScheduler:
    def __init__(self):
        self._tasks: dict[int, asyncio.Task] = {}
        self._scheduler: asyncio.Task | None = None

    def queue(self, connection_id: int) -> None:
        task = self._tasks.get(connection_id)
        if task is None or task.done():
            self._tasks[connection_id] = asyncio.create_task(sync_connection(connection_id))

    async def start(self) -> None:
        if self._scheduler is None or self._scheduler.done():
            self._scheduler = asyncio.create_task(self._run())

    async def stop(self) -> None:
        tasks = [*self._tasks.values()]
        if self._scheduler:
            tasks.append(self._scheduler)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._scheduler = None

    async def _run(self):
        while True:
            try:
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
                async with database.async_session() as db:
                    ids = list(
                        (
                            await db.scalars(
                                select(LexwareConnection.id).where(
                                    LexwareConnection.enabled.is_(True),
                                    LexwareConnection.encrypted_api_key.is_not(None),
                                    (LexwareConnection.last_attempt_at.is_(None))
                                    | (LexwareConnection.last_attempt_at < cutoff),
                                )
                            )
                        ).all()
                    )
                for connection_id in ids:
                    self.queue(connection_id)
                self._tasks = {key: task for key, task in self._tasks.items() if not task.done()}
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Lexware scheduler could not check pending connections")
            await asyncio.sleep(60)


lexware_scheduler = LexwareScheduler()
