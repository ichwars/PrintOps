from __future__ import annotations

import hashlib
import json


def build_cache_key(*, file_sha256: str, plate_index: int, profiles: dict) -> str:
    payload = json.dumps(
        {"file_sha256": file_sha256, "plate_index": plate_index, "profiles": profiles},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()
