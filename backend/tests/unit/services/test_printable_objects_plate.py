"""Skip-object extraction must follow the plate that is actually printing."""

import json
import zipfile
from io import BytesIO

from backend.app.services.archive import extract_printable_objects_from_3mf, peek_plate_index_in_3mf


def _plate_xml(index: int, ids: list[int]) -> str:
    objects = "".join(f'<object identify_id="{i}" name="part.stl" skipped="false" />' for i in ids)
    return f'<plate><metadata key="index" value="{index}"/>{objects}</plate>'


def _plate_json(boxes: list[list[float]]) -> str:
    return json.dumps(
        {
            "bbox_all": [
                min(b[0] for b in boxes),
                min(b[1] for b in boxes),
                max(b[2] for b in boxes),
                max(b[3] for b in boxes),
            ],
            "bbox_objects": [{"id": 9000 + idx, "name": "part.stl", "bbox": box} for idx, box in enumerate(boxes)],
        }
    )


def _multi_plate_3mf() -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Metadata/slice_info.config", f"<config>{_plate_xml(1, [101, 102])}{_plate_xml(2, [201])}</config>")
        zf.writestr("Metadata/plate_1.json", _plate_json([[0, 0, 10, 10], [90, 90, 100, 100]]))
        zf.writestr("Metadata/plate_2.json", _plate_json([[40, 40, 60, 60]]))
    return buf.getvalue()


def _single_plate_3mf(index: int) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Metadata/slice_info.config", f"<config>{_plate_xml(index, [201])}</config>")
        zf.writestr(f"Metadata/plate_{index}.json", _plate_json([[40, 40, 60, 60]]))
    return buf.getvalue()


def test_extract_printable_objects_uses_requested_plate():
    objects, bbox_all = extract_printable_objects_from_3mf(_multi_plate_3mf(), plate_number=2, include_positions=True)

    assert list(objects) == [201]
    assert objects[201]["x"] == 50
    assert objects[201]["y"] == 50
    assert bbox_all == [40, 40, 60, 60]


def test_extract_printable_objects_falls_back_to_first_plate_without_request():
    objects = extract_printable_objects_from_3mf(_multi_plate_3mf())

    assert sorted(objects) == [101, 102]


def test_peek_plate_index_returns_none_for_all_plates(tmp_path):
    path = tmp_path / "all-plates.3mf"
    path.write_bytes(_multi_plate_3mf())

    assert peek_plate_index_in_3mf(path) is None


def test_peek_plate_index_keeps_single_plate_index(tmp_path):
    path = tmp_path / "plate-2.3mf"
    path.write_bytes(_single_plate_3mf(2))

    assert peek_plate_index_in_3mf(path) == 2
