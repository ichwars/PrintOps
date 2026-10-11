"""Check visible surface contrast in the actual headless renderer."""

import io
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

from backend.app.services.plate_thumbnail import _render_model_thumbnails
from backend.app.services.stl_thumbnail import generate_stl_thumbnail
from backend.app.services.thumbnail_lighting import thumbnail_shading


def _surface_tone_count(png):
    rgb = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.int16)
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mask = (green > red) & (green > blue)
    keys = ((red >> 3) << 10) | ((green >> 3) << 5) | (blue >> 3)
    counts = np.bincount(keys[mask].ravel())
    return int((counts / counts.sum() >= 0.02).sum())


def test_cube_has_three_visible_surface_tones_in_library_and_plate(tmp_path):
    mesh = trimesh.creation.box()
    path = tmp_path / "cube.stl"
    mesh.export(path)
    thumbnail = generate_stl_thumbnail(path, tmp_path)
    assert thumbnail is not None
    assert _surface_tone_count(Path(thumbnail).read_bytes()) >= 3
    large, small = _render_model_thumbnails(mesh.export(file_type="3mf"))
    assert _surface_tone_count(large) >= 3
    assert _surface_tone_count(small) >= 3


def test_degenerate_facets_keep_the_unlit_fallback():
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    from backend.app.services.plate_thumbnail import _render_at_size

    triangles = np.zeros((2, 3, 3))
    assert thumbnail_shading(triangles) == {}
    assert _render_at_size(triangles, 128, Poly3DCollection).startswith(b"\x89PNG")


def test_broken_winding_is_repaired_without_losing_the_thumbnail(tmp_path):
    mesh = trimesh.creation.box()
    mesh.faces[::2] = mesh.faces[::2, ::-1]
    path = tmp_path / "mixed-winding.stl"
    mesh.export(path)
    thumbnail = generate_stl_thumbnail(path, tmp_path)
    assert thumbnail is not None
    assert _surface_tone_count(Path(thumbnail).read_bytes()) >= 3
