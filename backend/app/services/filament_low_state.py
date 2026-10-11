"""Restart-safe per-slot and per-provider low-filament notification outcomes."""

import json
from datetime import datetime
from hashlib import sha256
from typing import TypedDict

from sqlalchemy import select

from backend.app.models.settings import Settings

STATE_KEY = "filament_low_alert_state"
AlertKey = tuple[str, int, int, int, int]


class DeliveryState(TypedDict):
    identity: str
    spool_identity: str
    delivered: bool
    digest: bool


def provider_identity(provider) -> str:
    if provider.created_at is not None:
        return provider.created_at.isoformat()
    # Legacy rows may have no creation timestamp. Keep configuration out of Settings.
    destination = json.dumps([provider.provider_type, provider.config])
    return "legacy:" + sha256(destination.encode()).hexdigest()


def spool_identity(spool) -> str:
    created_at = spool.get("created_at") if isinstance(spool, dict) else spool.created_at
    if isinstance(created_at, datetime):
        return created_at.isoformat()
    # Spoolman exposes its registered timestamp through the mapped created_at field.
    return created_at if isinstance(created_at, str) else ""


def _alert_key(raw: str) -> AlertKey | None:
    try:
        key = json.loads(raw)
    except (TypeError, ValueError, RecursionError):
        return None
    if not isinstance(key, list) or len(key) != 5:
        return None
    if key[0] not in ("internal", "spoolman") or any(type(value) is not int for value in key[1:]):
        return None
    if key[1] <= 0 or key[2] < 0 or key[3] < 0 or key[4] <= 0:
        return None
    return tuple(key)


def _clean_state(raw: str) -> dict[AlertKey, dict[int, DeliveryState]]:
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError, RecursionError):
        return {}
    if not isinstance(decoded, dict):
        return {}
    result = {}
    for identity, providers in decoded.items():
        key = _alert_key(identity)
        if key is None or not isinstance(providers, dict):
            continue
        clean = {}
        for provider_id, state in providers.items():
            try:
                pid = int(provider_id)
            except (TypeError, ValueError):
                continue
            if pid <= 0 or str(pid) != provider_id or not isinstance(state, dict):
                continue
            clean[pid] = {
                "identity": state.get("identity") if isinstance(state.get("identity"), str) else "",
                "spool_identity": state.get("spool_identity") if isinstance(state.get("spool_identity"), str) else "",
                "delivered": state.get("delivered") is True,
                "digest": state.get("digest") is True,
            }
        result[key] = clean
    return result


class FilamentLowState:
    def __init__(self):
        self.alerts: dict[AlertKey, dict[int, DeliveryState]] = {}
        self._loaded = False
        self._persisted = ""

    def _serialize(self) -> str:
        return json.dumps(
            {
                json.dumps(key): {str(pid): state for pid, state in providers.items()}
                for key, providers in self.alerts.items()
            },
            sort_keys=True,
        )

    async def load(self, db) -> None:
        if self._loaded:
            return
        raw = await db.scalar(select(Settings.value).where(Settings.key == STATE_KEY))
        self.alerts = _clean_state(raw)
        self._persisted = self._serialize()
        self._loaded = True

    def providers_for(self, key: AlertKey, eligible: dict[int, str], spool_identity: str) -> dict[int, DeliveryState]:
        # Disabled or out-of-scope providers keep their history until actual recovery.
        current = self.alerts.setdefault(key, {})
        for pid, identity in eligible.items():
            if (
                pid not in current
                or current[pid]["identity"] != identity
                or current[pid]["spool_identity"] != spool_identity
            ):
                # Recreated providers or spools can reuse a deleted SQLite row ID.
                current[pid] = {
                    "identity": identity,
                    "spool_identity": spool_identity,
                    "delivered": False,
                    "digest": False,
                }
        return current

    def reconcile(self, mode: str, observed_printers: set[int], active: set[AlertKey]) -> None:
        # An inactive mode or unobserved printer supplies no evidence of recovery.
        self.alerts = {
            key: providers
            for key, providers in self.alerts.items()
            if key[0] != mode or key[1] not in observed_printers or key in active
        }

    async def save(self, db) -> None:
        serialized = self._serialize()
        if serialized == self._persisted:
            return
        row = await db.scalar(select(Settings).where(Settings.key == STATE_KEY))
        if row is None:
            db.add(Settings(key=STATE_KEY, value=serialized))
        else:
            row.value = serialized
        await db.commit()
        self._persisted = serialized
