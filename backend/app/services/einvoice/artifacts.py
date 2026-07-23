"""Protected, atomic storage for immutable electronic invoice artifacts."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.paths import resolve_data_dir
from backend.app.models.commercial_document import CommercialDocument, DocumentArtifact
from backend.app.services.document_audit import append_audit
from backend.app.services.einvoice.validator import EInvoiceValidationReport


class EInvoiceArtifactError(RuntimeError):
    """Stable failure raised before an E-invoice artifact can enter rendering."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ResolvedEInvoiceArtifact:
    artifact_id: int
    document_id: int
    kind: Literal["zugferd_xml", "xrechnung_xml"]
    content: bytes
    sha256: str
    standard: Literal["zugferd", "xrechnung"]
    syntax: Literal["cii-d22b", "cii-d16b", "ubl-2.1"]
    profile: str
    source_snapshot_sha256: str
    validation_report: dict


def _artifact_location(document_id: int, digest: str) -> tuple[Path, str]:
    relative = Path("document-artifacts") / str(document_id) / f"{digest}.xml"
    root = resolve_data_dir().resolve()
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise RuntimeError("Artifact path escaped DATA_DIR")
    return target, relative.as_posix()


def _atomic_write(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=".artifact-",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, target)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


async def store_artifact(
    session: AsyncSession,
    document: CommercialDocument,
    xml: bytes,
    report: EInvoiceValidationReport,
    rule_versions: dict | None = None,
    *,
    snapshot_sha256: str | None = None,
) -> DocumentArtifact:
    """Atomically store a valid XML artifact and stage its database metadata."""
    if not report.valid:
        raise ValueError("Only a valid electronic invoice may be stored")
    if document.id is None:
        raise ValueError("The commercial document must be persisted before its artifact")
    if not xml:
        raise ValueError("The electronic invoice XML must not be empty")

    digest = sha256(xml).hexdigest()
    target, relative_path = _artifact_location(document.id, digest)
    _atomic_write(target, xml)
    metadata = report.to_dict()
    metadata["byte_size"] = len(xml)
    kind = "xrechnung_xml" if report.standard == "xrechnung" else "zugferd_xml"
    artifact = DocumentArtifact(
        document_id=document.id,
        kind=kind,
        content_type="application/xml",
        storage_path=relative_path,
        content=None,
        sha256=digest,
        validation_status="valid",
        validation_report=metadata,
        rule_versions=dict(rule_versions or report.rule_versions),
        render_receipt={
            "source_document_id": document.id,
            "source_snapshot_sha256": snapshot_sha256,
            "einvoice_standard": report.standard,
            "einvoice_syntax": report.syntax,
            "einvoice_profile": report.profile,
        },
    )
    session.add(artifact)
    return artifact


def _read_stored_content(artifact: DocumentArtifact) -> bytes:
    if not artifact.storage_path or artifact.content is not None:
        raise EInvoiceArtifactError("EINVOICE_ARTIFACT_STORAGE_INVALID")
    root = resolve_data_dir().resolve()
    target = (root / artifact.storage_path).resolve()
    if root != target and root not in target.parents:
        raise EInvoiceArtifactError("EINVOICE_ARTIFACT_STORAGE_INVALID")
    try:
        content = target.read_bytes()
    except OSError as exc:
        raise EInvoiceArtifactError("EINVOICE_ARTIFACT_UNAVAILABLE") from exc
    if sha256(content).hexdigest() != artifact.sha256:
        code = (
            "ZUGFERD_XML_HASH_MISMATCH"
            if artifact.kind == "zugferd_xml"
            else "XRECHNUNG_XML_HASH_MISMATCH"
        )
        raise EInvoiceArtifactError(code)
    return content


def materialize_validated_artifact(
    artifact: DocumentArtifact,
    *,
    expected_document_id: int,
    expected_snapshot_sha256: str,
) -> ResolvedEInvoiceArtifact:
    """Resolve immutable bytes only after all stored ownership evidence matches."""
    if artifact.id is None or artifact.document_id != expected_document_id:
        raise EInvoiceArtifactError("EINVOICE_ARTIFACT_DOCUMENT_MISMATCH")
    if artifact.kind not in {"zugferd_xml", "xrechnung_xml"}:
        raise EInvoiceArtifactError("EINVOICE_ARTIFACT_KIND_INVALID")
    if artifact.validation_status != "valid":
        raise EInvoiceArtifactError("EINVOICE_ARTIFACT_NOT_VALID")
    report = dict(artifact.validation_report or {})
    if report.get("valid") is not True:
        raise EInvoiceArtifactError("EINVOICE_ARTIFACT_NOT_VALID")
    receipt = dict(artifact.render_receipt or {})
    if receipt.get("source_document_id") != expected_document_id:
        raise EInvoiceArtifactError("EINVOICE_ARTIFACT_DOCUMENT_MISMATCH")
    if receipt.get("source_snapshot_sha256") != expected_snapshot_sha256:
        raise EInvoiceArtifactError("EINVOICE_ARTIFACT_SNAPSHOT_MISMATCH")

    expected = {
        "zugferd_xml": ("zugferd", {"cii-d22b"}),
        "xrechnung_xml": ("xrechnung", {"ubl-2.1", "cii-d16b"}),
    }
    standard, syntaxes = expected[artifact.kind]
    syntax = str(report.get("syntax") or "")
    profile = str(report.get("profile") or "")
    if report.get("standard") != standard or syntax not in syntaxes or not profile:
        raise EInvoiceArtifactError("EINVOICE_ARTIFACT_PROFILE_MISMATCH")
    if artifact.kind == "zugferd_xml" and profile not in {"en16931", "xrechnung"}:
        raise EInvoiceArtifactError("EINVOICE_ARTIFACT_PROFILE_MISMATCH")

    content = _read_stored_content(artifact)
    return ResolvedEInvoiceArtifact(
        artifact_id=artifact.id,
        document_id=artifact.document_id,
        kind=artifact.kind,
        content=content,
        sha256=artifact.sha256,
        standard=standard,
        syntax=syntax,
        profile=profile,
        source_snapshot_sha256=expected_snapshot_sha256,
        validation_report=report,
    )


async def load_validated_artifact(
    session: AsyncSession,
    artifact_id: int,
    *,
    expected_document_id: int,
    expected_snapshot_sha256: str,
    actor_id: int | None = None,
    correlation_id: str = "einvoice-artifact-resolution",
) -> ResolvedEInvoiceArtifact:
    artifact = await session.scalar(
        select(DocumentArtifact).where(DocumentArtifact.id == artifact_id)
    )
    try:
        if artifact is None:
            raise EInvoiceArtifactError("EINVOICE_ARTIFACT_UNAVAILABLE")
        return materialize_validated_artifact(
            artifact,
            expected_document_id=expected_document_id,
            expected_snapshot_sha256=expected_snapshot_sha256,
        )
    except EInvoiceArtifactError as exc:
        await append_audit(
            session,
            action="einvoice_artifact_rejected",
            object_type="document_artifact",
            object_id=artifact_id,
            actor_id=actor_id,
            reason="Stored E-invoice evidence did not match the render request",
            before=None,
            after={
                "code": exc.code,
                "expected_document_id": expected_document_id,
            },
            correlation_id=correlation_id,
        )
        await session.flush()
        raise


def export_manifest(
    artifact: ResolvedEInvoiceArtifact,
    *,
    pdf_sha256: str,
) -> dict:
    if artifact.kind == "xrechnung_xml":
        return {
            "legal_original": "xml",
            "legal_original_artifact_id": artifact.artifact_id,
            "legal_original_sha256": artifact.sha256,
            "visual_copy": "pdf",
            "visual_copy_sha256": pdf_sha256,
        }
    return {
        "legal_original": "pdf",
        "legal_original_sha256": pdf_sha256,
        "embedded_xml_artifact_id": artifact.artifact_id,
        "embedded_xml_sha256": artifact.sha256,
        "embedded_xml_profile": artifact.profile,
    }


__all__ = [
    "EInvoiceArtifactError",
    "ResolvedEInvoiceArtifact",
    "export_manifest",
    "load_validated_artifact",
    "materialize_validated_artifact",
    "store_artifact",
]
