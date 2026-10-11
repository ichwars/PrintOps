"""Unit tests for the plate-thumbnail injection service.

The service backfills ``Metadata/plate_N.png`` when the sidecar CLI
(BS or Orca) skipped it in --slice --export-3mf. Each test builds a
synthetic sliced-3MF fixture: a trimesh-exported cube as
``3D/3dmodel.model`` plus dummy ``Metadata/plate_1.gcode`` so the
inject function sees it as "plate 1, no thumbnail."
"""

from __future__ import annotations

import io
import zipfile

import pytest


def _trimesh_available() -> bool:
    try:
        import trimesh  # noqa: F401

        return True
    except ImportError:
        return False


def _build_sliced_3mf(
    *,
    plate_ids: list[int],
    with_thumbnails: set[int] | None = None,
    with_model: bool = True,
) -> bytes:
    """Build a synthetic sliced .gcode.3mf for injection tests.

    - ``plate_ids``: which Metadata/plate_N.gcode entries to write
    - ``with_thumbnails``: subset of plate_ids that ALSO get plate_N.png +
      plate_N_small.png (simulates a desktop-Studio-style slice where the
      slicer did embed thumbnails)
    - ``with_model``: when True, embeds a trimesh-rendered cube as
      ``3D/3dmodel.model`` so the injector can reload + render it
    """
    import trimesh

    have_thumbs = with_thumbnails or set()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if with_model:
            # trimesh's primitives.Box exports cleanly to 3MF.
            mesh = trimesh.creation.box(extents=(10.0, 10.0, 10.0))
            model_bytes = mesh.export(file_type="3mf")
            # trimesh.export(file_type='3mf') returns a full 3MF zip; we
            # want just the embedded 3D/3dmodel.model XML so we can place
            # it under the sliced-3MF layout.
            with zipfile.ZipFile(io.BytesIO(model_bytes), "r") as inner:
                model_xml = inner.read("3D/3dmodel.model")
            zf.writestr("3D/3dmodel.model", model_xml)
        for n in plate_ids:
            # Dummy gcode is enough for the injector — it only matches the
            # filename to detect plate slots, not the content.
            zf.writestr(f"Metadata/plate_{n}.gcode", b"; dummy gcode\n")
            if n in have_thumbs:
                # 1x1 transparent PNG — pre-existing thumb sentinel; the
                # injector should preserve its bytes verbatim.
                zf.writestr(f"Metadata/plate_{n}.png", _PIXEL_PNG)
                zf.writestr(f"Metadata/plate_{n}_small.png", _PIXEL_PNG)
    return buf.getvalue()


# 1x1 transparent PNG used as a pre-existing thumbnail sentinel.
_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0dIDATx\x9cc\xfc\xff\xff?\x03\x00\x05\xfe\x02\xfe"
    b"\xdc\xccY\xe7"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _names_in_zip(blob: bytes) -> set[str]:
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        return set(zf.namelist())


@pytest.mark.skipif(not _trimesh_available(), reason="trimesh not installed")
class TestInjectPlateThumbnails:
    """Behaviour around when the injector renders vs returns the input."""

    def test_returns_input_unchanged_when_all_plates_have_thumbnails(self):
        """Desktop-Studio path: every plate already has plate_N.png — no work."""
        from backend.app.services.plate_thumbnail import inject_plate_thumbnails_if_missing

        fixture = _build_sliced_3mf(plate_ids=[1], with_thumbnails={1})
        result = inject_plate_thumbnails_if_missing(fixture)
        # Same object identity — the fast path returns the input verbatim
        # so the SliceResult._replace upstream never pays for a copy on the
        # common already-embedded case.
        assert result is fixture

    def test_injects_both_sizes_when_thumbnail_missing(self):
        """BS/Orca sidecar path: plate_1.gcode present, plate_1.png absent."""
        from backend.app.services.plate_thumbnail import inject_plate_thumbnails_if_missing

        fixture = _build_sliced_3mf(plate_ids=[1], with_thumbnails=set())
        before = _names_in_zip(fixture)
        assert "Metadata/plate_1.png" not in before

        result = inject_plate_thumbnails_if_missing(fixture)
        after = _names_in_zip(result)
        assert "Metadata/plate_1.png" in after
        assert "Metadata/plate_1_small.png" in after

    def test_injected_pngs_have_expected_dimensions(self):
        """Sanity-check the render geometry — 512x512 + 128x128, RGBA PNG."""
        from backend.app.services.plate_thumbnail import inject_plate_thumbnails_if_missing

        fixture = _build_sliced_3mf(plate_ids=[1], with_thumbnails=set())
        result = inject_plate_thumbnails_if_missing(fixture)

        with zipfile.ZipFile(io.BytesIO(result), "r") as zf:
            large = zf.read("Metadata/plate_1.png")
            small = zf.read("Metadata/plate_1_small.png")

        assert large.startswith(b"\x89PNG\r\n\x1a\n")
        assert small.startswith(b"\x89PNG\r\n\x1a\n")
        # PNG IHDR dimensions live at byte offsets 16..23 (big-endian width,
        # then big-endian height). matplotlib's bbox_inches='tight' shaves a
        # few pixels off, so assert "close to" rather than exact.
        import struct

        large_w, large_h = struct.unpack(">II", large[16:24])
        small_w, small_h = struct.unpack(">II", small[16:24])
        assert 480 <= large_w <= 540 and 480 <= large_h <= 540
        assert 100 <= small_w <= 140 and 100 <= small_h <= 140

    def test_injects_for_every_missing_plate_in_multi_plate_3mf(self):
        """Three plates, plate_2 already has a thumbnail; only plates 1 + 3 get rendered."""
        from backend.app.services.plate_thumbnail import inject_plate_thumbnails_if_missing

        fixture = _build_sliced_3mf(plate_ids=[1, 2, 3], with_thumbnails={2})
        result = inject_plate_thumbnails_if_missing(fixture)
        after = _names_in_zip(result)

        for n in (1, 2, 3):
            assert f"Metadata/plate_{n}.png" in after
            assert f"Metadata/plate_{n}_small.png" in after

        # Plate 2 had a pre-existing thumbnail — the inject must NOT clobber
        # it. The sentinel _PIXEL_PNG bytes should survive verbatim.
        with zipfile.ZipFile(io.BytesIO(result), "r") as zf:
            assert zf.read("Metadata/plate_2.png") == _PIXEL_PNG
            assert zf.read("Metadata/plate_2_small.png") == _PIXEL_PNG

    def test_returns_input_when_no_model_file_in_3mf(self):
        """No 3D/3dmodel.model → render is impossible; degrade gracefully."""
        from backend.app.services.plate_thumbnail import inject_plate_thumbnails_if_missing

        fixture = _build_sliced_3mf(plate_ids=[1], with_thumbnails=set(), with_model=False)
        result = inject_plate_thumbnails_if_missing(fixture)
        # Same object identity — early-out before render.
        assert result is fixture

    def test_returns_input_when_not_a_zip(self):
        """Non-zip input must not crash — degrade to passthrough."""
        from backend.app.services.plate_thumbnail import inject_plate_thumbnails_if_missing

        garbage = b"not a zip"
        assert inject_plate_thumbnails_if_missing(garbage) is garbage

    def test_idempotent_on_second_pass(self):
        """Re-running on a previously-injected 3MF must be a no-op."""
        from backend.app.services.plate_thumbnail import inject_plate_thumbnails_if_missing

        fixture = _build_sliced_3mf(plate_ids=[1], with_thumbnails=set())
        once = inject_plate_thumbnails_if_missing(fixture)
        twice = inject_plate_thumbnails_if_missing(once)
        # Same object identity — second pass hits the no-op fast path
        # because every plate now has its plate_N.png.
        assert twice is once


# Production-layout regressions: each part is stored once and instantiated via
# the production extension, rather than repeating its source triangles.
_NS = (
    'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
    'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"'
)
_IDENTITY = "1 0 0 0 1 0 0 0 1 0 0 0"


def _production_3mf(count=25, *, mesh=None, extra_parts="", depth=0, transform=None):
    import trimesh

    mesh = mesh if mesh is not None else trimesh.creation.box(extents=(10, 10, 10))
    vertices = "".join(f'<vertex x="{x}" y="{y}" z="{z}"/>' for x, y, z in mesh.vertices)
    faces = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mesh.faces)
    part = f'<object id="1"><mesh><vertices>{vertices}</vertices><triangles>{faces}</triangles></mesh></object>'
    objects = []
    items = []
    for i in range(count):
        objects.append(
            f'<object id="{100 + i}"><components>'
            '<component p:path="/3D/Objects/parts.model" objectid="1"/>'
            "</components></object>"
        )
        matrix = transform or f"1 0 0 0 1 0 0 0 1 {20 * (i % 5)} {20 * (i // 5)} 0"
        items.append(f'<item objectid="{100 + i}" transform="{matrix}"/>')
    if depth:
        objects = [
            f'<object id="{100 + i}"><components><component objectid="{101 + i}"/></components></object>'
            for i in range(depth)
        ] + [objects[0].replace('id="100"', f'id="{100 + depth}"', 1)]
        items = ['<item objectid="100"/>']
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as archive:
        archive.writestr("3D/Objects/parts.model", f"<model {_NS}><resources>{part}{extra_parts}</resources></model>")
        archive.writestr(
            "3D/3dmodel.model",
            f"<model {_NS}><resources>{''.join(objects)}</resources><build>{''.join(items)}</build></model>",
        )
        archive.writestr("Metadata/plate_1.gcode", "; dummy\n")
    return blob.getvalue()


def _capture_triangles(monkeypatch):
    import backend.app.services.plate_thumbnail as service

    captured = []

    def capture(poly3d, *_args):
        captured.append(poly3d.copy())
        return _PIXEL_PNG

    monkeypatch.setattr(service, "_render_at_size", capture)
    return service, captured


class TestBoundedProductionGeometry:
    def test_instances_render_linear_face_count_and_only_the_named_part(self, monkeypatch):
        import numpy as np

        service, captured = _capture_triangles(monkeypatch)
        extra = '<object id="2"><mesh><vertices><vertex x="0" y="0" z="1000"/><vertex x="1" y="0" z="0"/><vertex x="0" y="1" z="0"/></vertices><triangles><triangle v1="0" v2="1" v3="2"/></triangles></mesh></object>'
        blob = _production_3mf(extra_parts=extra)
        assert service.inject_plate_thumbnails_if_missing(blob) is not blob
        assert len(captured[0]) == 300  # 25 boxes, 12 triangles each.
        assert np.ptp(captured[0][:, :, 2]) == pytest.approx(1 / 9)

    def test_mirrored_transform_keeps_outward_normals(self, monkeypatch):
        import numpy as np

        service, captured = _capture_triangles(monkeypatch)
        blob = _production_3mf(1, transform="-1 0 0 0 1 0 0 0 1 0 0 0")
        assert service.inject_plate_thumbnails_if_missing(blob) is not blob
        triangles = captured[0]
        normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        assert (np.einsum("ij,ij->i", normals, triangles.mean(axis=1)) > 0).all()

    def test_placement_limit_skips_render_without_rewriting_file(self, monkeypatch):
        service, captured = _capture_triangles(monkeypatch)
        monkeypatch.setattr(service, "_MAX_PLACEMENTS", 3, raising=False)
        blob = _production_3mf(4)
        assert service.inject_plate_thumbnails_if_missing(blob) is blob
        assert captured == []

    def test_face_ceiling_skips_render_without_rewriting_file(self, monkeypatch):
        service, captured = _capture_triangles(monkeypatch)
        monkeypatch.setattr(service, "_MAX_PLACED_FACES", 100, raising=False)
        blob = _production_3mf()
        assert service.inject_plate_thumbnails_if_missing(blob) is blob
        assert captured == []

    def test_component_depth_limit_skips_render_without_rewriting_file(self, monkeypatch):
        service, captured = _capture_triangles(monkeypatch)
        monkeypatch.setattr(service, "_MAX_COMPONENT_DEPTH", 2, raising=False)
        blob = _production_3mf(1, depth=3)
        assert service.inject_plate_thumbnails_if_missing(blob) is blob
        assert captured == []

    def test_decimation_failure_is_checked_against_the_face_ceiling(self, monkeypatch):
        import trimesh

        service, captured = _capture_triangles(monkeypatch)
        monkeypatch.setattr(service, "_RENDER_FACE_BUDGET", 400, raising=False)
        monkeypatch.setattr(service, "_MIN_FACES_PER_MESH", 10, raising=False)
        monkeypatch.setattr(service, "_MAX_PLACED_FACES", 500, raising=False)

        def fail(*args, **kwargs):
            raise RuntimeError("optional decimator unavailable")

        monkeypatch.setattr(trimesh.Trimesh, "simplify_quadric_decimation", fail)
        blob = _production_3mf(2, mesh=trimesh.creation.icosphere(subdivisions=2))
        assert service.inject_plate_thumbnails_if_missing(blob) is blob
        assert captured == []

    def test_decimation_is_applied_before_instance_expansion(self, monkeypatch):
        import trimesh

        service, captured = _capture_triangles(monkeypatch)
        monkeypatch.setattr(service, "_RENDER_FACE_BUDGET", 2000, raising=False)
        monkeypatch.setattr(service, "_MIN_FACES_PER_MESH", 20, raising=False)
        blob = _production_3mf(10, mesh=trimesh.creation.icosphere(subdivisions=3))
        assert service.inject_plate_thumbnails_if_missing(blob) is not blob
        assert len(captured[0]) <= 2100

    def test_archive_budget_is_enforced_before_reading_geometry(self, monkeypatch):
        from dataclasses import replace
        from functools import partial

        from backend.app.utils.archive_budget import DEFAULT_ARCHIVE_BUDGET, validate_zip_archive

        service, captured = _capture_triangles(monkeypatch)
        monkeypatch.setattr(
            service,
            "validate_zip_archive",
            partial(validate_zip_archive, budget=replace(DEFAULT_ARCHIVE_BUDGET, max_members=1)),
            raising=False,
        )
        blob = _production_3mf(1)
        assert service.inject_plate_thumbnails_if_missing(blob) is blob
        assert captured == []

    def test_concurrent_injections_serialize_geometry_and_render_memory(self, monkeypatch):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from time import sleep

        import backend.app.services.plate_thumbnail as service

        active = 0
        maximum = 0
        lock = threading.Lock()

        def render(_blob):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            sleep(0.03)
            with lock:
                active -= 1
            return _PIXEL_PNG, _PIXEL_PNG

        monkeypatch.setattr(service, "_render_model_thumbnails", render)
        blob = _production_3mf(1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outputs = list(pool.map(service.inject_plate_thumbnails_if_missing, [blob, blob]))
        assert all("Metadata/plate_1.png" in _names_in_zip(output) for output in outputs)
        assert maximum == 1


def test_injection_preserves_an_existing_small_thumbnail_without_duplicate_members(monkeypatch):
    service, _ = _capture_triangles(monkeypatch)
    source = _production_3mf(1)
    fixture = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as src, zipfile.ZipFile(fixture, "w") as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item))
        dst.writestr("Metadata/plate_1_small.png", b"original small preview")
    result = service.inject_plate_thumbnails_if_missing(fixture.getvalue())
    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        assert archive.namelist().count("Metadata/plate_1_small.png") == 1
        assert archive.read("Metadata/plate_1_small.png") == b"original small preview"
        assert archive.read("Metadata/plate_1.png") == _PIXEL_PNG


def test_shared_part_file_consumes_source_xml_budget_once(monkeypatch):
    from dataclasses import replace

    from backend.app.utils.archive_budget import DEFAULT_ARCHIVE_BUDGET

    service, captured = _capture_triangles(monkeypatch)
    # Root nodes: 1 model + 1 resources + 3*25 wrappers + 1 build + 25 items
    # = 103; part nodes: 1 model + 1 resources + 1 object + 1 mesh + 1 vertices
    # + 8 vertex + 1 triangles + 12 triangle = 26. Budget is 129 nodes total.
    monkeypatch.setattr(service, "DEFAULT_ARCHIVE_BUDGET", replace(DEFAULT_ARCHIVE_BUDGET, max_xml_nodes=129))
    fixture = _production_3mf()
    assert service.inject_plate_thumbnails_if_missing(fixture) is not fixture
    assert len(captured[0]) == 300
    monkeypatch.setattr(service, "DEFAULT_ARCHIVE_BUDGET", replace(DEFAULT_ARCHIVE_BUDGET, max_xml_nodes=128))
    assert service.inject_plate_thumbnails_if_missing(fixture) is fixture
