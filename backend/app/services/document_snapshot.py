from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.commercial_document import (
    CommercialDocument,
    DocumentSnapshot,
    ImmutableDocumentError,
)
from backend.app.schemas.commercial_document import IssuedDocumentSnapshot


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="python"))
    if is_dataclass(value) and not isinstance(value, type):
        return _canonical_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return normalized.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        raise TypeError("Binary float values are forbidden in document snapshots")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"Unsupported snapshot value: {type(value).__name__}")


def canonicalize_snapshot(snapshot: IssuedDocumentSnapshot) -> bytes:
    return json.dumps(
        _canonical_value(snapshot),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def snapshot_sha256(snapshot: IssuedDocumentSnapshot) -> str:
    return sha256(canonicalize_snapshot(snapshot)).hexdigest()


async def attach_issued_snapshot(
    session: AsyncSession,
    document: CommercialDocument,
    snapshot: IssuedDocumentSnapshot,
    *,
    configuration_id: int | None,
    configuration_version: int,
    tax_rule_version: str,
    einvoice_rule_versions: dict[str, str],
    actor_id: int | None,
) -> DocumentSnapshot:
    if document.technical_status != "issued":
        raise ValueError("A snapshot can only be attached to an issued document")
    existing = await session.scalar(
        select(DocumentSnapshot.id).where(DocumentSnapshot.document_id == document.id)
    )
    if existing is not None:
        raise ImmutableDocumentError("The issued document already has a snapshot")

    canonical = canonicalize_snapshot(snapshot)
    evidence = DocumentSnapshot(
        document_id=document.id,
        canonical_json=canonical.decode("utf-8"),
        sha256=sha256(canonical).hexdigest(),
        configuration_id=configuration_id,
        configuration_version=configuration_version,
        tax_rule_version=tax_rule_version,
        einvoice_rule_versions=dict(einvoice_rule_versions),
        issued_by_id=actor_id,
        issued_at=datetime.now(UTC),
    )
    session.add(evidence)
    return evidence


async def replace_issued_snapshot(
    session: AsyncSession,
    document_id: int,
    snapshot: IssuedDocumentSnapshot,
) -> DocumentSnapshot:
    del session, document_id, snapshot
    raise ImmutableDocumentError("Issued document snapshots cannot be replaced")
