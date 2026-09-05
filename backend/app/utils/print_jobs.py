"""Identity helpers for printer-internal jobs that are not production prints."""

from __future__ import annotations

INTERNAL_JOB_NAMES = frozenset(
    {
        "auto_cali_for_user",
        "auto_pa_line_calib_mode",
        "pa_line_calib_mode",
        "pa_pattern_calib_mode",
    }
)


def _job_stem(value: str | None) -> str:
    if not value:
        return ""
    name = value.replace("\\", "/").rsplit("/", 1)[-1].strip().casefold()
    for suffix in (".gcode.3mf", ".gcode", ".3mf"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def is_internal_printer_job(filename: str | None, subtask_name: str | None) -> bool:
    """Return whether the MQTT identity names a known printer-owned job.

    Matching is deliberately exact after path/extension normalization. A user
    file such as ``pa_line_calib_mode_v2.3mf`` remains a production print.
    ``/usr/`` is the separate firmware-owned path signal used by older models.
    """

    normalized_path = (filename or "").strip().replace("\\", "/").casefold()
    if normalized_path.startswith("/usr/"):
        return True
    return any(_job_stem(value) in INTERNAL_JOB_NAMES for value in (filename, subtask_name))


def ignore_internal_printer_job(data: dict, logger, phase: str) -> bool:
    """Log and identify a printer-owned event before production side effects."""
    if not is_internal_printer_job(data.get("filename"), data.get("subtask_name")):
        return False
    logger.info(
        "[CALLBACK] Ignoring internal printer job at %s: filename=%r subtask=%r",
        phase,
        data.get("filename"),
        data.get("subtask_name"),
    )
    return True
