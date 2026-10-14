"""Narrow external-application notification interface; never returns secrets."""

from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import get_api_key
from backend.app.core.database import get_db
from backend.app.models.api_key import APIKey
from backend.app.services.app_messages import consume_quota, eligible_channels, validate_notification_owner
from backend.app.services.notification_service import notification_service

router = APIRouter()


class AppMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2000)
    url: str | None = Field(default=None, max_length=500)
    channel_ids: list[int] | None = Field(default=None, min_length=1, max_length=50)
    printer_id: int | None = Field(default=None, gt=0)

    @field_validator("title", "message")
    @classmethod
    def plain_text(cls, value):
        value = "".join(c for c in value if c.isprintable() or c in "\n\t").strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("url")
    @classmethod
    def http_url(cls, value):
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or any(c.isspace() or not c.isprintable() for c in value)
        ):
            raise ValueError("must be an HTTP(S) URL without credentials or whitespace")
        return value


async def app_caller(key: APIKey = Depends(get_api_key), db: AsyncSession = Depends(get_db)):
    owner = await validate_notification_owner(db, key)
    if not key.can_send_notifications:
        raise HTTPException(403, "API key lacks can_send_notifications")
    return key, owner


@router.get("/app-message/channels")
async def list_app_channels(
    printer_id: int | None = Query(default=None, gt=0), caller=Depends(app_caller), db: AsyncSession = Depends(get_db)
):
    providers = await eligible_channels(db, *caller, printer_id)
    return [{"id": p.id, "name": p.name, "provider_type": p.provider_type} for p in providers]


@router.post("/app-message")
async def send_app_message(data: AppMessage, caller=Depends(app_caller), db: AsyncSession = Depends(get_db)):
    key, owner = caller
    if data.printer_id is None and (key.printer_ids is not None or owner.allowed_printer_ids is not None):
        raise HTTPException(403, "A printer-scoped caller must specify printer_id")
    providers = await eligible_channels(db, key, owner, data.printer_id)
    if data.channel_ids is not None:
        requested = set(data.channel_ids)
        if not requested.issubset({p.id for p in providers}):
            raise HTTPException(403, "Requested channel is unavailable or outside scope")
        providers = [p for p in providers if p.id in requested]
    if len(providers) > 50:
        raise HTTPException(400, "Select at most 50 channels using channel_ids")
    if not providers:
        raise HTTPException(400, "No eligible app-message channels")
    await consume_quota(db, key)
    message = data.message + ("\n" + data.url if data.url else "")
    outcomes = await notification_service._send_to_providers(
        providers, data.title, message, db, event_type="app_message", printer_id=data.printer_id
    )
    return {"channels": len(outcomes)}
