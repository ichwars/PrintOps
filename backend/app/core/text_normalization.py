from __future__ import annotations

import unicodedata

MAX_TAG_NAME_KEY_UTF8_BYTES = 512


def normalize_case_insensitive_key(value: str) -> str:
    """Return the portable comparison key for user-visible text."""
    return unicodedata.normalize("NFKC", value).casefold()


def normalize_tag_name_key(value: str) -> str:
    """Return a tag key that is safe for exact PostgreSQL B-tree uniqueness."""
    normalized = normalize_case_insensitive_key(value)
    if len(normalized.encode("utf-8")) > MAX_TAG_NAME_KEY_UTF8_BYTES:
        raise ValueError(
            f"normalized tag name must not exceed {MAX_TAG_NAME_KEY_UTF8_BYTES} UTF-8 bytes"
        )
    return normalized
