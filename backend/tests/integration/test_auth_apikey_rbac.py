"""Integration tests for API key RBAC enforcement (security fix C1)."""

import pytest
from httpx import AsyncClient


@pytest.fixture
async def api_key_data(async_client: AsyncClient, db_session):
    """Create an API key and return its full key value."""
    from backend.app.core.auth import generate_api_key
    from backend.app.models.api_key import APIKey

    full_key, key_hash, key_prefix = generate_api_key()
    api_key = APIKey(
        name="test-key",
        key_hash=key_hash,
        key_prefix=key_prefix,
        can_queue=True,
        can_control_printer=True,
        can_read_status=True,
        enabled=True,
    )
    db_session.add(api_key)
    await db_session.commit()
    return full_key


@pytest.fixture
async def spoolman_settings(db_session):
    from backend.app.models.settings import Settings

    db_session.add(Settings(key="spoolman_enabled", value="true"))
    db_session.add(Settings(key="spoolman_url", value="http://localhost:7912"))
    await db_session.commit()


class TestApiKeyRbacDenied:
    """API keys must be refused for admin-only endpoints."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_api_key_cannot_access_settings_update_endpoint(
        self, async_client: AsyncClient, db_session, api_key_data
    ):
        """API key must not be usable for settings:update endpoints (C1)."""
        from backend.app.models.settings import Settings

        db_session.add(Settings(key="auth_enabled", value="true"))
        await db_session.commit()

        resp = await async_client.put(
            "/api/v1/settings/",
            json={},
            headers={"X-API-Key": api_key_data},
        )
        assert resp.status_code == 403
        assert "administrative operations" in resp.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_api_key_bearer_cannot_access_settings_update(
        self, async_client: AsyncClient, db_session, api_key_data
    ):
        """Bearer bb_ API key must also be refused for settings:update (C1)."""
        from backend.app.models.settings import Settings

        db_session.add(Settings(key="auth_enabled", value="true"))
        await db_session.commit()

        resp = await async_client.put(
            "/api/v1/settings/",
            json={},
            headers={"Authorization": f"Bearer {api_key_data}"},
        )
        assert resp.status_code == 403
        assert "administrative operations" in resp.json()["detail"]


class TestApiKeyRbacAllowed:
    """API keys must still work for non-admin endpoints."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_api_key_can_access_inventory_read(
        self, async_client: AsyncClient, db_session, api_key_data, spoolman_settings
    ):
        """API key must be accepted for inventory:read endpoints (C1)."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from backend.app.models.settings import Settings

        db_session.add(Settings(key="auth_enabled", value="true"))
        await db_session.commit()

        mock_client = MagicMock()
        mock_client.base_url = "http://localhost:7912"
        mock_client.health_check = AsyncMock(return_value=True)
        mock_client.get_all_spools = AsyncMock(return_value=[])
        mock_client.get_distinct_locations = AsyncMock(return_value=[])
        with patch(
            "backend.app.api.routes.spoolman_inventory._get_client",
            AsyncMock(return_value=mock_client),
        ):
            resp = await async_client.get(
                "/api/v1/spoolman/inventory/spools",
                headers={"X-API-Key": api_key_data},
            )
        assert resp.status_code == 200


class TestApiKeyDenylistIntegrity:
    """Drift-detection: assert that admin-tier permissions remain in the denylist."""

    def test_admin_permissions_are_denied_for_api_keys(self):
        """All known admin-tier permissions must be in _APIKEY_DENIED_PERMISSIONS (H1 guard)."""
        from backend.app.core.auth import _APIKEY_DENIED_PERMISSIONS
        from backend.app.core.permissions import Permission

        expected_denied = {
            # SETTINGS_READ is intentionally NOT denied — SpoolBuddy kiosk reads
            # settings via API key (e.g. to sync the UI language).
            Permission.SETTINGS_UPDATE,
            Permission.SETTINGS_BACKUP,
            Permission.SETTINGS_RESTORE,
            Permission.USERS_READ,
            Permission.USERS_CREATE,
            Permission.USERS_UPDATE,
            Permission.USERS_DELETE,
            Permission.GROUPS_READ,
            Permission.GROUPS_CREATE,
            Permission.GROUPS_UPDATE,
            Permission.GROUPS_DELETE,
            Permission.API_KEYS_READ,
            Permission.API_KEYS_CREATE,
            Permission.API_KEYS_UPDATE,
            Permission.API_KEYS_DELETE,
            Permission.GITHUB_BACKUP,
            Permission.GITHUB_RESTORE,
            Permission.FIRMWARE_UPDATE,
        }
        missing = expected_denied - _APIKEY_DENIED_PERMISSIONS
        assert not missing, (
            f"Admin-tier permissions not in API key denylist (add them to _APIKEY_DENIED_PERMISSIONS): {missing}"
        )

    def test_operational_permissions_are_allowed_for_api_keys(self):
        """Core operational permissions must NOT be in the denylist."""
        from backend.app.core.auth import _APIKEY_DENIED_PERMISSIONS
        from backend.app.core.permissions import Permission

        # NOTE: under the GHSA-r2qv-8222-hqg3 allowlist model, INVENTORY_CREATE
        # and INVENTORY_UPDATE are administrative (not in the allowlist) and
        # therefore denied for API keys regardless of denylist membership.
        # This test still guards the small denylist-redundancy set of read-y
        # permissions that the SpoolBuddy kiosk + status integrations rely on.
        expected_allowed = {
            Permission.INVENTORY_READ,
            Permission.PRINTERS_READ,
            Permission.PRINTERS_CONTROL,
            Permission.ARCHIVES_READ,
            # #1888: archive delete/update moved off the denylist to the
            # can_manage_archives allowlist scope; must not be denied.
            Permission.ARCHIVES_DELETE_ALL,
            Permission.ARCHIVES_UPDATE_ALL,
            # #1893: project CRUD moved off the denylist to the
            # can_manage_projects allowlist scope; must not be denied.
            Permission.PROJECTS_CREATE,
            Permission.PROJECTS_UPDATE,
            Permission.PROJECTS_DELETE,
            # SpoolBuddy kiosk reads settings (e.g. language) via API key — must stay allowed.
            Permission.SETTINGS_READ,
        }
        incorrectly_denied = expected_allowed & _APIKEY_DENIED_PERMISSIONS
        assert not incorrectly_denied, f"Operational permissions incorrectly in API key denylist: {incorrectly_denied}"


def _flags_in_use() -> set[str]:
    """Return every scope flag named by the API-key allowlist."""
    from backend.app.core.auth import _APIKEY_SCOPE_BY_PERMISSION

    flags: set[str] = set()
    for value in _APIKEY_SCOPE_BY_PERMISSION.values():
        flags.update((value,) if isinstance(value, str) else value)
    return flags


class TestApiKeyScopeAllowlist:
    """GHSA-r2qv-8222-hqg3 (CVSS 9.9) — allowlist-based scope enforcement.

    Verifies that ``_check_apikey_permissions`` (and the higher-level
    dependencies that call it) honour the per-permission scope mapping rather
    than the legacy denylist-only model. Failures here would re-open the
    "Read Status / Manage Queue / Control Printer / Manage Library checkboxes
    are decorative" class of bug.
    """

    def test_every_permission_has_a_classification(self):
        """Structural: every Permission must be either allowlisted or admin-denied.

        This is the load-bearing drift-detection test for the allowlist model.
        A new Permission added to ``core/permissions.py`` without a matching
        entry in ``_APIKEY_SCOPE_BY_PERMISSION`` or ``_APIKEY_DENIED_PERMISSIONS``
        is functionally admin-only (allowlist failure → 403) — that's the safe
        default, but it should be an explicit choice rather than an oversight.
        """
        from backend.app.core.auth import (
            _APIKEY_DENIED_PERMISSIONS,
            _APIKEY_SCOPE_BY_PERMISSION,
        )
        from backend.app.core.permissions import Permission

        unclassified = {
            perm
            for perm in Permission
            if perm not in _APIKEY_SCOPE_BY_PERMISSION and perm not in _APIKEY_DENIED_PERMISSIONS
        }
        assert not unclassified, (
            "Every Permission must be classified for API-key access. "
            "Either add to _APIKEY_SCOPE_BY_PERMISSION (with scope flag) or "
            f"_APIKEY_DENIED_PERMISSIONS (admin-only). Unclassified: {unclassified}"
        )

    def test_allowlist_uses_only_valid_scope_flags(self):
        """Every value in the scope mapping must be a real bool field on APIKey."""
        from backend.app.core.auth import _APIKEY_SCOPE_BY_PERMISSION
        from backend.app.models.api_key import APIKey

        # can_access_cloud / can_update_energy_cost are narrow opt-in scopes;
        # the latter routes through its own ``require_energy_cost_update`` dep
        # rather than the central allowlist, so it doesn't appear here.
        valid_flags = {
            "can_read_status",
            "can_queue",
            "can_control_printer",
            "can_manage_library",
            "can_manage_inventory",
            "can_manage_maintenance",
            "can_manage_archives",
            "can_manage_projects",
            "can_render_documents",
            "can_access_cloud",
        }
        used_flags = _flags_in_use()
        assert used_flags <= valid_flags, f"Unknown scope flags in mapping: {used_flags - valid_flags}"
        # And every flag must actually exist on the model.
        for flag in valid_flags:
            assert hasattr(APIKey, flag), f"APIKey model missing column referenced by allowlist: {flag}"

    def test_allowlist_and_denylist_are_disjoint(self):
        """A permission classified as allowlisted must not also be in the denylist (and v/v)."""
        from backend.app.core.auth import (
            _APIKEY_DENIED_PERMISSIONS,
            _APIKEY_SCOPE_BY_PERMISSION,
        )

        overlap = set(_APIKEY_SCOPE_BY_PERMISSION) & _APIKEY_DENIED_PERMISSIONS
        assert not overlap, f"Permissions in both allowlist and denylist: {overlap}"

    @pytest.mark.parametrize(
        "scope_flag",
        [
            "can_read_status",
            "can_queue",
            "can_control_printer",
            "can_manage_library",
            "can_manage_inventory",
            "can_manage_maintenance",
            "can_manage_archives",
            "can_manage_projects",
            "can_render_documents",
            "can_access_cloud",
        ],
    )
    def test_each_scope_flag_has_at_least_one_permission(self, scope_flag):
        """If a scope flag has no permissions, it's dead code — fail loudly."""
        assert scope_flag in _flags_in_use(), (
            f"No permission maps to {scope_flag} — either remove the flag or classify a permission under it."
        )


class _FakeApiKey:
    """Bool-attribute stand-in for APIKey used by the scope matrix tests.

    The ``_check_apikey_permissions`` function only inspects the four scope
    booleans, so a lightweight stub is enough; instantiating the real model
    requires a DB session which is overkill for pure-logic verification.
    """

    def __init__(
        self,
        can_read_status=False,
        can_queue=False,
        can_control_printer=False,
        can_manage_library=False,
        can_manage_inventory=False,
        can_manage_maintenance=False,
        can_manage_archives=False,
        can_manage_projects=False,
        can_render_documents=False,
    ):
        self.can_read_status = can_read_status
        self.can_queue = can_queue
        self.can_control_printer = can_control_printer
        self.can_manage_library = can_manage_library
        self.can_manage_inventory = can_manage_inventory
        self.can_manage_maintenance = can_manage_maintenance
        self.can_manage_archives = can_manage_archives
        self.can_manage_projects = can_manage_projects
        self.can_render_documents = can_render_documents


class TestCheckApiKeyPermissionsMatrix:
    """Pure-logic matrix: every (scope flag combo × representative permission) outcome.

    These are the tests that would have caught GHSA-r2qv-8222-hqg3 — they prove
    the actual gate function honours the scope flags, not just that some
    helper called by webhook.py does.
    """

    # (Permission, expected scope flag attribute, category description)
    _SCOPE_CASES = [
        # can_read_status
        ("PRINTERS_READ", "can_read_status", "read printer status"),
        ("ARCHIVES_READ", "can_read_status", "read archives"),
        ("QUEUE_READ", "can_read_status", "read queue"),
        ("SETTINGS_READ", "can_read_status", "SpoolBuddy kiosk settings read"),
        ("WEBSOCKET_CONNECT", "can_read_status", "websocket subscribe"),
        # can_queue
        ("QUEUE_CREATE", "can_queue", "add queue item"),
        ("QUEUE_DELETE_ALL", "can_queue", "delete any queue item"),
        ("ARCHIVES_REPRINT_ALL", "can_queue", "reprint an archive"),
        # can_control_printer
        ("PRINTERS_CONTROL", "can_control_printer", "start/stop print"),
        ("PRINTERS_FILES", "can_control_printer", "send file to printer"),
        ("SMART_PLUGS_CONTROL", "can_control_printer", "smart plug on/off"),
        # can_manage_library — OWN and ALL ownership variants both fold into
        # the same scope (#1832): API keys have no per-row ownership identity,
        # so splitting OWN/ALL across allowlist/denylist made the curation
        # surface unreachable. PURGE stays admin-only.
        ("LIBRARY_UPLOAD", "can_manage_library", "upload library file"),
        ("LIBRARY_UPDATE_OWN", "can_manage_library", "rename own library file"),
        ("LIBRARY_UPDATE_ALL", "can_manage_library", "rename any library file"),
        ("LIBRARY_DELETE_OWN", "can_manage_library", "delete own library file"),
        ("LIBRARY_DELETE_ALL", "can_manage_library", "delete any library file"),
        ("MAKERWORLD_IMPORT", "can_manage_library", "import from MakerWorld"),
        # can_manage_inventory
        ("INVENTORY_CREATE", "can_manage_inventory", "create spool record"),
        ("INVENTORY_UPDATE", "can_manage_inventory", "update spool / SpoolBuddy kiosk write"),
        ("INVENTORY_DELETE", "can_manage_inventory", "delete spool record"),
        ("INVENTORY_FORECAST_WRITE", "can_manage_inventory", "update forecast SKU settings"),
        # can_manage_maintenance (#1832 follow-up) — HA "cleaned nozzle" / reset counter
        # is the load-bearing use case; MAINTENANCE_UPDATE gates POST /maintenance/items/{id}/perform.
        ("MAINTENANCE_CREATE", "can_manage_maintenance", "assign maintenance type to printer"),
        ("MAINTENANCE_UPDATE", "can_manage_maintenance", "log maintenance / edit interval"),
        ("MAINTENANCE_DELETE", "can_manage_maintenance", "remove custom maintenance item"),
        # can_manage_archives (#1888) — prune print history via API key. OWN and
        # ALL ownership variants both fold into the same scope (API keys have no
        # per-row ownership identity), matching the can_manage_library shape.
        # ARCHIVES_PURGE stays admin-only (see _ADMIN_CASES).
        ("ARCHIVES_CREATE", "can_manage_archives", "create an archive"),
        ("ARCHIVES_UPDATE_OWN", "can_manage_archives", "edit own archive"),
        ("ARCHIVES_UPDATE_ALL", "can_manage_archives", "edit any archive"),
        ("ARCHIVES_DELETE_OWN", "can_manage_archives", "delete own archive"),
        ("ARCHIVES_DELETE_ALL", "can_manage_archives", "delete any archive"),
        # can_manage_projects (#1893) — project CRUD + membership via API key.
        # Projects gate on plain PROJECTS_* (no OWN/ALL split), so the three
        # permissions map directly to the one scope. PROJECTS_READ stays under
        # can_read_status. Membership edits (add-archives) gate on PROJECTS_UPDATE.
        ("PROJECTS_CREATE", "can_manage_projects", "create a project"),
        ("PROJECTS_UPDATE", "can_manage_projects", "update a project / add archives"),
        ("PROJECTS_DELETE", "can_manage_projects", "delete a project"),
        ("PIPELINES_READ", "can_read_status", "list pipelines / read run history"),
        ("DOCUMENT_LAYOUTS_READ", "can_render_documents", "read document layouts"),
        ("DOCUMENT_LAYOUTS_MANAGE", "can_render_documents", "manage document layouts"),
        ("COMMERCIAL_DOCUMENTS_READ", "can_render_documents", "read immutable document evidence"),
        ("COMMERCIAL_DOCUMENTS_EXPORT", "can_render_documents", "render and export a document"),
        ("ORDER_AUDIT_READ", "can_render_documents", "read document render audit"),
    ]

    _ADMIN_CASES = [
        # Documented denylist
        "SETTINGS_UPDATE",
        "USERS_CREATE",
        "GROUPS_DELETE",
        "API_KEYS_CREATE",
        "GITHUB_BACKUP",
        "FIRMWARE_UPDATE",
        # Unmapped administrative (allowlist fail-closed catches these too)
        "PRINTERS_CREATE",
        # LIBRARY_DELETE_ALL / LIBRARY_UPDATE_ALL moved to can_manage_library
        # under #1832 — covered by the _SCOPE_CASES matrix above.
        "LIBRARY_PURGE",
        # ARCHIVES_PURGE stays admin-only even though the rest of archive
        # management moved to can_manage_archives under #1888 — it drops the
        # print's stats contribution, mirroring LIBRARY_PURGE.
        "ARCHIVES_PURGE",
        "DISCOVERY_SCAN",
        "PIPELINES_WRITE",
    ]

    @pytest.mark.parametrize("perm_name,required_flag,_descr", _SCOPE_CASES)
    def test_permission_allowed_only_when_scope_flag_is_set(self, perm_name, required_flag, _descr):
        """For each (Permission, scope) case, true→allow and false→403."""
        from fastapi import HTTPException

        from backend.app.core.auth import _check_apikey_permissions
        from backend.app.core.permissions import Permission

        perm = Permission[perm_name].value

        # Flag set → passes
        _check_apikey_permissions(_FakeApiKey(**{required_flag: True}), [perm])

        # All flags off → 403
        with pytest.raises(HTTPException) as exc:
            _check_apikey_permissions(_FakeApiKey(), [perm])
        assert exc.value.status_code == 403

        # Wrong flag set, required flag off → 403 (no cross-scope leakage)
        other_flags = {
            f
            for f in (
                "can_read_status",
                "can_queue",
                "can_control_printer",
                "can_manage_library",
                "can_manage_inventory",
                "can_manage_maintenance",
                "can_manage_archives",
                "can_manage_projects",
                "can_render_documents",
            )
            if f != required_flag
        }
        for other in other_flags:
            with pytest.raises(HTTPException) as exc:
                _check_apikey_permissions(_FakeApiKey(**{other: True}), [perm])
            assert exc.value.status_code == 403

    @pytest.mark.parametrize("perm_name", _ADMIN_CASES)
    def test_admin_permissions_are_403_regardless_of_flags(self, perm_name):
        """A fully-flagged API key still cannot use administrative permissions."""
        from fastapi import HTTPException

        from backend.app.core.auth import _check_apikey_permissions
        from backend.app.core.permissions import Permission

        perm = Permission[perm_name].value
        all_flags = _FakeApiKey(can_read_status=True, can_queue=True, can_control_printer=True, can_manage_library=True)
        with pytest.raises(HTTPException) as exc:
            _check_apikey_permissions(all_flags, [perm])
        assert exc.value.status_code == 403
        assert "administrative" in exc.value.detail.lower() or "does not have" in exc.value.detail.lower()

    def test_unknown_permission_string_is_admin_denied(self):
        """An unrecognised permission string must fail closed, not silently pass."""
        from fastapi import HTTPException

        from backend.app.core.auth import _check_apikey_permissions

        all_flags = _FakeApiKey(can_read_status=True, can_queue=True, can_control_printer=True, can_manage_library=True)
        with pytest.raises(HTTPException) as exc:
            _check_apikey_permissions(all_flags, ["bogus:nonexistent"])
        assert exc.value.status_code == 403

    def test_empty_perm_list_is_403(self):
        """Defence-in-depth: an empty perm list must not silently allow."""
        from fastapi import HTTPException

        from backend.app.core.auth import _check_apikey_permissions

        all_flags = _FakeApiKey(can_read_status=True, can_queue=True, can_control_printer=True, can_manage_library=True)
        with pytest.raises(HTTPException) as exc:
            _check_apikey_permissions(all_flags, [])
        assert exc.value.status_code == 403

    def test_require_any_at_least_one_must_pass(self):
        """``require_any=True`` matches any-of semantics, but still respects scopes."""
        from fastapi import HTTPException

        from backend.app.core.auth import _check_apikey_permissions
        from backend.app.core.permissions import Permission

        # can_read_status only: any-of (PRINTERS_READ, QUEUE_CREATE) passes because the read flag is set.
        _check_apikey_permissions(
            _FakeApiKey(can_read_status=True),
            [Permission.PRINTERS_READ.value, Permission.QUEUE_CREATE.value],
            require_any=True,
        )
        # No flags: any-of fails.
        with pytest.raises(HTTPException):
            _check_apikey_permissions(
                _FakeApiKey(),
                [Permission.PRINTERS_READ.value, Permission.QUEUE_CREATE.value],
                require_any=True,
            )
        # All admin perms: any-of fails even with every flag set.
        with pytest.raises(HTTPException):
            _check_apikey_permissions(
                _FakeApiKey(can_read_status=True, can_queue=True, can_control_printer=True, can_manage_library=True),
                [Permission.USERS_CREATE.value, Permission.GROUPS_DELETE.value],
                require_any=True,
            )

    def test_require_all_every_perm_must_pass(self):
        """Default ``require_any=False``: every permission must pass — single failure → 403."""
        from fastapi import HTTPException

        from backend.app.core.auth import _check_apikey_permissions
        from backend.app.core.permissions import Permission

        # Read+queue set, queue+control required → fails because control flag is off.
        with pytest.raises(HTTPException) as exc:
            _check_apikey_permissions(
                _FakeApiKey(can_read_status=True, can_queue=True),
                [Permission.QUEUE_CREATE.value, Permission.PRINTERS_CONTROL.value],
            )
        assert exc.value.status_code == 403


class TestPipelineApiKeyScopes:
    """Pipeline execution spans queue and library trust dimensions."""

    def test_run_requires_queue_and_library_together(self):
        from fastapi import HTTPException

        from backend.app.core.auth import _check_apikey_permissions
        from backend.app.core.permissions import Permission

        run = Permission.PIPELINES_RUN.value
        _check_apikey_permissions(_FakeApiKey(can_queue=True, can_manage_library=True), [run])

        for partial in (
            _FakeApiKey(),
            _FakeApiKey(can_queue=True),
            _FakeApiKey(can_manage_library=True),
        ):
            with pytest.raises(HTTPException) as exc:
                _check_apikey_permissions(partial, [run])
            assert exc.value.status_code == 403

    def test_run_error_names_all_missing_scopes(self):
        from fastapi import HTTPException

        from backend.app.core.auth import _check_apikey_permissions
        from backend.app.core.permissions import Permission

        with pytest.raises(HTTPException) as exc:
            _check_apikey_permissions(_FakeApiKey(), [Permission.PIPELINES_RUN.value])
        assert "can_queue" in exc.value.detail
        assert "can_manage_library" in exc.value.detail

    def test_single_scope_error_message_is_unchanged(self):
        from fastapi import HTTPException

        from backend.app.core.auth import _check_apikey_permissions
        from backend.app.core.permissions import Permission

        with pytest.raises(HTTPException) as exc:
            _check_apikey_permissions(_FakeApiKey(), [Permission.QUEUE_CREATE.value])
        assert exc.value.detail == "API key does not have 'can_queue' permission"


class TestPipelineRoutesAcceptApiKeys:
    @pytest.fixture
    async def auth_on(self, db_session):
        from backend.app.models.settings import Settings

        db_session.add(Settings(key="auth_enabled", value="true"))
        await db_session.commit()

    async def _key(self, db_session, **flags):
        from backend.app.core.auth import generate_api_key
        from backend.app.models.api_key import APIKey

        full_key, key_hash, key_prefix = generate_api_key()
        db_session.add(
            APIKey(
                name="pipeline-key",
                key_hash=key_hash,
                key_prefix=key_prefix,
                enabled=True,
                **{"can_read_status": False, "can_queue": False, "can_manage_library": False, **flags},
            )
        )
        await db_session.commit()
        return full_key

    async def _printer(self, db_session, *, name: str, model: str = "X1C"):
        from backend.app.models.printer import Printer

        printer = Printer(
            name=name,
            serial_number=f"SERIAL-{name}",
            ip_address="192.0.2.10",
            access_code="ABCD1234",
            model=model,
            is_active=True,
        )
        db_session.add(printer)
        await db_session.commit()
        await db_session.refresh(printer)
        return printer

    async def _pipeline(
        self,
        db_session,
        *,
        target_printer_id: int | None = None,
        target_model_class: str | None = None,
    ):
        from backend.app.models.slicer_pipeline import SlicerPipeline

        pipeline = SlicerPipeline(
            name="Scoped pipeline",
            description=None,
            printer_preset_source="local",
            printer_preset_id="1",
            process_preset_source="local",
            process_preset_id="2",
            filament_presets_json="[]",
            bed_type=None,
            target_kind="specific_printer" if target_printer_id is not None else "printer_class",
            target_printer_id=target_printer_id,
            target_model_class=target_model_class,
            fanout_strategy="max_parallel",
        )
        db_session.add(pipeline)
        await db_session.commit()
        await db_session.refresh(pipeline)
        return pipeline

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_read_scope_can_list_pipelines_and_runs(self, async_client: AsyncClient, db_session, auth_on):
        key = await self._key(db_session, can_read_status=True)
        headers = {"X-API-Key": key}

        pipelines = await async_client.get("/api/v1/slicer-pipelines/", headers=headers)
        runs = await async_client.get("/api/v1/pipeline-runs", headers=headers)

        assert pipelines.status_code == 200
        assert runs.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_read_scope_cannot_author_pipeline(self, async_client: AsyncClient, db_session, auth_on):
        key = await self._key(
            db_session,
            can_read_status=True,
            can_queue=True,
            can_manage_library=True,
        )

        response = await async_client.post(
            "/api/v1/slicer-pipelines/",
            json={"name": "not-authorized"},
            headers={"X-API-Key": key},
        )

        assert response.status_code == 403
        assert "administrative operations" in response.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_read_scope_cannot_run_pipeline(self, async_client: AsyncClient, db_session, auth_on):
        key = await self._key(db_session, can_read_status=True)

        response = await async_client.post(
            "/api/v1/slicer-pipelines/1/run",
            json={"source_library_file_id": 1},
            headers={"X-API-Key": key},
        )

        assert response.status_code == 403
        assert "can_queue" in response.json()["detail"]
        assert "can_manage_library" in response.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_both_run_scopes_get_past_permission_gate(self, async_client: AsyncClient, db_session, auth_on):
        key = await self._key(
            db_session,
            can_read_status=True,
            can_queue=True,
            can_manage_library=True,
        )

        response = await async_client.post(
            "/api/v1/slicer-pipelines/999999/run",
            json={"source_library_file_id": 1},
            headers={"X-API-Key": key},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_restricted_key_cannot_run_pipeline_for_other_printer(
        self, async_client: AsyncClient, db_session, auth_on
    ):
        allowed = await self._printer(db_session, name="allowed")
        denied = await self._printer(db_session, name="denied")
        pipeline = await self._pipeline(db_session, target_printer_id=denied.id)
        key = await self._key(
            db_session,
            can_queue=True,
            can_manage_library=True,
            printer_ids=[allowed.id],
        )

        response = await async_client.post(
            f"/api/v1/slicer-pipelines/{pipeline.id}/run",
            json={"source_library_file_id": 999999},
            headers={"X-API-Key": key},
        )

        assert response.status_code == 403
        assert f"printer {denied.id}" in response.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_auth_disabled_ignores_restricted_key_printer_scope(self, async_client: AsyncClient, db_session):
        allowed = await self._printer(db_session, name="auth-off-allowed")
        denied = await self._printer(db_session, name="auth-off-denied")
        pipeline = await self._pipeline(db_session, target_printer_id=denied.id)
        key = await self._key(
            db_session,
            can_queue=True,
            can_manage_library=True,
            printer_ids=[allowed.id],
        )

        response = await async_client.post(
            f"/api/v1/slicer-pipelines/{pipeline.id}/run",
            json={"source_library_file_id": 999999},
            headers={"X-API-Key": key},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_restricted_key_cannot_run_class_containing_other_printer(
        self, async_client: AsyncClient, db_session, auth_on
    ):
        allowed = await self._printer(db_session, name="class-allowed")
        denied = await self._printer(db_session, name="class-denied")
        pipeline = await self._pipeline(db_session, target_model_class="X1C")
        key = await self._key(
            db_session,
            can_queue=True,
            can_manage_library=True,
            printer_ids=[allowed.id],
        )

        response = await async_client.post(
            f"/api/v1/slicer-pipelines/{pipeline.id}/run",
            json={"source_library_file_id": 999999},
            headers={"X-API-Key": key},
        )

        assert response.status_code == 403
        assert f"printer {denied.id}" in response.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_restricted_key_cannot_cancel_run_on_other_printer(
        self, async_client: AsyncClient, db_session, auth_on
    ):
        from backend.app.models.pipeline_run import PipelineJob, PipelineRun

        allowed = await self._printer(db_session, name="cancel-allowed")
        denied = await self._printer(db_session, name="cancel-denied")
        pipeline = await self._pipeline(db_session, target_printer_id=denied.id)
        run = PipelineRun(pipeline_id=pipeline.id, copies=1, status="queued")
        db_session.add(run)
        await db_session.flush()
        db_session.add(
            PipelineJob(
                pipeline_run_id=run.id,
                copy_index=0,
                assigned_printer_id=denied.id,
                status="pending",
            )
        )
        await db_session.commit()
        key = await self._key(
            db_session,
            can_queue=True,
            can_manage_library=True,
            printer_ids=[allowed.id],
        )

        response = await async_client.post(
            f"/api/v1/pipeline-runs/{run.id}/cancel",
            headers={"X-API-Key": key},
        )

        assert response.status_code == 403
        assert f"printer {denied.id}" in response.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_restricted_key_cannot_retry_run_on_other_printer(
        self, async_client: AsyncClient, db_session, auth_on
    ):
        from backend.app.models.library import LibraryFile
        from backend.app.models.pipeline_run import PipelineJob, PipelineRun

        allowed = await self._printer(db_session, name="retry-allowed")
        denied = await self._printer(db_session, name="retry-denied")
        pipeline = await self._pipeline(db_session, target_printer_id=denied.id)
        source = LibraryFile(
            filename="retry.3mf",
            file_path="retry.3mf",
            file_type="3mf",
            file_size=0,
            file_hash="retry-source",
            source_type="uploaded",
        )
        db_session.add(source)
        await db_session.flush()
        run = PipelineRun(
            pipeline_id=pipeline.id,
            source_library_file_id=source.id,
            copies=1,
            status="failed",
        )
        db_session.add(run)
        await db_session.flush()
        db_session.add(
            PipelineJob(
                pipeline_run_id=run.id,
                copy_index=0,
                assigned_printer_id=denied.id,
                status="failed",
            )
        )
        await db_session.commit()
        key = await self._key(
            db_session,
            can_queue=True,
            can_manage_library=True,
            printer_ids=[allowed.id],
        )

        response = await async_client.post(
            f"/api/v1/pipeline-runs/{run.id}/retry-failed",
            headers={"X-API-Key": key},
        )

        assert response.status_code == 403
        assert f"printer {denied.id}" in response.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_cloud_key_websocket_token_carries_owner_principal(
        self, async_client: AsyncClient, db_session, auth_on
    ):
        from backend.app.core.auth import verify_websocket_token
        from backend.app.models.user import User

        owner = User(username="pipeline-ws-owner", role="user", is_active=True)
        db_session.add(owner)
        await db_session.commit()
        await db_session.refresh(owner)
        key = await self._key(
            db_session,
            user_id=owner.id,
            can_read_status=True,
            can_access_cloud=True,
        )

        response = await async_client.post(
            "/api/v1/auth/ws-token",
            headers={"X-API-Key": key},
        )

        assert response.status_code == 200
        assert await verify_websocket_token(response.json()["token"]) == owner.username
