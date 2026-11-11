from unittest.mock import AsyncMock

import pytest

from backend.app.core.auth import generate_api_key
from backend.app.models.api_key import APIKey
from backend.app.services import external_camera
from backend.tests.integration.test_ownership_permissions import TestOwnershipPermissionsSetup

_STREAM = "rtsp://camera-user:fixture-stream-password@camera.example.test/live"
_SNAPSHOT = "http://fixture-snapshot-token@camera.example.test/snapshot"


class TestPrinterCameraPrivacy(TestOwnershipPermissionsSetup):
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_printer_reads_and_test_connection_respect_camera_permissions(
        self, async_client, auth_setup, db_session, printer_factory, monkeypatch
    ):
        printer = await printer_factory(
            external_camera_enabled=True,
            external_camera_type="rtsp",
            external_camera_url=_STREAM,
            external_camera_snapshot_url=_SNAPSHOT,
        )
        token, key_hash, prefix = generate_api_key()
        db_session.add(APIKey(name="Camera status", key_hash=key_hash, key_prefix=prefix, can_read_status=True))
        await db_session.commit()
        admin = {"Authorization": f"Bearer {auth_setup['admin_token']}"}
        viewer = {"Authorization": f"Bearer {auth_setup['viewer_token']}"}
        status_key = {"X-API-Key": token}

        for caller, headers, may_edit in [
            ("viewer", viewer, False),
            ("status key", status_key, False),
            ("admin", admin, True),
        ]:
            for path in ("/", f"/{printer.id}"):
                response = await async_client.get(f"/api/v1/printers{path}", headers=headers)
                assert response.status_code == 200, (caller, path)
                record = response.json()[0] if path == "/" else response.json()
                if may_edit:
                    assert record["external_camera_url"] == _STREAM
                    assert record["external_camera_snapshot_url"] == _SNAPSHOT
                else:
                    assert "fixture-" not in response.text
                    assert record["external_camera_url"] == "rtsp://camera-user:[REDACTED]@camera.example.test/live"
                    assert record["external_camera_snapshot_url"] == "http://[REDACTED]@camera.example.test/snapshot"

        test_connection = AsyncMock(return_value={"success": True})
        monkeypatch.setattr(external_camera, "test_connection", test_connection)
        endpoint = f"/api/v1/printers/{printer.id}/camera/external/test"
        parameters = {"url": _STREAM, "camera_type": "rtsp"}
        denied = await async_client.post(endpoint, json=parameters, headers=viewer)
        assert denied.status_code == 403
        test_connection.assert_not_awaited()
        for values in ({"json": parameters}, {"params": parameters}):
            result = await async_client.post(endpoint, headers=admin, **values)
            assert result.status_code == 200
            assert result.json() == {"success": True}
        assert test_connection.await_count == 2
        test_connection.assert_awaited_with(_STREAM, "rtsp")
