"""Queue and deliver daily digests for notification providers."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.notification import NotificationDigestQueue, NotificationProvider

logger = logging.getLogger(__name__)
_DIGEST_RETENTION = timedelta(hours=48)
_FLEET_DIGEST_EVENTS = {"app_message", "queue_completed", "stock_reorder_alert", "stock_break_alert"}


class NotificationDigests:
    async def _queue_for_digest(
        self,
        provider: NotificationProvider,
        event_type: str,
        title: str,
        message: str,
        db: AsyncSession,
        printer_id: int | None = None,
        printer_name: str | None = None,
    ) -> bool:
        """Queue a notification for later delivery in the daily digest."""
        try:
            queue_entry = NotificationDigestQueue(
                provider_id=provider.id,
                event_type=event_type,
                title=title,
                message=message,
                printer_id=printer_id,
                printer_name=printer_name,
            )
            db.add(queue_entry)
            await db.commit()
            logger.info("Queued notification for digest: %s for provider %s", event_type, provider.name)
            return True
        except Exception as e:
            logger.warning("Failed to queue notification for digest: %s", e)
            return False

    async def send_digest(self, provider_id: int):
        """Send all queued notifications as a single digest for a provider."""
        from backend.app.core.database import async_session

        async with async_session() as db:
            # Get the provider
            result = await db.execute(select(NotificationProvider).where(NotificationProvider.id == provider_id))
            provider = result.scalar_one_or_none()

            if not provider or not provider.enabled:
                return

            # Get all queued notifications for this provider
            result = await db.execute(
                select(NotificationDigestQueue)
                .where(NotificationDigestQueue.provider_id == provider_id)
                .order_by(NotificationDigestQueue.created_at)
            )
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            cutoff = now - _DIGEST_RETENTION
            queue_entries, expired = [], []
            for entry in result.scalars():
                too_old = entry.created_at is not None and entry.created_at < cutoff
                wrong_printer = (
                    provider.printer_id is not None
                    and entry.printer_id != provider.printer_id
                    and (entry.printer_id is not None or entry.event_type not in _FLEET_DIGEST_EVENTS)
                )
                bucket = expired if too_old or wrong_printer else queue_entries
                bucket.append(entry)
            if not queue_entries:
                for entry in expired:
                    await db.delete(entry)
                if expired:
                    await db.commit()
                logger.debug("No queued notifications for provider %s", provider.name)
                return

            # Build digest message
            title = f"Daily Digest - {len(queue_entries)} Events"

            # Group by event type
            events_by_type: dict[str, list] = {}
            for entry in queue_entries:
                if entry.event_type not in events_by_type:
                    events_by_type[entry.event_type] = []
                events_by_type[entry.event_type].append(entry)

            # Format the digest body
            body_parts = []
            for event_type, entries in events_by_type.items():
                event_label = event_type.replace("_", " ").title()
                body_parts.append(f"== {event_label} ({len(entries)}) ==")
                for entry in entries:
                    time_str = (
                        entry.created_at.strftime("%H:%M" if entry.created_at.date() == now.date() else "%m-%d %H:%M")
                        if entry.created_at is not None
                        else ""
                    )
                    printer_info = f"[{entry.printer_name}] " if entry.printer_name else ""
                    body_parts.append(f"  {time_str} {printer_info}{entry.title}")
                    if event_type == "app_message":
                        body_parts.append(entry.message)
                body_parts.append("")

            body = "\n".join(body_parts)

            # The digest has its own delivery time, including during quiet hours.
            app_digest = any(entry.event_type == "app_message" for entry in queue_entries)
            success, error = await self._send_to_provider(
                provider, title, body, db, event_type="app_message" if app_digest else None, bypass_quiet_hours=True
            )

            # Log the digest
            await self._log_notification(
                db=db,
                provider_id=provider.id,
                event_type="daily_digest",
                title=title,
                message=body,
                success=success,
                error_message=error if not success else None,
            )

            # Keep failed events for the next digest. Expired events are pruned on either outcome.
            for entry in expired + (queue_entries if success else []):
                await db.delete(entry)
            await db.commit()

            if success:
                logger.info("Sent daily digest with %s events to %s", len(queue_entries), provider.name)
            else:
                logger.warning("Failed to send daily digest to %s: %s", provider.name, error)

    async def check_and_send_digests(self):
        """Check all providers and send digests if it's their scheduled time."""
        from backend.app.core.database import async_session

        current_time = datetime.now().strftime("%H:%M")

        # Avoid duplicate checks within the same minute
        if current_time == self._last_digest_check:
            return
        self._last_digest_check = current_time

        async with async_session() as db:
            # Find all providers with digest enabled at this time
            result = await db.execute(
                select(NotificationProvider).where(
                    NotificationProvider.enabled.is_(True),
                    NotificationProvider.daily_digest_enabled.is_(True),
                    NotificationProvider.daily_digest_time == current_time,
                )
            )
            providers = result.scalars().all()

            for provider in providers:
                try:
                    await self.send_digest(provider.id)
                except Exception as e:
                    logger.error("Error sending digest for provider %s: %s", provider.id, e)

    def start_digest_scheduler(self):
        """Start the background scheduler for daily digest notifications."""
        if self._digest_scheduler_task is None:
            self._digest_scheduler_task = asyncio.create_task(self._digest_scheduler_loop())
            logger.info("Notification digest scheduler started")

    def stop_digest_scheduler(self):
        """Stop the background scheduler for daily digests."""
        if self._digest_scheduler_task:
            self._digest_scheduler_task.cancel()
            self._digest_scheduler_task = None
            logger.info("Notification digest scheduler stopped")

    async def _digest_scheduler_loop(self):
        """Background loop that checks for scheduled digests every minute."""
        while True:
            try:
                await self.check_and_send_digests()
            except Exception as e:
                logger.error("Error in digest scheduler: %s", e)

            # Wait until the next minute
            await asyncio.sleep(60)
