"""Detect repeated encoded pictures without reconnect churn in still scenes."""

import zlib


class FrozenFrameWatchdog:
    def __init__(self, frozen_seconds: float = 20.0, still_seconds: float = 300.0, *, adaptive: bool = False):
        self.frozen_seconds = frozen_seconds
        self.still_seconds = still_seconds
        self.adaptive = adaptive
        self.frozen_crc: int | None = None
        self.still_scene = False
        self.unchanged_for = 0.0
        self._longest_gap = 0.0
        self.begin_session()

    def begin_session(self) -> None:
        self.last_crc: int | None = None
        self.last_change = 0.0

    def observe(self, frame: bytes, now: float) -> bool:
        crc = zlib.crc32(frame)
        if self.last_crc is None:
            if self.adaptive and self.frozen_crc is not None and crc != self.frozen_crc:
                self._longest_gap = max(self._longest_gap, self.unchanged_for)
            self.still_scene = self.frozen_crc is not None and crc == self.frozen_crc
            if not self.still_scene:
                self.frozen_crc = None
            self.last_crc = crc
            self.last_change = now
        elif crc != self.last_crc:
            if self.adaptive:
                self._longest_gap = max(self._longest_gap, now - self.last_change)
            self.last_crc = crc
            self.last_change = now
            self.still_scene = False
            self.frozen_crc = None
        self.unchanged_for = now - self.last_change
        limit = self.still_seconds if self.still_scene else self.frozen_seconds
        if self.adaptive:
            limit = min(max(limit, 3 * self._longest_gap), self.still_seconds)
        if self.unchanged_for > limit:
            self.frozen_crc = crc
            return True
        return False
