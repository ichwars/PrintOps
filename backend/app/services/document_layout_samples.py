"""Load privacy-safe, deterministic preview snapshots from packaged fixtures."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from importlib import resources
from typing import Any

from backend.app.schemas.commercial_document import IssuedDocumentSnapshot
from backend.app.services.document_catalog import DOCUMENT_CAPABILITIES, DocumentType

_PACKAGE = "backend.tests.fixtures.document_layouts"
_RESOURCE = "sample-documents.json"
_NUMBER_PREFIXES = {
    DocumentType.QUOTATION: "AG",
    DocumentType.ORDER_CONFIRMATION: "AB",
    DocumentType.DELIVERY_NOTE: "LS",
    DocumentType.ADVANCE_INVOICE: "AR",
    DocumentType.PROGRESS_INVOICE: "TR",
    DocumentType.FINAL_INVOICE: "SR",
    DocumentType.INVOICE: "RE",
    DocumentType.CANCELLATION_INVOICE: "ST",
    DocumentType.INVOICE_CORRECTION: "RK",
    DocumentType.COMMERCIAL_CREDIT_NOTE: "GS",
    DocumentType.PAYMENT_REMINDER: "ZE",
    DocumentType.DUNNING_NOTICE: "MA",
    DocumentType.SELF_BILLING: "GU",
}


@dataclass(frozen=True, slots=True)
class SampleMetadata:
    key: str
    document_type: DocumentType
    language: str
    title: str


def _fixture() -> dict[str, Any]:
    return json.loads(resources.files(_PACKAGE).joinpath(_RESOURCE).read_text(encoding="utf-8"))


def _catalog_rows(payload: dict[str, Any]) -> list[dict[str, str]]:
    rows = payload["samples"]
    expected = {(document_type.value, language) for document_type in DOCUMENT_CAPABILITIES for language in ("de", "en")}
    actual = {(row["document_type"], row["language"]) for row in rows}
    if actual != expected or len(rows) != len(expected):
        raise ValueError("sample catalog must contain each document type in de and en exactly once")
    if len({row["key"] for row in rows}) != len(rows):
        raise ValueError("sample keys must be unique")
    return rows


def sample_catalog() -> tuple[SampleMetadata, ...]:
    payload = _fixture()
    return tuple(
        SampleMetadata(
            key=row["key"],
            document_type=DocumentType(row["document_type"]),
            language=row["language"],
            title=row["key"].replace("-standard", "").replace("-", " ").title(),
        )
        for row in _catalog_rows(payload)
    )


def _expand_snapshot(payload: dict[str, Any], row: dict[str, str], index: int) -> IssuedDocumentSnapshot:
    base = deepcopy(payload["base"])
    document_type = DocumentType(row["document_type"])
    language = row["language"]
    lines = list(base["lines"])
    repeat_count = int(base["metadata"]["repeat_line_count"])
    for position in range(3, repeat_count + 3):
        lines.append(
            {
                "position": position,
                "description": (
                    f"Prüfposition {position:02d} für kontrollierte Seitenumbrüche"
                    if language == "de"
                    else f"Test line {position:02d} for controlled page breaks"
                ),
                "quantity": "1.000",
                "unit_code": "C62",
                "unit_price": "0.00",
                "net_amount": "0.00",
                "tax_category_code": "Z",
                "tax_rate": "0.00",
                "metadata": {},
            }
        )
    text_blocks = [{"purpose": block["purpose"], "text": block[language]} for block in base["text_blocks"]]
    fixed_date = date.fromisoformat(payload["fixed_date"])
    data = {
        "document_type": document_type.value,
        "number": f"{_NUMBER_PREFIXES[document_type]}-2026-{1001 + index:04d}",
        "issue_date": fixed_date,
        "service_date": fixed_date,
        "due_date": date(2026, 8, 6) if DOCUMENT_CAPABILITIES[document_type].has_payment_terms else None,
        "language": language,
        "currency": base["currency"],
        "seller": base["seller"],
        "buyer": base["buyer"],
        "lines": lines,
        "totals": base["totals"],
        "payment": base["payment"],
        "references": base["references"],
        "text_blocks": text_blocks,
        "metadata": {
            **base["metadata"],
            "sample_key": row["key"],
            "has_tax": DOCUMENT_CAPABILITIES[document_type].has_tax,
            "issuer_role": DOCUMENT_CAPABILITIES[document_type].issuer_role,
        },
    }
    return IssuedDocumentSnapshot.model_validate(data)


def load_all_samples() -> dict[str, IssuedDocumentSnapshot]:
    payload = _fixture()
    return {row["key"]: _expand_snapshot(payload, row, index) for index, row in enumerate(_catalog_rows(payload))}


def load_sample(key: str) -> IssuedDocumentSnapshot:
    try:
        return load_all_samples()[key]
    except KeyError as exc:
        raise KeyError(f"unknown document sample {key!r}") from exc
