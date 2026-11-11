"""Authenticated dashboard events with current printer scope."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from backend.app.core.auth_websocket import WS_CLOSE_UNAUTHORIZED, read_websocket_access
from backend.app.core.websocket import ws_manager
from backend.app.services.printer_manager import printer_manager, printer_state_to_dict

logger = logging.getLogger(__name__)
router = APIRouter()
_ACCESS_RECHECK_SECONDS = 30


async def _send_printer_status(websocket: WebSocket, printer_id: int, state) -> None:
    await ws_manager.send_event(
        websocket,
        {
            "type": "printer_status",
            "printer_id": printer_id,
            "data": printer_state_to_dict(
                state, printer_id, printer_manager.get_model(printer_id), printer_manager.get_drying_targets(printer_id)
            ),
        },
    )


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = Query(default=None)) -> None:
    access = await read_websocket_access(token)
    if access is None:
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return
    if not await ws_manager.connect(websocket, access, token):
        return

    try:
        for printer_id, state in printer_manager.get_all_statuses().items():
            await _send_printer_status(websocket, printer_id, state)

        clock = asyncio.get_running_loop().time
        recheck_at = clock() + _ACCESS_RECHECK_SECONDS
        while True:
            if clock() >= recheck_at:
                if not await ws_manager.refresh_connection(websocket):
                    return
                recheck_at = clock() + _ACCESS_RECHECK_SECONDS
            try:
                async with asyncio.timeout_at(recheck_at):
                    data = await websocket.receive_json()
            except TimeoutError:
                continue

            if data.get("type") == "ping":
                await ws_manager.send_event(websocket, {"type": "pong"})
            elif data.get("type") == "get_status":
                printer_id = data.get("printer_id")
                if type(printer_id) is int and printer_id > 0:
                    state = printer_manager.get_status(printer_id)
                    if state:
                        await _send_printer_status(websocket, printer_id, state)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket connection failed")
    finally:
        await ws_manager.disconnect(websocket)
