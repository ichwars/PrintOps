"""A refused print command describes the rejected job, not the running job."""

import logging

logger = logging.getLogger(__name__)


def update_job_identity(client, data: dict) -> None:
    refused = (
        data.get("command") == "project_file"
        and data.get("result") is not None
        and str(data["result"]).upper() != "SUCCESS"
    )
    if refused:
        client.last_start_refusal = (str(data["result"]), data.get("reason"))
        logger.info("[%s] Printer refused project_file: %s", client.serial_number, client.last_start_refusal)
    if "gcode_file" in data:
        client.state.gcode_file = data["gcode_file"]
        client.state.current_print = data["gcode_file"]
    if "subtask_name" in data and not refused:
        client.state.subtask_name = data["subtask_name"]
        if data["subtask_name"]:
            client.state.current_print = data["subtask_name"]
    if "subtask_id" in data and not refused:
        client.state.subtask_id = data["subtask_id"]


def print_start_rejection(status, client) -> tuple[bool, tuple | None]:
    """Read explicit command rejection in either print-start watchdog phase."""
    developer_mode = any(
        getattr(error, "full_code", "") == "0500050000010007" for error in (getattr(status, "hms_errors", None) or [])
    )
    refusal = getattr(client, "last_start_refusal", None)
    return developer_mode, refusal if isinstance(refusal, tuple) else None


def update_print_layer(client, value) -> int:
    """Keep the previous job's final layer out of this job's usage accounting."""
    new_layer = int(value)
    if client._is_stale_layer(new_layer):
        new_layer = client.state.layer_num
    elif new_layer > 0:
        client._stale_layer_num = 0
    old_layer = client.state.layer_num
    if old_layer > 0:
        client._last_valid_layer_num = old_layer
    client.state.layer_num = new_layer
    if new_layer > old_layer and client.on_layer_change:
        client.on_layer_change(new_layer)
    return new_layer
