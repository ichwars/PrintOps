"""Tests for main._format_hms_error_summary — the helper that turns MQTT hms_errors
into a human-readable PrintQueueItem.error_message on pre-print failures (#1111)."""


def _format(hms_errors):
    from backend.app.main import _format_hms_error_summary

    return _format_hms_error_summary(hms_errors)


def test_returns_none_for_empty_list():
    assert _format([]) is None
    assert _format(None or []) is None


def test_formats_known_nozzle_mismatch_code():
    """0500_4038 is the nozzle-size-mismatch code from the HMS table — the common
    trigger for issue #1111."""
    summary = _format([{"code": "0x4038", "attr": 0x05000000, "module": 0x5, "severity": 1}])
    assert summary is not None
    assert "0500_4038" in summary
    assert "nozzle diameter" in summary.lower()


def test_formats_unknown_code_as_bare_short_code():
    summary = _format([{"code": "0x9999", "attr": 0x99990000, "module": 0x99, "severity": 1}])
    assert summary == "[9999_9999]"


def test_joins_multiple_errors_with_semicolons():
    summary = _format(
        [
            {"code": "0x4038", "attr": 0x05000000, "module": 0x5, "severity": 1},
            {"code": "0x9999", "attr": 0x99990000, "module": 0x99, "severity": 1},
        ]
    )
    assert summary is not None
    assert "; " in summary
    assert summary.count("[") == 2


def test_tolerates_malformed_entry_and_skips_it():
    summary = _format(
        [
            {"code": "not-hex", "attr": "also-not-int"},
            {"code": "0x4038", "attr": 0x05000000, "module": 0x5, "severity": 1},
        ]
    )
    assert summary is not None
    assert "0500_4038" in summary


def test_all_malformed_returns_none():
    assert _format([{"code": "not-hex", "attr": "also-not-int"}]) is None


def test_current_payload_uses_resolved_model_text_and_full_hms_code_without_neighbouring_short_lookup():
    payload = [
        {
            "code": "0x10008",
            "attr": 0x03000200,
            "full_code": "0300020000010008",
            "description": "Model-specific manufacturer text.",
        }
    ]
    assert _format(payload) == "[0300-0200-0001-0008] Model-specific manufacturer text."
    payload[0]["full_code"] = "0300020000014000"
    payload[0]["code"] = "0x14000"
    payload[0]["description"] = None
    assert _format(payload) == "[0300-0200-0001-4000]"
