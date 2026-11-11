"""Administrator-only Telegram identity binding; no public reaction endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StrictBool, StrictInt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.core.auth import RequirePermission, allowed_printer_ids_for_user
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.models.notification import NotificationProvider
from backend.app.models.telegram_quality import TelegramPollState, TelegramQualityConfig
from backend.app.services.notification_scope import provider_in_scope
from backend.app.services.telegram_quality import active_config, auth_enabled, configure

router = APIRouter()


class ActorBinding(BaseModel):
    actor_id: StrictInt = Field(gt=0, lt=2**52)
    user_id: StrictInt = Field(gt=0, lt=2**31)


class QualitySettings(BaseModel):
    enabled: StrictBool = False
    actors: list[ActorBinding] = Field(default_factory=list, max_length=100)


async def administrator(db=DB_SESSION, user=RequirePermission(Permission.NOTIFICATIONS_UPDATE)):
    if user is None or not user.is_active or not user.is_admin or not await auth_enabled(db):
        raise HTTPException(403, "An authenticated administrator is required")
    return user


async def get_provider(db, provider_id, user):
    provider = await db.get(NotificationProvider, provider_id)
    if (
        not provider
        or provider.provider_type != "telegram"
        or not provider_in_scope(provider.printer_id, allowed_printer_ids_for_user(user))
    ):
        raise HTTPException(404, "Telegram provider not found")
    return provider


@router.get("/{provider_id}/telegram-quality")
async def read_settings(provider_id: int, db=DB_SESSION, _=Depends(administrator)):
    await get_provider(db, provider_id, _)
    config = await db.scalar(select(TelegramQualityConfig).where(TelegramQualityConfig.provider_id == provider_id))
    state = await db.get(TelegramPollState, config.bot_id) if config else None
    active = await active_config(db, config.id) if config else None
    return {
        "enabled": bool(config and config.enabled),
        "actors": [{"actor_id": a["actor_id"], "user_id": a["user_id"]} for a in config.actors] if config else [],
        "status": (state.status if state else "idle") if active else "disabled",
    }


@router.put("/{provider_id}/telegram-quality")
async def write_settings(provider_id: int, settings: QualitySettings, db=DB_SESSION, _=Depends(administrator)):
    provider = await get_provider(db, provider_id, _)
    try:
        await configure(db, provider, settings.enabled, [a.model_dump() for a in settings.actors])
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "This bot already has a reaction polling provider") from None
    return await read_settings(provider_id, db, _)
