"""Quality prompt fan-out preserves standard notification delivery policy."""


async def send_confirmation(
    service, printer_id, printer_name, db, print_name, confirm_url, outcome_urls, archive_id, run_id
):
    providers = await service._get_providers_for_event(db, "on_print_confirm_request", printer_id)
    if not providers:
        return
    variables = {
        "printer": printer_name,
        "filename": print_name,
        "confirm_url": confirm_url,
        "archive_id": archive_id,
        "run_id": run_id,
    }
    title, message = await service._build_message_from_template(db, "print_confirm_request", variables)
    variables["_outcome_urls"] = outcome_urls
    if archive_id is not None and run_id is not None:
        variables["_telegram_quality_context"] = (archive_id, run_id)
    await service._send_to_providers(
        providers,
        title,
        message,
        db,
        event_type="print_confirm_request",
        printer_id=printer_id,
        printer_name=printer_name,
        variables=variables,
    )


class NotificationQualityEvents:
    async def on_print_confirm_request(
        self, printer_id, printer_name, db, *, print_name, confirm_url, outcome_urls, archive_id=None, run_id=None
    ):
        await send_confirmation(
            self, printer_id, printer_name, db, print_name, confirm_url, outcome_urls, archive_id, run_id
        )

    def start_background(self):
        from backend.app.services import telegram_polling

        self.start_digest_scheduler()
        telegram_polling.start()

    async def stop_background(self):
        from backend.app.services import telegram_polling

        self.stop_digest_scheduler()
        await telegram_polling.stop()
