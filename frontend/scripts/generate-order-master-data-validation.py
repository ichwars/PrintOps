from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pycountry

PYCOUNTRY_VERSION = "26.2.16"
UNICODE_VERSION = "15.1.0"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.core.text_normalization import unicodedata  # noqa: E402

CASEFOLD_SOURCE = ROOT / "backend" / "app" / "core" / "CaseFolding-15.1.0.txt"
BACKEND_TARGET = ROOT / "backend" / "app" / "core" / "unicode_casefold_15_1.py"
FRONTEND_TARGET = Path(__file__).parents[1] / "src" / "lib" / "orderMasterDataValidation.ts"


def assigned_ranges() -> tuple[list[tuple[int, int]], int]:
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    count = 0
    for code_point in range(0x110000):
        assigned = unicodedata.category(chr(code_point)) != "Cn"
        if assigned:
            count += 1
            if start is None:
                start = code_point
        elif start is not None:
            ranges.append((start, code_point - 1))
            start = None
    if start is not None:
        ranges.append((start, 0x10FFFF))
    return ranges, count


def parse_full_casefold_mappings() -> tuple[dict[int, str], str]:
    """Read the vendored Unicode default full casefold mappings (C and F)."""
    source = CASEFOLD_SOURCE.read_bytes()
    if not source.startswith(b"# CaseFolding-15.1.0.txt\n"):
        raise SystemExit(f"Expected Unicode 15.1 CaseFolding data: {CASEFOLD_SOURCE}")

    mappings: dict[int, str] = {}
    for raw_line in source.decode("utf-8").splitlines():
        fields = [field.strip() for field in raw_line.partition("#")[0].split(";") if field.strip()]
        if len(fields) != 3:
            continue
        code_point, status, mapping = fields
        if status not in {"C", "F"}:
            continue
        value = "".join(chr(int(item, 16)) for item in mapping.split())
        source_character = chr(int(code_point, 16))
        if value == source_character:
            continue
        if status == "F" or int(code_point, 16) not in mappings:
            mappings[int(code_point, 16)] = value
    return mappings, hashlib.sha256(source).hexdigest()


def format_ranges(ranges: list[tuple[int, int]]) -> str:
    values = [value for pair in ranges for value in pair]
    lines = []
    for index in range(0, len(values), 16):
        lines.append("  " + ", ".join(f"0x{value:X}" for value in values[index:index + 16]) + ",")
    return "\n".join(lines)


def format_code_list(values: list[str]) -> str:
    return "\n".join(
        "  " + ", ".join(json.dumps(value) for value in values[index:index + 12]) + ","
        for index in range(0, len(values), 12)
    )


def format_typescript_mappings(mappings: dict[int, str]) -> str:
    return "\n".join(
        f"  {json.dumps(chr(code_point), ensure_ascii=True)}: {json.dumps(value, ensure_ascii=True)},"
        for code_point, value in mappings.items()
    )


def python_literal(value: str) -> str:
    escaped = value.encode("unicode_escape").decode("ascii")
    return '"' + escaped.replace('"', '\\"') + '"'


def format_python_mappings(mappings: dict[int, str]) -> str:
    return "\n".join(
        f"    {python_literal(chr(code_point))}: {python_literal(value)},"
        for code_point, value in mappings.items()
    )


def backend_output(mappings: dict[int, str], source_hash: str) -> str:
    return f'''\"\"\"Generated Unicode 15.1 default full casefold mappings.

Source: CaseFolding-15.1.0.txt from https://www.unicode.org/Public/15.1.0/ucd/
SHA-256: {source_hash}
Do not edit manually; run frontend/scripts/generate-order-master-data-validation.py.
\"\"\"

CASEFOLD_UNICODE_VERSION = "{UNICODE_VERSION}"

# Every nonidentity default full casefold mapping from the vendored UCD source.
CASEFOLD_15_1: dict[str, str] = {{
{format_python_mappings(mappings)}
}}
'''


def frontend_output(
    countries: list[str],
    currencies: list[str],
    ranges: list[tuple[int, int]],
    assigned_count: int,
    mappings: dict[int, str],
    source_hash: str,
) -> str:
    return f'''/**
 * Generated for the pinned production Unicode contract from pycountry {PYCOUNTRY_VERSION},
 * unicodedata2 {UNICODE_VERSION}, and Unicode CaseFolding-15.1.0.txt.
 * CaseFolding source SHA-256: {source_hash}
 * ({assigned_count} assigned code points in {len(ranges)} ranges).
 * Keep synchronized with backend/app/core/text_normalization.py.
 */
export const orderMasterDataCountryCodes = Object.freeze([
{format_code_list(countries)}
]);
export const orderMasterDataCurrencyCodes = Object.freeze([
{format_code_list(currencies)}
]);

const ISO_COUNTRY_CODES = new Set(orderMasterDataCountryCodes);
const ISO_CURRENCY_CODES = new Set(orderMasterDataCurrencyCodes);

const UNICODE_15_1_ASSIGNED_RANGES = new Uint32Array([
{format_ranges(ranges)}
]);

// Every nonidentity default full casefold mapping from Unicode 15.1.
const FULL_CASEFOLD_MAPPINGS: Readonly<Record<string, string>> = {{
{format_typescript_mappings(mappings)}
}};

export const orderMasterDataValidationMetadata = Object.freeze({{
  pycountryVersion: '{PYCOUNTRY_VERSION}',
  pythonVersion: '3.10+',
  normalizationOwner: 'Unicode CaseFolding-15.1.0.txt',
  unicodeVersion: '{UNICODE_VERSION}',
  countryCodeCount: ISO_COUNTRY_CODES.size,
  currencyCodeCount: ISO_CURRENCY_CODES.size,
  assignedCodePointCount: {assigned_count},
  assignedRangeCount: UNICODE_15_1_ASSIGNED_RANGES.length / 2,
  fullCasefoldMappingCount: Object.keys(FULL_CASEFOLD_MAPPINGS).length,
}});

export function isIsoCountryCode(value: string): boolean {{
  return ISO_COUNTRY_CODES.has(value.toUpperCase());
}}

export function isIsoCurrencyCode(value: string): boolean {{
  return ISO_CURRENCY_CODES.has(value.toUpperCase());
}}

function isUnicode151Assigned(codePoint: number): boolean {{
  let low = 0;
  let high = UNICODE_15_1_ASSIGNED_RANGES.length / 2 - 1;

  while (low <= high) {{
    const middle = Math.floor((low + high) / 2);
    const start = UNICODE_15_1_ASSIGNED_RANGES[middle * 2];
    const end = UNICODE_15_1_ASSIGNED_RANGES[middle * 2 + 1];
    if (codePoint < start) high = middle - 1;
    else if (codePoint > end) low = middle + 1;
    else return true;
  }}
  return false;
}}

function normalizeAssignedRun(value: string): string {{
  return Array.from(value.normalize('NFKC'), (character) =>
    FULL_CASEFOLD_MAPPINGS[character] ?? character,
  ).join('');
}}

export function normalizeNfkcCasefold(value: string): string {{
  let assignedRun = '';
  let normalized = '';

  for (const character of value) {{
    const codePoint = character.codePointAt(0);
    if (codePoint !== undefined && isUnicode151Assigned(codePoint)) {{
      assignedRun += character;
    }} else {{
      normalized += normalizeAssignedRun(assignedRun) + character;
      assignedRun = '';
    }}
  }}
  return normalized + normalizeAssignedRun(assignedRun);
}}
'''


def write_or_check(path: Path, output: str, *, check: bool) -> None:
    expected = output.encode("utf-8")
    if check:
        if not path.exists() or path.read_bytes() != expected:
            raise SystemExit(f"Generated Unicode output is stale: {path}")
        return
    path.write_bytes(expected)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate pinned order master-data validation.")
    parser.add_argument("--check", action="store_true", help="Exit nonzero when generated outputs differ.")
    args = parser.parse_args()

    if pycountry.__version__ != PYCOUNTRY_VERSION:
        raise SystemExit(f"Expected pycountry {PYCOUNTRY_VERSION}, received {pycountry.__version__}")
    if unicodedata.unidata_version != UNICODE_VERSION:
        raise SystemExit(f"Expected Unicode {UNICODE_VERSION}, received {unicodedata.unidata_version}")

    countries = sorted(country.alpha_2 for country in pycountry.countries)
    currencies = sorted(currency.alpha_3 for currency in pycountry.currencies)
    ranges, assigned_count = assigned_ranges()
    mappings, source_hash = parse_full_casefold_mappings()
    write_or_check(BACKEND_TARGET, backend_output(mappings, source_hash), check=args.check)
    write_or_check(
        FRONTEND_TARGET,
        frontend_output(countries, currencies, ranges, assigned_count, mappings, source_hash),
        check=args.check,
    )
    action = "verified" if args.check else "generated"
    print(
        f"{action}: countries={len(countries)} currencies={len(currencies)} assigned={assigned_count} "
        f"ranges={len(ranges)} full_casefold_mappings={len(mappings)}"
    )


if __name__ == "__main__":
    main()
