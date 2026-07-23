"""Shared, bounded and deterministic PDF rendering pipeline.

The preview and final-document paths deliberately enter through the same
pipeline.  The only mode-dependent behaviour is preview marking/caching and
final artifact persistence; layout interpretation never diverges.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pikepdf
import psutil

from backend.app.core.config import settings
from backend.app.schemas.document_layout import EffectiveDocumentLayout
from backend.app.services.document_snapshot import canonicalize_payload
from backend.app.services.document_templates import render_document_html
from backend.app.services.document_view_model import DocumentViewModel, canonicalize_view_model
from backend.app.services.pdfa import PdfaError, canonical_source_sha256, prepare_pdfa3u
from backend.app.services.verapdf import (
    PdfaValidationReport,
    VeraPdfExecutionError,
    VeraPdfRunner,
    VeraPdfUnavailable,
)

logger = logging.getLogger(__name__)

RenderMode = Literal["preview", "final"]
Engine = Callable[[str, Path, RenderMode], bytes]
CacheAuthorizer = Callable[[str], bool]
FinalAuthorizer = Callable[["RenderInput"], bool]

_RESOURCE_PATTERN = re.compile(
    r"(?:\b(?:src|href)\s*=\s*[\"']([^\"']+)[\"']|url\(\s*[\"']?([^\"')]+))",
    re.IGNORECASE,
)
_SAFE_CORRELATION = re.compile(r"[^A-Za-z0-9_.-]+")
_ICC_PROFILE = Path(__file__).parents[1] / "resources" / "pdf" / "sRGB.icc"


class DocumentRendererError(RuntimeError):
    """Public renderer failure with a stable, non-sensitive machine code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class RenderLimits:
    timeout_seconds: float = 10.0
    max_memory_bytes: int = 512 * 1024 * 1024
    max_pages: int = 12
    max_output_bytes: int = 25 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class RenderInput:
    view_model: DocumentViewModel
    layout: EffectiveDocumentLayout
    document_timestamp: datetime
    correlation_id: str
    cache_scope: str
    assets: Mapping[str, bytes] = field(default_factory=dict)
    asset_roles: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.correlation_id.strip() or not self.cache_scope.strip():
            raise ValueError("correlation_id and cache_scope are required")
        if self.document_timestamp.tzinfo is None:
            raise ValueError("document_timestamp must be timezone-aware")
        for digest, content in self.assets.items():
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("asset handles must be lowercase SHA-256 values")
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError("asset content does not match its handle")
        allowed_roles = {
            "logo",
            "letterhead_first",
            "letterhead_following",
            "font_regular",
            "font_bold",
            "font_italic",
            "font_bold_italic",
        }
        if set(self.asset_roles) - allowed_roles:
            raise ValueError("unknown document asset role")
        if any(digest not in self.assets for digest in self.asset_roles.values()):
            raise ValueError("asset role references an unavailable handle")


# Public naming retained for the preview-facing API contract.
RenderRequest = RenderInput


@dataclass(frozen=True, slots=True)
class RenderedPdf:
    content: bytes
    sha256: str
    page_count: int
    page_format: Literal["A4", "Letter"]
    mode: RenderMode
    from_cache: bool
    duration_ms: int
    artifact_path: Path | None = None
    validation_status: Literal["not_requested", "unvalidated", "valid", "invalid"] = (
        "not_requested"
    )
    validation_report: PdfaValidationReport | None = None
    warnings: tuple[str, ...] = ()


class DocumentRenderer:
    """Render HTML in an isolated process and normalize its PDF deterministically."""

    def __init__(
        self,
        *,
        engine_cli: Path | None = None,
        cache_dir: Path | None = None,
        artifact_dir: Path | None = None,
        limits: RenderLimits | None = None,
        cache_authorizer: CacheAuthorizer | None = None,
        final_authorizer: FinalAuthorizer | None = None,
        engine: Engine | None = None,
        validator: VeraPdfRunner | Literal[False] | None = None,
    ) -> None:
        configured_cli = engine_cli or settings.weasyprint_cli
        discovered = shutil.which("weasyprint") if configured_cli is None else None
        self._engine_cli = Path(configured_cli or discovered) if configured_cli or discovered else None
        self._cache_dir = Path(cache_dir or settings.document_render_cache_dir)
        self._artifact_dir = Path(artifact_dir or settings.document_render_artifact_dir)
        self._limits = limits or RenderLimits(
            timeout_seconds=settings.document_render_timeout_seconds,
            max_memory_bytes=settings.document_render_memory_limit_mb * 1024 * 1024,
            max_pages=settings.document_render_page_limit,
            max_output_bytes=settings.document_render_output_limit_mb * 1024 * 1024,
        )
        self._cache_authorizer = cache_authorizer or (lambda _scope: True)
        self._final_authorizer = final_authorizer or (lambda _request: True)
        self._engine = engine or self._run_weasyprint
        if validator is False:
            self._validator: VeraPdfRunner | None = None
        elif validator is not None:
            self._validator = validator
        else:
            self._validator = VeraPdfRunner(
                cli_path=settings.verapdf_cli,
                report_dir=settings.document_validation_report_dir,
                timeout_seconds=settings.document_validation_timeout_seconds,
            )
        self._cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._artifact_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    def render_preview(self, request: RenderRequest) -> RenderedPdf:
        return self._render(request, "preview")

    def render_final(
        self,
        render_input: RenderInput,
        einvoice_artifact: object | None = None,
    ) -> RenderedPdf:
        # The artifact is integrated in the PDF/A/e-invoice tasks.  It is part
        # of this signature now so no second renderer path can emerge later.
        if einvoice_artifact is not None:
            raise DocumentRendererError("RENDER_INPUT_INVALID")
        if not self._final_authorizer(render_input):
            raise DocumentRendererError("RENDER_INPUT_INVALID")
        return self._render(render_input, "final")

    def _render(self, request: RenderInput, mode: RenderMode) -> RenderedPdf:
        started = time.perf_counter()
        try:
            cache_key = self._cache_key(request)
            if mode == "preview":
                cached = self._read_cache(cache_key, request.cache_scope, request.layout.page.page_format)
                if cached is not None:
                    return self._with_validation(cached, request.correlation_id)

            html = render_document_html(request.view_model, request.layout)
            html = self._add_asset_styles(html, request)
            if mode == "preview":
                html = self._add_preview_mark(html)
            self._validate_resource_access(html, request.assets)

            safe_id = _SAFE_CORRELATION.sub("-", request.correlation_id).strip("-.")[:48] or "render"
            with tempfile.TemporaryDirectory(
                prefix=f"printops-{safe_id}-",
                ignore_cleanup_errors=True,
            ) as workspace_name:
                workspace = Path(workspace_name)
                worker_html = self._materialize_assets(html, workspace, request.assets)
                raw_pdf = self._engine(worker_html, workspace, mode)

            normalized, page_count = self._normalize_pdf(raw_pdf, request)
            if page_count > self._limits.max_pages:
                raise DocumentRendererError("RENDER_PAGE_LIMIT")
            if len(normalized) > self._limits.max_output_bytes:
                raise DocumentRendererError("RENDER_ENGINE_FAILED")
            digest = hashlib.sha256(normalized).hexdigest()
            duration_ms = round((time.perf_counter() - started) * 1000)
            validation_status, validation_report, warnings = self._validate_output(
                normalized,
                mode=mode,
                correlation_id=request.correlation_id,
            )
            artifact_path = None
            if mode == "preview":
                self._write_cache(cache_key, normalized, page_count, request.layout.page.page_format)
            else:
                artifact_path = self._persist_artifact(digest, normalized)
            return RenderedPdf(
                content=normalized,
                sha256=digest,
                page_count=page_count,
                page_format=request.layout.page.page_format,
                mode=mode,
                from_cache=False,
                duration_ms=duration_ms,
                artifact_path=artifact_path,
                validation_status=validation_status,
                validation_report=validation_report,
                warnings=warnings,
            )
        except DocumentRendererError:
            raise
        except TimeoutError as exc:
            logger.warning("document renderer timed out", exc_info=exc)
            raise DocumentRendererError("RENDER_TIMEOUT") from None
        except MemoryError as exc:
            logger.warning("document renderer exceeded memory limit", exc_info=exc)
            raise DocumentRendererError("RENDER_MEMORY_LIMIT") from None
        except PdfaError as exc:
            logger.warning("PDF/A preparation failed with %s", exc.code)
            if exc.code.startswith("PDFA_LETTERHEAD"):
                raise DocumentRendererError("RENDER_ASSET_UNAVAILABLE") from None
            raise DocumentRendererError("RENDER_ENGINE_FAILED") from None
        except (ValueError, TypeError) as exc:
            logger.warning("invalid document render input", exc_info=exc)
            raise DocumentRendererError("RENDER_INPUT_INVALID") from None
        except Exception as exc:
            logger.exception("document renderer failed: %s", type(exc).__name__)
            raise DocumentRendererError("RENDER_ENGINE_FAILED") from None

    def _validate_output(
        self,
        content: bytes,
        *,
        mode: RenderMode,
        correlation_id: str,
    ) -> tuple[
        Literal["not_requested", "unvalidated", "valid", "invalid"],
        PdfaValidationReport | None,
        tuple[str, ...],
    ]:
        if self._validator is None:
            return "not_requested", None, ()
        try:
            report = self._validator.validate(content, correlation_id=correlation_id)
        except VeraPdfUnavailable:
            if mode == "preview":
                return "unvalidated", None, ("PDF_VALIDATOR_UNAVAILABLE",)
            raise DocumentRendererError("RENDER_ENGINE_FAILED") from None
        except VeraPdfExecutionError as exc:
            if mode == "preview":
                return "unvalidated", None, (exc.code,)
            raise DocumentRendererError("RENDER_ENGINE_FAILED") from None
        if report.compliant:
            return "valid", report, ()
        if mode == "preview":
            return "invalid", report, tuple(
                finding.external_rule_id or finding.code for finding in report.findings
            )
        raise DocumentRendererError("RENDER_ENGINE_FAILED")

    def _with_validation(self, rendered: RenderedPdf, correlation_id: str) -> RenderedPdf:
        status, report, warnings = self._validate_output(
            rendered.content,
            mode="preview",
            correlation_id=correlation_id,
        )
        return replace(
            rendered,
            validation_status=status,
            validation_report=report,
            warnings=warnings,
        )

    def _run_weasyprint(self, html: str, workspace: Path, _mode: RenderMode) -> bytes:
        if self._engine_cli is None or not self._engine_cli.is_file():
            raise OSError("configured WeasyPrint runtime is unavailable")
        input_path = workspace / "document.html"
        output_path = workspace / "document.pdf"
        input_path.write_text(html, encoding="utf-8", newline="\n")
        command = [
            str(self._engine_cli),
            "--quiet",
            "--media-type",
            "print",
            "--allowed-protocols",
            "file",
            "--no-http-redirects",
            "--fail-on-http-errors",
            "--pdf-variant",
            "pdf/a-3u",
            "--pdf-tags",
            "--output-intent",
            str(_ICC_PROFILE),
            "--full-fonts",
            "--timeout",
            "2",
            str(input_path),
            str(output_path),
        ]
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = "0"
        environment["SOURCE_DATE_EPOCH"] = "0"
        process = subprocess.Popen(
            command,
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        deadline = time.monotonic() + self._limits.timeout_seconds
        try:
            monitored = psutil.Process(process.pid)
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    self._terminate_process_tree(process, monitored)
                    raise TimeoutError
                try:
                    memory = monitored.memory_info().rss
                    memory += sum(child.memory_info().rss for child in monitored.children(recursive=True))
                    if memory > self._limits.max_memory_bytes:
                        self._terminate_process_tree(process, monitored)
                        raise MemoryError
                except psutil.Error:
                    pass
                time.sleep(0.02)
            stdout, stderr = process.communicate(timeout=1)
        finally:
            if process.poll() is None:
                self._terminate_process_tree(process, monitored)
        if process.returncode != 0 or not output_path.is_file():
            logger.error(
                "WeasyPrint exited with %s (stdout=%d bytes, stderr=%d bytes)",
                process.returncode,
                len(stdout),
                len(stderr),
            )
            raise OSError("WeasyPrint process failed")
        if output_path.stat().st_size > self._limits.max_output_bytes:
            raise OSError("rendered PDF exceeds output limit")
        return output_path.read_bytes()

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen, monitored: psutil.Process) -> None:
        """Stop all descendants before their temporary working directory is removed."""
        try:
            descendants = monitored.children(recursive=True)
        except psutil.Error:
            descendants = []
        for child in reversed(descendants):
            try:
                child.kill()
            except psutil.Error:
                pass
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        if descendants:
            psutil.wait_procs(descendants, timeout=2)

    def _validate_resource_access(
        self,
        html: str,
        assets: Mapping[str, bytes] | None = None,
    ) -> None:
        allowed = set((assets or {}).keys())
        for match in _RESOURCE_PATTERN.finditer(html):
            resource = (match.group(1) or match.group(2)).strip()
            asset_match = re.fullmatch(r"asset://([0-9a-f]{64})", resource)
            if asset_match and asset_match.group(1) in allowed:
                continue
            raise DocumentRendererError("RENDER_ASSET_UNAVAILABLE")

    @staticmethod
    def _add_asset_styles(html: str, request: RenderInput) -> str:
        font_rules: list[str] = []
        roles = (
            ("font_regular", "normal", "400"),
            ("font_bold", "normal", "700"),
            ("font_italic", "italic", "400"),
            ("font_bold_italic", "italic", "700"),
        )
        family = request.layout.typography.font_family
        for role, style, weight in roles:
            digest = request.asset_roles.get(role)
            if digest:
                font_rules.append(
                    "@font-face{"
                    f"font-family:'{family}';src:url('asset://{digest}');"
                    f"font-style:{style};font-weight:{weight};font-display:block"
                    "}"
                )
        if not font_rules:
            return html
        return html.replace("</head>", f"<style>{''.join(font_rules)}</style></head>", 1)

    @staticmethod
    def _materialize_assets(html: str, workspace: Path, assets: Mapping[str, bytes]) -> str:
        if not assets:
            return html
        asset_dir = workspace / "assets"
        asset_dir.mkdir(mode=0o700)
        result = html
        for digest, content in assets.items():
            if content.startswith(b"%PDF-"):
                suffix = ".pdf"
            elif content.startswith(b"\x89PNG"):
                suffix = ".png"
            elif content.startswith(b"OTTO"):
                suffix = ".otf"
            else:
                suffix = ".ttf"
            target = asset_dir / f"{digest}{suffix}"
            target.write_bytes(content)
            try:
                target.chmod(0o600)
            except OSError:
                pass
            result = result.replace(f"asset://{digest}", target.resolve().as_uri())
        if "asset://" in result:
            raise DocumentRendererError("RENDER_ASSET_UNAVAILABLE")
        return result

    @staticmethod
    def _add_preview_mark(html: str) -> str:
        mark = (
            '<div aria-hidden="true" style="position:fixed;inset:42% 0 auto;'
            'transform:rotate(-28deg);text-align:center;font-size:54pt;'
            'font-weight:bold;color:rgba(90,108,96,.13);z-index:-1">VORSCHAU</div>'
        )
        return html.replace("</body>", f"{mark}</body>", 1)

    def _normalize_pdf(self, raw_pdf: bytes, request: RenderInput) -> tuple[bytes, int]:
        if not raw_pdf.startswith(b"%PDF-"):
            raise OSError("renderer output is not a PDF")
        with pikepdf.open(io.BytesIO(raw_pdf)) as pdf:
            page_count = len(pdf.pages)
            if page_count > self._limits.max_pages:
                raise DocumentRendererError("RENDER_PAGE_LIMIT")
        first_digest = request.asset_roles.get("letterhead_first")
        following_digest = request.asset_roles.get("letterhead_following")
        if request.layout.page.use_first_page_letterhead and not first_digest:
            raise PdfaError("PDFA_LETTERHEAD_MISSING")
        if request.layout.page.use_following_page_letterhead and not following_digest:
            if request.layout.page.reuse_first_letterhead:
                following_digest = first_digest
            else:
                raise PdfaError("PDFA_LETTERHEAD_MISSING")
        prepared = prepare_pdfa3u(
            raw_pdf,
            language=request.view_model.language,
            timestamp=request.document_timestamp,
            document_id=canonical_source_sha256(raw_pdf),
            letterhead_first=(
                request.assets[first_digest]
                if request.layout.page.use_first_page_letterhead and first_digest
                else None
            ),
            letterhead_following=(
                request.assets[following_digest]
                if request.layout.page.use_following_page_letterhead and following_digest
                else None
            ),
        )
        return prepared, page_count

    def _cache_key(self, request: RenderInput) -> str:
        material = b"\x00".join(
            (
                canonicalize_view_model(request.view_model),
                canonicalize_payload(request.layout),
                request.cache_scope.encode("utf-8"),
                request.document_timestamp.astimezone(timezone.utc).isoformat().encode("ascii"),
                json.dumps(
                    dict(sorted(request.asset_roles.items())),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
                b"\n".join(
                    digest.encode("ascii") for digest in sorted(request.assets)
                ),
            )
        )
        return hashlib.sha256(material).hexdigest()

    def _read_cache(
        self,
        key: str,
        scope: str,
        page_format: Literal["A4", "Letter"],
    ) -> RenderedPdf | None:
        pdf_path = self._cache_dir / f"{key}.pdf"
        metadata_path = self._cache_dir / f"{key}.json"
        if not pdf_path.is_file() or not metadata_path.is_file():
            return None
        if not self._cache_authorizer(scope):
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            age = time.time() - float(metadata["created_at"])
            content = pdf_path.read_bytes()
            if age < 0 or age > settings.document_render_cache_ttl_seconds:
                pdf_path.unlink(missing_ok=True)
                metadata_path.unlink(missing_ok=True)
                return None
            if hashlib.sha256(content).hexdigest() != metadata["sha256"]:
                raise ValueError("cache digest mismatch")
            now = time.time()
            os.utime(pdf_path, (now, now))
            os.utime(metadata_path, (now, now))
            return RenderedPdf(
                content=content,
                sha256=metadata["sha256"],
                page_count=int(metadata["page_count"]),
                page_format=page_format,
                mode="preview",
                from_cache=True,
                duration_ms=0,
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            logger.warning("discarding invalid document render cache entry %s", key)
            pdf_path.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            return None

    def _write_cache(
        self,
        key: str,
        content: bytes,
        page_count: int,
        page_format: str,
    ) -> None:
        digest = hashlib.sha256(content).hexdigest()
        metadata = {
            "created_at": time.time(),
            "sha256": digest,
            "page_count": page_count,
            "page_format": page_format,
        }
        self._atomic_write(self._cache_dir / f"{key}.pdf", content)
        self._atomic_write(
            self._cache_dir / f"{key}.json",
            json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        )
        self._prune_cache()

    def _prune_cache(self) -> None:
        entries = sorted(self._cache_dir.glob("*.pdf"), key=lambda path: path.stat().st_mtime)
        total = sum(path.stat().st_size for path in entries)
        limit = settings.document_render_cache_limit_mb * 1024 * 1024
        for path in entries:
            if total <= limit:
                break
            size = path.stat().st_size
            path.unlink(missing_ok=True)
            path.with_suffix(".json").unlink(missing_ok=True)
            total -= size

    def _persist_artifact(self, digest: str, content: bytes) -> Path:
        target = self._artifact_dir / digest[:2] / f"{digest}.pdf"
        if not target.exists():
            self._atomic_write(target, content)
        return target

    @staticmethod
    def _atomic_write(target: Path, content: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                temp.chmod(0o600)
            except OSError:
                pass
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
