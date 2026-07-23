"""Stable veraPDF execution and report-normalization contracts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from backend.app.services.verapdf import (
    VeraPdfExecutionError,
    VeraPdfRunner,
    VeraPdfUnavailable,
)


def _report(*, compliant: bool) -> str:
    rules = [] if compliant else [
        {
            "ruleStatus": "FAILED",
            "specification": "ISO 19005-3:2012",
            "clause": "6.6.2.1",
            "testNumber": 1,
            "description": "Catalog metadata is required",
            "failedChecks": 1,
            "checks": [{"errorMessage": "Metadata stream is missing"}],
        }
    ]
    return json.dumps(
        {
            "report": {
                "buildInformation": {
                    "releaseDetails": [{"id": "core", "version": "1.30.2"}]
                },
                "jobs": [
                    {
                        "validationResult": [
                            {
                                "profileName": "PDF/A-3u validation profile",
                                "compliant": compliant,
                                "details": {"ruleSummaries": rules},
                            }
                        ]
                    }
                ],
            }
        }
    )


def _executor(report: str, *, version: str = "veraPDF 1.30.2"):
    def run(command, **_kwargs):
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, version, "")
        return subprocess.CompletedProcess(command, 0 if '"compliant": true' in report else 1, report, "")

    return run


def test_valid_report_is_normalized_and_raw_report_is_immutable(tmp_path):
    runner = VeraPdfRunner(
        cli_path=Path("verapdf"),
        report_dir=tmp_path / "reports",
        process_runner=_executor(_report(compliant=True)),
    )
    result = runner.validate(b"%PDF-1.7\n%%EOF", correlation_id="valid-report")
    assert result.compliant is True
    assert result.profile == "PDF/A-3U"
    assert result.validator_version == "1.30.2"
    assert result.ruleset == "ISO 19005-3:2012 / PDF/A-3u"
    assert result.findings == []
    stored = list((tmp_path / "reports").rglob("*.json"))
    assert len(stored) == 1
    assert stored[0].read_bytes() == _report(compliant=True).encode()


def test_failed_rules_keep_stable_external_rule_ids(tmp_path):
    report = _report(compliant=False)
    result = VeraPdfRunner(
        cli_path=Path("verapdf"),
        report_dir=tmp_path / "reports",
        process_runner=_executor(report),
    ).validate(b"%PDF-1.7\n%%EOF", correlation_id="invalid-report")
    assert result.compliant is False
    assert result.findings[0].external_rule_id == "ISO 19005-3:2012#6.6.2.1-1"
    assert result.findings[0].severity == "blocker"
    assert result.raw_report_sha256


def test_missing_cli_and_version_mismatch_are_unavailable(tmp_path):
    with pytest.raises(VeraPdfUnavailable):
        VeraPdfRunner(cli_path=None, report_dir=tmp_path).version()
    runner = VeraPdfRunner(
        cli_path=Path("verapdf"),
        report_dir=tmp_path,
        process_runner=_executor(_report(compliant=True), version="veraPDF 1.29.0"),
    )
    with pytest.raises(VeraPdfUnavailable):
        runner.version()


def test_timeout_and_malformed_report_have_stable_errors(tmp_path):
    def timeout(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, 30)

    with pytest.raises(VeraPdfExecutionError) as caught:
        VeraPdfRunner(
            cli_path=Path("verapdf"),
            report_dir=tmp_path,
            process_runner=timeout,
        ).validate(b"%PDF-1.7\n%%EOF", correlation_id="timeout")
    assert caught.value.code == "PDF_VALIDATOR_TIMEOUT"

    runner = VeraPdfRunner(
        cli_path=Path("verapdf"),
        report_dir=tmp_path,
        process_runner=_executor("not json"),
    )
    with pytest.raises(VeraPdfExecutionError) as caught:
        runner.validate(b"%PDF-1.7\n%%EOF", correlation_id="malformed")
    assert caught.value.code == "PDF_VALIDATOR_REPORT_INVALID"

