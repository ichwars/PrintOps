"""Installation defaults for queue options without an explicit caller choice."""

from sqlalchemy.ext.asyncio import AsyncSession

_DEFAULTS = {
    "bed_levelling": True,
    "flow_cali": False,
    "vibration_cali": True,
    "layer_inspect": False,
    "timelapse": False,
    "nozzle_offset_cali": True,
}


async def default_print_options(db: AsyncSession, explicit: dict | None = None) -> dict[str, bool]:
    from backend.app.api.routes.settings import get_setting

    supplied = explicit or {}
    options = {}
    for field, fallback in _DEFAULTS.items():
        if field in supplied:
            options[field] = supplied[field]
        else:
            stored = await get_setting(db, f"default_{field}")
            options[field] = fallback if stored is None else stored.strip().lower() in {"true", "1"}
    return options
