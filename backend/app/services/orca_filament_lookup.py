"""Best-effort Orca Cloud profile identity for printer slots."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.permissions import Permission
from backend.app.models.user import User

logger = logging.getLogger(__name__)

# Orca Cloud profile ids are UUIDs, the one preset reference in this codebase
# with no letter prefix to key off. A spool stores the bare id (the spool form
# persists ``preset.setting_id`` verbatim), so shape is all there is to go on.
_ORCA_PROFILE_ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


@dataclass(frozen=True)
class OrcaFilamentLookup:
    """Outcome of resolving an Orca Cloud profile to a printer filament id.

    ``filament_id`` is empty when nothing usable was found; ``reason`` then says
    why, so a caller in front of a user can say so instead of quietly sending
    a generic id (#3216). ``source`` is ``"own"`` for the profile's own id,
    ``"inherited"`` for one taken from a parent.
    """

    filament_id: str = ""
    name: str | None = None
    filament_type: str | None = None
    source: str = ""
    reason: str = ""


# How many ``inherits`` hops to follow before giving up. Orca presets are one
# or two deep in practice; the cap only guards against a cycle in hand-edited
# profiles.
_MAX_INHERITS_DEPTH = 5


def _content_filament_id(content: dict) -> str:
    raw = content.get("filament_id")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    return valid_filament_id(raw)


def _catalog_filament_id(preset_name: str) -> str:
    """Bambu catalog id for a Bambu system preset name, or ``""``.

    An Orca profile that inherits a system preset ("Bambu PLA Basic @BBL H2D")
    carries no id of its own. Its parent's id is the one the printer and the
    slicer both know -- OrcaSlicer since 2.5 translates the Bambu catalog ids
    at the printer boundary -- so it beats a generic for the material.
    """
    from backend.app.api.routes.cloud import _BUILTIN_FILAMENT_NAMES

    base = preset_name.split("@")[0].strip().lstrip("#").strip().lower()
    if not base:
        return ""
    for fid, fname in _BUILTIN_FILAMENT_NAMES.items():
        if fname.lower() == base:
            return fid
    return ""


async def lookup_orca_filament_id(
    db: AsyncSession,
    current_user: User | None,
    profile_id: str,
) -> OrcaFilamentLookup:
    """Look up the filament id an Orca Cloud profile puts in an AMS slot.

    OrcaSlicer resolves a slot to a preset by ``filament_id`` alone, so this is
    the value that decides whether "Sync filaments" finds the user's profile or
    falls back to Generic (#3216). Tried in order: the profile's own id; the
    nearest parent among the user's Orca profiles that has one; the Bambu
    catalog id of a Bambu system parent.

    Best-effort by construction: this runs inside spool assignment and slot
    configuration, so a missing pairing, a revoked token or a lapsed permission
    must degrade to the caller's fallback rather than fail the request. That is
    also why ``clear_on_auth_failure=False`` -- Orca reports every refresh
    rejection with one composite reason, so this caller cannot tell a real
    revocation from a lost rotation race and must not wipe a working pairing on
    it. The Orca Cloud routes hit the same failure in front of a user and clear
    there.
    """
    if current_user is not None and not current_user.has_permission(Permission.ORCA_CLOUD_AUTH.value):
        logger.info("Orca filament lookup skipped for %r: caller lacks orca_cloud:auth", profile_id)
        return OrcaFilamentLookup(reason="no_permission")

    svc = None
    try:
        if current_user is None:
            from backend.app.core.auth import is_auth_enabled

            if await is_auth_enabled(db):
                return OrcaFilamentLookup(reason="no_permission")
        from backend.app.api.routes.orca_cloud import _build_authenticated_service

        svc = await _build_authenticated_service(db, current_user, clear_on_auth_failure=False)
        profile = await svc.get_profile(profile_id)
        content = profile.get("content") if isinstance(profile, dict) else None
        if not isinstance(content, dict):
            logger.info("Orca filament lookup for %r: profile has no content", profile_id)
            return OrcaFilamentLookup(reason="no_filament_id")
        raw_name = profile.get("name")
        name = raw_name if isinstance(raw_name, str) and raw_name else None
        filament_type = _preset_filament_type(content.get("filament_type"))

        own = _content_filament_id(content)
        if own:
            logger.info("Orca filament lookup for %r: own filament_id %r", profile_id, own)
            return OrcaFilamentLookup(own, name, filament_type, source="own")

        parent = _preset_filament_type(content.get("inherits")) or ""
        by_name: dict[str, dict] | None = None
        for _ in range(_MAX_INHERITS_DEPTH):
            if not parent:
                break
            if by_name is None:
                # One more pull, only for a profile that needs its parent. A
                # failure here keeps the name and type already read, as the
                # lookup returned them before it followed parents.
                by_name = {}
                try:
                    entries = await svc.list_profiles()
                except Exception as e:
                    logger.info("Orca filament lookup for %r: could not read its parents: %s", profile_id, e)
                    return OrcaFilamentLookup(name=name, filament_type=filament_type, reason="lookup_failed")
                for entry in entries:
                    entry_content = entry.get("content") if isinstance(entry, dict) else None
                    if not isinstance(entry_content, dict):
                        continue
                    for key in (entry.get("name"), entry_content.get("name")):
                        if isinstance(key, str) and key:
                            by_name.setdefault(key, entry_content)
            parent_content = by_name.get(parent)
            if parent_content is None:
                catalog = _catalog_filament_id(parent)
                if catalog:
                    logger.info(
                        "Orca filament lookup for %r: catalog filament_id %r of system parent %r",
                        profile_id,
                        catalog,
                        parent,
                    )
                    return OrcaFilamentLookup(catalog, name, filament_type, source="inherited")
                break
            inherited = _content_filament_id(parent_content)
            if inherited:
                logger.info(
                    "Orca filament lookup for %r: filament_id %r inherited from %r", profile_id, inherited, parent
                )
                return OrcaFilamentLookup(inherited, name, filament_type, source="inherited")
            parent = _preset_filament_type(parent_content.get("inherits")) or ""

        logger.info("Orca filament lookup for %r: no filament_id on the profile or its parents", profile_id)
        return OrcaFilamentLookup(name=name, filament_type=filament_type, reason="no_filament_id")
    except Exception as e:
        # INFO, not DEBUG: this is the line that explains a slot coming out as
        # Generic in a support bundle (#3216).
        logger.info("Orca filament lookup failed for %r: %s", profile_id, e)
        return OrcaFilamentLookup(reason="lookup_failed")
    finally:
        # A raise in `finally` escapes the `except` above, so guard it: closing
        # an httpx client must never be what fails a spool assignment.
        if svc is not None:
            try:
                await svc.close()
            except Exception as e:  # noqa: BLE001 - close() is best-effort
                logger.debug("Orca client close failed after lookup of %r: %s", profile_id, e)


def _preset_filament_type(raw: object) -> str | None:
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def valid_filament_id(raw: object) -> str:
    """Reject UUIDs, material names and cloud setting IDs at the boundary."""
    if not isinstance(raw, str):
        return ""
    raw = raw.strip()
    return raw if len(raw) <= 32 and re.fullmatch(r"(?:GF[A-Za-z]\d+|P[0-9a-fA-F]+)", raw) else ""


_ORCA_GENERIC_IDS = {
    "PLA": "GFL99",
    "PLA-CF": "GFL98",
    "PLA SILK": "GFL96",
    "PLA HIGH SPEED": "GFL95",
    "PETG": "GFG99",
    "PETG HF": "GFG96",
    "PETG-CF": "GFG98",
    "PCTG": "GFG97",
    "ABS": "GFB99",
    "ASA": "GFB98",
    "PC": "GFC99",
    "PA": "GFN99",
    "PA-CF": "GFN98",
    "NYLON": "GFN99",
    "TPU": "GFU99",
    "PVA": "GFS99",
    "HIPS": "GFS98",
    "PE": "GFP99",
    "PP": "GFP97",
}


def _orca_generic_filament_id(material: str) -> str:
    """The generic for a material, tried as given, without a CF suffix, without
    a trailing "+", then by its first word -- the dialog's order."""
    material = (material or "").upper().strip()
    return (
        _ORCA_GENERIC_IDS.get(material)
        or _ORCA_GENERIC_IDS.get(re.sub(r"[-\s]?CF$", "", material))
        or _ORCA_GENERIC_IDS.get(re.sub(r"\+$", "", material))
        or _ORCA_GENERIC_IDS.get(re.split(r"[-\s]", material)[0])
        or ""
    )


async def orca_cloud_caller(request, db, current_user):
    """Resolve an API key's owner through the existing cloud scope fence."""
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    from backend.app.api.routes.cloud import _cloud_api_key_gate

    auth = request.headers.get("authorization", "").split(" ", 1)
    credentials = HTTPAuthorizationCredentials(scheme=auth[0], credentials=auth[1]) if len(auth) == 2 else None
    try:
        await _cloud_api_key_gate(
            request=request, db=db, credentials=credentials, x_api_key=request.headers.get("x-api-key")
        )
    except HTTPException:
        return None, False
    return current_user or getattr(request.state, "api_key_owner", None), True
