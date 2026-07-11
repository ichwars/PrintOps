from types import SimpleNamespace

import pytest

from backend.app.core.text_normalization import (
    _select_unicode_provider,
    normalize_case_insensitive_key,
)
from backend.app.core.unicode_casefold_15_1 import CASEFOLD_15_1, CASEFOLD_UNICODE_VERSION


def test_normalization_uses_the_complete_pinned_unicode_casefold_table():
    assert CASEFOLD_UNICODE_VERSION == "15.1.0"
    assert len(CASEFOLD_15_1) == 1530
    assert CASEFOLD_15_1["A"] == "a"
    assert CASEFOLD_15_1["\u00df"] == "ss"
    assert CASEFOLD_15_1["\u03d0"] == "\u03b2"
    assert normalize_case_insensitive_key("Stra\u00dfe") == "strasse"


def test_python_313_stdlib_is_used_without_the_backport():
    stdlib = SimpleNamespace(unidata_version="15.1.0")

    assert _select_unicode_provider(stdlib, None) is stdlib


def test_older_python_uses_the_pinned_backport():
    stdlib = SimpleNamespace(unidata_version="14.0.0")
    backport = SimpleNamespace(unidata_version="15.1.0")

    assert _select_unicode_provider(stdlib, backport) is backport


def test_unsupported_unicode_provider_versions_fail_closed():
    stdlib = SimpleNamespace(unidata_version="16.0.0")

    with pytest.raises(RuntimeError, match="requires Unicode 15.1.0"):
        _select_unicode_provider(stdlib, None)
