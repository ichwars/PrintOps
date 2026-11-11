"""Validate link identities before either remote or local assignment changes."""

from fastapi import HTTPException


def resolve_link_tag(request) -> tuple[str, str, str]:
    # Resolve and validate spool tag (supports tray_uuid=32 hex and tag_uid=16 hex)
    raw_spool_tag = (request.spool_tag or "").strip()
    tray_uuid = (request.tray_uuid or "").strip().upper()
    tag_uid = (request.tag_uid or "").strip().upper()
    if raw_spool_tag:
        if len(raw_spool_tag) == 32 and not tray_uuid:
            tray_uuid = raw_spool_tag.upper()
        elif not tag_uid:
            tag_uid = raw_spool_tag.upper()
    spool_tag = tray_uuid or tag_uid
    if not spool_tag:
        raise HTTPException(status_code=400, detail="Missing spool tag (tray_uuid or tag_uid)")
    if len(spool_tag) not in (16, 32):
        raise HTTPException(status_code=400, detail="Invalid spool tag format (must be 16 or 32 hex characters)")
    try:
        int(spool_tag, 16)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid spool tag format (must be hex)")

    if set(spool_tag) == {"0"}:
        raise HTTPException(status_code=400, detail="Invalid spool tag format (all-zero tag is not linkable)")

    return spool_tag, tray_uuid, tag_uid
