import logging

import pytest
from uvicorn.logging import AccessFormatter

from backend.app.core.logging_filters import SensitiveLogRedactFilter, redact_url_credentials
from backend.app.schemas.printer import PrinterResponse, PrinterResponseWithSecret
from backend.app.services import log_reader

_PRINTER = {
    "id": 1,
    "name": "Camera printer",
    "serial_number": "00M09A000000001",
    "ip_address": "192.168.1.10",
    "model": "X1C",
    "is_active": True,
    "created_at": "2026-10-13T00:00:00",
    "updated_at": "2026-10-13T00:00:00",
}


@pytest.mark.parametrize(
    ("stored", "redacted"),
    [
        ("rtsp://admin:fixture@cam.example.test/live", "rtsp://admin:[REDACTED]@cam.example.test/live"),
        ("http://:fixture@cam.example.test/snapshot", "http://:[REDACTED]@cam.example.test/snapshot"),
        ("rtsp://fixture-token@cam.example.test/live", "rtsp://[REDACTED]@cam.example.test/live"),
        ("rtsp://admin:p?ass#@cam.example.test/live", "rtsp://admin:[REDACTED]@cam.example.test/live"),
        (
            "rtsp://me@example.test:fixt ure@cam.example.test/live",
            "rtsp://me@example.test:[REDACTED]@cam.example.test/live",
        ),
        ("http://cam.example.test/path@part?a=b@c", "http://cam.example.test/path@part?a=b@c"),
        ("/dev/video0", "/dev/video0"),
        (None, None),
    ],
)
def test_reader_camera_urls_mask_login_and_editors_can_edit_original_url(stored, redacted):
    cameras = {"external_camera_url": stored, "external_camera_snapshot_url": stored}
    reader = PrinterResponse(**_PRINTER, **cameras)
    editor = PrinterResponseWithSecret(**_PRINTER, **cameras, access_code="fixture-printer-code")

    assert reader.external_camera_url == reader.external_camera_snapshot_url == redacted
    assert editor.external_camera_url == editor.external_camera_snapshot_url == stored


def test_camera_url_log_mask_covers_bare_logins_and_malformed_passwords():
    text = "Input rtsp://fixture-token@cam.example.test/live and rtsp://user:pass?word#x@cam2.example.test/live"
    assert redact_url_credentials(text) == (
        "Input rtsp://[REDACTED]@cam.example.test/live and rtsp://user:[REDACTED]@cam2.example.test/live"
    )


def test_camera_access_log_redacts_legacy_query_and_keeps_uvicorn_record():
    path = "/api/v1/printers/1/camera/external/test/?camera_type=rtsp&url=rtsp%3A%2F%2Ffixture-camera-token"
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1234", "POST", path, "1.1", 200),
        None,
    )
    assert SensitiveLogRedactFilter().filter(record)
    assert isinstance(record.args, tuple) and len(record.args) == 5
    formatted = AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s').format(record)
    assert "fixture-camera-token" not in formatted
    assert "POST /api/v1/printers/1/camera/external/test/?[REDACTED] HTTP/1.1" in formatted


def test_log_search_and_export_cannot_find_historical_camera_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(log_reader.settings, "log_dir", tmp_path)
    old = (
        "2026-11-11 09:33:00,000 INFO [uvicorn.access] POST /api/v1/printers/1/camera/external/test?"
        "url=rtsp%3A%2F%2Ffixture-query-token&camera_type=rtsp HTTP/1.1 200\n"
        "2026-11-11 09:34:00,000 WARNING [backend.app.services.camera] Input rtsps://fixture-login@camera.test/live\n"
    )
    (tmp_path / "printops.log").write_text(old)
    messages, total = log_reader.read_log_entries()
    assert total == len(messages) == 2
    assert all("fixture-" not in entry.message for entry in messages)
    assert not log_reader.read_log_entries(search="fixture-query-token")[0]
    assert "fixture-" not in log_reader.sanitize_log_content(old)
