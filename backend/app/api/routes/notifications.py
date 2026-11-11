"""API routes for notification providers."""

import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes.app_messages import router as app_messages_router
from backend.app.api.routes.telegram_quality import router as telegram_quality_router
from backend.app.core.auth import OwnershipAccess, require_permission_with_key
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.core.printer_associations import delete_notification_provider_rows
from backend.app.core.user_printer_scope import prepare_printer_scope_write, validate_printer_grants
from backend.app.models.notification import NotificationLog, NotificationProvider
from backend.app.schemas.notification import (
    NotificationLogResponse,
    NotificationLogStats,
    NotificationProviderCreate,
    NotificationProviderResponse,
    NotificationProviderUpdate,
    NotificationTestRequest,
    NotificationTestResponse,
)
from backend.app.services.notification_scope import notification_log_scope, provider_in_scope
from backend.app.services.notification_service import notification_service
from backend.app.services.secret_fields import (
    SecretConfigError,
    mask_notification_config,
    merge_notification_config,
    reject_placeholder,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])
router.include_router(app_messages_router)
router.include_router(telegram_quality_router)


def _stored_provider_config(provider: NotificationProvider) -> dict:
    config = json.loads(provider.config) if isinstance(provider.config, str) else provider.config
    return config if isinstance(config, dict) else {}


def _provider_to_dict(provider: NotificationProvider) -> dict:
    """Convert a NotificationProvider model to a response dictionary."""
    return {
        "id": provider.id,
        "name": provider.name,
        "provider_type": provider.provider_type,
        "enabled": provider.enabled,
        "attach_photo": provider.attach_photo is not False,
        "config": mask_notification_config(_stored_provider_config(provider)),
        # Print lifecycle events
        "on_print_start": provider.on_print_start,
        "on_print_complete": provider.on_print_complete,
        "on_print_confirm_request": bool(provider.on_print_confirm_request),
        "on_print_failed": provider.on_print_failed,
        "on_print_stopped": provider.on_print_stopped,
        "on_print_progress": provider.on_print_progress,
        "on_print_missing_spool_assignment": provider.on_print_missing_spool_assignment,
        # Printer status events
        "on_printer_offline": provider.on_printer_offline,
        "on_printer_error": provider.on_printer_error,
        "on_ai_failure_detection": provider.on_ai_failure_detection,
        "on_filament_low": provider.on_filament_low,
        "on_maintenance_due": provider.on_maintenance_due,
        "on_stock_reorder_alert": provider.on_stock_reorder_alert,
        "on_stock_break_alert": provider.on_stock_break_alert,
        "on_storage_sensor_alert": provider.on_storage_sensor_alert,
        "on_ha_sensor_alert": provider.on_ha_sensor_alert,
        "on_app_message": provider.on_app_message,
        # AMS environmental alarms (regular AMS)
        "on_ams_humidity_high": provider.on_ams_humidity_high,
        "on_ams_temperature_high": provider.on_ams_temperature_high,
        # AMS-HT environmental alarms
        "on_ams_ht_humidity_high": provider.on_ams_ht_humidity_high,
        "on_ams_ht_temperature_high": provider.on_ams_ht_temperature_high,
        # Build plate detection
        "on_plate_not_empty": provider.on_plate_not_empty,
        # Bed cooled
        "on_bed_cooled": provider.on_bed_cooled,
        # First layer complete
        "on_print_pause_upcoming": provider.on_print_pause_upcoming,
        "on_first_layer_complete": provider.on_first_layer_complete,
        # Print queue events
        "on_queue_job_added": provider.on_queue_job_added,
        "on_queue_job_assigned": provider.on_queue_job_assigned,
        "on_queue_job_started": provider.on_queue_job_started,
        "on_queue_job_waiting": provider.on_queue_job_waiting,
        "on_queue_job_skipped": provider.on_queue_job_skipped,
        "on_queue_job_failed": provider.on_queue_job_failed,
        "on_queue_completed": provider.on_queue_completed,
        # Quiet hours
        "quiet_hours_enabled": provider.quiet_hours_enabled,
        "quiet_hours_start": provider.quiet_hours_start,
        "quiet_hours_end": provider.quiet_hours_end,
        # Daily digest
        "daily_digest_enabled": provider.daily_digest_enabled,
        "daily_digest_time": provider.daily_digest_time,
        # Printer filter
        "printer_id": provider.printer_id,
        # Status tracking
        "last_success": provider.last_success,
        "last_error": provider.last_error,
        "last_error_at": provider.last_error_at,
        # Timestamps
        "created_at": provider.created_at,
        "updated_at": provider.updated_at,
    }


async def _load_provider(
    db: AsyncSession, provider_id: int, printer_scope: set[int] | None, *, lock: bool = False
) -> NotificationProvider:
    provider = await db.get(NotificationProvider, provider_id, with_for_update=lock)
    if provider is None or not provider_in_scope(provider.printer_id, printer_scope):
        raise HTTPException(404, "Notification provider not found")
    return provider


def _ensure_target_in_scope(printer_id: int | None, printer_scope: set[int] | None) -> None:
    if provider_in_scope(printer_id, printer_scope):
        return
    if printer_id is None:
        raise HTTPException(400, "Choose one of your printers for this provider")
    raise HTTPException(404, "Printer not found")


# Provider List/Create Routes (no path parameters)


@router.get("/photos/{token}")
async def get_notification_photo(token: str, db: AsyncSession = DB_SESSION):
    """Only an unexpired capability bound to this immutable image can read it."""
    from backend.app.services.notification_photos import resolve_notification_photo

    data = await resolve_notification_photo(db, token)
    if data is None:
        raise HTTPException(404, "Notification photo not found")
    return Response(
        data,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/", response_model=list[NotificationProviderResponse])
async def list_notification_providers(
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.NOTIFICATIONS_READ)),
):
    """List all notification providers."""
    result = await db.execute(select(NotificationProvider).order_by(NotificationProvider.created_at.desc()))
    scope = access.printer_ids
    providers = [provider for provider in result.scalars() if provider_in_scope(provider.printer_id, scope)]

    return [_provider_to_dict(provider) for provider in providers]


@router.post("/", response_model=NotificationProviderResponse)
async def create_notification_provider(
    provider_data: NotificationProviderCreate,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.NOTIFICATIONS_CREATE)),
):
    """Create a new notification provider."""
    try:
        reject_placeholder(provider_data.config)
    except SecretConfigError as exc:
        raise HTTPException(400, str(exc)) from None
    _ensure_target_in_scope(provider_data.printer_id, access.printer_ids)
    if provider_data.printer_id is not None:
        await prepare_printer_scope_write(db)
        await validate_printer_grants(db, [provider_data.printer_id])
    provider = NotificationProvider(
        name=provider_data.name,
        provider_type=provider_data.provider_type.value,
        enabled=provider_data.enabled,
        attach_photo=provider_data.attach_photo,
        config=json.dumps(provider_data.config),
        # Print lifecycle events
        on_print_start=provider_data.on_print_start,
        on_print_complete=provider_data.on_print_complete,
        on_print_confirm_request=provider_data.on_print_confirm_request,
        on_print_failed=provider_data.on_print_failed,
        on_print_stopped=provider_data.on_print_stopped,
        on_print_progress=provider_data.on_print_progress,
        on_print_missing_spool_assignment=provider_data.on_print_missing_spool_assignment,
        # Printer status events
        on_printer_offline=provider_data.on_printer_offline,
        on_printer_error=provider_data.on_printer_error,
        on_ai_failure_detection=provider_data.on_ai_failure_detection,
        on_filament_low=provider_data.on_filament_low,
        on_maintenance_due=provider_data.on_maintenance_due,
        on_stock_reorder_alert=provider_data.on_stock_reorder_alert,
        on_stock_break_alert=provider_data.on_stock_break_alert,
        on_storage_sensor_alert=provider_data.on_storage_sensor_alert,
        on_ha_sensor_alert=provider_data.on_ha_sensor_alert,
        on_app_message=provider_data.on_app_message,
        # AMS environmental alarms (regular AMS)
        on_ams_humidity_high=provider_data.on_ams_humidity_high,
        on_ams_temperature_high=provider_data.on_ams_temperature_high,
        # AMS-HT environmental alarms
        on_ams_ht_humidity_high=provider_data.on_ams_ht_humidity_high,
        on_ams_ht_temperature_high=provider_data.on_ams_ht_temperature_high,
        # Build plate detection
        on_plate_not_empty=provider_data.on_plate_not_empty,
        # Bed cooled
        on_bed_cooled=provider_data.on_bed_cooled,
        # First layer complete
        on_print_pause_upcoming=provider_data.on_print_pause_upcoming,
        on_first_layer_complete=provider_data.on_first_layer_complete,
        # Print queue events
        on_queue_job_added=provider_data.on_queue_job_added,
        on_queue_job_assigned=provider_data.on_queue_job_assigned,
        on_queue_job_started=provider_data.on_queue_job_started,
        on_queue_job_waiting=provider_data.on_queue_job_waiting,
        on_queue_job_skipped=provider_data.on_queue_job_skipped,
        on_queue_job_failed=provider_data.on_queue_job_failed,
        on_queue_completed=provider_data.on_queue_completed,
        # Quiet hours
        quiet_hours_enabled=provider_data.quiet_hours_enabled,
        quiet_hours_start=provider_data.quiet_hours_start,
        quiet_hours_end=provider_data.quiet_hours_end,
        # Daily digest
        daily_digest_enabled=provider_data.daily_digest_enabled,
        daily_digest_time=provider_data.daily_digest_time,
        # Printer filter
        printer_id=provider_data.printer_id,
    )

    db.add(provider)
    await db.commit()
    await db.refresh(provider)

    logger.info("Created notification provider: %s (%s)", provider.name, provider.provider_type)

    return _provider_to_dict(provider)


# Static Path Routes (must come BEFORE parameterized routes)


@router.post("/test-config", response_model=NotificationTestResponse)
async def test_notification_config(
    test_request: NotificationTestRequest,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.NOTIFICATIONS_CREATE)),
):
    """Test a new provider or resolve an editor's placeholders for a saved provider."""
    provider_type = test_request.provider_type.value
    config = test_request.config
    try:
        if test_request.provider_id is None:
            reject_placeholder(config)
        else:
            if access.api_key is not None or (
                access.user is not None and not access.user.has_permission(Permission.NOTIFICATIONS_UPDATE.value)
            ):
                raise HTTPException(403, "Testing a saved provider requires notifications:update")
            provider = await _load_provider(db, test_request.provider_id, access.printer_ids)
            config = merge_notification_config(
                provider.provider_type, _stored_provider_config(provider), provider_type, config
            )
    except SecretConfigError as exc:
        raise HTTPException(400, str(exc)) from None
    success, message = await notification_service.send_test_notification(provider_type, config, db)

    return NotificationTestResponse(success=success, message=message)


@router.post("/test-all")
async def test_all_notification_providers(
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.NOTIFICATIONS_UPDATE)),
):
    """Send a test notification to all enabled providers."""
    result = await db.execute(select(NotificationProvider).where(NotificationProvider.enabled.is_(True)))
    scope = access.printer_ids
    providers = [provider for provider in result.scalars() if provider_in_scope(provider.printer_id, scope)]

    if not providers:
        return {"tested": 0, "success": 0, "failed": 0, "results": []}

    results = []
    success_count = 0
    failed_count = 0

    for provider in providers:
        config = json.loads(provider.config) if isinstance(provider.config, str) else provider.config
        success, message = await notification_service.send_test_notification(provider.provider_type, config, db)

        # Update provider status
        if success:
            provider.last_success = datetime.now(timezone.utc)
            success_count += 1
        else:
            provider.last_error = message
            provider.last_error_at = datetime.now(timezone.utc)
            failed_count += 1

        results.append(
            {
                "provider_id": provider.id,
                "provider_name": provider.name,
                "provider_type": provider.provider_type,
                "success": success,
                "message": message,
            }
        )

    await db.commit()

    return {
        "tested": len(providers),
        "success": success_count,
        "failed": failed_count,
        "results": results,
    }


# Notification Log Routes (must come BEFORE /{provider_id} routes)


@router.get("/logs", response_model=list[NotificationLogResponse])
async def get_notification_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    provider_id: int | None = Query(default=None),
    event_type: str | None = Query(default=None),
    success: bool | None = Query(default=None),
    days: int | None = Query(default=7, ge=1, le=90, description="Filter logs from the last N days"),
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.NOTIFICATIONS_READ)),
):
    """Get notification logs with optional filters."""
    query = select(NotificationLog).order_by(desc(NotificationLog.created_at))
    scope = access.printer_ids
    if scope is not None:
        query = query.where(notification_log_scope(scope))

    # Apply filters
    if provider_id is not None:
        query = query.where(NotificationLog.provider_id == provider_id)
    if event_type is not None:
        query = query.where(NotificationLog.event_type == event_type)
    if success is not None:
        query = query.where(NotificationLog.success == success)
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        query = query.where(NotificationLog.created_at >= cutoff)

    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    logs = result.scalars().all()

    # Get provider info for each log
    response = []
    providers_cache: dict[int, NotificationProvider | None] = {}

    for log in logs:
        if log.provider_id not in providers_cache:
            provider_result = await db.execute(
                select(NotificationProvider).where(NotificationProvider.id == log.provider_id)
            )
            providers_cache[log.provider_id] = provider_result.scalar_one_or_none()

        provider = providers_cache[log.provider_id]
        hidden_provider = scope is not None and (provider is None or not provider_in_scope(provider.printer_id, scope))
        if hidden_provider:
            provider = None
        response.append(
            NotificationLogResponse(
                id=log.id,
                provider_id=log.provider_id,
                provider_name=provider.name if provider else None,
                provider_type=provider.provider_type if provider else None,
                event_type=log.event_type,
                title=log.title,
                message=log.message,
                success=log.success,
                error_message=None if hidden_provider else log.error_message,
                printer_id=log.printer_id,
                printer_name=log.printer_name,
                created_at=log.created_at,
            )
        )

    return response


@router.get("/logs/stats", response_model=NotificationLogStats)
async def get_notification_log_stats(
    days: int = Query(default=7, ge=1, le=90, description="Statistics for the last N days"),
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.NOTIFICATIONS_READ)),
):
    """Get notification log statistics."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    scope = access.printer_ids
    window = [NotificationLog.created_at >= cutoff]
    if scope is not None:
        window.append(notification_log_scope(scope))

    # Total counts
    total_result = await db.execute(select(func.count(NotificationLog.id)).where(*window))
    total = total_result.scalar() or 0

    success_result = await db.execute(
        select(func.count(NotificationLog.id)).where(*window, NotificationLog.success.is_(True))
    )
    success_count = success_result.scalar() or 0

    # By event type
    event_result = await db.execute(
        select(NotificationLog.event_type, func.count(NotificationLog.id))
        .where(*window)
        .group_by(NotificationLog.event_type)
    )
    by_event_type = {row[0]: row[1] for row in event_result.fetchall()}

    # By provider (need to join to get name)
    provider_result = await db.execute(
        select(NotificationProvider.name, NotificationProvider.printer_id, func.count(NotificationLog.id))
        .join(NotificationProvider, NotificationLog.provider_id == NotificationProvider.id)
        .where(*window)
        .group_by(NotificationProvider.name, NotificationProvider.printer_id)
    )
    by_provider: dict[str, int] = {}
    for name, printer_id, count in provider_result:
        label = name if provider_in_scope(printer_id, scope) else "Other"
        by_provider[label] = by_provider.get(label, 0) + count

    return NotificationLogStats(
        total=total,
        success_count=success_count,
        failure_count=total - success_count,
        by_event_type=by_event_type,
        by_provider=by_provider,
    )


@router.delete("/logs")
async def clear_notification_logs(
    older_than_days: int = Query(default=30, ge=1, description="Delete logs older than N days"),
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.NOTIFICATIONS_DELETE)),
):
    """Clear old notification logs."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

    statement = delete(NotificationLog).where(NotificationLog.created_at < cutoff)
    if (scope := access.printer_ids) is not None:
        statement = statement.where(NotificationLog.printer_id.in_(scope))
    result = await db.execute(statement)
    await db.commit()

    deleted_count = result.rowcount
    logger.info("Deleted %s notification logs older than %s days", deleted_count, older_than_days)

    return {"deleted": deleted_count, "message": f"Deleted {deleted_count} logs older than {older_than_days} days"}


# Provider Instance Routes (parameterized - must come LAST)


@router.get("/{provider_id}", response_model=NotificationProviderResponse)
async def get_notification_provider(
    provider_id: int,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.NOTIFICATIONS_READ)),
):
    """Get a specific notification provider."""
    provider = await _load_provider(db, provider_id, access.printer_ids)

    return _provider_to_dict(provider)


@router.patch("/{provider_id}", response_model=NotificationProviderResponse)
async def update_notification_provider(
    provider_id: int,
    update_data: NotificationProviderUpdate,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.NOTIFICATIONS_UPDATE)),
):
    """Update a notification provider."""
    scope = access.printer_ids
    update_dict = update_data.model_dump(exclude_unset=True)
    if "printer_id" in update_dict:
        _ensure_target_in_scope(update_dict["printer_id"], scope)
    await prepare_printer_scope_write(db)
    if update_data.printer_id is not None:
        await validate_printer_grants(db, [update_data.printer_id])
    provider = await _load_provider(db, provider_id, scope, lock=True)

    if update_dict.get("provider_type") is None:
        update_dict.pop("provider_type", None)
    new_type = update_dict.get("provider_type", provider.provider_type)
    new_type = getattr(new_type, "value", new_type)
    if update_dict.get("config") is None:
        update_dict.pop("config", None)
        if new_type != provider.provider_type:
            raise HTTPException(400, "Enter a configuration for the new provider type")
    else:
        try:
            update_dict["config"] = merge_notification_config(
                provider.provider_type, _stored_provider_config(provider), new_type, update_dict["config"]
            )
        except SecretConfigError as exc:
            raise HTTPException(400, str(exc)) from None

    if {"config", "enabled", "provider_type", "printer_id", "on_print_confirm_request"} & update_dict.keys():
        from backend.app.services.telegram_quality import invalidate_provider

        await invalidate_provider(db, provider_id)

    for key, value in update_dict.items():
        if key == "config" and value is not None:
            setattr(provider, key, json.dumps(value))
        elif key == "provider_type" and value is not None:
            setattr(provider, key, value.value)
        else:
            setattr(provider, key, value)

    await db.commit()
    await db.refresh(provider)

    logger.info("Updated notification provider: %s", provider.name)

    return _provider_to_dict(provider)


@router.delete("/{provider_id}")
async def delete_notification_provider(
    provider_id: int,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.NOTIFICATIONS_DELETE)),
):
    """Delete a notification provider."""
    await prepare_printer_scope_write(db)
    provider = await _load_provider(db, provider_id, access.printer_ids, lock=True)

    name = provider.name
    await delete_notification_provider_rows(db, provider_id)
    await db.commit()

    logger.info("Deleted notification provider: %s", name)

    return {"message": f"Notification provider '{name}' deleted"}


@router.post("/{provider_id}/test", response_model=NotificationTestResponse)
async def test_notification_provider(
    provider_id: int,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.NOTIFICATIONS_UPDATE)),
):
    """Send a test notification using an existing provider."""
    provider = await _load_provider(db, provider_id, access.printer_ids)

    config = json.loads(provider.config) if isinstance(provider.config, str) else provider.config
    success, message = await notification_service.send_test_notification(provider.provider_type, config, db)

    # Update provider status
    if success:
        provider.last_success = datetime.now(timezone.utc)
    else:
        provider.last_error = message
        provider.last_error_at = datetime.now(timezone.utc)

    await db.commit()

    return NotificationTestResponse(success=success, message=message)
