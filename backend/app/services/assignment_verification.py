"""Read back slot configuration without confusing publication with printer acceptance."""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class _VerificationState:
    pending: dict[tuple[int, int], dict] = field(default_factory=dict)
    lock: Any = field(default_factory=threading.RLock)


def _color(value: object) -> str:
    rgb = str(value or "").strip().lstrip("#").upper()[:6]
    return rgb if len(rgb) == 6 and all(char in "0123456789ABCDEF" for char in rgb) else ""


class AssignmentVerificationMixin:
    """Shared by the MQTT client; callbacks run on its message-processing thread."""

    ASSIGNMENT_VERIFY_TIMEOUT = 30.0
    on_assignment_verified: Callable[[int, int, bool, dict], None] | None = None

    @property
    def _assignment_verification(self) -> _VerificationState:
        state = self.__dict__.get("_slot_verifier")
        if state is None:
            state = self.__dict__.setdefault("_slot_verifier", _VerificationState())
        return state

    @property
    def _pending_assignments(self) -> dict:
        return self._assignment_verification.pending

    def clear_assignment_verifications(self) -> None:
        state = self._assignment_verification
        with state.lock:
            state.pending.clear()

    def register_assignment_verification(
        self,
        ams_id: int,
        tray_id: int,
        tray_info_idx: str,
        tray_color: str,
        cali_idx: int | None,
    ) -> None:
        """Remember prepared values; a later telemetry push must report them."""
        preset = str(tray_info_idx or "").strip().upper()
        if not preset or (str(tray_color or "").strip() and not _color(tray_color)):
            return
        state = self._assignment_verification
        with state.lock:
            state.pending[(ams_id, tray_id)] = {
                "tray_info_idx": preset,
                "tray_color": _color(tray_color),
                "cali_idx": cali_idx,
                "deadline": time.monotonic() + self.ASSIGNMENT_VERIFY_TIMEOUT,
                "last_seen_idx": None,
                "saw_tray": False,
            }

    def _find_verify_tray(self, ams_id: int, tray_id: int) -> dict | None:
        return find_reported_tray(self.state, ams_id, tray_id)

    def check_assignment_push(self, payload: dict) -> None:
        """Ignore command acknowledgements; check normalized AMS/external telemetry only."""
        if payload.get("command") not in (None, "push_status"):
            return
        if any(key in payload for key in ("ams", "vt_tray", "vir_slot")):
            self._check_assignment_verifications()

    def _check_assignment_verifications(self) -> None:
        """Resolve once on matching telemetry, or after the deadline on a later push.

        A silent printer remains unconfirmed. Registry changes and removal share
        a lock, so a message cannot discard a newer assignment to the same slot.
        """
        state = self._assignment_verification
        events = []
        now = time.monotonic()
        with state.lock:
            for (ams_id, tray_id), want in list(state.pending.items()):
                tray = self._find_verify_tray(ams_id, tray_id)
                actual = str((tray or {}).get("tray_info_idx") or "").strip().upper()
                if tray is not None:
                    want["saw_tray"] = True
                    want["last_seen_idx"] = actual
                matches = actual == want["tray_info_idx"] and (
                    not want["tray_color"] or _color((tray or {}).get("tray_color")) == want["tray_color"]
                )
                if matches:
                    wanted_cali = want["cali_idx"]
                    actual_cali = (tray or {}).get("cali_idx")
                    try:
                        actual_cali = (
                            int(actual_cali) if actual_cali is not None and not isinstance(actual_cali, bool) else None
                        )
                    except (TypeError, ValueError):
                        actual_cali = None
                    k_matches = wanted_cali is None or wanted_cali < 0 or actual_cali == wanted_cali
                    if not k_matches and now < want["deadline"]:
                        continue
                    detail = {
                        "tray_info_idx": actual,
                        "kprofile_applied": k_matches,
                    }
                    events.append((ams_id, tray_id, True, detail))
                elif now >= want["deadline"]:
                    events.append(
                        (
                            ams_id,
                            tray_id,
                            False,
                            {
                                "expected_tray_info_idx": want["tray_info_idx"],
                                "actual_tray_info_idx": want["last_seen_idx"],
                                "saw_tray": want["saw_tray"],
                            },
                        )
                    )
                else:
                    continue
                state.pending.pop((ams_id, tray_id), None)
        for event in events:
            self._fire_assignment_verified(*event)

    def _fire_assignment_verified(self, ams_id: int, tray_id: int, verified: bool, detail: dict) -> None:
        logger.info(
            "Slot configuration %s: AMS%s-T%s %s", "verified" if verified else "not confirmed", ams_id, tray_id, detail
        )
        if self.on_assignment_verified:
            try:
                self.on_assignment_verified(ams_id, tray_id, verified, detail)
            except Exception:
                logger.exception("Slot verification callback failed")


def find_reported_tray(state, ams_id: int, tray_id: int) -> dict | None:
    raw = getattr(state, "raw_data", None) or {}
    if not isinstance(raw, dict):
        return None
    if ams_id == 255:
        trays = raw.get("vt_tray") or []
        trays = [trays] if isinstance(trays, dict) else trays
        for tray in trays if isinstance(trays, list) else []:
            if isinstance(tray, dict) and str(tray.get("id", 254)) == str(254 + tray_id):
                return tray
        return None
    units = raw.get("ams") or []
    if isinstance(units, dict):
        units = units.get("ams") or []
    for unit in units if isinstance(units, list) else []:
        if not isinstance(unit, dict) or str(unit.get("id")) != str(ams_id):
            continue
        raw_trays = unit.get("tray") or []
        trays = [tray for tray in raw_trays if isinstance(tray, dict)] if isinstance(raw_trays, list) else []
        for tray in trays:
            if str(tray.get("id")) == str(tray_id):
                return tray
        if ams_id >= 128 and len(trays) == 1:
            return trays[0]
    return None


def register_sent_assignment(client, state, ams_id, tray_id, preset, color, cali_idx, *, request_update=True):
    """Start read-back for a sent configuration; empty slots cannot echo it yet."""
    from backend.app.services.ams_slot_presence import spool_present

    tray = find_reported_tray(state, ams_id, tray_id)
    present = spool_present(tray)
    if (
        not str(preset or "").strip()
        or present is False
        or (present is not True and (tray or {}).get("state") in (9, 10))
    ):
        return
    client.register_assignment_verification(
        ams_id=ams_id,
        tray_id=tray_id,
        tray_info_idx=preset,
        tray_color=color,
        cali_idx=cali_idx,
    )
    if request_update:
        client.request_status_update()
