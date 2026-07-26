import os
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _read_app_version() -> str:
    """Read the PrintOps runtime version for registration and heartbeats."""
    env_version = os.environ.get("APP_VERSION", "").strip()
    if env_version:
        return env_version

    for version_file in (_ROOT / "VERSION", _ROOT / "spoolbuddy" / "VERSION"):
        try:
            version = version_file.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if version:
            return version

    config_path = _ROOT / "backend" / "app" / "core" / "config.py"
    try:
        text = config_path.read_text(encoding="utf-8")
        match = re.search(r'^(?:_DEFAULT_APP_VERSION|APP_VERSION)\s*=\s*["\'](.+?)["\']', text, re.MULTILINE)
        if match:
            return match.group(1)
    except OSError:
        pass
    return "0.0.0"


__version__ = _read_app_version()
