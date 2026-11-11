"""Share preview downloads briefly; bound retained bytes and entry count."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable

CACHE_SECONDS = 60.0
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_ENTRY_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 256
Key = tuple[int, str]


class PrinterFileCache:
    def __init__(self):
        self._entries: OrderedDict[Key, tuple[float, bytes]] = OrderedDict()
        self._total = 0
        self._in_flight: dict[Key, asyncio.Task[bytes]] = {}

    async def get(self, printer_id: int, path: str, fetch: Callable[[], Awaitable[bytes]]) -> bytes:
        key = (printer_id, path)
        self._sweep()
        if key in self._entries:
            self._entries.move_to_end(key)
            return self._entries[key][1]
        task = self._in_flight.get(key)
        if task is None or task.get_loop() is not asyncio.get_running_loop():
            task = asyncio.create_task(self._fetch(key, fetch))
            self._in_flight[key] = task
            task.add_done_callback(self._consume_outcome)
        return await asyncio.shield(task)

    @staticmethod
    def _consume_outcome(task):
        if not task.cancelled():
            task.exception()

    async def _fetch(self, key, fetch):
        try:
            data = await fetch()
        finally:
            owned = self._in_flight.get(key) is asyncio.current_task()
            if owned:
                self._in_flight.pop(key, None)
        # Invalidating a pending download removes its ownership, even before
        # this coroutine starts. It cannot repopulate a deleted or cleared file.
        if owned:
            self._keep(key, data)
        return data

    def _keep(self, key, data):
        size = len(data)
        if not size or size > MAX_ENTRY_BYTES or size > MAX_TOTAL_BYTES:
            return
        self._drop(key)
        self._sweep()
        while self._entries and (self._total + size > MAX_TOTAL_BYTES or len(self._entries) >= MAX_ENTRIES):
            self._drop(next(iter(self._entries)))
        self._entries[key] = (time.monotonic() + CACHE_SECONDS, data)
        self._total += size

    def _sweep(self):
        now = time.monotonic()
        for key in [key for key, (expires, _) in self._entries.items() if expires <= now]:
            self._drop(key)

    def _drop(self, key):
        entry = self._entries.pop(key, None)
        if entry is not None:
            self._total -= len(entry[1])

    def forget(self, printer_id, path):
        self._forget_key((printer_id, path))

    def forget_printer(self, printer_id):
        for key in {key for key in [*self._entries, *self._in_flight] if key[0] == printer_id}:
            self._forget_key(key)

    def clear(self):
        self._entries.clear()
        self._total = 0
        self._in_flight.clear()

    def _forget_key(self, key):
        self._drop(key)
        # Existing waiters finish; subsequent requests start a fresh download.
        self._in_flight.pop(key, None)


printer_file_cache = PrinterFileCache()
