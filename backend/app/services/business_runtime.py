"""Lifecycle of local business-data background services."""

from backend.app.services.lexware_sync import lexware_scheduler
from backend.app.services.local_backup import local_backup_service


async def start() -> None:
    await local_backup_service.start_scheduler()
    await lexware_scheduler.start()


async def stop() -> None:
    await lexware_scheduler.stop()
    local_backup_service.stop_scheduler()
