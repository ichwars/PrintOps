"""Expire unstarted expectations without taking metadata from an active print."""


def expire_expectations(expected, creators, registered, active, mappings, plates, cutoff) -> int:
    stale = [key for key, timestamp in registered.items() if timestamp < cutoff]
    evicted = set()
    for key in stale:
        archive_id = expected.pop(key, None)
        if archive_id is not None:
            evicted.add((key[0], archive_id))
        creators.pop(key, None)
        registered.pop(key, None)
    live = {(pid, archive_id) for state in (expected, active) for (pid, _), archive_id in state.items()}
    for dispatch in evicted - live:
        mappings.pop(dispatch, None)
        plates.pop(dispatch, None)
    return len(stale)
