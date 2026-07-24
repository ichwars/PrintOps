from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.document_audit import DocumentAuditEvent
from backend.app.models.document_layout import (
    DocumentLayoutAuditReceipt,
    DocumentLayoutConfiguration,
)

_REASON_REQUIRED_ACTIONS = frozenset({"publication", "tax_override", "issue", "cancel", "correct", "export"})


async def append_audit(
    session: AsyncSession,
    *,
    action: str,
    object_type: str,
    object_id: int,
    actor_id: int | None,
    reason: str | None,
    before: dict | None,
    after: dict | None,
    correlation_id: str,
) -> DocumentAuditEvent:
    normalized_reason = reason.strip() if reason else None
    if action in _REASON_REQUIRED_ACTIONS and not normalized_reason:
        raise ValueError(f"A reason is required for audit action {action!r}")
    if not correlation_id.strip():
        raise ValueError("A correlation_id is required for audit events")

    audit_event = DocumentAuditEvent(
        action=action,
        object_type=object_type,
        object_id=object_id,
        actor_id=actor_id,
        reason=normalized_reason,
        before=before,
        after=after,
        correlation_id=correlation_id.strip(),
    )
    session.add(audit_event)
    return audit_event


async def append_or_merge_layout_edit_session(
    session: AsyncSession,
    *,
    layout: DocumentLayoutConfiguration,
    edit_session_id: str,
    actor_id: int | None,
    changed_field_paths: list[str],
    before_lock_version: int,
    after_lock_version: int,
) -> DocumentLayoutAuditReceipt:
    """Append one autosave receipt, merging repeated writes from one edit session."""
    normalized_session = edit_session_id.strip()
    if not normalized_session:
        raise ValueError("An edit_session_id is required")
    now = datetime.now(UTC)
    receipt = await session.scalar(
        select(DocumentLayoutAuditReceipt)
        .where(
            DocumentLayoutAuditReceipt.configuration_id == layout.id,
            DocumentLayoutAuditReceipt.edit_session_id == normalized_session,
        )
        .with_for_update()
    )
    if receipt is None:
        receipt = DocumentLayoutAuditReceipt(
            configuration_id=layout.id,
            event_type="autosave",
            edit_session_id=normalized_session,
            changed_field_paths=sorted(set(changed_field_paths)),
            actor_id=actor_id,
            before_lock_version=before_lock_version,
            after_lock_version=after_lock_version,
            first_seen_at=now,
            last_seen_at=now,
            evidence={"writes": 1},
        )
        session.add(receipt)
        return receipt

    merged_paths = sorted(set(receipt.changed_field_paths) | set(changed_field_paths))
    writes = int((receipt.evidence or {}).get("writes", 1)) + 1
    # Audit rows are append-only to ordinary ORM code. This narrowly scoped SQL update
    # is the defined edit-session coalescing operation and preserves first_seen_at.
    await session.execute(
        update(DocumentLayoutAuditReceipt)
        .where(DocumentLayoutAuditReceipt.id == receipt.id)
        .values(
            changed_field_paths=merged_paths,
            after_lock_version=after_lock_version,
            last_seen_at=now,
            evidence={"writes": writes},
        )
    )
    receipt_id = receipt.id
    session.expire(receipt)
    return await session.scalar(select(DocumentLayoutAuditReceipt).where(DocumentLayoutAuditReceipt.id == receipt_id))
