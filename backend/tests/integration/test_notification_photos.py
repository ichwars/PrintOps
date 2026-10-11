"""Selected notification images never grant a session or broader media access."""

import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

from backend.app.core.config import settings
from backend.app.models.auth_ephemeral import AuthEphemeralToken
from backend.app.models.notification import NotificationProvider
from backend.app.models.settings import Settings
from backend.app.services.notification_service import NotificationService


@pytest.fixture
def jpeg():
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(stream, "JPEG")
    return stream.getvalue()


async def test_photo_opt_out_omits_existing_attachment_but_default_preserves_it(monkeypatch, jpeg):
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "sent"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        service = NotificationService()
        monkeypatch.setattr(service, "_get_client", AsyncMock(return_value=client))
        provider = NotificationProvider(
            name="Photos", provider_type="ntfy", config='{"topic":"photos"}', quiet_hours_enabled=False
        )
        await service._send_to_provider(provider, "Print", "Finished", image_data=jpeg)
        assert requests[0].method == "PUT"
        assert requests[0].content == jpeg
        provider.attach_photo = False
        await service._send_to_provider(provider, "Print", "Finished", image_data=jpeg)
        assert requests[1].method == "POST"
        assert requests[1].content == b"Finished"


async def test_provider_photo_preference_round_trips_and_defaults_enabled(async_client):
    base = {"name": "Photos", "provider_type": "ntfy", "config": {"topic": "photos"}}
    created = await async_client.post("/api/v1/notifications/", json=base)
    assert created.status_code == 200
    assert created.json()["attach_photo"] is True
    updated = await async_client.patch(f"/api/v1/notifications/{created.json()['id']}", json={"attach_photo": False})
    assert updated.json()["attach_photo"] is False


@pytest.fixture
async def photo_grant(db_session, tmp_path, monkeypatch, jpeg):
    monkeypatch.setattr(settings, "base_dir", tmp_path)
    directory = tmp_path / "notification_photos"
    directory.mkdir()
    filename = "1" * 32 + ".jpg"
    (directory / filename).write_bytes(jpeg)
    token = "A" * 43
    grant = AuthEphemeralToken(
        token=hashlib.sha256(token.encode()).hexdigest(),
        token_type="notification_photo",
        nonce=filename,
        code_verifier=hashlib.sha256(jpeg).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    db_session.add_all([grant, Settings(key="auth_enabled", value="true")])
    await db_session.commit()
    return f"/api/v1/notifications/photos/{token}", grant, directory / filename


async def test_photo_capability_returns_only_selected_image_without_login(async_client, photo_grant, jpeg):
    path, _, _ = photo_grant
    response = await async_client.get(path)
    assert response.status_code == 200
    assert response.content == jpeg
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"
    token = path.rsplit("/", 1)[1]
    for other in ("/api/v1/notifications/", "/api/v1/archives/1/thumbnail", "/api/v1/camera/1/snapshot"):
        assert (
            await async_client.get(other, params={"token": token}, headers={"Authorization": f"Bearer {token}"})
        ).status_code == 401


async def test_photo_capability_expiry_is_not_extended_by_touching_file(async_client, photo_grant, db_session):
    path, grant, photo = photo_grant
    grant.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()
    photo.touch()
    assert (await async_client.get(path)).status_code == 404


async def test_photo_capability_rejects_replaced_deleted_or_escaped_resource(
    async_client, photo_grant, db_session, jpeg
):
    path, grant, photo = photo_grant
    photo.write_bytes(b"other image")
    assert (await async_client.get(path)).status_code == 404
    photo.unlink()
    assert (await async_client.get(path)).status_code == 404
    secret = photo.parent.parent / "secret.jpg"
    secret.write_bytes(jpeg)
    grant.nonce = "../secret.jpg"
    await db_session.commit()
    assert (await async_client.get(path)).status_code == 404


async def test_photo_capability_does_not_accept_another_ephemeral_purpose(async_client, photo_grant, db_session):
    path, grant, _ = photo_grant
    grant.token_type = "media"
    await db_session.commit()
    assert (await async_client.get(path)).status_code == 404


async def test_finish_photo_link_with_auth_opens_only_this_photo_and_revokes_on_archive_delete(
    async_client,
    db_session,
    tmp_path,
    monkeypatch,
    jpeg,
    printer_factory,
):
    from backend.app.models.archive import PrintArchive
    from backend.app.services.notification_photos import finish_photo_for_notification

    monkeypatch.setattr(settings, "base_dir", tmp_path)
    printer = await printer_factory()
    archive = PrintArchive(filename="print.3mf", file_path="archive/run/print.3mf", file_size=1, printer_id=printer.id)
    db_session.add_all(
        [
            archive,
            Settings(key="auth_enabled", value="true"),
            Settings(key="external_url", value="https://printops.example"),
        ]
    )
    await db_session.commit()
    photos = tmp_path / "archive/run/photos"
    photos.mkdir(parents=True)
    (photos / "finish.jpg").write_bytes(jpeg)
    url, attachment = await finish_photo_for_notification(db_session, archive, "finish.jpg")
    assert attachment == jpeg
    assert url.startswith("https://printops.example/api/v1/notifications/photos/")
    response = await async_client.get(url.removeprefix("https://printops.example"))
    assert response.content == jpeg
    archive.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()
    assert (await async_client.get(url.removeprefix("https://printops.example"))).status_code == 404


@pytest.mark.parametrize("provider_type", ["bark", "homeassistant", "webhook"])
async def test_plate_notification_url_providers_receive_scoped_image_with_existing_payloads(
    async_client,
    db_session,
    tmp_path,
    monkeypatch,
    jpeg,
    printer_factory,
    provider_type,
):
    monkeypatch.setattr(settings, "base_dir", tmp_path)
    printer = await printer_factory()
    provider = NotificationProvider(
        name="Images",
        provider_type=provider_type,
        config=json.dumps(
            {
                "device_key": "device-secret",
                "service": "notify.mobile_app_phone",
                "webhook_url": "https://hooks.example/events",
            }
        ),
        on_plate_not_empty=True,
    )
    db_session.add_all(
        [
            provider,
            Settings(key="external_url", value="https://printops.example"),
            Settings(key="ha_url", value="https://ha.example"),
            Settings(key="ha_token", value="ha-secret"),
        ]
    )
    await db_session.commit()
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json={"code": 200})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        service = NotificationService()
        monkeypatch.setattr(service, "_get_client", AsyncMock(return_value=client))
        await service.on_plate_not_empty(printer.id, printer.name, db_session, difference_percent=12.5, image_data=jpeg)
    assert len(requests) == 1
    payload = json.loads(requests[0].content)
    image_url = (
        payload["image"]
        if provider_type == "bark"
        else payload["data"]["image"]
        if provider_type == "homeassistant"
        else payload["image_url"]
    )
    assert image_url.startswith("https://printops.example/api/v1/notifications/photos/")
    assert (await async_client.get(image_url.removeprefix("https://printops.example"))).content == jpeg
    if provider_type == "webhook":
        import base64

        assert payload["image"] == base64.b64encode(jpeg).decode()
        assert payload["event"] == "plate_not_empty"
        assert "_outcome_urls" not in payload and "_notification_photo_url" not in payload


@pytest.mark.parametrize("failure", ["none", "detector", "capture"])
async def test_plate_start_callback_attaches_local_capture_before_restoring_light(
    async_client,
    db_session,
    printer_factory,
    jpeg,
    monkeypatch,
    failure,
):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from backend.app import main
    from backend.app.services import external_camera, plate_detection

    printer = await printer_factory(
        auto_archive=False,
        plate_detection_enabled=True,
        external_camera_enabled=True,
        external_camera_url="https://camera.example/frame",
    )
    db_session.add(
        NotificationProvider(name="Plate", provider_type="ntfy", config='{"topic":"plate"}', on_plate_not_empty=True)
    )
    await db_session.commit()
    light = SimpleNamespace(chamber_light=False)
    toggles, captured_lights, requests = [], [], []

    def toggle(value):
        toggles.append(value)
        light.chamber_light = value

    printer_client = SimpleNamespace(state=light, set_chamber_light=toggle, pause_print=Mock())
    monkeypatch.setattr(main.printer_manager, "get_client", lambda _: printer_client)
    monkeypatch.setattr(main.printer_manager, "get_printer", lambda _: None)
    monkeypatch.setattr(main.ws_manager, "send_print_start", AsyncMock())
    monkeypatch.setattr(main.ws_manager, "broadcast", AsyncMock())
    monkeypatch.setattr(main, "notify_missing_spool_assignments_on_print_start", AsyncMock())
    monkeypatch.setattr(main.print_provenance, "capture_print_start", AsyncMock(return_value=False))
    monkeypatch.setattr(main.smart_plug_manager, "on_print_start", AsyncMock())
    monkeypatch.setattr(main.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(
        plate_detection,
        "check_plate_empty",
        AsyncMock(
            return_value=SimpleNamespace(
                is_empty=False, needs_calibration=False, confidence=0.9, difference_percent=12.5
            )
        ),
    )

    if failure == "detector":
        monkeypatch.setattr(
            plate_detection, "check_plate_empty", AsyncMock(side_effect=OSError("fixture detector unavailable"))
        )

    async def capture(*args, **kwargs):
        captured_lights.append(light.chamber_light)
        if failure == "capture":
            raise OSError("fixture camera unavailable")
        return jpeg

    monkeypatch.setattr(external_camera, "capture_frame", capture)

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "sent"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        monkeypatch.setattr(main.notification_service, "_get_client", AsyncMock(return_value=client))
        await main.on_print_start(printer.id, {"filename": "fixture.3mf"})
    assert toggles == [True, False]
    if failure == "detector":
        assert not requests
        printer_client.pause_print.assert_not_called()
    else:
        assert captured_lights[0] is True
        printer_client.pause_print.assert_called_once()
        assert requests[0].method == ("POST" if failure == "capture" else "PUT")
        if failure == "none":
            assert requests[0].content == jpeg


async def test_ai_detector_carries_the_flagged_frame_through_action_to_http(
    async_client,
    db_session,
    printer_factory,
    jpeg,
    monkeypatch,
):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from backend.app.services import obico_actions, obico_detection
    from backend.app.services.notification_service import notification_service
    from backend.app.services.obico_smoothing import WARMUP_FRAMES, PrintState

    printer = await printer_factory()
    db_session.add(
        NotificationProvider(
            name="AI",
            provider_type="ntfy",
            config='{"topic":"ai"}',
            on_ai_failure_detection=True,
            on_printer_error=False,
        )
    )
    await db_session.commit()

    @asynccontextmanager
    async def session():
        yield db_session

    monkeypatch.setattr(obico_actions, "async_session", session)
    service = obico_detection.ObicoDetectionService()
    state = PrintState()
    for _ in range(WARMUP_FRAMES + 500):
        state.update(1.0)
    service._states[printer.id] = state
    service._state_keys[printer.id] = "job"
    monkeypatch.setattr(service, "_capture_frame", AsyncMock(return_value=jpeg))
    requests = []

    def transport(request):
        if request.url.host == "ml.example":
            return httpx.Response(200, json={"detections": [["failure", 0.99, [0, 0, 1, 1]]]})
        requests.append(request)
        return httpx.Response(200, json={"id": "sent"})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        obico_detection.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(transport), **kwargs),
    )
    async with original_client(transport=httpx.MockTransport(transport)) as client:
        monkeypatch.setattr(notification_service, "_get_client", AsyncMock(return_value=client))
        config = {
            "enabled": True,
            "ml_url": "https://ml.example",
            "sensitivity": "medium",
            "action": "notify",
            "external_url": "https://printops.example",
        }
        await service._check_printer(printer.id, SimpleNamespace(task_name="job", subtask_name=""), config)
        await service._check_printer(printer.id, SimpleNamespace(task_name="job", subtask_name=""), config)
    assert len(requests) == 1, "one action per detected print"
    assert requests[0].method == "PUT" and requests[0].content == jpeg


async def test_photo_links_are_digest_stored_three_day_capabilities_and_expired_files_are_pruned(
    async_client,
    db_session,
    tmp_path,
    monkeypatch,
    jpeg,
):
    from sqlalchemy import select

    from backend.app.services.notification_photos import create_notification_photo_url

    monkeypatch.setattr(settings, "base_dir", tmp_path)
    db_session.add(Settings(key="external_url", value="https://printops.example"))
    await db_session.commit()
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    url = await create_notification_photo_url(db_session, jpeg)
    token = url.rsplit("/", 1)[1]
    grant = await db_session.scalar(select(AuthEphemeralToken))
    assert grant.token == hashlib.sha256(token.encode()).hexdigest() and token not in grant.token
    assert timedelta(days=3) <= grant.expires_at - before < timedelta(days=3, seconds=5)
    old_file = tmp_path / "notification_photos" / grant.nonce
    grant.expires_at = before - timedelta(seconds=1)
    await db_session.commit()
    await create_notification_photo_url(db_session, jpeg)
    assert not old_file.exists()
    assert (await async_client.get(url.removeprefix("https://printops.example"))).status_code == 404


async def test_photo_capability_rejects_symlinked_storage_root(async_client, photo_grant, tmp_path, jpeg):
    path, _, photo = photo_grant
    photo.unlink()
    photo.parent.rmdir()
    outside = tmp_path.parent / (tmp_path.name + "_outside")
    outside.mkdir()
    try:
        (outside / photo.name).write_bytes(jpeg)
        photo.parent.symlink_to(outside, target_is_directory=True)
        assert (await async_client.get(path)).status_code == 404
    finally:
        photo.parent.unlink()
        (outside / photo.name).unlink()
        outside.rmdir()


async def test_public_link_failure_keeps_the_photo_attachment_and_text_delivery(
    async_client,
    db_session,
    jpeg,
    printer_factory,
    monkeypatch,
):
    from backend.app.services import notification_photos

    printer = await printer_factory()
    db_session.add(
        NotificationProvider(
            name="Webhook",
            provider_type="webhook",
            config='{"webhook_url":"https://hooks.example"}',
            on_plate_not_empty=True,
        )
    )
    await db_session.commit()
    monkeypatch.setattr(
        notification_photos, "create_notification_photo_url", AsyncMock(side_effect=OSError("disk full"))
    )
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        service = NotificationService()
        monkeypatch.setattr(service, "_get_client", AsyncMock(return_value=client))
        await service.on_plate_not_empty(printer.id, printer.name, db_session, image_data=jpeg)
    assert len(requests) == 1
    assert "image" in json.loads(requests[0].content)


async def test_finish_event_keeps_template_link_and_email_cid_under_auth(
    async_client,
    db_session,
    printer_factory,
    tmp_path,
    monkeypatch,
    jpeg,
):
    from email import message_from_string

    from backend.app.models.archive import PrintArchive
    from backend.app.models.notification_template import NotificationTemplate
    from backend.app.services.notification_photos import finish_photo_for_notification

    monkeypatch.setattr(settings, "base_dir", tmp_path)
    printer = await printer_factory()
    archive = PrintArchive(
        filename="finish.3mf", file_path="archive/run/finish.3mf", file_size=1, printer_id=printer.id
    )
    db_session.add_all(
        [
            archive,
            Settings(key="auth_enabled", value="true"),
            Settings(key="external_url", value="https://printops.example"),
            NotificationProvider(
                name="Email",
                provider_type="email",
                config=json.dumps(
                    {
                        "smtp_server": "smtp.example",
                        "smtp_port": 25,
                        "security": "none",
                        "auth_enabled": "false",
                        "from_email": "from@example.test",
                        "to_email": "to@example.test",
                    }
                ),
                on_print_complete=True,
            ),
            NotificationTemplate(
                event_type="print_complete",
                name="Finished",
                title_template="{printer}",
                body_template="Photo: {finish_photo_url}",
            ),
        ]
    )
    await db_session.commit()
    photos = tmp_path / "archive/run/photos"
    photos.mkdir(parents=True)
    (photos / "finish.jpg").write_bytes(jpeg)
    url, image = await finish_photo_for_notification(db_session, archive, "finish.jpg")
    messages = []

    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def sendmail(self, sender, recipient, message):
            messages.append(message)

        def quit(self):
            pass

    monkeypatch.setattr("backend.app.services.notification_service.smtplib.SMTP", SMTP)
    await NotificationService().on_print_complete(
        printer.id,
        printer.name,
        "completed",
        {"filename": "finish.3mf"},
        db_session,
        archive_data={"finish_photo_url": url, "image_data": image},
    )
    assert len(messages) == 1
    message = message_from_string(messages[0])
    assert message.get_content_type() == "multipart/related"
    parts = {part.get_content_type(): part for part in message.walk() if not part.is_multipart()}
    assert url in parts["text/plain"].get_payload(decode=True).decode()
    assert "cid:printops-finish-photo" in parts["text/html"].get_payload(decode=True).decode()
    assert parts["image/jpeg"].get_payload(decode=True) == jpeg
    assert (await async_client.get(url.removeprefix("https://printops.example"))).content == jpeg


async def test_finish_photo_keeps_legacy_url_without_auth_and_rejects_path_escape(
    db_session, tmp_path, monkeypatch, jpeg
):
    from types import SimpleNamespace

    from backend.app.services.notification_photos import finish_photo_for_notification

    monkeypatch.setattr(settings, "base_dir", tmp_path)
    photos = tmp_path / "archive/run/photos"
    photos.mkdir(parents=True)
    (photos / "finish.jpg").write_bytes(jpeg)
    archive = SimpleNamespace(id=7, file_path="archive/run/finish.3mf")
    assert await finish_photo_for_notification(db_session, archive, "finish.jpg") == (
        "/api/v1/archives/7/photos/finish.jpg",
        jpeg,
    )
    assert await finish_photo_for_notification(db_session, archive, "../finish.jpg") == (None, None)
    archive.file_path = "../outside/finish.3mf"
    assert await finish_photo_for_notification(db_session, archive, "finish.jpg") == (None, None)
