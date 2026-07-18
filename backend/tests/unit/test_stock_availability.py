from decimal import Decimal

import pytest

from backend.app.services.stock_availability import (
    InsufficientStock,
    StockCandidate,
    allocate_candidates,
    requirements_from_snapshot,
)


def test_filament_allocation_is_deterministic_and_can_split_spools():
    candidates = [
        StockCandidate("internal", "1", Decimal("500"), "PETG"),
        StockCandidate("internal", "2", Decimal("400"), "PETG"),
    ]

    allocations = allocate_candidates("plate:1", Decimal("750"), candidates)

    assert [(item.candidate.resource_id, item.quantity) for item in allocations] == [
        ("1", Decimal("500")),
        ("2", Decimal("250")),
    ]


def test_allocation_reports_shortage_without_partial_success():
    with pytest.raises(InsufficientStock) as error:
        allocate_candidates(
            "plate:1",
            Decimal("750"),
            [StockCandidate("internal", "1", Decimal("500"), "PETG")],
        )

    assert error.value.shortage == Decimal("250")


def test_requirements_are_derived_from_immutable_selected_variant():
    snapshot = {
        "variants": [
            {
                "sort_order": 0,
                "is_preferred": True,
                "plates": [
                    {
                        "project_plate_id": 12,
                        "stable_key": "plate-a",
                        "good_parts": 7,
                        "parts_per_print": 3,
                        "scrap_prints": 1,
                        "material_code": "PETG",
                        "grams_per_print": "100",
                    }
                ],
                "small_parts": [
                    {
                        "small_part_id": 8,
                        "quantity": "4",
                        "unit_code": "C62",
                        "description": "M3 screw",
                    }
                ],
            }
        ],
    }

    requirements = requirements_from_snapshot(snapshot, 0)

    assert requirements[0].quantity == Decimal("400")
    assert requirements[0].material_code == "PETG"
    assert requirements[1].small_part_id == 8
    assert requirements[1].quantity == Decimal("4")
