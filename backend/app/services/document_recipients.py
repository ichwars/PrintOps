"""Resolve the display names printed on commercial documents."""

from collections.abc import Mapping

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.commercial_document import CommercialDocument
from backend.app.models.customer import Customer
from backend.app.schemas.commercial_document import IssuedDocumentSnapshot


def issued_recipient_name(canonical_json: str | None) -> str | None:
    if canonical_json is None:
        return None
    try:
        snapshot = IssuedDocumentSnapshot.model_validate_json(canonical_json)
    except ValidationError:
        # Older snapshots may not match the current format.
        return None
    name = snapshot.buyer.get("name")
    return name.strip() if isinstance(name, str) and name.strip() else None


def document_recipient(document: CommercialDocument) -> str | int | None:
    if document.snapshot is not None:
        name = issued_recipient_name(document.snapshot.canonical_json)
        if name is not None:
            return name
    return document.customer_id


async def resolve_recipient_names(
    db: AsyncSession,
    recipients: Mapping[int, str | int | None],
    *,
    known_names: Mapping[int, str] | None = None,
) -> dict[int, str | None]:
    names = dict(known_names or {})
    missing_ids = {
        recipient for recipient in recipients.values() if isinstance(recipient, int) and recipient not in names
    }
    if missing_ids:
        rows = await db.execute(select(Customer.id, Customer.display_name).where(Customer.id.in_(missing_ids)))
        names.update(dict(rows.tuples().all()))
    return {
        record_id: names.get(recipient) if isinstance(recipient, int) else recipient
        for record_id, recipient in recipients.items()
    }
