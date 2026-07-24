"""Helpers for logging external identifiers without credential-bearing detail."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

_SAFE_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*$")


def url_for_log(value: str) -> str:
    """Return a deliberately lossy URL representation suitable for logs.

    Userinfo, host text, path, query, and fragment are never copied. Keeping
    only the validated scheme and optional port is enough to diagnose the
    integration type without persisting credentials hidden in URL components.
    """
    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        if not _SAFE_SCHEME.fullmatch(scheme) or not parsed.hostname:
            return "[INVALID_URL]"
        port = parsed.port
    except (TypeError, ValueError):
        return "[INVALID_URL]"
    suffix = f":{port}" if port is not None else ""
    return f"{scheme}://[HOST]{suffix}/[REDACTED]"
