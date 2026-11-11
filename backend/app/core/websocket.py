import asyncio
import json
import logging
from collections.abc import Callable, Collection
from contextlib import suppress
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from backend.app.core import database
from backend.app.core.auth_websocket import WS_CLOSE_UNAUTHORIZED, WebSocketAccess, read_websocket_access
from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import INCLUDE_OPEN_RUNS, PrintLogEntry

logger = logging.getLogger(__name__)
_UNKNOWN_ARCHIVE_PRINTER = -1
_ARCHIVE_EVENTS = frozenset({"archive_created", "archive_updated"})


async def _archive_printer_ids(archive_id: object) -> list[int | None]:
    if type(archive_id) is not int:
        return [_UNKNOWN_ARCHIVE_PRINTER]
    try:
        async with database.async_session() as db:
            row = (await db.execute(select(PrintArchive.printer_id).where(PrintArchive.id == archive_id))).first()
            if row is None:
                return [_UNKNOWN_ARCHIVE_PRINTER]
            history = await db.scalars(
                select(PrintLogEntry.printer_id)
                .where(PrintLogEntry.archive_id == archive_id, PrintLogEntry.printer_id.is_not(None))
                .distinct()
                .execution_options(**{INCLUDE_OPEN_RUNS: True})
            )
            return list(dict.fromkeys([row[0], *history]))
    except (OSError, RuntimeError, SQLAlchemyError):
        logger.warning("Could not resolve the printers for an archive update", exc_info=True)
        return [_UNKNOWN_ARCHIVE_PRINTER]


def _message_for_access(access: WebSocketAccess, message: dict[str, Any]) -> dict[str, Any] | None:
    kind = message.get("type")
    printer_id = message.get("printer_id")
    if printer_id is None and kind in _ARCHIVE_EVENTS:
        data = message.get("data")
        printer_id = data.get("printer_id") if isinstance(data, dict) else None
    if kind == "archive_updated":
        printers = message.get("_archive_printer_ids", [printer_id])
        if access.printer_ids is not None:
            return {"type": kind} if any(access.allows_printer(item) for item in printers) else None
        if "_archive_printer_ids" in message:
            return {key: value for key, value in message.items() if key != "_archive_printer_ids"}
    if kind in _ARCHIVE_EVENTS and printer_id is None and access.printer_ids is not None:
        return {"type": kind}
    if kind == "pipeline_run_updated" and printer_id is None:
        run = message.get("run")
        printer_id = run.get("assigned_printer_id") if isinstance(run, dict) else None
    return message if access.allows_printer(printer_id) else None


class ConnectionManager:
    """Manages WebSocket connections and broadcasts."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, access: WebSocketAccess, token: str | None) -> bool:
        await websocket.accept()
        # Register only after the second check. Permission refreshes share this
        # lock and cannot overlook a socket between validation and registration.
        async with self._lock:
            opener = token if access.authenticated else None
            current = await read_websocket_access(opener)
            if current is not None:
                websocket.state.printops_live_access = current
                websocket.state.printops_live_token = opener if current.authenticated else None
                self.active_connections.append(websocket)
                return True
        await self._close_unauthorized(websocket)
        return False

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    @staticmethod
    async def _close_unauthorized(websocket: WebSocket) -> None:
        with suppress(WebSocketDisconnect, RuntimeError, OSError):
            await websocket.close(code=WS_CLOSE_UNAUTHORIZED)

    async def _close_matching(self, matches: Callable[[WebSocketAccess], bool]) -> None:
        async with self._lock:
            closing = [
                websocket for websocket in self.active_connections if matches(websocket.state.printops_live_access)
            ]
            for websocket in closing:
                self.active_connections.remove(websocket)
        for websocket in closing:
            await self._close_unauthorized(websocket)

    async def close_session(self, issuer_jti: str) -> None:
        await self._close_matching(lambda access: access.issuer_jti == issuer_jti)

    async def close_user_sessions(self, user_id: int) -> None:
        await self._close_matching(lambda access: access.user_id == user_id and access.api_key_id is None)

    async def close_api_keys(self, key_ids: Collection[int]) -> None:
        if key_ids:
            await self._close_matching(lambda access: access.api_key_id in key_ids)

    async def close_anonymous(self) -> None:
        await self._close_matching(lambda access: not access.authenticated)

    async def reconcile_restored_access(self, auth_enabled: bool) -> None:
        if auth_enabled:
            await self._close_matching(lambda access: access.api_key_id is None)
        await self.refresh_live_access()

    async def refresh_live_access(self, *, user_id: int | None = None, api_key_id: int | None = None) -> None:
        """Update open scopes after a committed change to grants or credentials."""
        denied = []
        async with self._lock:
            for connection in list(self.active_connections):
                access = connection.state.printops_live_access
                if (user_id is not None and access.user_id != user_id) or (
                    api_key_id is not None and access.api_key_id != api_key_id
                ):
                    continue
                if not await self._refresh_connection(connection):
                    denied.append(connection)
        for connection in denied:
            await self._close_unauthorized(connection)

    async def refresh_connection(self, websocket: WebSocket) -> bool:
        async with self._lock:
            if websocket not in self.active_connections:
                return False
            if await self._refresh_connection(websocket):
                return True
        await self._close_unauthorized(websocket)
        return False

    async def _refresh_connection(self, websocket: WebSocket) -> bool:
        current = await read_websocket_access(websocket.state.printops_live_token, websocket.state.printops_live_access)
        if current is None:
            self.active_connections.remove(websocket)
            return False
        websocket.state.printops_live_access = current
        if not current.authenticated:
            websocket.state.printops_live_token = None
        return True

    async def send_event(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        async with self._lock:
            if websocket in self.active_connections:
                allowed = _message_for_access(websocket.state.printops_live_access, message)
                if allowed is not None:
                    await websocket.send_json(allowed)

    async def broadcast(self, message: dict[str, Any]):
        await self.broadcast_to_user(None, message)

    async def broadcast_to_user(
        self, user_id: int | None, message: dict[str, Any], *, user_sessions_only: bool = False
    ):
        """Send an event within the current printer scope and optional owner scope."""
        if not self.active_connections:
            return

        data = json.dumps(message)
        async with self._lock:
            for connection in list(self.active_connections):
                access = connection.state.printops_live_access
                if user_sessions_only and access.api_key_id is not None:
                    continue
                if user_id is not None and access.user_id != user_id:
                    continue
                allowed = _message_for_access(access, message)
                if allowed is None:
                    continue
                try:
                    await connection.send_text(data if allowed is message else json.dumps(allowed))
                except Exception:
                    self.active_connections.remove(connection)

    async def send_printer_status(self, printer_id: int, status: dict):
        """Send printer status update to all clients."""
        await self.broadcast(
            {
                "type": "printer_status",
                "printer_id": printer_id,
                "data": status,
            }
        )

    async def send_print_start(self, printer_id: int, data: dict):
        """Notify clients that a print has started."""
        await self.broadcast(
            {
                "type": "print_start",
                "printer_id": printer_id,
                "data": data,
            }
        )

    async def send_print_complete(self, printer_id: int, data: dict):
        """Notify clients that a print has completed."""
        await self.broadcast(
            {
                "type": "print_complete",
                "printer_id": printer_id,
                "data": data,
            }
        )

    async def send_archive_created(self, archive: dict):
        """Notify clients that a new archive was created."""
        await self.broadcast(
            {
                "type": "archive_created",
                "data": archive,
            }
        )

    async def send_archive_updated(self, archive: dict):
        """Notify dashboards allowed to see the archive's printer."""
        if not self.active_connections:
            return
        message = {"type": "archive_updated", "data": archive}
        message["_archive_printer_ids"] = await _archive_printer_ids(archive.get("id"))
        await self.broadcast(message)

    async def send_queue_item_uploading(
        self,
        user_id: int | None,
        queue_item_id: int,
        printer_id: int,
        printer_name: str | None,
        file_name: str,
        total_bytes: int,
    ):
        """Toast trigger: scheduler picked the item up, FTP upload starts."""
        await self.broadcast_to_user(
            user_id,
            {
                "type": "queue_item_uploading",
                "queue_item_id": queue_item_id,
                "printer_id": printer_id,
                "printer_name": printer_name,
                "file_name": file_name,
                "total_bytes": total_bytes,
            },
        )

    async def send_queue_item_upload_progress(
        self,
        user_id: int | None,
        queue_item_id: int,
        bytes_transferred: int,
        total_bytes: int,
    ):
        """Toast update: throttled byte-level progress during the FTP upload."""
        pct = int(round(100 * bytes_transferred / total_bytes)) if total_bytes else 0
        await self.broadcast_to_user(
            user_id,
            {
                "type": "queue_item_upload_progress",
                "queue_item_id": queue_item_id,
                "bytes_transferred": bytes_transferred,
                "total_bytes": total_bytes,
                "pct": pct,
            },
        )

    async def send_file_download_progress(
        self,
        user_id: int | None,
        download_id: str,
        bytes_transferred: int,
        total_bytes: int,
    ):
        """Progress update for a manual printer-file download (file manager).

        Keyed by a client-generated ``download_id`` rather than a queue item
        id — file-manager downloads aren't queue rows. Mirrors
        send_queue_item_upload_progress's shape/throttling contract.
        """
        pct = int(round(100 * bytes_transferred / total_bytes)) if total_bytes else 0
        await self.broadcast_to_user(
            user_id,
            {
                "type": "file_download_progress",
                "download_id": download_id,
                "bytes_transferred": bytes_transferred,
                "total_bytes": total_bytes,
                "pct": pct,
            },
        )

    async def send_queue_item_acked(
        self,
        user_id: int | None,
        queue_item_id: int,
        printer_id: int,
    ):
        """Toast trigger: watchdog confirmed the printer transitioned out of pre_state."""
        await self.broadcast_to_user(
            user_id,
            {
                "type": "queue_item_acked",
                "queue_item_id": queue_item_id,
                "printer_id": printer_id,
            },
        )

    async def send_queue_item_failed(
        self,
        user_id: int | None,
        queue_item_id: int,
        printer_id: int | None,
        reason: str,
    ):
        """Toast trigger: dispatch failed at any stage. Toast turns red, auto-dismisses."""
        await self.broadcast_to_user(
            user_id,
            {
                "type": "queue_item_failed",
                "queue_item_id": queue_item_id,
                "printer_id": printer_id,
                "reason": reason,
            },
        )

    async def send_missing_spool_assignment(
        self,
        printer_id: int,
        printer_name: str,
        missing_slots: list[dict[str, str]],
    ):
        """Notify clients that a print started with missing spool assignments."""
        await self.broadcast(
            {
                "type": "missing_spool_assignment",
                "printer_id": printer_id,
                "printer_name": printer_name,
                "missing_slots": missing_slots,
            }
        )


# Global connection manager
ws_manager = ConnectionManager()
