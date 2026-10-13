"""Tests for ``resolve_slicer_filament`` (#1815).

The defensive filter at the end of the resolver clears ``tray_info_idx``
when its value isn't slicer-acceptable (literal material names + PFUS /
PFCN cloud-preset prefixes that the printer's calibration table can't
key on). Pre-#1815 it cleared ``setting_id`` alongside, which dropped
the slicer's only handle on the user's actual custom preset and forced
the caller into the generic-material fallback — Bambu Studio then
displayed "Generic <Material>" for spools whose Bambu Cloud detail
lookup didn't resolve a ``filament_id`` (cloud unauth on the on_ams_change
replay path, transient cloud failure, or custom presets whose detail
JSON omits ``filament_id``).

Post-#1815 the filter preserves a setting_id that's still a valid
slicer reference (PFUS / PFCN cloud user/shared preset, or GFS Bambu
official preset) even when ``tray_info_idx`` is cleared.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.slicer_filament_resolver import resolve_slicer_filament


@pytest.mark.asyncio
async def test_pfus_cloud_unavailable_preserves_setting_id():
    """Reporter scenario: PFUS cloud user preset, cloud lookup fails to
    return a filament_id. setting_id must survive so the slicer can
    still find the user's actual custom preset."""
    db = MagicMock()
    with patch(
        "backend.app.api.routes.cloud.build_authenticated_cloud",
        AsyncMock(return_value=None),
    ):
        tray_info_idx, setting_id, sub_brand, _ = await resolve_slicer_filament(
            db=db,
            current_user=None,
            slicer_filament="PFUS990b6e19965353",
            slicer_filament_name="Jayo PETG HF",
            material="PETG",
        )
    assert tray_info_idx == ""
    assert setting_id == "PFUS990b6e19965353"
    assert sub_brand is None


@pytest.mark.asyncio
async def test_pfcn_cloud_unavailable_preserves_setting_id():
    """PFCN partner/shared cloud preset (e.g. Polymaker H2D variants,
    #1648) shares the same shape problem as PFUS."""
    db = MagicMock()
    with patch(
        "backend.app.api.routes.cloud.build_authenticated_cloud",
        AsyncMock(return_value=None),
    ):
        tray_info_idx, setting_id, sub_brand, _ = await resolve_slicer_filament(
            db=db,
            current_user=None,
            slicer_filament="PFCN1234567890",
            slicer_filament_name="Polymaker PolyTerra PLA",
            material="PLA",
        )
    assert tray_info_idx == ""
    assert setting_id == "PFCN1234567890"
    assert sub_brand is None


@pytest.mark.asyncio
async def test_pfus_cloud_resolves_filament_id_regression_guard():
    """When cloud auth works and returns a filament_id, the resolver
    keeps its existing behaviour: tray_info_idx = real filament_id,
    setting_id = original PFUS reference."""
    db = MagicMock()
    cloud_mock = MagicMock()
    cloud_mock.is_authenticated = True
    cloud_mock.get_setting_detail = AsyncMock(return_value={"filament_id": "P285e239", "name": "Jayo PETG HF @P1S"})
    cloud_mock.close = AsyncMock()
    with patch(
        "backend.app.api.routes.cloud.build_authenticated_cloud",
        AsyncMock(return_value=cloud_mock),
    ):
        tray_info_idx, setting_id, sub_brand, _ = await resolve_slicer_filament(
            db=db,
            current_user=MagicMock(),
            slicer_filament="PFUS990b6e19965353",
            slicer_filament_name="Jayo PETG HF",
            material="PETG",
        )
    assert tray_info_idx == "P285e239"
    assert setting_id == "PFUS990b6e19965353"
    assert sub_brand == "Jayo PETG HF"


@pytest.mark.asyncio
async def test_gfs_cloud_unavailable_resolves_via_normalize():
    """GFS Bambu official preset + cloud unavailable: normalize strips
    the 'S' to give a real filament_id ('GFG02'), so tray_info_idx is
    valid and the defensive filter doesn't trigger. setting_id stays as
    the original GFS reference. Regression guard for the cloud-down
    Bambu-official path."""
    db = MagicMock()
    with patch(
        "backend.app.api.routes.cloud.build_authenticated_cloud",
        AsyncMock(return_value=None),
    ):
        tray_info_idx, setting_id, sub_brand, _ = await resolve_slicer_filament(
            db=db,
            current_user=None,
            slicer_filament="GFSG02",
            slicer_filament_name=None,
            material="PETG",
        )
    assert tray_info_idx == "GFG02"
    assert setting_id == "GFSG02"
    assert sub_brand is None


@pytest.mark.asyncio
async def test_literal_material_name_clears_both():
    """slicer_filament='PETG' (free-text material leak from legacy
    spools): both tray_info_idx and setting_id must be cleared so the
    caller's generic-material fallback rescues the slot. Regression
    guard that the PFUS preservation doesn't accidentally preserve
    literal material names."""
    db = MagicMock()
    with patch(
        "backend.app.api.routes.cloud.build_authenticated_cloud",
        AsyncMock(return_value=None),
    ):
        tray_info_idx, setting_id, sub_brand, _ = await resolve_slicer_filament(
            db=db,
            current_user=None,
            slicer_filament="PETG",
            slicer_filament_name=None,
            material="PETG",
        )
    assert tray_info_idx == ""
    assert setting_id == ""
    assert sub_brand is None


@pytest.mark.asyncio
async def test_cloud_preset_returns_its_authoritative_protocol_type():
    db = MagicMock()
    cloud = MagicMock()
    cloud.is_authenticated = True
    cloud.get_setting_detail = AsyncMock(
        return_value={
            "filament_id": "GFL99",
            "name": "Bambu PLA Aero @P1S",
            "setting": {"filament_type": ["PLA-AERO"]},
        }
    )
    cloud.close = AsyncMock()
    with patch("backend.app.api.routes.cloud.build_authenticated_cloud", AsyncMock(return_value=cloud)):
        tray_info_idx, setting_id, sub_brand, type_override = await resolve_slicer_filament(
            db=db,
            current_user=MagicMock(),
            slicer_filament="GFSB02",
            slicer_filament_name=None,
            material="PLA",
        )

    assert (tray_info_idx, setting_id) == ("GFL99", "GFSB02")
    assert sub_brand == "Bambu PLA Aero"
    assert type_override == "PLA-AERO"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reference", ["34d8f588-860b-5be1-bcbe-c0d46d96324b", "orca_34d8f588-860b-5be1-bcbe-c0d46d96324b"]
)
async def test_orca_spool_resolver_preserves_four_value_protocol_contract(reference):
    svc = MagicMock()
    svc.get_profile = AsyncMock(
        return_value={
            "name": "Mine PETG-CF @Orca",
            "content": {"filament_id": ["Pfc74047"], "filament_type": ["PETG-CF"]},
        }
    )
    svc.close = AsyncMock()
    with patch("backend.app.api.routes.orca_cloud._build_authenticated_service", AsyncMock(return_value=svc)):
        resolved = await resolve_slicer_filament(
            db=MagicMock(),
            current_user=MagicMock(),
            slicer_filament=reference,
            slicer_filament_name=None,
            material="PLA",
        )
    assert resolved == ("Pfc74047", "Pfc74047", "Mine PETG-CF", "PETG-CF")


class TestOrcaLookupFollowsParents:
    """``lookup_orca_filament_id`` (#3216).

    A profile that inherits carries only its overrides, so its filament id lives
    on a parent: another of the user's Orca profiles, or a system preset. The
    parent's id is what OrcaSlicer resolves the slot to, which beats a generic.
    """

    ORCA_ID = "34d8f588-860b-5be1-bcbe-c0d46d96324b"

    @staticmethod
    def _svc(profile, others=()):
        svc = MagicMock()
        svc.get_profile = AsyncMock(return_value=profile)
        svc.list_profiles = AsyncMock(return_value=[profile, *others])
        svc.close = AsyncMock()
        return svc

    async def _lookup(self, svc):
        from backend.app.services import slicer_filament_resolver

        lookup_orca_filament_id = getattr(slicer_filament_resolver, "lookup_orca_filament_id", None)
        assert lookup_orca_filament_id is not None, "Orca identity lookup behavior is absent"

        with patch(
            "backend.app.api.routes.orca_cloud._build_authenticated_service",
            AsyncMock(return_value=svc),
        ):
            return await lookup_orca_filament_id(MagicMock(), MagicMock(), self.ORCA_ID)

    @pytest.mark.asyncio
    async def test_own_id_needs_no_second_pull(self):
        svc = self._svc({"id": self.ORCA_ID, "name": "Mine", "content": {"filament_id": "Pfc74047", "inherits": ""}})
        found = await self._lookup(svc)
        assert (found.filament_id, found.source, found.reason) == ("Pfc74047", "own", "")
        svc.list_profiles.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_inherited_from_a_user_profile(self):
        child = {"id": self.ORCA_ID, "name": "Mine v2", "content": {"inherits": "Mine v1", "filament_type": ["PLA"]}}
        parent = {"id": "p", "name": "Mine v1", "content": {"name": "Mine v1", "filament_id": "Pad3f856"}}
        found = await self._lookup(self._svc(child, [parent]))
        assert (found.filament_id, found.source) == ("Pad3f856", "inherited")
        assert found.filament_type == "PLA"

    @pytest.mark.asyncio
    async def test_through_two_user_profiles_to_a_bambu_system_preset(self):
        child = {"id": self.ORCA_ID, "name": "C", "content": {"inherits": "B"}}
        middle = {"id": "b", "name": "B", "content": {"inherits": "Bambu PLA Basic @BBL H2D"}}
        found = await self._lookup(self._svc(child, [middle]))
        # The catalog id OrcaSlicer translates at the printer boundary.
        assert (found.filament_id, found.source) == ("GFA00", "inherited")

    @pytest.mark.asyncio
    async def test_an_unknown_system_parent_leaves_the_fallback(self):
        child = {"id": self.ORCA_ID, "name": "C", "content": {"inherits": "Someone PLA @Somewhere"}}
        found = await self._lookup(self._svc(child))
        assert (found.filament_id, found.reason) == ("", "no_filament_id")

    @pytest.mark.asyncio
    async def test_an_inherits_cycle_terminates(self):
        a = {"id": self.ORCA_ID, "name": "A", "content": {"inherits": "B"}}
        b = {"id": "b", "name": "B", "content": {"inherits": "A"}}
        found = await self._lookup(self._svc(a, [b]))
        assert (found.filament_id, found.reason) == ("", "no_filament_id")

    @pytest.mark.asyncio
    async def test_a_failed_lookup_says_so(self):
        svc = MagicMock()
        svc.get_profile = AsyncMock(side_effect=RuntimeError("network down"))
        svc.close = AsyncMock()
        found = await self._lookup(svc)
        assert (found.filament_id, found.reason) == ("", "lookup_failed")
        svc.close.assert_awaited()

    @pytest.mark.asyncio
    async def test_a_caller_without_orca_access_is_told_so(self):
        from backend.app.services import slicer_filament_resolver

        lookup_orca_filament_id = getattr(slicer_filament_resolver, "lookup_orca_filament_id", None)
        assert lookup_orca_filament_id is not None, "Orca identity lookup behavior is absent"

        user = MagicMock()
        user.has_permission.return_value = False
        found = await lookup_orca_filament_id(MagicMock(), user, self.ORCA_ID)
        assert found.reason == "no_permission"

    @pytest.mark.asyncio
    async def test_a_failed_parent_pull_keeps_name_and_type(self):
        """The spool resolver uses them for the slot's brand and type, as it did
        before the lookup followed parents."""
        child = {"id": self.ORCA_ID, "name": "Mine v2", "content": {"inherits": "Mine v1", "filament_type": ["PETG"]}}
        svc = self._svc(child)
        svc.list_profiles = AsyncMock(side_effect=RuntimeError("timeout"))
        found = await self._lookup(svc)
        assert (found.filament_id, found.reason) == ("", "lookup_failed")
        assert (found.name, found.filament_type) == ("Mine v2", "PETG")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw", ["PLA", "PFUS12345", "PFCN12345", "34d8f588-860b-5be1-bcbe-c0d46d96324b", "P" * 40, {"bad": "id"}, []]
)
async def test_orca_malformed_id_uses_safe_fallback(raw):
    from backend.app.services import slicer_filament_resolver

    lookup = getattr(slicer_filament_resolver, "lookup_orca_filament_id", None)
    assert lookup is not None, "Orca identity lookup behavior is absent"
    svc = TestOrcaLookupFollowsParents._svc({"name": "Bad", "content": {"filament_id": raw}})
    with patch("backend.app.api.routes.orca_cloud._build_authenticated_service", AsyncMock(return_value=svc)):
        result = await lookup(MagicMock(), MagicMock(), TestOrcaLookupFollowsParents.ORCA_ID)
    assert (result.filament_id, result.reason) == ("", "no_filament_id")


@pytest.mark.asyncio
async def test_orca_missing_pairing_falls_back_without_clearing_credentials():
    from backend.app.services import slicer_filament_resolver

    lookup = getattr(slicer_filament_resolver, "lookup_orca_filament_id", None)
    assert lookup is not None, "Orca identity lookup behavior is absent"
    with patch(
        "backend.app.api.routes.orca_cloud._build_authenticated_service",
        AsyncMock(side_effect=RuntimeError("not paired")),
    ) as builder:
        result = await lookup(MagicMock(), MagicMock(), TestOrcaLookupFollowsParents.ORCA_ID)
    assert result.reason == "lookup_failed"
    assert builder.await_args.kwargs == {"clear_on_auth_failure": False}


@pytest.mark.asyncio
async def test_orca_anonymous_replay_cannot_use_global_pairing_when_auth_enabled(db_session):
    from backend.app.services.slicer_filament_resolver import lookup_orca_filament_id

    with (
        patch("backend.app.core.auth.is_auth_enabled", AsyncMock(return_value=True)),
        patch("backend.app.api.routes.orca_cloud._build_authenticated_service", AsyncMock()) as builder,
    ):
        found = await lookup_orca_filament_id(db_session, None, TestOrcaLookupFollowsParents.ORCA_ID)
    assert found.reason == "no_permission"
    builder.assert_not_awaited()
