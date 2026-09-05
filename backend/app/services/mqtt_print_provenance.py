"""Small MQTT provenance state machines shared by the printer client."""

REQUEST_TOPIC_PROBE_FAILURES: dict[str, int] = {}
REQUEST_TOPIC_PROBE_LIMIT = 2


def clear_request_topic_probe_failure(serial_number: str) -> None:
    REQUEST_TOPIC_PROBE_FAILURES.pop(serial_number, None)


def request_topic_probe_rejected(serial_number: str, logger) -> bool:
    """Return True only after two consecutive circumstantial probe drops."""
    failures = REQUEST_TOPIC_PROBE_FAILURES.get(serial_number, 0) + 1
    REQUEST_TOPIC_PROBE_FAILURES[serial_number] = failures
    if failures >= REQUEST_TOPIC_PROBE_LIMIT:
        logger.warning(
            "[%s] Disconnected shortly after request topic subscription %d times. Disabling request topic.",
            serial_number,
            failures,
        )
        return True
    logger.info(
        "[%s] Disconnected shortly after request topic subscription (%d/%d); retrying.",
        serial_number,
        failures,
        REQUEST_TOPIC_PROBE_LIMIT,
    )
    return False


def observe_loaded_tray(state, was_running: bool, completion_triggered: bool, callback, serial_number: str, logger):
    """Record and emit one physical tray transition during an active print."""
    tray = state.tray_now
    valid = 0 <= tray <= 15 or 24 <= tray <= 27 or 128 <= tray <= 135 or tray == 254
    if not valid:
        return
    if tray != state.last_loaded_tray and was_running and not completion_triggered:
        state.tray_change_log.append((tray, state.layer_num))
        logger.info("[%s] Tray change during print: tray=%d at layer=%d", serial_number, tray, state.layer_num)
        if callback:
            callback(tray, state.layer_num)
    state.last_loaded_tray = tray
