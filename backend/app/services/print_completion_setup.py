"""Side-effect gates that must run before production print completion."""

from __future__ import annotations


async def prepare_print_completion(printer_id: int, data: dict, logger, baselines: dict):
    """Claim attribution, reject internal jobs, recover cache, then evict it."""
    from backend.app.services import active_print_provenance as provenance
    from backend.app.services.bambu_ftp import clear_3mf_cache
    from backend.app.services.fallback_archive_recovery import recover_cached_fallback_archive
    from backend.app.utils.print_jobs import ignore_internal_printer_job

    session = await provenance.claim_print_session(printer_id, data, logger)
    if ignore_internal_printer_job(data, logger, "completion"):
        await provenance.discard_print_session(printer_id, session, logger)
        baselines.pop(printer_id, None)
        return session, True
    await recover_cached_fallback_archive(printer_id, data)
    clear_3mf_cache(printer_id)
    return session, False
