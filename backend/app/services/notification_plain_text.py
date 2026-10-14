"""Transport-specific literal text for untrusted application content."""

import html
import re


def escape_markdown(value: str) -> str:
    # Also suppress raw HTML, mentions and automatic link syntax.
    value = html.escape(value, quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~\-])", r"\\\1", value)
