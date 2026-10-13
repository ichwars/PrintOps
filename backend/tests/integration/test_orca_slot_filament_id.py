"""An Orca Cloud profile reaches the AMS slot with its own filament id (#3216).

OrcaSlicer's "Sync filaments" resolves a slot to a preset by ``filament_id``
alone. The Configure dialog used to look the id up in the browser and, when
that came back empty, quietly sent the generic for the material -- so every
Orca custom filament reached the slicer as "Generic <material>", and nothing
in the log said why. The lookup now runs in ``configure`` and its outcome is
reported back.

The slot preset row also records the filament id it was written with, so the
slot card can tell when OrcaSlicer's Device tab re-configured the slot.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


def OrcaFilamentLookup(filament_id="", source="", reason=""):
    return SimpleNamespace(filament_id=filament_id, name=None, filament_type=None, source=source, reason=reason)


ORCA_ID = "34d8f588-860b-5be1-bcbe-c0d46d96324b"


def _client():
    client = MagicMock()
    client.ams_set_filament_setting.return_value = True
    client.extrusion_cali_sel.return_value = True
    client.request_status_update.return_value = True
    return client


def _status(tray_info_idx: str = "", tray_type: str = ""):
    status = MagicMock()
    status.raw_data = {
        "ams": {
            "ams": [
                {"id": 0, "tray": [{"id": 2, "tray_info_idx": tray_info_idx, "tray_type": tray_type}]},
            ]
        }
    }
    return status


async def _configure(async_client: AsyncClient, printer_id: int, **extra):
    params = {
        "tray_info_idx": "",
        "tray_type": "PLA",
        "tray_sub_brands": "XXXXX EXAMPLE PLA Example",
        "tray_color": "FCECD6FF",
        "nozzle_temp_min": 190,
        "nozzle_temp_max": 230,
        "orca_profile_id": ORCA_ID,
    }
    params.update(extra)
    return await async_client.post(f"/api/v1/printers/{printer_id}/slots/0/2/configure", params=params)


class TestConfigureWithOrcaProfile:
    @pytest.mark.asyncio
    async def test_the_profiles_own_filament_id_goes_to_the_slot(self, async_client: AsyncClient, printer_factory):
        """The id OrcaSlicer itself sends from its Device tab: Pfc74047 in the
        reporter's log, where Bambuddy sent GFL99 for the same profile."""
        printer = await printer_factory(name="H2D")
        client = _client()
        lookup = AsyncMock(return_value=OrcaFilamentLookup("Pfc74047", source="own"))

        with (
            patch("backend.app.api.routes.printers.printer_manager") as pm,
            patch("backend.app.api.routes.printers_ams.lookup_orca_filament_id", lookup, create=True),
        ):
            pm.get_client.return_value = client
            pm.get_status.return_value = _status()
            response = await _configure(async_client, printer.id)

        assert response.status_code == 200
        body = response.json()
        assert body["tray_info_idx"] == "Pfc74047"
        assert body["orca_fallback_reason"] == ""
        assert lookup.await_args.args[2] == ORCA_ID
        kwargs = client.ams_set_filament_setting.call_args.kwargs
        assert kwargs["tray_info_idx"] == "Pfc74047"
        # Never the profile UUID: it is foreign to the printer and to the slicer.
        assert ORCA_ID not in kwargs["setting_id"]

    @pytest.mark.asyncio
    async def test_no_id_falls_back_to_the_generic_and_says_so(self, async_client: AsyncClient, printer_factory):
        """Not the slot's previous filament: reusing it would put the previous
        spool's preset in front of the slicer for a profile the user just chose."""
        printer = await printer_factory(name="H2D")
        client = _client()
        lookup = AsyncMock(return_value=OrcaFilamentLookup(reason="lookup_failed"))

        with (
            patch("backend.app.api.routes.printers.printer_manager") as pm,
            patch("backend.app.api.routes.printers_ams.lookup_orca_filament_id", lookup, create=True),
        ):
            pm.get_client.return_value = client
            pm.get_status.return_value = _status("P4d64437", "PLA")
            response = await _configure(async_client, printer.id)

        assert response.status_code == 200
        body = response.json()
        assert body["tray_info_idx"] == "GFL99"
        assert body["orca_fallback_reason"] == "lookup_failed"
        assert client.ams_set_filament_setting.call_args.kwargs["tray_info_idx"] == "GFL99"

    @pytest.mark.asyncio
    async def test_an_explicit_filament_id_skips_the_lookup(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory(name="H2D")
        client = _client()
        lookup = AsyncMock()

        with (
            patch("backend.app.api.routes.printers.printer_manager") as pm,
            patch("backend.app.api.routes.printers_ams.lookup_orca_filament_id", lookup, create=True),
        ):
            pm.get_client.return_value = client
            pm.get_status.return_value = _status()
            response = await _configure(async_client, printer.id, tray_info_idx="Pad3f856")

        assert response.status_code == 200
        lookup.assert_not_awaited()
        assert client.ams_set_filament_setting.call_args.kwargs["tray_info_idx"] == "Pad3f856"

    @pytest.mark.asyncio
    async def test_other_presets_report_no_fallback(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory(name="H2D")
        client = _client()

        with patch("backend.app.api.routes.printers.printer_manager") as pm:
            pm.get_client.return_value = client
            pm.get_status.return_value = _status()
            response = await _configure(async_client, printer.id, tray_info_idx="GFA00", orca_profile_id="")

        assert response.status_code == 200
        assert response.json()["orca_fallback_reason"] == ""
        assert response.json()["tray_info_idx"] == "GFA00"


class TestOrcaFallbackKeepsTheDialogsGenerics:
    """The fallback the Configure dialog used to pick in the browser, kept when
    the lookup moved to the server: its table has Silk, PCTG, PP and PE."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("material", "expected"),
        [
            ("PLA SILK", "GFL96"),
            ("PCTG", "GFG97"),
            ("PP", "GFP97"),
            ("PETG-CF", "GFG98"),
            ("ASA-CF", "GFB98"),
            ("PLA+", "GFL99"),
        ],
    )
    async def test_material_generic(self, async_client: AsyncClient, printer_factory, material, expected):
        printer = await printer_factory(name="H2D")
        client = _client()
        lookup = AsyncMock(return_value=OrcaFilamentLookup(reason="no_filament_id"))

        with (
            patch("backend.app.api.routes.printers.printer_manager") as pm,
            patch("backend.app.api.routes.printers_ams.lookup_orca_filament_id", lookup, create=True),
        ):
            pm.get_client.return_value = client
            pm.get_status.return_value = _status()
            response = await _configure(async_client, printer.id, tray_type=material)

        assert response.status_code == 200
        assert client.ams_set_filament_setting.call_args.kwargs["tray_info_idx"] == expected
        assert response.json()["orca_fallback_reason"] == "no_filament_id"

    @pytest.mark.asyncio
    async def test_an_unstorable_looked_up_id_is_refused(self, async_client: AsyncClient, printer_factory):
        """Same refusal as the #3003 guard: an 18-character PFUS would be
        stored truncated and resolve nowhere."""
        printer = await printer_factory(name="H2D")
        client = _client()
        lookup = AsyncMock(return_value=OrcaFilamentLookup("PFUS9ac902733670a9", source="own"))

        with (
            patch("backend.app.api.routes.printers.printer_manager") as pm,
            patch("backend.app.api.routes.printers_ams.lookup_orca_filament_id", lookup, create=True),
        ):
            pm.get_client.return_value = client
            pm.get_status.return_value = _status()
            response = await _configure(async_client, printer.id)

        assert client.ams_set_filament_setting.call_args.kwargs["tray_info_idx"] == "GFL99"
        assert response.json()["orca_fallback_reason"] == "no_filament_id"

    @pytest.mark.asyncio
    async def test_a_kprofile_realignment_clears_the_warning(self, async_client: AsyncClient, printer_factory):
        """The slot ends up on the K-profile's own filament, not a generic."""
        printer = await printer_factory(name="H2D")
        client = _client()
        lookup = AsyncMock(return_value=OrcaFilamentLookup(reason="no_filament_id"))

        with (
            patch("backend.app.api.routes.printers.printer_manager") as pm,
            patch("backend.app.api.routes.printers_ams.lookup_orca_filament_id", lookup, create=True),
        ):
            pm.get_client.return_value = client
            pm.get_status.return_value = _status()
            response = await _configure(async_client, printer.id, kprofile_filament_id="P4d64437")

        assert response.status_code == 200
        assert response.json()["tray_info_idx"] == "P4d64437"
        assert response.json()["orca_fallback_reason"] == ""


class TestSlotPresetRecordsItsFilamentId:
    @pytest.mark.asyncio
    async def test_saved_and_returned(self, async_client: AsyncClient, printer_factory):
        printer = await printer_factory(name="H2D")
        url = f"/api/v1/printers/{printer.id}/slot-presets/0/2"
        response = await async_client.put(
            url,
            params={
                "preset_id": f"orca_{ORCA_ID}",
                "preset_name": "XXXXX EXAMPLE PLA Example",
                "preset_source": "orca_cloud",
                "tray_info_idx": "Pfc74047",
            },
        )
        assert response.status_code == 200
        assert response.json()["tray_info_idx"] == "Pfc74047"

        assert (await async_client.get(url)).json()["tray_info_idx"] == "Pfc74047"
        listed = (await async_client.get(f"/api/v1/printers/{printer.id}/slot-presets")).json()
        assert listed["2"]["tray_info_idx"] == "Pfc74047"

    @pytest.mark.asyncio
    async def test_a_save_without_one_clears_the_old_one(self, async_client: AsyncClient, printer_factory):
        """A stale id must not outlive the preset it came with: the slot card
        would compare the new preset against the old preset's filament."""
        printer = await printer_factory(name="H2D")
        url = f"/api/v1/printers/{printer.id}/slot-presets/0/2"
        await async_client.put(
            url, params={"preset_id": "GFSL99", "preset_name": "Generic PLA", "tray_info_idx": "GFL99"}
        )
        response = await async_client.put(
            url, params={"preset_id": "local_5", "preset_name": "Mine", "preset_source": "local"}
        )

        assert response.status_code == 200
        assert response.json()["tray_info_idx"] is None
        assert (await async_client.get(url)).json()["tray_info_idx"] is None

    @pytest.mark.asyncio
    async def test_an_overlong_id_is_dropped_not_refused(self, async_client: AsyncClient, printer_factory):
        """Refusing it would lose the preset save itself, which the dialog only
        logs; recording nothing keeps the row shown as before."""
        printer = await printer_factory(name="H2D")
        url = f"/api/v1/printers/{printer.id}/slot-presets/0/2"
        response = await async_client.put(url, params={"preset_id": "x", "preset_name": "X", "tray_info_idx": "P" * 40})
        assert response.status_code == 200
        assert response.json()["tray_info_idx"] is None


@pytest.mark.asyncio
async def test_nullable_identity_migration_preserves_legacy_rows_and_is_repeatable():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from backend.app.core import database

    migrate = getattr(database, "_migrate_slot_preset_identity", None)
    assert migrate is not None, "Slot identity migration behavior is absent"
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("CREATE TABLE slot_preset_mappings (id INTEGER PRIMARY KEY, preset_name VARCHAR(200))")
            )
            await conn.execute(text("INSERT INTO slot_preset_mappings VALUES (1, 'Legacy')"))
            await migrate(conn)
            await migrate(conn)
            assert (await conn.execute(text("SELECT preset_name, tray_info_idx FROM slot_preset_mappings"))).one() == (
                "Legacy",
                None,
            )
            await conn.execute(text("UPDATE slot_preset_mappings SET tray_info_idx='Pfc74047'"))
            await migrate(conn)
            assert (
                await conn.execute(text("SELECT tray_info_idx FROM slot_preset_mappings"))
            ).scalar_one() == "Pfc74047"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_orca_configure_uses_profiles_protocol_material(async_client, printer_factory):
    printer = await printer_factory()
    client = _client()
    lookup = AsyncMock(
        return_value=SimpleNamespace(
            filament_id="Pfc74047", name="Mine", filament_type="PETG-CF", source="own", reason=""
        )
    )
    with (
        patch("backend.app.api.routes.printers.printer_manager") as pm,
        patch("backend.app.api.routes.printers_ams.lookup_orca_filament_id", lookup),
    ):
        pm.get_client.return_value = client
        response = await _configure(async_client, printer.id)
    assert response.status_code == 200
    assert client.ams_set_filament_setting.call_args.kwargs["tray_type"] == "PETG-CF"


@pytest.mark.asyncio
async def test_orca_configure_cloud_api_key_fence_never_looks_up_denied_key(async_client, printer_factory):
    from fastapi import HTTPException

    printer = await printer_factory()
    client = _client()
    with (
        patch("backend.app.api.routes.printers.printer_manager") as pm,
        patch(
            "backend.app.api.routes.cloud._cloud_api_key_gate",
            AsyncMock(side_effect=HTTPException(403, "Missing cloud scope")),
        ),
        patch("backend.app.api.routes.printers_ams.lookup_orca_filament_id", AsyncMock()) as lookup,
    ):
        pm.get_client.return_value = client
        response = await _configure(async_client, printer.id)
    assert response.status_code == 200
    assert response.json()["orca_fallback_reason"] == "no_permission"
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_orca_configure_cloud_api_key_uses_its_owner(async_client, printer_factory):
    printer = await printer_factory()
    client = _client()
    owner = MagicMock()

    async def gate(request, **kwargs):
        request.state.api_key_owner = owner

    with (
        patch("backend.app.api.routes.printers.printer_manager") as pm,
        patch("backend.app.api.routes.cloud._cloud_api_key_gate", gate),
        patch(
            "backend.app.api.routes.printers_ams.lookup_orca_filament_id",
            AsyncMock(return_value=OrcaFilamentLookup("Pfc74047", source="own")),
        ) as lookup,
    ):
        pm.get_client.return_value = client
        response = await _configure(async_client, printer.id)
    assert response.status_code == 200
    assert lookup.await_args.args[1] is owner


@pytest.mark.asyncio
@pytest.mark.parametrize("filament_id, expected", [("", "GFL99"), ("Pfc74047", "Pfc74047")])
async def test_local_inventory_orca_assignment_records_actual_identity_without_slot_reuse(
    db_session, printer_factory, filament_id, expected
):
    from sqlalchemy import select

    from backend.app.api.routes.inventory import apply_spool_to_slot_via_mqtt
    from backend.app.models.slot_preset import SlotPresetMapping
    from backend.app.models.spool import Spool

    printer = await printer_factory(model="X1C")
    spool = Spool(
        material="PLA", brand="Mine", slicer_filament=ORCA_ID, slicer_filament_name="Mine PLA", label_weight=1000
    )
    db_session.add(spool)
    await db_session.commit()
    from sqlalchemy.orm import selectinload

    spool = (
        await db_session.execute(select(Spool).options(selectinload(Spool.k_profiles)).where(Spool.id == spool.id))
    ).scalar_one()
    svc = MagicMock()
    svc.get_profile = AsyncMock(
        return_value={"name": "Mine PLA", "content": {"filament_id": filament_id, "filament_type": ["PLA"]}}
    )
    svc.close = AsyncMock()
    client = _client()
    with (
        patch("backend.app.services.printer_manager.printer_manager") as pm,
        patch("backend.app.api.routes.orca_cloud._build_authenticated_service", AsyncMock(return_value=svc)),
    ):
        pm.get_client.return_value = client
        pm.get_status.return_value = None
        result = await apply_spool_to_slot_via_mqtt(
            db=db_session,
            current_user=MagicMock(),
            spool=spool,
            printer_id=printer.id,
            ams_id=0,
            tray_id=2,
            current_tray_info_idx="P4d64437",
            current_tray_type="PLA",
        )
    assert result is True
    assert client.ams_set_filament_setting.call_args.kwargs["tray_info_idx"] == expected
    mapping = (
        await db_session.execute(select(SlotPresetMapping).where(SlotPresetMapping.printer_id == printer.id))
    ).scalar_one()
    assert (mapping.preset_id, mapping.preset_source, mapping.tray_info_idx) == (
        f"orca_{ORCA_ID}",
        "orca_cloud",
        expected,
    )


@pytest.mark.asyncio
async def test_orca_uuid_is_never_sent_as_a_printer_identity(async_client, printer_factory):
    printer = await printer_factory()
    client = _client()
    with (
        patch("backend.app.api.routes.printers.printer_manager") as pm,
        patch(
            "backend.app.api.routes.printers_ams.lookup_orca_filament_id",
            AsyncMock(return_value=OrcaFilamentLookup("Pfc74047", source="own")),
        ),
    ):
        pm.get_client.return_value = client
        response = await _configure(async_client, printer.id, tray_info_idx=ORCA_ID, setting_id=ORCA_ID)
    assert response.status_code == 200
    kwargs = client.ams_set_filament_setting.call_args.kwargs
    assert kwargs["tray_info_idx"] == "Pfc74047"
    assert kwargs["setting_id"] == "Pfc74047"


@pytest.mark.asyncio
async def test_orca_uuid_cannot_enter_calibration_context(async_client, printer_factory):
    printer = await printer_factory()
    client = _client()
    with patch("backend.app.api.routes.printers.printer_manager") as pm:
        pm.get_client.return_value = client
        response = await _configure(
            async_client,
            printer.id,
            tray_info_idx="Pfc74047",
            kprofile_filament_id=ORCA_ID,
            kprofile_setting_id=ORCA_ID,
        )
    assert response.status_code == 200
    assert client.ams_set_filament_setting.call_args.kwargs["tray_info_idx"] == "Pfc74047"
    assert client.extrusion_cali_sel.call_args.kwargs["filament_id"] == "Pfc74047"


@pytest.mark.asyncio
async def test_slot_identity_postgres_duplicate_column_uses_savepoint_and_sqlstate():
    from sqlalchemy.exc import ProgrammingError

    from backend.app.core.database import _migrate_slot_preset_identity

    class PostgresDuplicateColumn(Exception):
        sqlstate = "42701"

    conn = MagicMock()
    conn.begin_nested.return_value.__aenter__ = AsyncMock()
    conn.begin_nested.return_value.__aexit__ = AsyncMock(return_value=False)
    conn.execute = AsyncMock(
        side_effect=[None, ProgrammingError("ALTER TABLE", {}, PostgresDuplicateColumn("Spalte bereits vorhanden"))]
    )
    await _migrate_slot_preset_identity(conn)
    await _migrate_slot_preset_identity(conn)
    assert conn.begin_nested.call_count == 2
    assert (
        str(conn.execute.await_args.args[0]) == "ALTER TABLE slot_preset_mappings ADD COLUMN tray_info_idx VARCHAR(32)"
    )
