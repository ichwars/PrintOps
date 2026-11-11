"""Unstarted sends do not leave stale usage metadata or steal a running plate's."""

import pytest


@pytest.fixture
def state():
    from backend.app import main

    names = (
        "_expected_prints",
        "_expected_print_creators",
        "_expected_print_registered_at",
        "_active_prints",
        "_print_ams_mappings",
        "_print_plate_ids",
    )
    saved = {name: dict(getattr(main, name)) for name in names}
    for name in names:
        getattr(main, name).clear()
    yield main
    for name in names:
        getattr(main, name).clear()
        getattr(main, name).update(saved[name])


def test_fresh_dispatch_drops_unstarted_plate_and_mapping(state):
    state.register_expected_print(1, "part.3mf", 99, ams_mapping=[4], plate_id=2)
    state.register_expected_print(1, "part.3mf", 99)
    assert (1, 99) not in state._print_ams_mappings
    assert (1, 99) not in state._print_plate_ids


def test_running_plate_keeps_its_metadata(state):
    state.register_expected_print(1, "part.3mf", 99, ams_mapping=[4], plate_id=2)
    state._active_prints[(1, "part.3mf")] = 99
    state.register_expected_print(2, "part.3mf", 99, ams_mapping=[8], plate_id=3)
    assert state._get_start_ams_mapping({}, 1, 99) == [4]
    assert state._get_start_ams_mapping({}, 2, 99) == [8]
    assert state._get_start_plate_id(1, 99) == 2
    assert state._get_start_plate_id(2, 99) == 3
    state.unregister_expected_print(2, "part.3mf", 99)
    assert (2, 99) not in state._print_ams_mappings
    assert (2, 99) not in state._print_plate_ids
    assert state._print_ams_mappings[(1, 99)] == [4]
    assert state._print_plate_ids[(1, 99)] == 2


def test_withdraw_does_not_remove_a_later_expectation(state):
    state.register_expected_print(1, "part.3mf", 99, created_by_id=7)
    state.register_expected_print(1, "part.3mf", 100, created_by_id=8)
    state.unregister_expected_print(1, "part.3mf", 99)
    assert state._expected_prints[(1, "part.3mf")] == 100
    assert state._expected_print_creators[(1, "part.3mf")] == 8


@pytest.mark.parametrize("running", [False, True])
def test_expiry_keeps_only_live_metadata(state, running):
    state.register_expected_print(1, "part.3mf", 99, ams_mapping=[4], plate_id=2)
    if running:
        state._active_prints[(1, "part.3mf")] = 99
    for key in state._expected_print_registered_at:
        state._expected_print_registered_at[key] = -100_000
    state._evict_stale_expected_prints()
    assert not state._expected_prints
    assert ((1, 99) in state._print_ams_mappings) == running
    assert ((1, 99) in state._print_plate_ids) == running
