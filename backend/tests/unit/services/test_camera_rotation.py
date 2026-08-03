import io
import logging

import pytest
from PIL import Image

from backend.app.services.camera import apply_camera_rotation, apply_camera_rotation_to_file

logger = logging.getLogger(__name__)


def _jpeg(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), (0, 0, 255))
    for x in range(min(8, width)):
        for y in range(min(8, height)):
            img.putpixel((x, y), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def _brightest_corner(img: Image.Image) -> str:
    w, h = img.size
    probes = {
        "top-left": (3, 3),
        "top-right": (w - 4, 3),
        "bottom-left": (3, h - 4),
        "bottom-right": (w - 4, h - 4),
    }
    return max(probes, key=lambda name: img.getpixel(probes[name])[0] - img.getpixel(probes[name])[2])


def test_zero_rotation_returns_input_object():
    src = _jpeg(64, 32)
    assert apply_camera_rotation(src, 0, logger) is src


def test_90_degrees_turns_clockwise_without_cropping():
    out = _open(apply_camera_rotation(_jpeg(64, 32), 90, logger))
    assert out.size == (32, 64)
    assert _brightest_corner(out) == "top-right"


def test_undecodable_bytes_return_unchanged():
    junk = b"not a jpeg"
    assert apply_camera_rotation(junk, 90, logger) is junk


@pytest.mark.asyncio
async def test_apply_camera_rotation_to_file_rotates_in_place(tmp_path):
    path = tmp_path / "finish.jpg"
    path.write_bytes(_jpeg(64, 32))

    await apply_camera_rotation_to_file(path, 90, logger)

    out = _open(path.read_bytes())
    assert out.size == (32, 64)
    assert _brightest_corner(out) == "top-right"


@pytest.mark.asyncio
async def test_apply_camera_rotation_to_file_leaves_bad_file_intact(tmp_path):
    path = tmp_path / "finish.jpg"
    path.write_bytes(b"not a jpeg")

    await apply_camera_rotation_to_file(path, 90, logger)

    assert path.read_bytes() == b"not a jpeg"
