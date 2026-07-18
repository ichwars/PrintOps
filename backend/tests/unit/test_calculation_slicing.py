from backend.app.services.calculation_slicing import build_cache_key


def test_calculation_slice_cache_key_is_stable_and_plate_specific():
    first = build_cache_key(file_sha256="a" * 64, plate_index=1, profiles={"source": "embedded"})
    same = build_cache_key(file_sha256="a" * 64, plate_index=1, profiles={"source": "embedded"})
    other_plate = build_cache_key(file_sha256="a" * 64, plate_index=2, profiles={"source": "embedded"})

    assert first == same
    assert first != other_plate
    assert len(first) == 64
