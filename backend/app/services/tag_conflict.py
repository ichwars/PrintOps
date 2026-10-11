"""Shared API conflict detail for local and remote inventory identifiers."""

from fastapi import HTTPException


def tag_conflict(spool_id: int, field: str) -> HTTPException:
    return HTTPException(
        409,
        detail={
            "code": "tag_already_linked",
            "field": field,
            "spool_id": spool_id,
            "message": f"Tag is already linked to spool {spool_id}",
        },
    )
