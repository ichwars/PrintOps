"""Record changed system preset settings in slicer output."""

import json
import logging
import shutil
import zipfile
from io import BytesIO

from backend.app.utils.archive_budget import read_zip_member

logger = logging.getLogger(__name__)
_PROJECT_SETTINGS = "Metadata/project_settings.config"


def changed_process_keys(before_json: str, after_json: str) -> list[str]:
    """The keys PrintOps set on a process JSON between two points (#3497).

    Added keys and keys whose value changed. Empty when either side does not
    parse as a JSON object, so a caller then records nothing rather than a
    guess.
    """
    try:
        before = json.loads(before_json)
        after = json.loads(after_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(before, dict) or not isinstance(after, dict):
        return []
    return sorted(key for key, value in after.items() if key not in before or before[key] != value)


def record_process_changes(zip_bytes: bytes, keys: list[str]) -> bytes:
    """List *keys* as changed from the system process preset in a sliced 3MF (#3497).

    The slicer CLI writes ``different_settings_to_system`` but never fills it,
    so the settings PrintOps put on the picked preset are in the file without
    being marked. Bambu Studio then opens the project with the stock preset's
    values for them, and a re-slice there drops them.

    Merges into the process entry (index 0) only: keys already listed stay,
    the filament and printer entries are left alone. Returns the bytes
    unchanged when there is nothing to add or the file is not one whose layout
    we understand.
    """
    if not keys:
        return zip_bytes
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zin:
            if _PROJECT_SETTINGS not in zin.namelist():
                return zip_bytes
            config = json.loads(read_zip_member(zin, _PROJECT_SETTINGS, max_bytes=8 * 1024 * 1024).decode("utf-8"))
            if not isinstance(config, dict):
                return zip_bytes
            changed = config.get("different_settings_to_system")
            filaments = config.get("filament_settings_id")
            if (
                not isinstance(changed, list)
                or not isinstance(filaments, list)
                or len(changed) != len(filaments) + 2
                or not isinstance(changed[0], str)
            ):
                logger.info("Sliced 3MF has no usable different_settings_to_system; process changes not recorded")
                return zip_bytes
            listed = [key.strip() for key in changed[0].split(";") if key.strip()]
            merged = sorted(set(listed) | set(keys))
            if merged == sorted(listed):
                return zip_bytes
            changed[0] = ";".join(merged)
            patched = json.dumps(config, indent=4)

            dst = BytesIO()
            with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename == _PROJECT_SETTINGS:
                        zout.writestr(item, patched)
                    else:
                        with zin.open(item) as source, zout.open(item, "w") as target:
                            shutil.copyfileobj(source, target)
    except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError, OSError):
        return zip_bytes
    logger.info("Recorded %d process setting(s) as changed from the system preset", len(keys))
    return dst.getvalue()
