from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from backend.app.services.business_profile_logo import (
    InvalidBusinessProfileLogo,
    logo_path,
    validate_logo,
)


def image_bytes(image_format: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (4, 4), color="white").save(output, format=image_format)
    return output.getvalue()


@pytest.mark.parametrize(
    ("image_format", "media_type"),
    [("PNG", "image/png"), ("JPEG", "image/jpeg")],
)
def test_validate_logo_accepts_supported_decoded_images(image_format, media_type):
    assert validate_logo(image_bytes(image_format), media_type) == media_type


def test_validate_logo_rejects_declared_type_mismatch():
    with pytest.raises(InvalidBusinessProfileLogo, match="invalid_logo_type"):
        validate_logo(image_bytes("JPEG"), "image/png")


def test_validate_logo_rejects_truncated_image():
    with pytest.raises(InvalidBusinessProfileLogo, match="invalid_logo_image"):
        validate_logo(b"\x89PNG\r\n\x1a\ntruncated", "image/png")


def test_validate_logo_rejects_file_over_two_megabytes():
    with pytest.raises(InvalidBusinessProfileLogo, match="logo_too_large"):
        validate_logo(b"x" * (2 * 1024 * 1024 + 1), "image/png")


def test_logo_path_is_server_generated_below_root(tmp_path):
    path = logo_path(tmp_path, profile_id=42, version=7, media_type="image/jpeg")

    assert path == tmp_path / "42-7.jpeg"
    assert path.resolve().is_relative_to(tmp_path.resolve())
