"""Queue and inventory events rendered and delivered by NotificationService."""

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.services.notification_delivery import NotificationDelivery


class NotificationQueueEvents:
    """Keep event-specific payloads separate from provider transport logic."""

    # ==================== Queue Notifications ====================

    async def on_queue_job_added(
        self,
        job_name: str,
        target: str,
        db: AsyncSession,
        printer_id: int | None = None,
        printer_name: str | None = None,
    ):
        """Handle queue job added event."""
        providers = await self._get_providers_for_event(db, "on_queue_job_added", printer_id)
        if not providers:
            return

        variables = {
            "job_name": job_name,
            "target": target,  # e.g., "Printer1" or "Any X1C"
            "printer": printer_name or target,
        }

        title, message = await self._build_message_from_template(db, "queue_job_added", variables)
        await self._send_to_providers(
            providers, title, message, db, "queue_job_added", printer_id, printer_name, variables=variables
        )

    async def on_queue_job_assigned(
        self,
        job_name: str,
        printer_id: int,
        printer_name: str,
        target_model: str,
        db: AsyncSession,
    ):
        """Handle model-based job assigned to printer event."""
        providers = await self._get_providers_for_event(db, "on_queue_job_assigned", printer_id)
        if not providers:
            return

        variables = {
            "job_name": job_name,
            "printer": printer_name,
            "target_model": target_model,
        }

        title, message = await self._build_message_from_template(db, "queue_job_assigned", variables)
        await self._send_to_providers(
            providers, title, message, db, "queue_job_assigned", printer_id, printer_name, variables=variables
        )

    async def on_queue_job_started(
        self,
        job_name: str,
        printer_id: int,
        printer_name: str,
        db: AsyncSession,
        estimated_time: int | None = None,
    ):
        """Handle queue job started printing event."""
        providers = await self._get_providers_for_event(db, "on_queue_job_started", printer_id)
        if not providers:
            return

        eta_str = await self._format_eta(estimated_time, db)

        variables = {
            "job_name": job_name,
            "printer": printer_name,
            "estimated_time": self._format_duration(estimated_time),
            "eta": eta_str,
        }

        title, message = await self._build_message_from_template(db, "queue_job_started", variables)
        await self._send_to_providers(
            providers, title, message, db, "queue_job_started", printer_id, printer_name, variables=variables
        )

    async def on_queue_job_waiting(
        self,
        job_name: str,
        target_model: str,
        waiting_reason: str,
        db: AsyncSession,
    ):
        """Handle job waiting for filament event."""
        providers = await self._get_providers_for_event(db, "on_queue_job_waiting", None)
        if not providers:
            return

        variables = {
            "job_name": job_name,
            "target_model": target_model,
            "waiting_reason": waiting_reason,
        }

        title, message = await self._build_message_from_template(db, "queue_job_waiting", variables)
        await self._send_to_providers(providers, title, message, db, "queue_job_waiting", variables=variables)

    async def on_queue_job_skipped(
        self,
        job_name: str,
        printer_id: int,
        printer_name: str,
        reason: str,
        db: AsyncSession,
    ):
        """Handle job skipped event (e.g., previous print failed)."""
        providers = await self._get_providers_for_event(db, "on_queue_job_skipped", printer_id)
        if not providers:
            return

        variables = {
            "job_name": job_name,
            "printer": printer_name,
            "reason": reason,
        }

        title, message = await self._build_message_from_template(db, "queue_job_skipped", variables)
        await self._send_to_providers(
            providers, title, message, db, "queue_job_skipped", printer_id, printer_name, variables=variables
        )

    async def on_queue_job_failed(
        self,
        job_name: str,
        printer_id: int | None,
        printer_name: str | None,
        reason: str,
        db: AsyncSession,
    ):
        """Handle job failed to start event (upload error, etc.)."""
        providers = await self._get_providers_for_event(db, "on_queue_job_failed", printer_id)
        if not providers:
            return

        variables = {
            "job_name": job_name,
            "printer": printer_name or "Unknown",
            "reason": reason,
        }

        title, message = await self._build_message_from_template(db, "queue_job_failed", variables)
        await self._send_to_providers(
            providers, title, message, db, "queue_job_failed", printer_id, printer_name, variables=variables
        )

    async def on_queue_completed(
        self,
        completed_count: int,
        db: AsyncSession,
    ):
        """Handle all queue jobs completed event."""
        providers = await self._get_providers_for_event(db, "on_queue_completed", None)
        if not providers:
            return

        variables = {
            "completed_count": str(completed_count),
        }

        title, message = await self._build_message_from_template(db, "queue_completed", variables)
        await self._send_to_providers(providers, title, message, db, "queue_completed", variables=variables)

    # ==================== Inventory Stock Alerts ====================

    async def on_stock_reorder_alert(
        self,
        material: str,
        brand: str | None,
        stock_g: float,
        rate_g_day: float,
        days_left: int,
        db: AsyncSession,
        skip_break_subscribers: bool = False,
        provider_ids: set[int] | None = None,
        skip_digest_provider_ids: set[int] | None = None,
    ) -> dict[int, NotificationDelivery]:
        """Fire when an inventory SKU reaches its reorder point."""
        providers = await self._get_providers_for_event(db, "on_stock_reorder_alert", None)
        if skip_break_subscribers:
            providers = [provider for provider in providers if not provider.on_stock_break_alert]
        if provider_ids is not None:
            providers = [provider for provider in providers if provider.id in provider_ids]
        if not providers:
            return {}

        variables = {
            "material": material,
            "brand": brand or "",
            "stock_g": f"{stock_g:.0f}",
            "rate_g_day": f"{rate_g_day:.1f}",
            "days_left": str(days_left),
        }

        title, message = await self._build_message_from_template(db, "stock_reorder_alert", variables)
        return await self._send_to_providers(
            providers,
            title,
            message,
            db,
            "stock_reorder_alert",
            variables=variables,
            skip_digest_provider_ids=skip_digest_provider_ids,
        )

    async def on_stock_break_alert(
        self,
        material: str,
        brand: str | None,
        stock_g: float,
        rate_g_day: float,
        days_left: int,
        lead_time_days: int,
        db: AsyncSession,
        provider_ids: set[int] | None = None,
        skip_digest_provider_ids: set[int] | None = None,
    ) -> dict[int, NotificationDelivery]:
        """Fire when a stock break is detected (stock runs out before lead time)."""
        providers = await self._get_providers_for_event(db, "on_stock_break_alert", None)
        if provider_ids is not None:
            providers = [provider for provider in providers if provider.id in provider_ids]
        if not providers:
            return {}

        variables = {
            "material": material,
            "brand": brand or "",
            "stock_g": f"{stock_g:.0f}",
            "rate_g_day": f"{rate_g_day:.1f}",
            "days_left": str(days_left),
            "lead_time_days": str(lead_time_days),
        }

        title, message = await self._build_message_from_template(db, "stock_break_alert", variables)
        return await self._send_to_providers(
            providers,
            title,
            message,
            db,
            "stock_break_alert",
            variables=variables,
            skip_digest_provider_ids=skip_digest_provider_ids,
        )
