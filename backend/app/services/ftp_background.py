"""A stalled file service pauses background scans, without blocking user work."""

import logging
import time

logger = logging.getLogger(__name__)
STALL_SECONDS = 300.0
_stalled_until: dict[str, float] = {}


def stalled(ip_address):
    until = _stalled_until.get(ip_address)
    if until is None:
        return False
    if until <= time.monotonic():
        _stalled_until.pop(ip_address, None)
        return False
    return True


def record_stall(ip_address, what):
    if not stalled(ip_address):
        logger.warning(
            "Printer %s file service stalled (%s); pausing background scans for %.0fs", ip_address, what, STALL_SECONDS
        )
    _stalled_until[ip_address] = time.monotonic() + STALL_SECONDS


def clear_stall(ip_address):
    _stalled_until.pop(ip_address, None)
