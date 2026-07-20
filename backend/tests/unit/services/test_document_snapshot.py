from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.app.schemas.commercial_document import IssuedDocumentSnapshot, SnapshotLine
from backend.app.services.document_snapshot import canonicalize_snapshot, snapshot_sha256


def _snapshot(*, metadata: dict, net_amount: Decimal = Decimal("10.00")) -> IssuedDocumentSnapshot:
    return IssuedDocumentSnapshot(
        document_type="invoice",
        number="RE-2026-0001",
        issue_date=date(2026, 7, 20),
        language="de-DE",
        currency="EUR",
        seller={"name": "Muster & Söhne GmbH", "country_code": "DE"},
        buyer={"name": "Atelier Nord GmbH", "country_code": "DE"},
        lines=(
            SnapshotLine(
                position=1,
                description="3D-Druck",
                quantity=Decimal("1.000"),
                unit_code="C62",
                unit_price=net_amount,
                net_amount=net_amount,
                tax_category_code="S",
                tax_rate=Decimal("19.00"),
            ),
        ),
        totals={
            "line_net": net_amount,
            "tax": Decimal("1.90"),
            "payable": Decimal("11.90"),
        },
        metadata=metadata,
    )


def test_snapshot_hash_is_key_order_independent_and_decimal_exact():
    left = _snapshot(metadata={"b": 2, "a": 1})
    right = _snapshot(metadata={"a": 1, "b": 2})

    canonical = canonicalize_snapshot(left)

    assert canonical == canonicalize_snapshot(right)
    assert snapshot_sha256(left) == snapshot_sha256(right)
    assert b'"net_amount":"10.00"' in canonical
    assert b'"quantity":"1.000"' in canonical
    assert "Söhne".encode() in canonical


def test_snapshot_line_order_changes_hash():
    first = _snapshot(metadata={})
    second_line = first.lines[0].model_copy(update={"position": 2, "description": "Versand"})
    reversed_snapshot = first.model_copy(update={"lines": (second_line, first.lines[0])})
    ordered_snapshot = first.model_copy(update={"lines": (first.lines[0], second_line)})

    assert snapshot_sha256(reversed_snapshot) != snapshot_sha256(ordered_snapshot)


def test_snapshot_rejects_binary_float_values():
    snapshot = _snapshot(metadata={"unsafe": 1.2})

    with pytest.raises(TypeError, match="float"):
        canonicalize_snapshot(snapshot)
