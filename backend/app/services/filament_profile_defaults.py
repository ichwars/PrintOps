"""Find product defaults and copy their missing settings into new spools."""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.filament_profile_default import FilamentProfileDefault
from backend.app.models.printer import Printer
from backend.app.models.spool_filament_preset import SpoolFilamentPreset, SpoolmanFilamentPreset
from backend.app.models.spool_k_profile import SpoolKProfile
from backend.app.models.spoolman_k_profile import SpoolmanKProfile
from backend.app.schemas.filament_profile_default import ProfileProduct

_PRODUCT_FIELDS = ("brand", "material", "subtype", "color_name")
_PRESET_FIELDS = ("slicer_filament", "slicer_filament_name")


def product_key(spool, *, all_colors: bool = False) -> str:
    def value(name):
        return spool.get(name) if isinstance(spool, dict) else getattr(spool, name)

    identity = [(value(name) or "").strip().casefold() for name in _PRODUCT_FIELDS]
    if all_colors or (isinstance(spool, dict) and spool.get("color_name_is_synthesized")):
        identity[-1] = ""
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def calibration_key(row):
    if isinstance(row, dict):
        return row["printer_id"], row["extruder"], row["nozzle_diameter"], row["nozzle_type"] or ""
    return row.printer_id, row.extruder, row.nozzle_diameter, row.nozzle_type or ""


async def matching_defaults(db: AsyncSession, spool) -> list[FilamentProfileDefault]:
    general, exact = product_key(spool, all_colors=True), product_key(spool)
    rows = {
        row.product_key: row
        for row in await db.scalars(
            select(FilamentProfileDefault).where(FilamentProfileDefault.product_key.in_({general, exact}))
        )
    }
    return [rows[key] for key in dict.fromkeys((general, exact)) if key in rows]


async def _valid_calibrations(db, rows, printer_scope):
    calibrations = {calibration_key(profile): profile for row in rows for profile in row.k_profiles}
    candidates = {profile["printer_id"] for profile in calibrations.values()}
    if printer_scope is not None:
        candidates &= set(printer_scope)
    if not candidates:
        return {}
    printer_ids = set(await db.scalars(select(Printer.id).where(Printer.id.in_(candidates))))
    return {key: value for key, value in calibrations.items() if key[0] in printer_ids}


async def copy_profiles(db, spool, rows, printer_scope=None, *, client=None) -> bool:
    if not rows:
        return False
    external = client is not None
    if external:
        id_value = spool["id"]
        preset_model, preset_id = SpoolmanFilamentPreset, "spoolman_spool_id"
        calibration_model, calibration_id = SpoolmanKProfile, "spoolman_spool_id"
    else:
        await db.flush()
        id_value = spool.id
        preset_model, preset_id = SpoolFilamentPreset, "spool_id"
        calibration_model, calibration_id = SpoolKProfile, "spool_id"
    presets = {preset["printer_model"]: preset for row in rows for preset in row.presets}
    calibrations = await _valid_calibrations(db, rows, printer_scope)
    existing_presets = await db.scalars(
        select(preset_model.printer_model).where(getattr(preset_model, preset_id) == id_value)
    )
    existing_calibrations = await db.scalars(
        select(calibration_model).where(getattr(calibration_model, calibration_id) == id_value)
    )
    new_presets = [
        preset_model(**{preset_id: id_value}, **presets[key]) for key in presets.keys() - set(existing_presets)
    ]
    new_calibrations = [
        calibration_model(**{calibration_id: id_value}, **calibrations[key])
        for key in calibrations.keys() - {calibration_key(profile) for profile in existing_calibrations}
    ]
    db.add_all([*new_presets, *new_calibrations])
    generic = next((row for row in reversed(rows) if row.slicer_filament), None)
    changed = bool(new_presets or new_calibrations)
    if generic is None:
        return changed
    if not external and not spool.slicer_filament:
        spool.slicer_filament, spool.slicer_filament_name = generic.slicer_filament, generic.slicer_filament_name
        return True
    if external and not spool.get("slicer_filament"):
        extra = {}
        for field in _PRESET_FIELDS:
            if (value := getattr(generic, field)) is not None:
                key = f"bambu_{field}"
                await client.ensure_extra_field(key)
                extra[key] = json.dumps(value)
        updated = await client.merge_spool_extra(id_value, extra)
        from backend.app.api.routes._spoolman_helpers import _map_spoolman_spool

        spool.update(_map_spoolman_spool(updated))
        return True
    return changed


async def apply_product_defaults(db, spool, printer_scope=None, *, client=None) -> bool:
    rows = await matching_defaults(db, spool)
    return await copy_profiles(db, spool, rows, printer_scope, client=client)


def profile_product(row) -> ProfileProduct:
    return ProfileProduct(**{name: getattr(row, name) for name in _PRODUCT_FIELDS})
