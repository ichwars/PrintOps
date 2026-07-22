"""Protected, atomic storage for immutable electronic invoice artifacts."""

from __future__ import annotations

import os
import tempfile
from hashlib import sha256
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.paths import resolve_data_dir
from backend.app.models.commercial_document import CommercialDocument, DocumentArtifact
from backend.app.services.einvoice.validator import EInvoiceValidationReport


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
    )
    session.add(artifact)
    return artifact


__all__ = ["store_artifact"]
