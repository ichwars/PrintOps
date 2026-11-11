"""Confirm object skips from telemetry and retain the ownership of overlapping writes."""

import json
import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger("backend.app.services.bambu_mqtt")
SKIP_CONFIRM_TIMEOUT_S = 60.0


@dataclass
class _SkipState:
    pending: dict[int, tuple[str, float]] = field(default_factory=dict)
    commands: dict[str, list[int]] = field(default_factory=dict)
    lock: object = field(default_factory=threading.RLock)


def _state(client) -> _SkipState:
    state = client.__dict__.get("_skip_verification")
    return state if state is not None else client.__dict__.setdefault("_skip_verification", _SkipState())


def _undo(client, sequence: str, objects: list[int]) -> None:
    state = _state(client)
    with state.lock:
        owned = {oid for oid in objects if state.pending.get(oid, (None,))[0] == sequence}
        for oid in owned:
            state.pending.pop(oid, None)
        client.state.skipped_objects = [oid for oid in client.state.skipped_objects if oid not in owned]
        state.commands.pop(sequence, None)


def publish_skip_objects(client, command: dict, objects: list[int]) -> bool:
    """Register before publish so a fast refusal can undo the optimistic state."""
    state = _state(client)
    sequence = str(command["print"]["sequence_id"])
    with state.lock:
        confirmed = set(client.state.skipped_objects) - state.pending.keys()
        now = time.monotonic()
        for oid in objects:
            if oid not in confirmed:
                state.pending[oid] = (sequence, now)
            if oid not in client.state.skipped_objects:
                client.state.skipped_objects.append(oid)
        state.commands[sequence] = list(objects)
    try:
        result = client._client.publish(client.topic_publish, json.dumps(command), qos=1)
    except Exception:
        _undo(client, sequence, objects)
        raise
    code = getattr(result, "rc", None)
    if type(code) is int and code != 0:
        _undo(client, sequence, objects)
        logger.warning("[%s] Could not publish object skip: code=%s", client.serial_number, code)
        return False
    logger.info("[%s] Sent skip_objects command: %s", client.serial_number, objects)
    return True


def handle_skip_answer(client, data: dict) -> None:
    sequence = str(data.get("sequence_id", ""))
    state = client.__dict__.get("_skip_verification")
    if state is None:
        return
    with state.lock:
        objects = state.commands.pop(sequence, None)
        if objects is None or str(data.get("result") or "").lower() in ("", "success"):
            return
        logger.error(
            "[%s] Printer refused skipping objects %s: result=%s reason=%s",
            client.serial_number,
            objects,
            data.get("result"),
            data.get("reason", ""),
        )
        _undo(client, sequence, objects)


def parse_skipped_objects(values: list) -> list[int]:
    objects = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            continue
        try:
            oid = int(value)
        except ValueError:
            continue
        if oid >= 0 and oid not in objects:
            objects.append(oid)
    return objects


def observe_skipped_objects(client, data: dict) -> None:
    """Only a real s_obj report confirms skips; timeout is logged once."""
    if data.get("command") not in (None, "push_status"):
        return
    state = client.__dict__.get("_skip_verification")
    if state is None:
        return
    with state.lock:
        if client.state.state not in ("RUNNING", "PAUSE"):
            state.pending.clear()
            state.commands.clear()
            return
        reported = data.get("s_obj")
        if isinstance(reported, list):
            for oid in parse_skipped_objects(reported):
                state.pending.pop(oid, None)
        now = time.monotonic()
        expired = [oid for oid, (_, sent_at) in state.pending.items() if now - sent_at > SKIP_CONFIRM_TIMEOUT_S]
        if expired:
            logger.error(
                "[%s] Printer did not confirm skipping objects %s within %.0fs; they may still be printed",
                client.serial_number,
                sorted(expired),
                SKIP_CONFIRM_TIMEOUT_S,
            )
            for oid in expired:
                state.pending.pop(oid, None)
        active = {sequence for sequence, _ in state.pending.values()}
        state.commands = {sequence: ids for sequence, ids in state.commands.items() if sequence in active}
