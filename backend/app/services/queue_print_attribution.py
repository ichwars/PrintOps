"""Withdraw dispatch attribution when the printer never starts its queued print."""

import logging

from backend.app.services.printer_manager import printer_manager

logger = logging.getLogger(__name__)
ACTIVE_PRINT_STATES = frozenset({"PREPARE", "SLICING", "RUNNING", "PAUSE"})


class QueuePrintAttribution:
    def _init_print_attribution(self):
        self._unconfirmed_expected_print: dict[int, tuple[int, str, int]] = {}
        self._unconfirmed_print_user: dict[int, int] = {}
        self._sent_unstarted_print: dict[int, tuple[int, str | None, int | None]] = {}

    def _rollback_unconfirmed_expected_print(self, item_id: int):
        expected = self._unconfirmed_expected_print.pop(item_id, None)
        if expected is not None:
            from backend.app.main import unregister_expected_print

            unregister_expected_print(*expected)

    def _rollback_unconfirmed_print_user(self, item_id: int):
        printer_id = self._unconfirmed_print_user.pop(item_id, None)
        if printer_id is not None:
            printer_manager.clear_current_print_user_for_item(printer_id, item_id)

    def _forget_unstarted_print(self, item_id: int, *, unless_printing: bool, keep_expected: bool = False):
        sent = self._sent_unstarted_print.get(item_id)
        if sent is None:
            return
        printer_id, filename, archive_id = sent
        status = printer_manager.get_status(printer_id)
        if unless_printing and status is not None and status.state in ACTIVE_PRINT_STATES:
            return
        printer_manager.clear_current_print_user_for_item(printer_id, item_id)
        if keep_expected:
            return
        self._sent_unstarted_print.pop(item_id, None)
        if filename is not None and archive_id is not None:
            from backend.app.main import unregister_expected_print

            unregister_expected_print(printer_id, filename, archive_id)

    def notify_dispatch_cancelled(self, item_id: int):
        from backend.app.services.preheat_ownership import preheat_ownership

        preheat_ownership.cancel_dispatch(item_id)
        self._forget_unstarted_print(item_id, unless_printing=False)

    def forget_printer(self, printer_id: int):
        for table in (self._sent_unstarted_print, self._unconfirmed_expected_print):
            for item_id in [item_id for item_id, sent in table.items() if sent[0] == printer_id]:
                table.pop(item_id, None)
        for item_id in [item_id for item_id, owner in self._unconfirmed_print_user.items() if owner == printer_id]:
            self._unconfirmed_print_user.pop(item_id, None)
        printer_manager.clear_current_print_user(printer_id)
