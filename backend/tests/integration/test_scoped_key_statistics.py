"""Per-user statistics and Obico diagnostics respect the key owner's grants."""

import csv
from unittest.mock import AsyncMock

import pytest

from backend.app.core.auth import generate_api_key
from backend.app.models.api_key import APIKey
from backend.app.models.settings import Settings
from backend.app.models.user import User
from backend.app.services.obico_detection import obico_detection_service
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_statistics_and_obico_use_the_selected_keys_owner_and_printers(
    async_client, db_session, printer_factory, archive_factory, monkeypatch
):
    await _setup_admin(async_client)
    visible, hidden = await printer_factory(), await printer_factory()
    owner = User(username="stats-reader", allowed_printer_ids=[visible.id])
    db_session.add(owner)
    await db_session.flush()
    token, key_hash, prefix = generate_api_key()
    db_session.add_all(
        [
            APIKey(
                name="Stats",
                key_hash=key_hash,
                key_prefix=prefix,
                user_id=owner.id,
                printer_ids=[visible.id, hidden.id],
            ),
            Settings(key="energy_tracking_mode", value="per_print"),
        ]
    )
    await db_session.commit()
    await archive_factory(visible.id, created_by_id=owner.id)
    await archive_factory(hidden.id, created_by_id=owner.id)
    await archive_factory(None, created_by_id=owner.id)
    headers = {"X-API-Key": "invalid", "Authorization": f"Bearer {token}"}

    stats = "/api/v1/archives/stats"
    for endpoint in (stats, f"{stats}/export"):
        denied = await async_client.get(endpoint, params={"created_by_id": owner.id}, headers=headers)
        assert denied.status_code == 403
        assert denied.json()["detail"] == "Permission stats:filter_by_user required"

    summary = await async_client.get(stats, headers=headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["prints_by_printer"] == {str(visible.id): 1}

    export = await async_client.get(f"{stats}/export", headers=headers)
    assert export.status_code == 200, export.text
    assert ["Total Prints", "1"] in list(csv.reader(export.text.splitlines()))

    monkeypatch.setattr(
        obico_detection_service, "_load_settings", AsyncMock(return_value={"enabled": True, "enabled_printers": None})
    )
    monkeypatch.setattr(
        obico_detection_service,
        "get_per_printer",
        lambda: {
            visible.id: {"class": "error", "error": "Internal visible-printer error"},
            hidden.id: {"class": "error", "error": "Internal hidden-printer error"},
        },
    )
    monkeypatch.setattr(obico_detection_service, "_last_error", "Internal hidden-printer error")
    obico = await async_client.get("/api/v1/obico/printer-status", headers=headers)
    assert obico.status_code == 200
    assert obico.json() == {
        "enabled": True,
        "monitored_printers": [visible.id],
        "per_printer": {str(visible.id): {"class": "error", "error": None}},
        "last_error": None,
    }
