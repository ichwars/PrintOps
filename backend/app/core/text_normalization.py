from __future__ import annotations

import unicodedata as stdlib_unicodedata

try:
    import unicodedata2
except ImportError:  # Python 3.13 already ships the pinned Unicode 15.1 tables.
    unicodedata2 = None

from backend.app.core.unicode_casefold_15_1 import CASEFOLD_15_1, CASEFOLD_UNICODE_VERSION

MAX_TAG_NAME_KEY_UTF8_BYTES = 512
UNICODE_NORMALIZATION_VERSION = CASEFOLD_UNICODE_VERSION


def _select_unicode_provider(stdlib_provider, backport_provider):
    if stdlib_provider.unidata_version == UNICODE_NORMALIZATION_VERSION:
        return stdlib_provider
    if backport_provider is not None and backport_provider.unidata_version == UNICODE_NORMALIZATION_VERSION:
        return backport_provider

    available_versions = [f"stdlib={stdlib_provider.unidata_version}"]
    if backport_provider is not None:
        available_versions.append(f"unicodedata2={backport_provider.unidata_version}")
    raise RuntimeError(
        f"PrintOps requires Unicode {UNICODE_NORMALIZATION_VERSION}; "
        f"available providers: {', '.join(available_versions)}"
    )


unicodedata = _select_unicode_provider(stdlib_unicodedata, unicodedata2)


def normalize_case_insensitive_key(value: str) -> str:
    """Return the portable comparison key for user-visible text."""
    return "".join(CASEFOLD_15_1.get(character, character) for character in unicodedata.normalize("NFKC", value))


def normalize_tag_name_key(value: str) -> str:
    """Return a tag key that is safe for exact PostgreSQL B-tree uniqueness."""
    normalized = normalize_case_insensitive_key(value)
    if len(normalized.encode("utf-8")) > MAX_TAG_NAME_KEY_UTF8_BYTES:
        raise ValueError(f"normalized tag name must not exceed {MAX_TAG_NAME_KEY_UTF8_BYTES} UTF-8 bytes")
    return normalized
