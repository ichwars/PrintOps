"""Keep AMS weight estimates off while completed prints are being charged."""

from functools import wraps

_completing: dict[int, int] = {}


def printer_is_charging(printer_id: int) -> bool:
    from backend.app.services.usage_tracker import _active_sessions

    return printer_id in _active_sessions or bool(_completing.get(printer_id))


def hold_completion_charges(callback):
    @wraps(callback)
    async def complete(printer_id, data):
        # Reference counts also cover overlapping completions and a new start
        # arriving while an earlier completion is still awaiting its writes.
        _completing[printer_id] = _completing.get(printer_id, 0) + 1
        try:
            return await callback(printer_id, data)
        finally:
            remaining = _completing[printer_id] - 1
            if remaining:
                _completing[printer_id] = remaining
            else:
                _completing.pop(printer_id, None)

    return complete


def is_completing(printer_id: int) -> bool:
    return bool(_completing.get(printer_id))
