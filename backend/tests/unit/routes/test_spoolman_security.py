"""Authorization regressions for Spoolman printer-side effects."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from backend.app.api.routes.spoolman import LinkSpoolRequest, link_spool
from backend.app.api.routes.spoolman_inventory import (
    SpoolSlotAssignmentRequest,
    assign_spoolman_slot,
)


@pytest.mark.asyncio
async def test_slot_assignment_enforces_api_key_printer_allowlist():
    body = SpoolSlotAssignmentRequest(
        spoolman_spool_id=10,
        printer_id=7,
        ams_id=0,
        tray_id=0,
    )
    api_key = SimpleNamespace(printer_ids=[3])

    with (
        patch(
            "backend.app.api.routes.spoolman_inventory._validate_api_key",
            new=AsyncMock(return_value=api_key),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await assign_spoolman_slot(
            body,
            AsyncMock(),
            None,
            None,
            "bb_inventory_and_control",
        )

    assert exc_info.value.status_code == 403
    assert "printer 7" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_link_spool_requires_printer_permission_for_ams_side_effects():
    request = LinkSpoolRequest(
        tray_uuid="a" * 32,
        printer_id=7,
        ams_id=0,
        tray_id=0,
    )
    user = SimpleNamespace(has_all_permissions=lambda *_: False)
    client = SimpleNamespace(health_check=AsyncMock(return_value=True))

    with (
        patch(
            "backend.app.api.routes.spoolman.get_spoolman_settings",
            new=AsyncMock(return_value={"enabled": True, "url": "https://spoolman.example"}),
        ),
        patch("backend.app.api.routes.spoolman.get_spoolman_client", new=AsyncMock(return_value=client)),
        pytest.raises(HTTPException) as exc_info,
    ):
        await link_spool(10, request, AsyncMock(), user)

    assert exc_info.value.status_code == 403
    assert "Printer AMS control permission" in str(exc_info.value.detail)
