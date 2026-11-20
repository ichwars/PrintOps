from types import SimpleNamespace

from backend.app.services.automatic_drying_state import AutomaticDryAttempt, parked_retry


def test_stalled_countdown_retries_only_our_cycle_and_suspends_once():
    telemetry = object()
    state = SimpleNamespace(_drying_attempts={})
    key = (1, 2)

    def check(at, remaining=90):
        return parked_retry(state, key, telemetry, True, remaining, 80, 60, at)

    assert check(9999) == (False, False)
    state._drying_attempts[key] = AutomaticDryAttempt(telemetry, 100, 1)
    assert check(1899) == (False, False)
    assert check(1900) == (True, False)
    state._drying_attempts[key] = AutomaticDryAttempt(telemetry, 1900, 2)
    assert check(2100) == (False, False)
    assert check(3700) == (False, True)
    assert check(3900) == (False, False)
    parked_retry(state, key, telemetry, False, 0, 55, 60, 4000)
    assert key not in state._drying_attempts
