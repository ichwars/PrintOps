from __future__ import annotations

import argparse
import json
import sys
import unicodedata as stdlib_unicodedata
from pathlib import Path

import pycountry

PYCOUNTRY_VERSION = "26.2.16"
UNICODE_VERSION = "15.1.0"

if stdlib_unicodedata.unidata_version == UNICODE_VERSION:
    unicodedata = stdlib_unicodedata
else:
    import unicodedata2 as unicodedata


def assigned_ranges() -> tuple[list[tuple[int, int]], int]:
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    count = 0
    for code_point in range(sys.maxunicode + 1):
        assigned = unicodedata.category(chr(code_point)) != "Cn"
        if assigned:
            count += 1
            if start is None:
                start = code_point
        elif start is not None:
            ranges.append((start, code_point - 1))
            start = None
    if start is not None:
        ranges.append((start, sys.maxunicode))
    return ranges, count


def format_ranges(ranges: list[tuple[int, int]]) -> str:
    values = [value for pair in ranges for value in pair]
    lines = []
    for index in range(0, len(values), 16):
        lines.append("  " + ", ".join(f"0x{value:X}" for value in values[index:index + 16]) + ",")
    return "\n".join(lines)


def format_overrides(overrides: dict[str, str]) -> str:
    return "\n".join(
        f"  {json.dumps(key, ensure_ascii=True)}: {json.dumps(value, ensure_ascii=True)},"
        for key, value in overrides.items()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate frontend order master-data validation.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero when the generated target differs without writing it.",
    )
    args = parser.parse_args()

    if pycountry.__version__ != PYCOUNTRY_VERSION:
        raise SystemExit(f"Expected pycountry {PYCOUNTRY_VERSION}, received {pycountry.__version__}")
    if unicodedata.unidata_version != UNICODE_VERSION:
        raise SystemExit(f"Expected Unicode {UNICODE_VERSION}, received {unicodedata.unidata_version}")

    countries = sorted(country.alpha_2 for country in pycountry.countries)
    currencies = sorted(currency.alpha_3 for currency in pycountry.currencies)
    ranges, assigned_count = assigned_ranges()
    overrides = {
        character: character.casefold()
        for code_point in range(sys.maxunicode + 1)
        if unicodedata.category(character := chr(code_point)) != "Cn"
        and character.casefold() != character.lower()
    }

    output = f'''/**
 * Generated for the Python 3.13.x production contract from pycountry {PYCOUNTRY_VERSION}
 * and Unicode {UNICODE_VERSION} via unicodedata2 {UNICODE_VERSION}.
 * ({assigned_count} assigned code points in {len(ranges)} ranges).
 * Keep synchronized with backend/app/schemas/customer.py and
 * backend/app/core/text_normalization.py when those dependencies change.
 */
const ISO_COUNTRY_CODES = new Set('{" ".join(countries)}'.split(' '));
const ISO_CURRENCY_CODES = new Set('{" ".join(currencies)}'.split(' '));

const UNICODE_15_1_ASSIGNED_RANGES = new Uint32Array([
{format_ranges(ranges)}
]);

// Full Unicode casefold entries whose result differs from lowercase.
const FULL_CASEFOLD_OVERRIDES: Readonly<Record<string, string>> = {{
{format_overrides(overrides)}
}};

export const orderMasterDataValidationMetadata = Object.freeze({{
  pycountryVersion: '{PYCOUNTRY_VERSION}',
  pythonVersion: '3.13.x',
  unicodeVersion: '{UNICODE_VERSION}',
  countryCodeCount: ISO_COUNTRY_CODES.size,
  currencyCodeCount: ISO_CURRENCY_CODES.size,
  assignedCodePointCount: {assigned_count},
  assignedRangeCount: UNICODE_15_1_ASSIGNED_RANGES.length / 2,
  fullCasefoldOverrideCount: Object.keys(FULL_CASEFOLD_OVERRIDES).length,
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
    FULL_CASEFOLD_OVERRIDES[character] ?? character.toLowerCase(),
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
    target = Path(__file__).parents[1] / "src" / "lib" / "orderMasterDataValidation.ts"
    expected = output.encode("utf-8")
    if args.check:
        if not target.exists() or target.read_bytes() != expected:
            raise SystemExit(f"Generated order master data is stale: {target}")
        action = "verified"
    else:
        target.write_bytes(expected)
        action = "generated"
    print(
        f"{action} {target}: countries={len(countries)} currencies={len(currencies)} "
        f"assigned={assigned_count} ranges={len(ranges)} overrides={len(overrides)}"
    )


if __name__ == "__main__":
    main()
