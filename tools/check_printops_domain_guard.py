"""Guard PrintOps-specific domains during upstream integrations.

The Bambuddy upstream does not contain PrintOps commerce, warehouse, document,
and e-invoice domains. A direct upstream merge therefore looks like hundreds of
valid deletions to Git. This check makes those deletions explicit before they
can slip through a review or CI run.
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from dataclasses import dataclass

PROTECTED_PATTERNS = (
    "backend/app/api/routes/business_profiles.py",
    "backend/app/api/routes/calculation*.py",
    "backend/app/api/routes/commercial_documents.py",
    "backend/app/api/routes/customers.py",
    "backend/app/api/routes/document_*.py",
    "backend/app/api/routes/einvoices.py",
    "backend/app/api/routes/equipment.py",
    "backend/app/api/routes/offers.py",
    "backend/app/api/routes/orders.py",
    "backend/app/api/routes/procurement.py",
    "backend/app/api/routes/small_parts.py",
    "backend/app/models/business_profile.py",
    "backend/app/models/calculation*.py",
    "backend/app/models/commerce.py",
    "backend/app/models/commercial_document.py",
    "backend/app/models/customer.py",
    "backend/app/models/document_*.py",
    "backend/app/models/equipment.py",
    "backend/app/models/number_sequence.py",
    "backend/app/models/procurement.py",
    "backend/app/models/small_part.py",
    "backend/app/models/stock_reservation.py",
    "backend/app/models/warehouse_number_sequence.py",
    "backend/app/resources/document_defaults/**",
    "backend/app/resources/einvoice/**",
    "backend/app/resources/pdf/**",
    "backend/app/schemas/business_profile.py",
    "backend/app/schemas/calculation*.py",
    "backend/app/schemas/commerce.py",
    "backend/app/schemas/commercial_document.py",
    "backend/app/schemas/customer.py",
    "backend/app/schemas/document_*.py",
    "backend/app/schemas/einvoice.py",
    "backend/app/schemas/equipment.py",
    "backend/app/schemas/number_sequence.py",
    "backend/app/schemas/procurement.py",
    "backend/app/schemas/small_part.py",
    "backend/app/schemas/stock_reservation.py",
    "backend/app/schemas/warehouse_number_sequence.py",
    "backend/app/services/business_profile*.py",
    "backend/app/services/calculation*.py",
    "backend/app/services/commercial_documents.py",
    "backend/app/services/customer.py",
    "backend/app/services/document_*.py",
    "backend/app/services/einvoice/**",
    "backend/app/services/equipment*.py",
    "backend/app/services/number_sequence.py",
    "backend/app/services/offers.py",
    "backend/app/services/procurement.py",
    "backend/app/services/small_parts.py",
    "backend/app/services/stock_*.py",
    "backend/app/services/tax_decision.py",
    "backend/app/services/warehouse_number_sequence.py",
    "docs/document-management.md",
    "docs/order-management.md",
    "frontend/src/api/calculations.ts",
    "frontend/src/api/document*.ts",
    "frontend/src/api/offers.ts",
    "frontend/src/api/procurement.ts",
    "frontend/src/api/smallParts.ts",
    "frontend/src/components/orders/**",
    "frontend/src/components/settings/BusinessProfile*.tsx",
    "frontend/src/components/settings/SmallPartsSettings.tsx",
    "frontend/src/components/settings/WarehouseNumberSequenceSettings.tsx",
    "frontend/src/components/settings/document-layout/**",
    "frontend/src/components/settings/documents/**",
    "frontend/src/components/warehouse/**",
    "frontend/src/pages/CalculationsPage.tsx",
    "frontend/src/pages/OffersPage.tsx",
    "frontend/src/pages/Order*.tsx",
    "frontend/src/pages/SmallPartsPage.tsx",
    "frontend/src/pages/SuppliersPage.tsx",
    "frontend/src/pages/WarehousePage.tsx",
)


@dataclass(frozen=True)
class DiffEntry:
    status: str
    path: str


def _normalize(path: str) -> str:
    return path.replace("\\", "/")


def is_protected(path: str) -> bool:
    normalized = _normalize(path)
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in PROTECTED_PATTERNS)


def parse_name_status(output: str) -> list[DiffEntry]:
    entries: list[DiffEntry] = []
    for raw_line in output.splitlines():
        if not raw_line.strip():
            continue
        parts = raw_line.split("\t")
        status = parts[0]
        path = parts[-1]
        if status.startswith("D"):
            entries.append(DiffEntry(status=status, path=_normalize(path)))
    return entries


def diff_name_status(base: str, head: str) -> str:
    result = subprocess.run(
        ["git", "diff", "--name-status", f"{base}..{head}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="Base ref for git diff")
    parser.add_argument("--head", default="HEAD", help="Head ref for git diff")
    parser.add_argument(
        "--allow-protected-deletions",
        action="store_true",
        help="Report but do not fail. Use only for deliberate removals with review notes.",
    )
    args = parser.parse_args()

    entries = parse_name_status(diff_name_status(args.base, args.head))
    protected = [entry.path for entry in entries if is_protected(entry.path)]
    if not protected:
        print("PrintOps domain guard: no protected deletions detected")
        return 0

    print("PrintOps domain guard: protected deletions detected", file=sys.stderr)
    for path in protected:
        print(f"  D {path}", file=sys.stderr)
    return 0 if args.allow_protected_deletions else 1


if __name__ == "__main__":
    raise SystemExit(main())
