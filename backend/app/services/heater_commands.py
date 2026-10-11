"""Existing bed/chamber commands with local ownership revision tracking."""

import time


def set_heater_temperature(client, heater: str, target: int) -> bool:
    command = "M140" if heater == "bed" else "M141"
    result = client.send_gcode(f"{command} S{target}")
    if result:
        revisions = getattr(client, "_heater_command_revisions", None)
        if revisions is None:
            revisions = client._heater_command_revisions = {}
        revisions[heater] = revisions.get(heater, 0) + 1
        client.state.temperatures[f"{heater}_target"] = float(target)
        client.state.temperatures[f"_{heater}_target_set_time"] = time.time()
        if heater == "chamber":
            current = client.state.temperatures.get("chamber", 0)
            client.state.temperatures["chamber_heating"] = target > 0 and current < target
    return result
