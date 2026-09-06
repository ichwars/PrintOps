"""Translate domain filament names into printer-safe AMS protocol values."""

import re

from backend.app.utils.filament_ids import GENERIC_FILAMENT_IDS, MATERIAL_TEMPS

# Product lines (PLA+, PLA Silk, PolyTerra PLA) stay out of this list: they
# belong in tray_sub_brands. Filled and foamed materials remain distinct types.
_PRINTER_TYPES: tuple[str, ...] = (
    "PLA-AERO",
    "ASA-AERO",
    "PAHT-CF",
    "PA12-CF",
    "PETG-CF",
    "PPS-CF",
    "PPS-GF",
    "PPA-CF",
    "PPA-GF",
    "PLA-CF",
    "PLA-GF",
    "PA6-CF",
    "PA6-GF",
    "ABS-GF",
    "ASA-CF",
    "ASA-GF",
    "PET-CF",
    "PC-ABS",
    "PA-CF",
    "PC-CF",
    "PP-CF",
    "PP-GF",
    "PE-CF",
    "PCTG",
    "PETG",
    "BVOH",
    "HIPS",
    "PEEK",
    "PLA",
    "PHA",
    "ABS",
    "ASA",
    "TPU",
    "PVA",
    "PPS",
    "EVA",
    "PEI",
    "PC",
    "PA",
    "PP",
    "PE",
)
_TYPE_ALIASES = {"NYLON": "PA"}
_PRINTER_TYPE_SET = frozenset(_PRINTER_TYPES)
_TYPES_LONGEST_FIRST = tuple(sorted((*_PRINTER_TYPES, *_TYPE_ALIASES), key=len, reverse=True))
_WORDS = re.compile(r"[^A-Z0-9+\-]+")


def _word_names_type(word: str, candidate: str) -> bool:
    if word == candidate:
        return True
    if len(candidate) < 3:
        return False
    if word.startswith(candidate) and not word[len(candidate)].isalpha():
        return True
    return word.endswith(candidate)


def printer_filament_type(material: str | None) -> str:
    """Return an AMS-supported type, or the original text when unknown."""
    text = (material or "").strip()
    if not text:
        return ""

    upper = text.upper()
    if upper in _PRINTER_TYPE_SET:
        return upper
    if upper in _TYPE_ALIASES:
        return _TYPE_ALIASES[upper]

    words = [word for word in _WORDS.split(upper) if word]
    for first, second in zip(words, words[1:], strict=False):
        joined = f"{first}-{second}"
        if joined in _PRINTER_TYPE_SET:
            return joined
        if joined in _TYPE_ALIASES:
            return _TYPE_ALIASES[joined]

    for candidate in _TYPES_LONGEST_FIRST:
        if any(_word_names_type(word, candidate) for word in words):
            return _TYPE_ALIASES.get(candidate, candidate)
    return text


def generic_filament_id(material: str | None, tray_type: str | None = None) -> str:
    """Resolve a generic preset without discarding a product-specific match."""
    raw = (material or "").upper().strip()
    return (
        GENERIC_FILAMENT_IDS.get(raw)
        or GENERIC_FILAMENT_IDS.get(raw.split("-")[0].split(" ")[0])
        or GENERIC_FILAMENT_IDS.get((tray_type or "").upper().strip())
        or ""
    )


def nozzle_temp_range(material: str | None, tray_type: str | None) -> tuple[int, int]:
    """Prefer the product range, then protocol type, then base material."""
    base = (tray_type or "").split("-")[0]
    for key in (material, tray_type, base):
        temperatures = MATERIAL_TEMPS.get((key or "").upper().strip())
        if temperatures:
            return temperatures
    return (200, 240)


def tray_sub_brand(brand: str | None, material: str | None, subtype: str | None) -> str:
    """Keep domain/product wording on the descriptive AMS field."""
    return " ".join(part for part in (brand, material, subtype) if part)


_MATERIAL_NAMES = frozenset(MATERIAL_TEMPS) | frozenset(GENERIC_FILAMENT_IDS)
_PRESET_ID_SHAPE = re.compile(r"^(?:GF|P)[A-Za-z0-9_]*$")


def is_material_name(value: str | None) -> bool:
    """Return whether a candidate filament id is really material wording."""
    text = (value or "").strip()
    if not text:
        return False
    if text.upper() in _MATERIAL_NAMES:
        return True
    if _PRESET_ID_SHAPE.match(text):
        return False
    reduced = printer_filament_type(text).upper()
    if reduced in _MATERIAL_NAMES:
        return True
    return reduced.split("-")[0] in _MATERIAL_NAMES
