"""Drop settings resolved for a particular printer when a queue job moves."""

from collections.abc import Iterable

from backend.app.models.print_queue import PrintQueueItem

PRINTER_RESOLVED_DEFAULTS: dict[str, bool | None] = {
    "ams_mapping": None,
    "skip_filament_check": False,
    "nozzle_mapping": None,
}


def drop_printer_resolved(item: PrintQueueItem, keep: Iterable[str] = ()) -> None:
    """Keep print options, but discard the previous printer's tray/nozzle picks."""
    kept = set(keep)
    for field, default in PRINTER_RESOLVED_DEFAULTS.items():
        if field not in kept:
            setattr(item, field, default)
