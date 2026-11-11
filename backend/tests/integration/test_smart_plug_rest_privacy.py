import pytest
from httpx import AsyncClient

from backend.app.core.auth import generate_api_key
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.services.secret_fields import SECRET_PLACEHOLDER
from backend.tests.integration.test_ownership_permissions import TestOwnershipPermissionsSetup

_PRIVATE_CONFIGURATION = {
    "password": "fixture-password",
    "rest_headers": '{"Authorization":"Bearer fixture-header"}',
    "rest_on_url": "http://login:fixture-userinfo@plug.example.test/on",
    "rest_on_body": '{"payload":"fixture-on-body"}',
    "rest_off_url": "http://plug.example.test/off?auth_key=fixture-query",
    "rest_off_body": '{"payload":"fixture-off-body"}',
    "rest_status_url": "http://plug.example.test/status/fixture-status",
    "rest_power_url": "http://plug.example.test/power/fixture-power",
    "rest_energy_url": "http://plug.example.test/energy/fixture-energy",
}


class TestRESTPlugPrivacy(TestOwnershipPermissionsSetup):
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_readers_and_status_keys_receive_only_operational_fields(
        self, async_client: AsyncClient, auth_setup, printer_factory, smart_plug_factory, db_session
    ):
        printer = await printer_factory()
        plug = await smart_plug_factory(
            plug_type="rest",
            printer_id=printer.id,
            rest_status_path="state",
            **_PRIVATE_CONFIGURATION,
        )
        await db_session.commit()
        admin = {"Authorization": f"Bearer {auth_setup['admin_token']}"}
        viewer = {"Authorization": f"Bearer {auth_setup['viewer_token']}"}
        key, key_hash, prefix = generate_api_key()
        db_session.add(
            APIKey(
                name="Status key",
                key_hash=key_hash,
                key_prefix=prefix,
                user_id=auth_setup["admin_user"]["id"],
                can_read_status=True,
            )
        )
        await db_session.commit()
        group = await async_client.post(
            "/api/v1/groups/",
            headers=admin,
            json={
                "name": "Plug editors",
                "permissions": [Permission.SMART_PLUGS_READ.value, Permission.SMART_PLUGS_UPDATE.value],
            },
        )
        assert group.status_code == 201
        editor = await async_client.post(
            "/api/v1/users/",
            headers=admin,
            json={"username": "plug-editor", "password": "EditorPass1!", "group_ids": [group.json()["id"]]},
        )
        assert editor.status_code == 201
        login = await async_client.post(
            "/api/v1/auth/login", json={"username": "plug-editor", "password": "EditorPass1!"}
        )
        editor_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        callers = [
            ("viewer", viewer, False),
            ("status header", {"X-API-Key": key}, False),
            ("status bearer", {"Authorization": f"Bearer {key}"}, False),
            ("editor", editor_headers, True),
            ("admin", admin, True),
        ]
        for caller, headers, may_edit in callers:
            for path in ("/", f"/{plug.id}", f"/by-printer/{printer.id}"):
                response = await async_client.get(f"/api/v1/smart-plugs{path}", headers=headers)
                assert response.status_code == 200, (caller, path)
                payload = response.json()[0] if path == "/" else response.json()
                assert payload["id"] == plug.id
                assert payload["rest_status_path"] == "state"
                if may_edit:
                    assert payload["rest_on_url"] == _PRIVATE_CONFIGURATION["rest_on_url"]
                    assert payload["rest_on_body"] == _PRIVATE_CONFIGURATION["rest_on_body"]
                    assert payload["rest_headers"] == payload["password"] == SECRET_PLACEHOLDER
                else:
                    assert "fixture-" not in response.text
                    assert all(payload[field] is None for field in _PRIVATE_CONFIGURATION)
