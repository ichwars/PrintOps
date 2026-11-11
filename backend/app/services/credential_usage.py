"""Bound the rate of credential usage writes, including failed attempts."""

from collections import OrderedDict
from datetime import datetime, timedelta, timezone

_USAGE_INTERVAL = timedelta(minutes=1)
_MAX_TRACKED_ATTEMPTS = 4096


class CredentialUsageThrottle:
    def __init__(self) -> None:
        self._attempts: OrderedDict[str, datetime] = OrderedDict()

    def due(self, credential_hash: str, stored: datetime | None, now: datetime) -> bool:
        for timestamp in (stored, self._attempts.get(credential_hash)):
            if timestamp is None:
                continue
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            if timedelta(0) <= now - timestamp < _USAGE_INTERVAL:
                return False

        # A deleted row can share its id with a new key. Scope the throttle to
        # the verified credential and cap the number of attempts held in memory.
        self._attempts[credential_hash] = now
        self._attempts.move_to_end(credential_hash)
        if len(self._attempts) > _MAX_TRACKED_ATTEMPTS:
            self._attempts.popitem(last=False)
        return True
