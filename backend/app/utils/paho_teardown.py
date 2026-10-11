"""Retire MQTT clients without joining a stalled network thread on the caller."""

import logging
import threading
import time

logger = logging.getLogger(__name__)
_CALLBACKS = ("on_connect", "on_disconnect", "on_subscribe", "on_message")


def retire_paho_client(client, label: str) -> None:
    """Detach callbacks inline, then disconnect and stop on a daemon thread.

    A TLS reconnect can stall paho's unbounded ``loop_stop`` join. Clearing
    callbacks first prevents that old session from changing its replacement's
    state when it eventually returns. DISCONNECT still prevents QoS replay.
    """
    for attr in _CALLBACKS:
        try:
            setattr(client, attr, None)
        except Exception:
            pass

    def teardown() -> None:
        started = time.monotonic()
        try:
            client.disconnect()
        except Exception:
            pass
        try:
            client.loop_stop()
        except Exception:
            pass
        elapsed = time.monotonic() - started
        if elapsed >= 5:
            logger.warning("[%s] MQTT retirement took %.0fs; the replacement remained available", label, elapsed)

    try:
        threading.Thread(target=teardown, name=f"mqtt-retire-{label}", daemon=True).start()
    except RuntimeError as exc:
        logger.error("[%s] Could not start MQTT retirement: %s", label, exc)
        try:
            client.disconnect()
        except Exception:
            pass
