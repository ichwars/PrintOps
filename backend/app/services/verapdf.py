"""Bounded veraPDF 1.30.2 execution and stable report normalization."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.app.schemas.document_layout import LayoutFinding

EXPECTED_VERAPDF_VERSION = "1.30.2"
_MAX_REPORT_BYTES = 10 * 1024 * 1024
_VERSION_PATTERN = re.compile(r"\bveraPDF\s+([0-9]+(?:\.[0-9]+){2})\b", re.IGNORECASE)


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PdfaValidationReport(_ImmutableModel):
    compliant: bool
    profile: Literal["PDF/A-3U"] = "PDF/A-3U"
    validator_version: str
    ruleset: str = "ISO 19005-3:2012 / PDF/A-3u"
    findings: list[LayoutFinding]
    raw_report_sha256: str


class VeraPdfError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class VeraPdfUnavailable(VeraPdfError):
    pass


class VeraPdfExecutionError(VeraPdfError):
    pass


ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]


class VeraPdfRunner:
    """Execute only the configured CLI with a fixed PDF/A-3u argument set."""

    def __init__(
        self,
        *,
        cli_path: Path | None,
        report_dir: Path,
        expected_version: str = EXPECTED_VERAPDF_VERSION,
        timeout_seconds: float = 30.0,
        process_runner: ProcessRunner | None = None,
    ) -> None:
        self._cli_path = Path(cli_path) if cli_path is not None else None
        self._report_dir = Path(report_dir)
        self._expected_version = expected_version
        self._timeout_seconds = timeout_seconds
        self._process_runner = process_runner or subprocess.run
        self._virtual_cli = process_runner is not None
        self._version: str | None = None

    @property
    def available(self) -> bool:
        try:
            self.version()
        except VeraPdfUnavailable:
            return False
        return True

    def _command(self, arguments: list[str]) -> list[str]:
        if self._cli_path is None:
            raise VeraPdfUnavailable("PDF_VALIDATOR_UNAVAILABLE")
        if not self._virtual_cli and not self._cli_path.is_file():
            raise VeraPdfUnavailable("PDF_VALIDATOR_UNAVAILABLE")
        if os.name == "nt" and self._cli_path.suffix.lower() in {".bat", ".cmd"}:
            return [
                os.environ.get("COMSPEC", "cmd.exe"),
                "/d",
                "/c",
                str(self._cli_path),
                *arguments,
            ]
        return [str(self._cli_path), *arguments]

    def _execute(self, arguments: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
        command = self._command(arguments)
        try:
            result = self._process_runner(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except subprocess.TimeoutExpired as exc:
            raise VeraPdfExecutionError("PDF_VALIDATOR_TIMEOUT") from exc
        except OSError as exc:
            raise VeraPdfUnavailable("PDF_VALIDATOR_UNAVAILABLE") from exc
        if len(result.stdout.encode("utf-8")) > _MAX_REPORT_BYTES or len(
            result.stderr.encode("utf-8")
        ) > _MAX_REPORT_BYTES:
            raise VeraPdfExecutionError("PDF_VALIDATOR_OUTPUT_LIMIT")
        return result

    def version(self) -> str:
        if self._version is not None:
            return self._version
        result = self._execute(["--version"], timeout=5)
        match = _VERSION_PATTERN.search(f"{result.stdout}\n{result.stderr}")
        if result.returncode != 0 or match is None or match.group(1) != self._expected_version:
            raise VeraPdfUnavailable("PDF_VALIDATOR_VERSION_MISMATCH")
        self._version = match.group(1)
        return self._version

    def validate(self, content: bytes, *, correlation_id: str) -> PdfaValidationReport:
        if not content.startswith(b"%PDF-"):
            raise VeraPdfExecutionError("PDF_VALIDATOR_INPUT_INVALID")
        version = self.version()
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", correlation_id).strip("-.")[:48] or "pdf"
        with tempfile.TemporaryDirectory(prefix=f"printops-verapdf-{safe_id}-") as workspace_name:
            source = Path(workspace_name) / "document.pdf"
            source.write_bytes(content)
            try:
                source.chmod(0o600)
            except OSError:
                pass
            result = self._execute(
                [
                    "--format",
                    "json",
                    "--flavour",
                    "3u",
                    "--maxfailures",
                    "100",
                    "--maxfailuresdisplayed",
                    "10",
                    str(source),
                ],
                timeout=self._timeout_seconds,
            )
        report_text = result.stdout.strip()
        try:
            start = report_text.index("{")
            end = report_text.rindex("}") + 1
            raw_report = report_text[start:end].encode("utf-8")
            payload = json.loads(raw_report)
            validation = payload["report"]["jobs"][0]["validationResult"][0]
            compliant = bool(validation["compliant"])
            summaries = validation["details"].get("ruleSummaries", [])
        except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise VeraPdfExecutionError("PDF_VALIDATOR_REPORT_INVALID") from exc
        if result.returncode not in {0, 1}:
            raise VeraPdfExecutionError("PDF_VALIDATOR_FAILED")

        findings = [self._finding(summary) for summary in summaries[:100]]
        if compliant and findings:
            raise VeraPdfExecutionError("PDF_VALIDATOR_REPORT_INVALID")
        if not compliant and not findings:
            raise VeraPdfExecutionError("PDF_VALIDATOR_REPORT_INVALID")
        raw_sha256 = hashlib.sha256(raw_report).hexdigest()
        self._persist_raw_report(raw_sha256, raw_report)
        return PdfaValidationReport(
            compliant=compliant,
            validator_version=version,
            findings=findings,
            raw_report_sha256=raw_sha256,
        )

    @staticmethod
    def _finding(summary: dict) -> LayoutFinding:
        specification = str(summary.get("specification") or "ISO 19005-3:2012")
        clause = str(summary.get("clause") or "unknown")
        test_number = str(summary.get("testNumber") or "unknown")
        external_id = f"{specification}#{clause}-{test_number}"
        checks = summary.get("checks") or []
        detail = checks[0].get("errorMessage") if checks and isinstance(checks[0], dict) else None
        message = str(detail or summary.get("description") or "PDF/A rule failed")
        return LayoutFinding(
            code="PDFA_VERAPDF_RULE_FAILED",
            severity="blocker",
            field_path=None,
            message_key="documents.pdfa.verapdf.rule_failed",
            message=message,
            correction_hint="Dokumentlayout oder Quelldaten anhand der Regelkennung korrigieren.",
            external_rule_id=external_id[:160],
        )

    def _persist_raw_report(self, digest: str, content: bytes) -> None:
        target = self._report_dir / digest[:2] / f"{digest}.json"
        if target.exists():
            if target.read_bytes() != content:
                raise VeraPdfExecutionError("PDF_VALIDATOR_REPORT_COLLISION")
            return
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                temporary.chmod(0o600)
            except OSError:
                pass
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

