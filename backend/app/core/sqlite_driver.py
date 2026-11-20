"""Compatibility with repeated stop requests in aiosqlite 0.22.1."""

import functools


def make_aiosqlite_stop_idempotent() -> None:
    """Make aiosqlite's ``Connection.stop()`` safe to call twice (#3515).

    aiosqlite 0.22.1 queues a stop request for the connection's worker thread
    on every call, and the thread exits at the first. A second call's future
    is then never resolved, and whoever awaits it waits forever. SQLAlchemy
    reaches this on a cancelled read: it discards the connection, and when
    that close is cancelled in turn it calls ``stop()`` while the close is
    still running. The close never ends, its session's exit waits on it, a
    pooled connection is lost, and in a camera stream the cancelled wait spun
    one CPU core at 100%.

    Upstream: omnilib/aiosqlite#403, fix in #404. Once a release has it, this
    stays harmless (a second call returns the first call's future either way)
    and can go.

    aiosqlite before 0.22.1 has no ``stop()``, and SQLAlchemy then never calls
    one, so there is nothing to fix. requirements.txt still allows those
    versions, and the in-app update keeps an installed one.
    """
    try:
        from aiosqlite.core import Connection
    except ImportError:  # PostgreSQL-only environment
        return
    original = getattr(Connection, "stop", None)
    if original is None or getattr(original, "_printops_idempotent", False):
        return

    @functools.wraps(original)
    def stop(self):
        try:
            return self.__dict__["_printops_stop_future"]
        except KeyError:
            future = original(self)
            self.__dict__["_printops_stop_future"] = future
            return future

    stop._printops_idempotent = True  # type: ignore[attr-defined]
    Connection.stop = stop
