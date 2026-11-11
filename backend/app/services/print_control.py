"""Record user stops so firmware terminal reports become cancellations."""

from collections.abc import Callable

from backend.app.services.printer_manager import printer_manager

STOPPABLE_STATES = frozenset({"RUNNING", "PRINTING", "PAUSE"})


def mark_stopped_by_user(printer_id: int) -> None:
    from backend.app.main import mark_printer_stopped_by_user

    mark_printer_stopped_by_user(printer_id)


def stop_print_by_user(
    printer_id: int,
    *,
    send: Callable[[], bool] | None = None,
    mark_when_unsent: bool = False,
    should_mark: bool = True,
) -> bool:
    """Send a synchronous stop and record the user intent before yielding."""
    sent = False
    try:
        sent = send() if send is not None else printer_manager.stop_print(printer_id)
        return sent
    finally:
        if should_mark and (sent or mark_when_unsent):
            mark_stopped_by_user(printer_id)
