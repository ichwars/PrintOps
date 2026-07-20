from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.document_audit import DocumentAuditEvent

_REASON_REQUIRED_ACTIONS = frozenset(
    {"publication", "tax_override", "issue", "cancel", "correct", "export"}
)


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
