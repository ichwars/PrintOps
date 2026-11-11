import asyncio
import json
import logging
import mimetypes as _mimetypes
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, or_, select, text, update

from backend.app.api.commerce_router import router as commerce_router
from backend.app.api.routes import (
    ams_history,
    api_keys,
    archive_purge,
    archives,
    archives_latest,
    auth,
    bug_report,
    bulk,
    camera,
    camwall,
    cloud,
    connected_apps,
    discovery,
    external_links,
    filaments,
    firmware,
    github_backup,
    groups,
    ha_sensors,
    inventory,
    kprofiles,
    labels,
    library,
    library_tags,
    library_trash,
    library_variants,
    local_backup,
    local_presets,
    maintenance,
    makerworld,
    metrics,
    mfa,
    notification_templates,
    notifications,
    obico,
    orca_cloud,
    pending_uploads,
    pipeline_runs,
    print_log,
    print_queue,
    printer_files,
    printer_sensor_history,
    printers,
    projects,
    queue_history,
    settings as settings_routes,
    slice_jobs,
    slicer_pipelines,
    slicer_presets,
    smart_plugs,
    sponsor_prompt,
    spoolbuddy,
    spoolman,
    spoolman_inventory,
    storage_ha_sensors,
    support,
    system,
    updates,
    user_notifications,
    users,
    virtual_printers,
    webhook,
    websocket,
)
from backend.app.api.routes.maintenance import _get_printer_maintenance_internal, ensure_default_types
from backend.app.api.routes.support import init_debug_logging
from backend.app.core.config import APP_VERSION, settings as app_settings
from backend.app.core.database import async_session, engine, init_db
from backend.app.core.request_validation import request_validation_error
from backend.app.core.static_assets import AssetStaticFiles
from backend.app.core.tasks import spawn_background_task
from backend.app.core.websocket import ws_manager
from backend.app.services import (
    active_print_provenance as print_provenance,
    business_runtime,
    fallback_archive_recovery as fallback_recovery,
    slot_unlink_grace,
)
from backend.app.services.ams_assignment_lock import get_ams_assignment_lock
from backend.app.services.ams_weight_sync import sync_automatic_weight
from backend.app.services.archive import ArchiveService, peek_plate_index_in_3mf, swap_plate_suffix
from backend.app.services.archive_cost_estimate import schedule_archive_cost_estimate, settle_archive_cost_estimate
from backend.app.services.archive_purge import archive_purge_service
from backend.app.services.bambu_ftp import (
    FileNotOnPrinterError,
    cache_3mf_download,
    download_file_async,
    get_cached_3mf,
    get_ftp_retry_settings,
    with_ftp_retry,
)
from backend.app.services.bambu_mqtt import PrinterState
from backend.app.services.camera_light import automatic_camera_light
from backend.app.services.github_backup import github_backup_service
from backend.app.services.ha_sensor_manager import ha_sensor_manager
from backend.app.services.homeassistant import homeassistant_service
from backend.app.services.library_trash import library_trash_service
from backend.app.services.mqtt_relay import mqtt_relay
from backend.app.services.mqtt_smart_plug import mqtt_smart_plug_service
from backend.app.services.notification_service import notification_service
from backend.app.services.obico_detection import obico_detection_service
from backend.app.services.pause_eta import observe as observe_scheduled_pause
from backend.app.services.print_completion_identity import (
    bump_library_file_usage_if_completed as _bump_library_file_usage_if_completed,
    update_queue_status_for_completion,
)
from backend.app.services.print_completion_setup import prepare_print_completion
from backend.app.services.print_event_tasks import (
    backfill_completed_batches,
    calculate_print_energy,
    check_kprofile_status,
    check_print_maintenance,
    check_print_start_plate,
    complete_layer_timelapse,
)
from backend.app.services.print_scheduler import scheduler as print_scheduler
from backend.app.services.print_usage_lifecycle import hold_completion_charges, printer_is_charging
from backend.app.services.printer_deletion import clear_state_if_printer_deleted
from backend.app.services.printer_job_identity import expected_print_keys
from backend.app.services.printer_manager import (
    init_printer_connections,
    parse_plate_id,
    printer_manager,
    printer_state_to_dict,
    resolve_plate_id,
)
from backend.app.services.printer_status_fingerprint import machine_status_key
from backend.app.services.sensor_history_settings import history_cutoff
from backend.app.services.smart_plug_manager import smart_plug_manager
from backend.app.services.smart_plug_selection import read_printer_energy
from backend.app.services.spool_assignment_notifications import (
    notify_missing_spool_assignments_on_print_start,
)
from backend.app.services.spool_slot_material import expected_spool_protocol_types
from backend.app.services.spoolman import close_spoolman_client, get_spoolman_client, init_spoolman_client
from backend.app.services.spoolman_costs import resolve_print_log_cost
from backend.app.services.spoolman_slot_sync import refresh_synced_presets, write_slot_results
from backend.app.services.spoolman_tracking import (
    cleanup_tracking as _cleanup_spoolman_tracking,
    release_archived_slot_rows as _release_archived_spoolman_slots,
    report_usage as _report_spoolman_usage,
    store_print_data as _store_spoolman_print_data,
)
from backend.app.services.tasmota import tasmota_service
from backend.app.utils.filament_types import printer_filament_type
from backend.app.utils.local_time import to_naive_utc, utcnow_naive


def _start_error_server(missing_packages: list):
    """Start a minimal HTTP server to display dependency errors in browser."""
    import os
    import signal
    from http.server import BaseHTTPRequestHandler, HTTPServer

    packages_html = "".join(f"<li><code>{p}</code></li>" for p in missing_packages)

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>PrintOps - Setup Required</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a; color: #e2e8f0;
            display: flex; justify-content: center; align-items: center;
            min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box;
        }}
        .container {{
            background: #1e293b; border-radius: 12px; padding: 40px;
            max-width: 600px; text-align: center; box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }}
        h1 {{ color: #f87171; margin-bottom: 10px; }}
        h2 {{ color: #94a3b8; font-weight: normal; margin-top: 0; }}
        .packages {{
            background: #0f172a; border-radius: 8px; padding: 20px;
            margin: 20px 0; text-align: left;
        }}
        .packages ul {{ margin: 0; padding-left: 20px; }}
        .packages li {{ color: #fbbf24; margin: 8px 0; }}
        .command {{
            background: #0f172a; border-radius: 8px; padding: 15px 20px;
            margin: 15px 0; font-family: monospace; color: #4ade80;
            text-align: left; overflow-x: auto;
        }}
        .note {{ color: #94a3b8; font-size: 14px; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Setup Required</h1>
        <h2>Missing Python packages</h2>
        <div class="packages"><ul>{packages_html}</ul></div>
        <p>To fix, run this command on your server:</p>
        <div class="command">pip install --require-hashes -r requirements.lock.txt</div>
        <p>Or if using a virtual environment:</p>
        <div class="command">./venv/bin/pip install --require-hashes -r requirements.lock.txt</div>
        <p class="note">After installing, restart PrintOps:<br>
        <code>sudo systemctl restart printops</code></p>
    </div>
</body>
</html>"""

    class ErrorHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(503)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html.encode())

        def log_message(self, format, *args):
            print(f"[Error Server] {args[0]}")

    port = int(os.environ.get("PORT", 8000))
    print(f"\nStarting error server on http://0.0.0.0:{port}")
    print("Visit this URL in your browser to see the error details.\n")

    server = HTTPServer(("0.0.0.0", port), ErrorHandler)  # nosec B104

    def shutdown(signum, frame):
        print("\nShutting down error server...")
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    server.serve_forever()


def check_dependencies():
    """Check that all required packages are installed."""
    missing = []

    # Map of import name -> package name (for pip install)
    required = {
        "jwt": "PyJWT",
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "sqlalchemy": "sqlalchemy",
        "aiosqlite": "aiosqlite",
        "pydantic": "pydantic",
        "paho.mqtt": "paho-mqtt",
    }

    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if missing:
        print("\n" + "=" * 60)
        print("ERROR: Missing required Python packages!")
        print("=" * 60)
        print(f"\nMissing packages: {', '.join(missing)}")
        print("\nTo fix, run:")
        print("  pip install --require-hashes -r requirements.lock.txt")
        print("\nOr if using a virtual environment:")
        print("  ./venv/bin/pip install --require-hashes -r requirements.lock.txt")
        print("=" * 60 + "\n")
        _start_error_server(missing)


check_dependencies()

# Import settings first for logging configuration

# Configure logging based on settings
# DEBUG=true -> DEBUG level, else use LOG_LEVEL setting
log_level_str = "DEBUG" if app_settings.debug else app_settings.log_level.upper()
log_level = getattr(logging, log_level_str, logging.INFO)
# Trace ID column ([-] when no request scope is active — startup, MQTT
# callbacks, scheduled tasks not chained from a request — so the column
# stays visually aligned and missing values are obvious in grep). See
# backend/app/core/trace.py for the ContextVar that feeds this slot.
log_format = "%(asctime)s %(levelname)s [%(name)s] [%(trace_id)s] %(message)s"

root_logger = logging.getLogger()
root_logger.setLevel(log_level)

# Trace-ID injection: this filter populates record.trace_id from the
# per-request ContextVar so the format string above can reference it.
# Attached to each HANDLER (not the root logger) because Python's
# logging semantics only invoke a logger's filters on records that
# *originated* at that logger — records propagated up from child
# loggers (every named logger in the app) never trigger root's filter.
# Putting it on the handlers means every record any handler emits gets
# trace_id injected just before the formatter runs, regardless of which
# logger created the record. Without this, the formatter raises
# KeyError on every child-logger record and the record is silently
# dropped — which is exactly the "logs/printops.log only shows logs
# partially" bug we hit. See backend/app/core/trace.py for the
# ContextVar the filter reads.
from backend.app.core.logging_filters import SensitiveLogRedactFilter
from backend.app.core.response_redaction import RefusedHeaderResponseMask
from backend.app.core.trace import TraceIDFilter

_trace_id_filter = TraceIDFilter()
_sensitive_log_filter = SensitiveLogRedactFilter()

# Console handler - always enabled
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
console_handler.setFormatter(logging.Formatter(log_format))
console_handler.addFilter(_trace_id_filter)
console_handler.addFilter(_sensitive_log_filter)
root_logger.addHandler(console_handler)

# File handler - only in production or if explicitly enabled
if app_settings.log_to_file:
    log_file = app_settings.log_dir / "printops.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logging.Formatter(log_format))
    file_handler.addFilter(_trace_id_filter)
    file_handler.addFilter(_sensitive_log_filter)
    root_logger.addHandler(file_handler)
    logging.info("Logging to file: %s", log_file)

    # Pipe uvicorn's HTTP access log to printops.log too. Uvicorn ships its
    # access logger with propagate=False by default, so without this attach
    # there is no on-disk record of which endpoint triggered a server-state
    # change — the rogue stop_print mystery on 2026-04-26 was untraceable
    # for exactly this reason. Filtered to write methods only
    # (POST/PUT/PATCH/DELETE) so the high-volume status-poll GETs from the
    # frontend don't churn the rotation window faster than it's useful.
    from backend.app.core.logging_filters import (
        CancelledPoolNoiseFilter,
        WriteRequestsOnlyFilter,
    )

    logging.getLogger("uvicorn.error").addHandler(file_handler)
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.addHandler(file_handler)
    uvicorn_access_logger.addFilter(WriteRequestsOnlyFilter())
    # Uvicorn's access logger has propagate=False (its own default), so the
    # root-attached TraceIDFilter never sees these records. Attach a
    # second instance directly so HTTP access lines carry the same trace
    # ID column as the application logs they correlate with.
    uvicorn_access_logger.addFilter(TraceIDFilter())

    # Drop SQLAlchemy connection-pool log noise that's caused by Starlette's
    # BaseHTTPMiddleware cancelling the inner task scope on client
    # disconnect (#1112). The cancel-safe `get_db` already prevents the
    # underlying transaction leak; this filter only suppresses the residual
    # log records that pre-existing pools still emit during their cleanup.
    logging.getLogger("sqlalchemy.pool").addFilter(CancelledPoolNoiseFilter())

from backend.app.core.logging_filters import ShutdownCancelledRequestFilter  # noqa: E402

logging.getLogger("uvicorn.error").addFilter(ShutdownCancelledRequestFilter())
for _logger_name in ("uvicorn.access", "uvicorn.error"):
    logging.getLogger(_logger_name).addFilter(_sensitive_log_filter)

# HTTP request URLs can contain bot credentials, even in application debug mode.
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
if not app_settings.debug:
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("paho.mqtt").setLevel(logging.WARNING)

logging.info("PrintOps starting - debug=%s, log_level=%s", app_settings.debug, log_level_str)

# Track active prints: {(printer_id, filename): archive_id}
_active_prints: dict[tuple[int, str], int] = {}

# #1721: stage-22 pre-captured finish photo bytes per printer. on_finish_photo_moment
# fires when stg_cur enters 22 ("Filament unloading") at end-of-print — toolhead
# parked, bed not yet dropped — and grabs a single camera frame into this cache.
# `_background_finish_photo` (inside on_print_complete) consumes the cached bytes
# instead of running its own grab-now chain when present, so the finish photo
# captures the better-framed pre-bed-drop moment without us having to force
# timelapse on at dispatch (the #1397 mechanism that caused #1721's per-layer
# nozzle parking on slicer profiles with Timelapse Type = Smooth).
_stage22_finish_frames: dict[int, bytes] = {}

# #1790: per-printer producer-done event. Set by `on_finish_photo_moment` in its
# `finally` block (whether it captured a frame or not). The consumer in
# `_background_finish_photo` waits on it before reading `_stage22_finish_frames`
# so the FINISH-state fallback path — where moment and completion are dispatched
# back-to-back — doesn't race past the producer with an empty pop, and the
# consumer's RTSP fallback can't collide with the producer's still-in-flight RTSP
# grab (Bambu printers allow only one RTSP client at a time).
_stage22_finish_in_flight: dict[int, asyncio.Event] = {}

# Per-printer "connected" edge tracker. Used by `on_printer_status_change`
# to fire `reconcile_stale_active_prints` exactly once per (re)connection
# (#1542 follow-up — power-cycle ghost prints). The value is True after
# the first connected status update for that connection; transitions back
# to False whenever we observe `state.connected = False` so the next
# reconnect re-arms reconciliation. Keyed by printer_id.
_printer_reconciled_since_connect: dict[int, bool] = {}

# Track expected prints from reprint/scheduled (skip auto-archiving for these)
# {(printer_id, filename): archive_id}
_expected_prints: dict[tuple[int, str], int] = {}

# Dispatch metadata, keyed by (printer_id, archive_id) until completion or expiry.
_print_ams_mappings: dict[tuple[int, int], list[int]] = {}
_print_plate_ids: dict[tuple[int, int], int] = {}

# Track progress milestones for notifications: {printer_id: last_milestone_notified}
# Milestones are 25, 50, 75. Value of 0 means no milestone notified yet for current print.
_last_progress_milestone: dict[int, int] = {}

# Track whether first layer complete notification has been sent for current print
_first_layer_notified: dict[int, bool] = {}

# Full fault identity and last observation, even when adjacent faults remain present.
_notified_hms_errors: dict[int, dict[str, float]] = {}
_hms_print_state: dict[int, str] = {}
_hms_forget_when_gone: dict[int, set[str]] = {}
_HMS_CLEAR_GRACE_SECONDS = 600.0

# Track timelapse file baselines at print start: {printer_id: set of video filenames}
# Used for snapshot-diff detection at print completion
_timelapse_baselines: dict[int, set[str]] = {}

# Track printers waiting for bed to cool after print completion.
# Event-driven: fires when bed_temper arrives via MQTT below threshold.
# {printer_id: {"threshold": float, "filename": str, "registered_at": float}}
_bed_cool_waiters: dict[int, dict] = {}

# Track printers where the user explicitly stopped the print from the queue UI.
# When on_print_complete fires with status "failed" for these printers we treat it
# as "cancelled" (stopped by user) so the correct notification email is sent.
_user_stopped_printers: set[int] = set()

# Offline-notification edge state (#1752): fire `on_printer_offline` exactly
# once when a printer transitions connected → disconnected. `_printer_last_connected`
# holds the previous observation so we only fire on the True → False edge (a
# False → False repeat doesn't notify; an initial False at startup doesn't
# notify either, since there's no prior True). `_printer_offline_notify_tasks`
# holds the per-printer pending asyncio task that fires the notification
# after a debounce window — cancelled if the printer reconnects before the
# window elapses, so transient MQTT blips don't flood the user.
_printer_last_connected: dict[int, bool] = {}
_printer_offline_published: set[int] = set()
_printer_offline_notify_tasks: dict[int, asyncio.Task] = {}
# Debounce: a printer must stay offline this long before we notify. Sized
# against the staleness path (`bambu_mqtt.py::STALE_RECONNECT_COOLDOWN = 30s`)
# so a single stale-trigger cooldown isn't enough to fire — only a real
# offline that survives one reconnect attempt notifies.
_PRINTER_OFFLINE_NOTIFY_DEBOUNCE_SECONDS = 60.0

# HMS short-code → human-readable failure reason. Used by _dispatch_archive_update
# when status="failed" to label the print's failure_reason in archives.
#
# Earlier code matched on `module` alone (e.g. "any module 0x0C HMS → Layer shift"),
# which is wrong on two counts:
#   1. Real layer-shift codes live in module 0x03 (see Bambu wiki), not 0x0C.
#   2. Module 0x0C is "Motion Controller" — broad category that also covers cameras
#      and visual markers, AND the H2D firmware emits a 0x0C HMS (0C00_001B, not in
#      the public wiki) as part of its user-cancel sequence. Matching on the module
#      alone caused user-cancellations to be archived as "Layer shift" failures.
# We now match by full short code only — anything not in this map leaves
# failure_reason=None rather than guessing.
_HMS_FAILURE_REASONS: dict[str, str] = {
    # Layer shift / step loss
    "0300_4057": "Layer shift",
    "0300_4068": "Layer shift",
    "0300_800C": "Layer shift",
    # Filament runout (printer-side & per-AMS-slot)
    "0300_8004": "Filament runout",
    "0700_8011": "Filament runout",
    "0701_8011": "Filament runout",
    "0702_8011": "Filament runout",
    "0703_8011": "Filament runout",
    "0704_8011": "Filament runout",
    "0705_8011": "Filament runout",
    "0706_8011": "Filament runout",
    "0707_8011": "Filament runout",
    "07FF_8011": "Filament runout",
    # Clogged nozzle / extruder
    "0300_4006": "Clogged nozzle",
    "0300_8016": "Clogged nozzle",
    "0300_801C": "Clogged nozzle",
    "0700_8003": "Clogged nozzle",
    "0700_8007": "Clogged nozzle",
    "0700_8013": "Clogged nozzle",
    "0701_8003": "Clogged nozzle",
    "0701_8007": "Clogged nozzle",
    "0701_8013": "Clogged nozzle",
    "0702_8003": "Clogged nozzle",
}


def _hms_short_code(attr: int, code: int | str) -> str:
    """Build the canonical "MMMM_CCCC" HMS short code from raw attr/code values."""
    if isinstance(code, str):
        code_int = int(code.replace("0x", ""), 16) if code else 0
    else:
        code_int = int(code or 0)
    attr_int = int(attr or 0)
    return f"{(attr_int >> 16) & 0xFFFF:04X}_{code_int & 0xFFFF:04X}"


def derive_failure_reason(status: str, hms_errors: list[dict] | None) -> str | None:
    """Derive a human-readable failure_reason for an archived print.

    Returns "User cancelled" for cancelled/aborted prints; for failed prints,
    returns the first matching reason from _HMS_FAILURE_REASONS, or None when
    no HMS code matches (don't guess — null is honest).
    """
    if status in ("aborted", "cancelled"):
        return "User cancelled"
    if status != "failed":
        return None
    for err in hms_errors or []:
        short_code = _hms_short_code(err.get("attr", 0), err.get("code", 0))
        if short_code in _HMS_FAILURE_REASONS:
            return _HMS_FAILURE_REASONS[short_code]
    return None


# Track created_by_id for expected prints so the user email can be sent even when
# the archive itself doesn't have created_by_id set (e.g. library-file-based prints).
# {(printer_id, filename): created_by_id}
_expected_print_creators: dict[tuple[int, str], int] = {}

# Per-printer dedup for unknown_tag WS broadcasts. Keyed by
# (ams_id, tray_id) -> (tag_uid, tray_uuid); we only re-broadcast when the
# tag tuple changes for the slot. Cleared when the slot is reported empty
# so remove + reinsert reliably re-prompts the UI.
_unknown_tag_last_broadcast: dict[int, dict[tuple[int, int], tuple[str, str]]] = {}


async def _broadcast_unknown_tag(
    *,
    printer_id: int,
    ams_id: int,
    tray_id: int,
    tag_uid: str,
    tray_uuid: str,
    tray_type: str | None = None,
    tray_color: str | None = None,
    tray_sub_brands: str | None = None,
    tray_count: int | None = None,
) -> None:
    """Broadcast unknown_tag, deduped so repeated MQTT pushes for the same slot+tag don't spam the UI."""
    _logger = logging.getLogger(__name__)
    slot_key = (ams_id, tray_id)
    tag_key = (tag_uid or "", tray_uuid or "")
    per_printer = _unknown_tag_last_broadcast.setdefault(printer_id, {})
    if per_printer.get(slot_key) == tag_key:
        _logger.debug(
            "unknown_tag deduped for printer=%d AMS=%d slot=%d tag=%s",
            printer_id,
            ams_id,
            tray_id,
            tag_key[0][:8] or tag_key[1][:8] or "(none)",
        )
        return
    _logger.info(
        "unknown_tag broadcast: printer=%d AMS=%d slot=%d type=%r color=%r tag=%s",
        printer_id,
        ams_id,
        tray_id,
        tray_type,
        tray_color,
        tag_key[0][:8] or tag_key[1][:8] or "(none)",
    )
    # Broadcast first; only commit the dedup if the WS write succeeds.
    # If broadcast raises, the next MQTT push retries instead of being
    # permanently silenced by a poisoned dedup entry.
    await ws_manager.broadcast(
        {
            "type": "unknown_tag",
            "printer_id": printer_id,
            "ams_id": ams_id,
            "tray_id": tray_id,
            "tag_uid": tag_uid,
            "tray_uuid": tray_uuid,
            "tray_type": tray_type,
            "tray_color": tray_color,
            "tray_sub_brands": tray_sub_brands,
            "tray_count": tray_count,
        }
    )
    per_printer[slot_key] = tag_key


def _clear_unknown_tag_dedup(printer_id: int, ams_id: int, tray_id: int) -> None:
    """Drop the cached last-broadcast tag for a slot (called when slot reports empty or gets matched)."""
    per_printer = _unknown_tag_last_broadcast.get(printer_id)
    if per_printer is None:
        return
    per_printer.pop((ams_id, tray_id), None)


# TTL for expected-print entries: evict registrations older than this to prevent
# unbounded growth when a print is registered but never starts (e.g. printer
# disconnect, app restart, print started from the printer panel).
_EXPECTED_PRINT_TTL_SECONDS: int = 2 * 60 * 60  # 2 hours

# Registration timestamps used for TTL eviction: {(printer_id, filename): monotonic_time}
_expected_print_registered_at: dict[tuple[int, str], float] = {}

# Cleanup loop interval
_EXPECTED_PRINT_CLEANUP_INTERVAL: int = 15 * 60  # 15 minutes
_expected_prints_cleanup_task: asyncio.Task | None = None


async def _get_plug_energy(plug, db) -> dict | None:
    """Get energy from plug regardless of type (Tasmota, Home Assistant, MQTT, or REST).

    For HA plugs, configures the service with current settings from DB.
    For MQTT plugs, returns data from the subscription service.
    For REST plugs, polls the status URL with JSON path extraction.
    """
    if plug.plug_type == "homeassistant":
        from backend.app.api.routes.settings import get_homeassistant_settings

        ha_settings = await get_homeassistant_settings(db)
        homeassistant_service.configure(ha_settings["ha_url"], ha_settings["ha_token"])
        return await homeassistant_service.get_energy(plug)
    elif plug.plug_type == "mqtt":
        # MQTT plugs report "today" energy, not lifetime total
        # For per-print tracking, we use "today" as the counter (resets at midnight)
        mqtt_data = mqtt_relay.smart_plug_service.get_plug_data(plug.id)
        if mqtt_data:
            return {
                "power": mqtt_data.power,
                "today": mqtt_data.energy,
                "total": mqtt_data.energy,  # Use today as total for per-print calculations
            }
        return None
    elif plug.plug_type == "rest":
        from backend.app.services.rest_smart_plug import rest_smart_plug_service

        return await rest_smart_plug_service.get_energy(plug)
    else:
        return await tasmota_service.get_energy(plug)


async def _record_energy_start(archive, printer_id: int, db, *, context: str = "", run=None) -> bool:
    """Capture the smart plug lifetime counter for this print run."""
    _logger = logging.getLogger(__name__)
    try:
        selected = await read_printer_energy(
            db, printer_id, _get_plug_energy, log_prefix="ENERGY", context=f"archive {archive.id}"
        )
        if selected is None:
            return False
        plug, energy = selected
        from backend.app.services.print_log_run import record_run_energy_start

        await record_run_energy_start(db, archive, printer_id, float(energy["total"]), plug.id, run=run)
        await db.commit()
        _logger.info(
            "[ENERGY] Recorded starting energy%s for archive %s from plug '%s': %s kWh",
            f" ({context})" if context else "",
            archive.id,
            plug.name,
            energy["total"],
        )
        return True
    except Exception as e:
        _logger.warning("[ENERGY] Failed to record starting energy for archive %s: %s", archive.id, e)
        return False


def register_expected_print(
    printer_id: int,
    filename: str,
    archive_id: int,
    ams_mapping: list[int] | None = None,
    created_by_id: int | None = None,
    plate_id: int | None = None,
):
    """Register an expected print from reprint/scheduled so we don't create duplicate archives."""
    keys = [(printer_id, filename)]
    if filename.endswith(".3mf"):
        base = filename[:-4]
        keys.extend(((printer_id, base), (printer_id, f"{base}.gcode")))
    registered_at = time.monotonic()
    for key in keys:
        _expected_prints[key] = archive_id
        _expected_print_registered_at[key] = registered_at
        if created_by_id is None:
            _expected_print_creators.pop(key, None)
        else:
            _expected_print_creators[key] = created_by_id
    dispatch = (printer_id, archive_id)
    archive_printing = any(pid == printer_id and aid == archive_id for (pid, _), aid in _active_prints.items())
    if ams_mapping is not None:
        _print_ams_mappings[dispatch] = ams_mapping
    elif not archive_printing:
        _print_ams_mappings.pop(dispatch, None)
    # Store plate_id for usage tracking when this is a single-plate dispatch from
    # a multi-plate 3MF — without this, the direct-Print path attributes the whole
    # file's filament total to the spool instead of just the printed plate (#1697).
    if plate_id is not None:
        _print_plate_ids[dispatch] = plate_id
    elif not archive_printing:
        _print_plate_ids.pop(dispatch, None)
    logging.getLogger(__name__).info(
        f"Registered expected print: printer={printer_id}, file={filename}, archive={archive_id}, ams_mapping={ams_mapping}, plate_id={plate_id}"
    )


def _consume_expected_print(printer_id, keys):
    """Take a dispatch and every alias registered with it, including unreported names."""
    key = next((key for key in keys if key in _expected_prints), None)
    if key is None:
        return None, None
    archive_id = _expected_prints[key]
    registered_at = _expected_print_registered_at.get(key)
    creator_id = _expected_print_creators.get(key)
    for alias, expected_id in list(_expected_prints.items()):
        if (
            alias[0] == printer_id
            and expected_id == archive_id
            and _expected_print_registered_at.get(alias) == registered_at
        ):
            _expected_prints.pop(alias, None)
            _expected_print_registered_at.pop(alias, None)
            _expected_print_creators.pop(alias, None)
    return archive_id, creator_id


def unregister_expected_print(printer_id: int, filename: str, archive_id: int) -> None:
    """Withdraw only this failed send, keeping metadata of expected or running plates."""
    keys = [(printer_id, filename)]
    if filename.endswith(".3mf"):
        base = filename[:-4]
        keys.extend(((printer_id, base), (printer_id, f"{base}.gcode")))
    for key in keys:
        if _expected_prints.get(key) == archive_id:
            _expected_prints.pop(key, None)
            _expected_print_creators.pop(key, None)
            _expected_print_registered_at.pop(key, None)
    dispatch = (printer_id, archive_id)
    if not any(
        pid == printer_id and aid == archive_id
        for state in (_expected_prints, _active_prints)
        for (pid, _), aid in state.items()
    ):
        _print_ams_mappings.pop(dispatch, None)
        _print_plate_ids.pop(dispatch, None)


def _bind_active_print(printer_id, archive_id, archive_filename, filename, subtask_name):
    """Use the same archive and printer names for every print-start path."""
    names = {archive_filename, filename, subtask_name}
    if subtask_name:
        names.add(f"{subtask_name}.3mf")
    for name in names - {None, ""}:
        _active_prints[(printer_id, name)] = archive_id


async def _bind_and_record_print_run(db, printer, archive, filename, subtask_name, logger) -> bool:
    from backend.app.core.printer_lifecycle import lock_existing_printer
    from backend.app.services.print_log_run import record_print_run_start

    try:
        async with db.begin_nested():
            if not await lock_existing_printer(db, printer.id):
                return False
            opened, discarded = await record_print_run_start(
                db, printer, archive, _get_start_plate_id(printer.id, archive.id)
            )
        await db.commit()
        for run in discarded:
            for key in [
                key for key, value in _active_prints.items() if key[0] == printer.id and value == run.archive_id
            ]:
                _active_prints.pop(key)
            if run.archive_id != archive.id:
                _print_ams_mappings.pop((printer.id, run.archive_id), None)
                _print_plate_ids.pop((printer.id, run.archive_id), None)
            await mqtt_relay.on_run_event("discarded", run, printer)
        _bind_active_print(printer.id, archive.id, archive.filename, filename, subtask_name)
        if opened is not None:
            await mqtt_relay.on_run_event("started", opened, printer)
    except Exception:
        logger.warning("Could not record start of archive %s on printer %s", archive.id, printer.id, exc_info=True)
        _bind_active_print(printer.id, archive.id, archive.filename, filename, subtask_name)

    return True


def _compute_run_filament_grams(
    status: str,
    archive_filament_used_grams: float | None,
    progress: float | int | None,
    usage_results: list[dict] | None,
) -> float | None:
    """Per-run filament for PrintLogEntry, partial- and tracker-aware (#1378, #1390).

    Priority for every status:
        1. Sum of tracked spool deltas in ``usage_results`` (AMS-measured
           weight delta — same source that drives "Total Consumed" on the
           Inventory page, so Stats and Inventory totals stay aligned).
        2. For ``completed``: the slicer estimate (no tracker available, fall
           back to the canonical "this print used X" value).
        3. For partial statuses: ``estimate * progress%``.
        4. ``None`` if nothing is known.
    """
    tracked_grams = sum(r.get("weight_used") or 0 for r in (usage_results or []))
    if tracked_grams > 0:
        return round(tracked_grams, 1)

    if status == "completed":
        return archive_filament_used_grams

    if archive_filament_used_grams:
        scale = max(0.0, min(((progress or 0) / 100.0), 1.0))
        if scale > 0:
            return round(archive_filament_used_grams * scale, 1)

    return None


def _get_start_ams_mapping(data: dict, printer_id: int, archive_id: int | None) -> list[int] | None:
    """Resolve AMS mapping for print start without consuming stored queue/reprint state."""
    stored_ams_mapping = data.get("ams_mapping")
    if not stored_ams_mapping and archive_id:
        stored_ams_mapping = _print_ams_mappings.get((printer_id, archive_id))
    return stored_ams_mapping


def _get_start_plate_id(printer_id: int, archive_id: int | None) -> int | None:
    return _print_plate_ids.get((printer_id, archive_id)) if archive_id is not None else None


def _partial_progress_scale(progress: int | float | None) -> float:
    """Clamp ``progress / 100`` into [0.0, 1.0] for partial-print scaling.

    Used by every site that multiplies a "would-have-used" slicer estimate
    down to "actually-used" for failed / cancelled / stopped prints. Centralised
    so the three sites in ``_background_notifications`` (and the per-plate
    override helper) can't drift apart on the coercion shape.
    """
    return max(0.0, min((progress or 0) / 100.0, 1.0))


def _scope_notification_archive_data_to_plate(
    archive_data: dict,
    archive_file_path: str | None,
    plate_id: int | None,
    print_status: str,
    progress: int | float | None,
    base_dir: Path,
) -> dict:
    """Override summed-across-plates totals in ``archive_data`` with the values
    for ``plate_id`` so the completion notification reports what was actually
    printed, not the whole project (#1785).

    The 3MF parser at services/archive.py:200-264 sums ``prediction`` and
    ``weight`` across every plate of a multi-plate file (#1593) — correct for
    the archive card's "whole project" headline, wrong for the completion
    notification of a single-plate print. The queue UI already re-reads the
    3MF per-plate at print_queue.py:272-285; this helper mirrors that for the
    notification payload (filament grams, time estimate, per-slot breakdown).

    No-ops when ``plate_id`` is None, the file is missing, or the 3MF carries
    no per-plate values — in every fail case the original ``archive_data`` is
    returned unchanged so the notification still sends.
    """
    if plate_id is None or not archive_file_path:
        return archive_data

    from backend.app.utils.threemf_tools import (
        extract_filament_usage_from_3mf,
        extract_print_time_from_3mf,
    )

    archive_path = base_dir / archive_file_path
    if not archive_path.exists():
        return archive_data

    plate_slots = extract_filament_usage_from_3mf(archive_path, plate_id)
    plate_grams = sum(f.get("used_g", 0) for f in plate_slots)
    plate_time = extract_print_time_from_3mf(archive_path, plate_id)

    scale = 1.0 if print_status == "completed" else _partial_progress_scale(progress)

    if plate_time:
        archive_data["print_time_seconds"] = plate_time

    # Gate both the grams headline AND the per-slot breakdown on the same
    # `plate_grams > 0` signal: if the 3MF carries per-plate filament rows but
    # they all sum to zero (slicer bug / re-slice without estimate), drop back
    # to the project-level grams the archive columns already provide rather
    # than ship a project-level headline next to an all-zero per-plate
    # breakdown.
    if plate_grams > 0:
        archive_data["actual_filament_grams"] = round(plate_grams * scale, 1)
        archive_data["filament_slots"] = [
            {
                "slot_id": s.get("slot_id"),
                "used_g": round((s.get("used_g") or 0) * scale, 1),
                "type": s.get("type", ""),
                "color": s.get("color", ""),
            }
            for s in plate_slots
        ]

    return archive_data


def _extract_filament_data_from_mqtt(data: dict, ams_mapping: list[int] | None = None) -> dict[str, str]:
    """Best-effort filament metadata from the MQTT print-start snapshot.

    Used when the 3MF can't be downloaded (P1S/A1/P2S firmwares lock the
    file during print, see #1533) so the fallback PrintArchive still has
    enough filament info to support the inventory views and AMS-expansion
    planning the operator opens it for. Returns a dict with optional
    ``filament_type`` and ``filament_color`` keys in the same
    comma-separated format the 3MF extractor produces, so the rest of the
    codebase treats the fallback archive identically to a normal one.

    ``ams_mapping`` is the slicer's slot-per-print-filament list captured
    from the MQTT print payload (global tray IDs, possibly -1 for VT-tray
    entries). When supplied, only the slots actually consumed by this
    print contribute. Without it the function falls back to every loaded
    AMS slot — less accurate but still useful.

    Accepts both the raw inner payload (``{"ams": {"ams": [...]}, ...}``)
    that the unit tests pass directly, AND the on_print_start callback
    shape (``{"raw_data": {"ams": {"ams": [...]}, ...}, ...}``) the
    bambu_mqtt service hands to main.py at runtime. The original
    ``_extract_filament_data_from_mqtt(data)`` shipped in #1533 only
    handled the inner shape and silently returned ``{}`` for every real
    print start, leaving fallback archives' filament fields NULL — the
    exact regression the fix was meant to close. Reported with a log
    proving the AMS state was right there at
    ``data["raw_data"]["ams"]["ams"][0]["tray"][0]`` (#1533 follow-up).
    """
    result: dict[str, str] = {}
    # Look at the on_print_start wrapper first, then the inner shape.
    raw_data = (data or {}).get("raw_data")
    ams_root = (raw_data or {}).get("ams") if isinstance(raw_data, dict) else None
    if not isinstance(ams_root, dict):
        ams_root = (data or {}).get("ams") or {}
    ams_units = ams_root.get("ams") if isinstance(ams_root, dict) else None
    if not isinstance(ams_units, list) or not ams_units:
        return result

    from backend.app.utils.color_utils import filament_rgb

    # AMS HT addresses its single tray by unit ID.
    loaded: dict[int, tuple[str, str]] = {}
    for unit in ams_units:
        if not isinstance(unit, dict):
            continue
        try:
            unit_id = int(unit.get("id", 0))
        except (TypeError, ValueError):
            continue
        for tray in unit.get("tray") or []:
            if not isinstance(tray, dict):
                continue
            try:
                tray_id = int(tray.get("id", 0))
            except (TypeError, ValueError):
                continue
            ttype = (tray.get("tray_type") or "").strip()
            tcolor = filament_rgb(tray.get("tray_color"))
            if not ttype:
                continue  # Empty / unloaded slot.
            loaded[unit_id if unit_id >= 128 else unit_id * 4 + tray_id] = (ttype, tcolor)

    if not loaded:
        return result

    if ams_mapping:
        used_ids = [int(x) for x in ams_mapping if isinstance(x, (int, float)) and int(x) >= 0]
        filaments = [loaded[g] for g in used_ids if g in loaded]
        if not filaments:
            return result  # Mapping points entirely at slots we have no data for.
    else:
        filaments = [loaded[g] for g in sorted(loaded.keys())]

    types_joined = ",".join(f[0] for f in filaments)
    colors_joined = ",".join([color for _, color in filaments if color][:25])

    # Column limits per backend/app/models/archive.py: filament_type=50,
    # filament_color=200.
    if types_joined:
        result["filament_type"] = types_joined[:50]
    if colors_joined:
        result["filament_color"] = colors_joined[:200]
    return result


def _maybe_start_layer_timelapse(printer, printer_id: int, archive_id: int) -> bool:
    """Start a layer-timelapse session for *archive_id* when the printer has
    an external camera configured. Returns True if a session was started.

    Three call sites in on_print_start (expected-archive promotion, fallback
    archive creation, fresh-archive creation) used to inline this same
    if-block; the inline copies kept drifting (#1353 fixed only one of them
    on the first pass). Centralising the conditional + call here makes the
    contract testable in isolation and keeps the three sites locked in step.
    """
    if not (printer.external_camera_enabled and printer.external_camera_url):
        return False
    from backend.app.services.layer_timelapse import start_session

    start_session(
        printer_id,
        archive_id,
        printer.external_camera_url,
        printer.external_camera_type or "mjpeg",
        snapshot_url=printer.external_camera_snapshot_url,
        rotation=getattr(printer, "camera_rotation", 0) or 0,
    )
    logging.getLogger(__name__).info("Started layer timelapse for printer %s, archive %s", printer_id, archive_id)
    return True


def _format_hms_error_summary(hms_errors: list[dict]) -> str | None:
    """Build a human-readable failure reason from MQTT hms_errors for PrintQueueItem.error_message.

    Current payloads carry the resolved manufacturer description and full code.
    Historical payloads without those fields keep their print_error short-code
    lookup. A 64-bit HMS code never borrows text from the 32-bit keyspace.
    Unknown faults retain their code; an empty list returns None.
    """
    if not hms_errors:
        return None
    from backend.app.services.hms_errors import describe_fault, get_error_description

    parts: list[str] = []
    for err in hms_errors:
        try:
            code_str = str(err.get("code", "")).replace("0x", "")
            error_num = int(code_str, 16) if code_str else 0
            module_num = (int(err.get("attr", 0)) >> 16) & 0xFFFF
            short_code = f"{module_num:04X}_{error_num:04X}"
        except (TypeError, ValueError):
            continue
        full_code = err.get("full_code") or ""
        if "description" in err:
            description = err["description"]
        elif full_code:
            description = describe_fault(full_code)
        else:
            description = get_error_description(short_code)
        display_code = (
            "-".join(full_code[index : index + 4] for index in range(0, 16, 4)) if len(full_code) == 16 else short_code
        )
        parts.append(f"[{display_code}] {description}" if description else f"[{display_code}]")
    return "; ".join(parts) if parts else None


def mark_printer_stopped_by_user(printer_id: int) -> None:
    """Mark that the active print on this printer was stopped by the user from the queue UI.

    When on_print_complete fires with status 'failed' for a printer in this set we
    reclassify it as 'cancelled' so the correct 'print stopped' notification is sent
    rather than a 'print failed' notification.
    """
    _user_stopped_printers.add(printer_id)
    logging.getLogger(__name__).info("Marked printer %s as user-stopped from queue", printer_id)


_last_status_broadcast: dict[int, str] = {}
# Track printers where we've updated nozzle_count
_nozzle_count_updated: set[int] = set()
_persisted_firmware_versions: dict[int, str] = {}


async def _maybe_notify_printer_offline(printer_id: int) -> None:
    """Wait the debounce window then fire `on_printer_offline` if the printer
    is still offline.

    Scheduled by `on_printer_status_change` on the connected → disconnected
    edge (#1752). Cancelled by the same handler if the printer reconnects
    before the window elapses, so a single MQTT blip + recovery doesn't
    notify. Both the staleness-detector path (`bambu_mqtt.py::check_staleness`)
    and the smart-plug power-off path (`printer_manager.mark_printer_offline`)
    route through the same status-change callback, so this covers both.
    """
    logger = logging.getLogger(__name__)
    try:
        await asyncio.sleep(_PRINTER_OFFLINE_NOTIFY_DEBOUNCE_SECONDS)
        still_offline = not printer_manager.is_connected(printer_id)
        logger.info(
            "[#1752] Printer %s offline debounce elapsed: still_offline=%s",
            printer_id,
            still_offline,
        )
        if not still_offline:
            return
        async with async_session() as db:
            from backend.app.models.printer import Printer

            result = await db.execute(select(Printer).where(Printer.id == printer_id))
            printer = result.scalar_one_or_none()
            if not printer:
                logger.warning(
                    "[#1752] Printer %s missing from DB at offline-notify time; skipping",
                    printer_id,
                )
                return
            if mqtt_relay.enabled and mqtt_relay.connected:
                try:
                    if await mqtt_relay.on_printer_offline(printer_id, printer.name, printer.serial_number):
                        _printer_offline_published.add(printer_id)
                except Exception:
                    logger.warning("Could not relay offline event for printer %s", printer_id, exc_info=True)
            logger.info(
                "[#1752] Dispatching on_printer_offline for printer %s (%s)",
                printer_id,
                printer.name,
            )
            await notification_service.on_printer_offline(printer_id, printer.name, db)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("Printer offline notification failed for printer %s: %s", printer_id, e)
    finally:
        _printer_offline_notify_tasks.pop(printer_id, None)


async def _relay_printer_reconnect(printer_id: int) -> None:
    if printer_id not in _printer_offline_published or not mqtt_relay.connected:
        return
    printer = printer_manager.get_printer(printer_id)
    if printer is None:
        return
    _printer_offline_published.discard(printer_id)
    try:
        if await mqtt_relay.on_printer_online(printer_id, printer.name, printer.serial_number):
            return
    except Exception:
        logging.getLogger(__name__).warning("Could not relay printer %s reconnect", printer_id, exc_info=True)
    _printer_offline_published.add(printer_id)


_NO_PREPARATION_STAGES = frozenset({0, -1, 255})


def _progress_milestone_to_notify(printer_id: int, state: PrinterState) -> int | None:
    """The milestone (25, 50 or 75) this status update reaches for the first time, if any.

    Records it as notified. Called only for a printing state with progress above 0.

    Progress before the first layer is not progress through the print (#3211).
    An A1 mini reports ``mc_percent`` 85 in the first frame of a print, while
    still preheating the bed at layer 0, then 3, 7, 40 and 44 through its
    calibration, and starts layer 1 at 45. Read as progress, that 85 sent the
    75% notification together with Print Started, and since 75 was then on
    record, 25 and 50 could never fire. So nothing counts while the printer
    reports a layer count but has not started layer 1.

    Without a layer count -- a print whose first frame carried no
    ``total_layer_num``, until the pushall that asks for it is answered
    (#2702) -- the preparation stage says the same thing: before layer 1 the
    A1 mini reported ``stg_cur`` 2, 4, 14 and 1 (bed preheating, calibration,
    homing), and 0 from layer 1 on. -1 and 255 are "no stage". A printer that
    reports neither keeps the old behaviour rather than never notifying.
    """
    if (state.layer_num or 0) < 1:
        if (state.total_layers or 0) > 0:
            return None
        if state.stg_cur not in _NO_PREPARATION_STAGES:
            return None

    progress = state.progress or 0
    current_milestone = 0
    if progress >= 75:
        current_milestone = 75
    elif progress >= 50:
        current_milestone = 50
    elif progress >= 25:
        current_milestone = 25

    if current_milestone > _last_progress_milestone.get(printer_id, 0):
        _last_progress_milestone[printer_id] = current_milestone
        return current_milestone
    return None


def _hms_notify_key(error) -> str:
    """Different faults on the same module/part must notify independently."""
    return (getattr(error, "full_code", "") or f"{error.attr:08X}:{error.code}").upper()


def _hms_errors_to_notify(errors: list, new_error_codes: set[str]) -> list:
    from backend.app.services.hms_errors import fault_counts

    return [error for error in errors if _hms_notify_key(error) in new_error_codes and fault_counts(error)]


def _take_new_hms_faults(printer_id: int, errors: list, print_state: str | None) -> list:
    """Suppress a flickering fault until it clears or the print changes state."""
    now = time.monotonic()
    current = {_hms_notify_key(error) for error in errors}
    seen = _notified_hms_errors.setdefault(printer_id, {})
    forget = _hms_forget_when_gone.setdefault(printer_id, set())
    state = print_state.upper() if print_state else ""
    if state and state != "UNKNOWN":
        if _hms_print_state.get(printer_id, state) != state:
            forget.update(seen)
        _hms_print_state[printer_id] = state
    for key, last_seen in list(seen.items()):
        if key not in current and (key in forget or now - last_seen >= _HMS_CLEAR_GRACE_SECONDS):
            del seen[key]
            forget.discard(key)
    new_keys = current - seen.keys()
    seen.update(dict.fromkeys(current, now))
    if not seen:
        _notified_hms_errors.pop(printer_id, None)
    if not forget:
        _hms_forget_when_gone.pop(printer_id, None)
    return _hms_errors_to_notify(errors, new_keys)


async def on_printer_status_change(printer_id: int, state: PrinterState):
    """Handle printer status changes - broadcast via WebSocket."""
    check_kprofile_status(printer_id, state, spawn_background_task, logging.getLogger(__name__))
    # Connected-edge reconciliation (#1542 follow-up). When the printer
    # transitions disconnected → connected — which covers both PrintOps
    # startup (no prior connection) and a mid-session MQTT reconnect — fire
    # `reconcile_stale_active_prints` exactly once for this connection so
    # any archive still in `status="printing"` that can't actually be
    # running anymore (printer IDLE / different subtask / empty subtask)
    # gets a synthesised PRINT COMPLETE. Without this, a print that
    # finished during a disconnect window + a smart-plug power cycle
    # leaves the .3mf on the SD card and the firmware ghost-replays it on
    # next boot. Reconciliation runs concurrently — it must not block the
    # WebSocket dedup / broadcast logic below, and the connected edge is
    # marked True BEFORE the await so concurrent status updates inside
    # the same connection don't re-trigger reconciliation.
    #
    # Wait for a real push_status before reconciling (#1679): MQTT
    # `_on_connect` broadcasts `state` IMMEDIATELY after the broker accepts
    # the connection, BEFORE `_request_push_all` round-trips. At that
    # instant the `PrinterState` is still on construction defaults — most
    # importantly `state.state == "unknown"` and `state.subtask_name == ""`.
    # If reconcile spawns here, every in-flight archive falls through to
    # the empty-subtask_name trigger and gets synthesised `aborted`, which
    # creates a duplicate archive on the real PRINT COMPLETE and
    # double-counts filament. Gating on `state.state ∉ ("", "unknown")`
    # keeps the #1542 mechanism intact: once the first real push_status
    # updates `state.state` (RUNNING / IDLE / FINISH / …), this handler
    # fires again with the flag still False — reconcile then runs against
    # actual evidence.
    state_known = bool(state.state) and state.state.upper() not in ("", "UNKNOWN")
    if state.connected and state_known and not _printer_reconciled_since_connect.get(printer_id, False):
        _printer_reconciled_since_connect[printer_id] = True
        spawn_background_task(
            reconcile_stale_active_prints(printer_id),
            name=f"reconcile-stale-prints-{printer_id}",
        )
    elif not state.connected and _printer_reconciled_since_connect.get(printer_id, False):
        # Re-arm so the next reconnect triggers reconciliation again.
        _printer_reconciled_since_connect[printer_id] = False

    # Debounce offline notifications. The relay pairs a published offline event with its reconnect.
    prev_connected = _printer_last_connected.get(printer_id)
    _printer_last_connected[printer_id] = state.connected
    if prev_connected is True and not state.connected:
        existing = _printer_offline_notify_tasks.get(printer_id)
        if existing is None or existing.done():
            logging.getLogger(__name__).info(
                "[#1752] Printer %s connected→disconnected edge; scheduling offline notification in %.0fs",
                printer_id,
                _PRINTER_OFFLINE_NOTIFY_DEBOUNCE_SECONDS,
            )
            _printer_offline_notify_tasks[printer_id] = asyncio.create_task(
                _maybe_notify_printer_offline(printer_id),
                name=f"printer-offline-notify-{printer_id}",
            )
    elif state.connected:
        pending = _printer_offline_notify_tasks.pop(printer_id, None)
        if pending is not None and not pending.done():
            logging.getLogger(__name__).info(
                "[#1752] Printer %s reconnected before debounce; cancelling pending offline notification",
                printer_id,
            )
            pending.cancel()
        await _relay_printer_reconnect(printer_id)

    observe_scheduled_pause(printer_id, state, printer_manager)

    # Only broadcast if something meaningful changed (reduce WebSocket spam)
    # Include rounded temperatures to detect meaningful temp changes (within 1 degree)
    temps = state.temperatures or {}
    nozzle_temp = round(temps.get("nozzle", 0))
    bed_temp = round(temps.get("bed", 0))
    nozzle_2_temp = round(temps.get("nozzle_2", 0)) if "nozzle_2" in temps else ""
    chamber_temp = round(temps.get("chamber", 0)) if "chamber" in temps else ""

    # Auto-detect dual-nozzle printers from MQTT temperature data
    if "nozzle_2" in temps and printer_id not in _nozzle_count_updated:
        _nozzle_count_updated.add(printer_id)
        # Update nozzle_count in database
        async with async_session() as db:
            from backend.app.models.printer import Printer

            result = await db.execute(select(Printer).where(Printer.id == printer_id))
            printer = result.scalar_one_or_none()
            if printer and printer.nozzle_count != 2:
                printer.nozzle_count = 2
                await db.commit()
                logging.getLogger(__name__).info(
                    f"Auto-detected dual-nozzle printer {printer_id}, updated nozzle_count=2"
                )

    # Persist the last firmware reported by get_version so dispatch safety
    # decisions remain auditable across reconnects and restarts (#126).
    firmware_version = state.firmware_version
    if firmware_version and _persisted_firmware_versions.get(printer_id) != firmware_version:
        async with async_session() as db:
            from backend.app.models.printer import Printer

            result = await db.execute(select(Printer).where(Printer.id == printer_id))
            printer = result.scalar_one_or_none()
            if printer and printer.firmware_version != firmware_version:
                printer.firmware_version = firmware_version
                await db.commit()
            _persisted_firmware_versions[printer_id] = firmware_version

    # Include target temps for heating phase detection
    bed_target = round(temps.get("bed_target", 0))
    nozzle_target = round(temps.get("nozzle_target", 0))

    # Include tray_now and vt_tray hash so external spool changes trigger broadcasts
    vt_tray_key = hash(str(state.raw_data.get("vt_tray", []))) if state.raw_data else 0
    # Include AMS dry_time and tray state values so drying/slot changes trigger broadcasts
    ams_dry_key = tuple(a.get("dry_time", 0) for a in (state.raw_data.get("ams") or [])) if state.raw_data else ()
    # Include tray states so load/unload transitions (state 11→10) trigger broadcasts (#784)
    ams_tray_key = (
        tuple(
            (t.get("id"), t.get("tray_type", ""), t.get("state"))
            for a in (state.raw_data.get("ams") or [])
            for t in a.get("tray", [])
        )
        if state.raw_data
        else ()
    )
    # Fault-only pushes must reach both WebSocket and notification consumers.
    hms_key = tuple(
        (
            getattr(error, "full_code", ""),
            error.code,
            error.severity,
            getattr(error, "description", None),
            tuple(getattr(error, "actions", None) or []),
            getattr(error, "job_id", None),
        )
        for error in (getattr(state, "hms_errors", None) or [])
    )
    status_key = (
        f"{state.connected}:{state.state}:{state.progress}:{state.layer_num}:"
        f"{state.remaining_time}:{state.speed_level}:{state.subtask_id}:"
        f"{nozzle_temp}:{bed_temp}:{nozzle_2_temp}:{chamber_temp}:"
        f"{state.stg_cur}:{bed_target}:{nozzle_target}:"
        f"{state.cooling_fan_speed}:{state.big_fan1_speed}:{state.big_fan2_speed}:"
        f"{state.chamber_light}:{state.active_extruder}:{state.tray_now}:{vt_tray_key}:"
        f"{ams_dry_key}:{ams_tray_key}:{state.door_open}:{state.ams_filament_backup}:{hms_key}:{machine_status_key(state)}"
    )

    # MQTT relay - publish status (before dedup check - always publish to MQTT)
    try:
        printer_info = printer_manager.get_printer(printer_id)
        if printer_info:
            await mqtt_relay.on_printer_status(printer_id, state, printer_info.name, printer_info.serial_number)
    except Exception:
        pass  # Don't fail status callback if MQTT fails

    if _last_status_broadcast.get(printer_id) == status_key:
        return  # No change, skip WebSocket broadcast

    _last_status_broadcast[printer_id] = status_key

    # Check for progress milestone notifications (25%, 50%, 75%)
    progress = state.progress or 0
    is_printing = state.state in ("RUNNING", "PRINTING")

    if is_printing and progress > 0:
        current_milestone = _progress_milestone_to_notify(printer_id, state)
        if current_milestone is not None:
            try:
                async with async_session() as db:
                    from backend.app.models.printer import Printer

                    result = await db.execute(select(Printer).where(Printer.id == printer_id))
                    printer = result.scalar_one_or_none()
                    printer_name = printer.name if printer else f"Printer {printer_id}"
                    filename = state.subtask_name or state.gcode_file or "Unknown"
                    # remaining_time is in minutes, convert to seconds for notification
                    remaining_time_seconds = state.remaining_time * 60 if state.remaining_time else None

                    # Capture camera snapshot for notification image attachment
                    image_data = await _capture_snapshot_for_notification(
                        printer_id, printer, logging.getLogger(__name__)
                    )

                    await notification_service.on_print_progress(
                        printer_id,
                        printer_name,
                        filename,
                        current_milestone,
                        db,
                        remaining_time_seconds,
                        image_data=image_data,
                    )
            except Exception as e:
                logging.getLogger(__name__).warning(f"Progress milestone notification failed: {e}")
    elif progress < 5:
        # Reset milestone tracking when print restarts or new print begins
        _last_progress_milestone[printer_id] = 0
        _first_layer_notified[printer_id] = False

    # HMS error codes that should not trigger notifications even though they
    # have known descriptions (e.g. user-initiated actions, not real errors).
    _HMS_NOTIFICATION_SUPPRESS = {
        "0500_400E",  # Printing was cancelled (user action, not an error)
    }

    # Check for new HMS errors and send notifications
    current_hms_errors = getattr(state, "hms_errors", []) or []
    new_errors = _take_new_hms_faults(printer_id, current_hms_errors, state.state if state.connected else None)
    if new_errors:
        try:
            async with async_session() as db:
                from backend.app.models.printer import Printer

                result = await db.execute(select(Printer).where(Printer.id == printer_id))
                printer = result.scalar_one_or_none()
                printer_name = printer.name if printer else f"Printer {printer_id}"

                # Format error details for notification
                # Module 0x07 = AMS/Filament, 0x05 = Nozzle, 0x0C = Motion Controller, etc.
                module_names = {
                    0x03: "Print/Task",
                    0x05: "Nozzle/Extruder",
                    0x07: "AMS/Filament",
                    0x0C: "Motion Controller",
                    0x12: "Chamber",
                }

                # Capture camera snapshot once for all error notifications
                error_image_data = await _capture_snapshot_for_notification(
                    printer_id, printer, logging.getLogger(__name__)
                )

                sent_count = 0
                for error in new_errors:
                    module_name = module_names.get(error.module, f"Module 0x{error.module:02X}")
                    # Build short code like "0700_8010"
                    # Mask to 16 bits to handle printers that send larger values
                    error_code_int = int(error.code.replace("0x", ""), 16) if error.code else 0
                    error_code_masked = error_code_int & 0xFFFF
                    short_code = f"{(error.attr >> 16) & 0xFFFF:04X}_{error_code_masked:04X}"

                    # The parser resolves the full manufacturer identifier once.
                    description = error.description
                    if not description or short_code in _HMS_NOTIFICATION_SUPPRESS:
                        continue

                    error_type = f"{module_name} Error"
                    error_detail = description

                    await notification_service.on_printer_error(
                        printer_id, printer_name, error_type, db, error_detail, image_data=error_image_data
                    )
                    sent_count += 1

                if sent_count:
                    logging.getLogger(__name__).info(
                        f"[HMS] Sent notification for {sent_count} error(s) on printer {printer_id}"
                    )

                # Also publish to MQTT relay
                printer_info = printer_manager.get_printer(printer_id)
                if printer_info:
                    errors_data = [
                        {
                            "code": e.code,
                            "attr": e.attr,
                            "module": e.module,
                            "severity": e.severity,
                            "description": e.description,
                            "full_code": e.full_code,
                            "actions": e.actions,
                            "job_id": e.job_id,
                        }
                        for e in new_errors
                    ]
                    await mqtt_relay.on_printer_error(
                        printer_id, printer_info.name, printer_info.serial_number, errors_data
                    )

        except Exception as e:
            logging.getLogger(__name__).warning(f"HMS error notification failed: {e}")

    await ws_manager.send_printer_status(
        printer_id,
        printer_state_to_dict(
            state,
            printer_id,
            printer_manager.get_model(printer_id),
            printer_manager.get_drying_targets(printer_id),
        ),
    )


def _is_bambu_uuid(tray_uuid: str) -> bool:
    """Check if a tray UUID looks like a valid Bambu Lab RFID UUID (non-empty, non-zero)."""
    return bool(tray_uuid) and tray_uuid not in ("", "0" * len(tray_uuid))


def _slot_feeds_print(printer_id: int, ams_id: int, tray_id: int) -> bool:
    """Is this slot the one feeding the printer right now?

    ``tray_now`` names one slot for the whole printer, so on a dual-nozzle
    machine each extruder's own fed slot is asked as well. Only meaningful
    while a print runs; the caller checks that.
    """
    status = printer_manager.get_status(printer_id)
    if status is None:
        return False
    if ams_id == 255:
        global_id = 254 + tray_id
    elif ams_id >= 128:
        global_id = ams_id
    else:
        global_id = ams_id * 4 + tray_id
    if getattr(status, "tray_now", None) == global_id:
        return True
    slots = getattr(status, "extruder_slots", None) or {}
    if any(slot.has_filament and slot.holds(ams_id, tray_id) for slot in slots.values()):
        return True
    # PrintOps retains normalized per-extruder tray IDs from the H2D snow reports.
    return global_id in (getattr(status, "h2d_extruder_snow", None) or {}).values()


async def _unlink_stale_assignments(printer_id: int, ams_data: list, _print_active: bool) -> None:
    """Run inventory cleanup independently of MQTT updates for delayed removal checks."""
    logger = logging.getLogger(__name__)

    from backend.app.utils.color_utils import colors_similar as _colors_similar

    # Auto-unlink spool assignments with stale fingerprints
    try:
        async with get_ams_assignment_lock(printer_id), async_session() as db:
            from sqlalchemy.orm import selectinload

            from backend.app.api.routes.inventory import _find_tray_in_ams_data
            from backend.app.models.spool import Spool as _Spool
            from backend.app.models.spool_assignment import SpoolAssignment as SA
            from backend.app.services.inventory_mode import spoolman_owns_assignments

            assignments = []
            if not await spoolman_owns_assignments(db):
                result = await db.execute(
                    select(SA)
                    .where(SA.printer_id == printer_id)
                    .options(selectinload(SA.spool).selectinload(_Spool.k_profiles))
                )
                assignments = result.scalars().all()
            stale = []
            held: set[tuple] = set()
            for assignment in assignments:
                # External spool assignments (ams_id=255) live in vt_tray, not AMS data
                if assignment.ams_id == 255:
                    ps = printer_manager.get_status(printer_id)
                    vt_tray_raw = ps.raw_data.get("vt_tray", []) if ps else []
                    ext_id = assignment.tray_id + 254  # 0→254, 1→255
                    current_tray = None
                    for vt in vt_tray_raw:
                        if isinstance(vt, dict) and int(vt.get("id", 254)) == ext_id:
                            current_tray = vt
                            break
                    if not current_tray:
                        # vt_tray data may not have arrived yet — keep assignment
                        continue
                else:
                    current_tray = _find_tray_in_ams_data(ams_data, assignment.ams_id, assignment.tray_id)
                hold_key = ("inventory", assignment.ams_id, assignment.tray_id, assignment.spool_id)
                if not current_tray:
                    if not _print_active:
                        if slot_unlink_grace.removal_confirmed(printer_id, hold_key):
                            stale.append(assignment)
                        else:
                            held.add(hold_key)
                    continue
                if _is_bambu_uuid(current_tray.get("tray_uuid", "")):
                    # A Bambu Lab spool is in this slot — check if it's the same spool
                    # that's currently assigned. If yes, keep the assignment (avoids
                    # unnecessary unlink/re-assign/ams_filament_setting cycle that clears
                    # the printer's filament preset on every startup).
                    tray_uuid = current_tray.get("tray_uuid", "")
                    tag_uid = current_tray.get("tag_uid", "")
                    spool = assignment.spool
                    spool_matches = False
                    if spool:
                        if (spool.tray_uuid and spool.tray_uuid.upper() == tray_uuid.upper()) or (
                            spool.tag_uid
                            and tag_uid
                            and tag_uid != "0000000000000000"
                            and spool.tag_uid.upper() == tag_uid.upper()
                        ):
                            spool_matches = True
                    if spool_matches:
                        # Same BL spool still in slot — keep assignment, update fingerprint if needed
                        cur_color = current_tray.get("tray_color", "")
                        cur_type = current_tray.get("tray_type", "")
                        fp_color = assignment.fingerprint_color or ""
                        fp_type = assignment.fingerprint_type or ""
                        if cur_color.upper() != fp_color.upper() or cur_type.upper() != fp_type.upper():
                            assignment.fingerprint_color = cur_color
                            assignment.fingerprint_type = cur_type
                            logger.debug(
                                "Auto-unlink: spool %d AMS%d-T%d — same BL spool, updated fingerprint",
                                assignment.spool_id,
                                assignment.ams_id,
                                assignment.tray_id,
                            )
                        continue
                    # Different BL spool or unrecognized — unlink so auto-assign can match
                    logger.info(
                        "Auto-unlink: spool %d AMS%d-T%d — different Bambu Lab spool detected (uuid=%s)",
                        assignment.spool_id,
                        assignment.ams_id,
                        assignment.tray_id,
                        tray_uuid,
                    )
                    stale.append(assignment)
                else:
                    cur_color = current_tray.get("tray_color", "")
                    cur_type = current_tray.get("tray_type", "")
                    cur_state = current_tray.get("state")
                    fp_color = assignment.fingerprint_color or ""
                    fp_type = assignment.fingerprint_type or ""

                    # Presence bits overrule cached empty states, including AMS-HT;
                    # retain the existing firmware fallback when no bit is present.
                    from backend.app.services.ams_slot_presence import spool_present

                    present = spool_present(current_tray)
                    loaded = present is True or cur_state == 11 or (cur_state not in (9, 10) and cur_type.strip())
                    if (
                        not fp_type.strip()
                        and loaded
                        and assignment.spool
                        and _print_active
                        and _slot_feeds_print(printer_id, assignment.ams_id, assignment.tray_id)
                    ):
                        continue
                    if not fp_type.strip() and loaded and assignment.spool:
                        try:
                            from backend.app.api.routes.inventory import (
                                apply_spool_to_slot_via_mqtt,
                            )

                            configured = await apply_spool_to_slot_via_mqtt(
                                db=db,
                                current_user=None,
                                orca_generic_fallback=False,
                                spool=assignment.spool,
                                printer_id=printer_id,
                                ams_id=assignment.ams_id,
                                tray_id=assignment.tray_id,
                                current_tray_info_idx=current_tray.get("tray_info_idx", ""),
                                current_tray_type=cur_type,
                                current_tray_sub_brands=current_tray.get("tray_sub_brands", ""),
                                assignment=assignment,
                            )
                            if configured:
                                logger.info(
                                    "SpoolBuddy pre-config applied on insert: spool %d → printer %d AMS%d-T%d",
                                    assignment.spool_id,
                                    printer_id,
                                    assignment.ams_id,
                                    assignment.tray_id,
                                )
                        except Exception:
                            configured = None
                            logger.exception(
                                "Pre-config apply failed for spool %d on printer %d AMS%d-T%d",
                                assignment.spool_id,
                                printer_id,
                                assignment.ams_id,
                                assignment.tray_id,
                            )
                        if (
                            configured is not False
                            and not (assignment.fingerprint_type or "").strip()
                            and cur_type.strip()
                            and cur_color.strip()
                        ):
                            # Keep a usable report when a command may have been partially applied.
                            assignment.fingerprint_color, assignment.fingerprint_type = cur_color, cur_type
                        continue

                    if not _colors_similar(cur_color, fp_color) or cur_type.upper() != fp_type.upper():
                        if not cur_color.strip() and not cur_type.strip():
                            if _print_active or present is True:
                                continue
                            if not slot_unlink_grace.removal_confirmed(printer_id, hold_key):
                                held.add(hold_key)
                                continue
                        spool = assignment.spool
                        if spool:
                            spool_color = (spool.rgba or "FFFFFFFF").upper()
                            spool_types = await expected_spool_protocol_types(db, spool)
                            same_type = printer_filament_type(cur_type).upper() in spool_types
                            if _colors_similar(cur_color, spool_color) and same_type:
                                logger.info(
                                    "Auto-unlink: spool %d AMS%d-T%d — fingerprint mismatch but tray matches spool, updating fp",
                                    assignment.spool_id,
                                    assignment.ams_id,
                                    assignment.tray_id,
                                )
                                assignment.fingerprint_color = cur_color
                                assignment.fingerprint_type = cur_type
                                continue
                        logger.info(
                            "Auto-unlink: spool %d AMS%d-T%d — fingerprint mismatch (cur=%s/%s fp=%s/%s spool=%s/%s)",
                            assignment.spool_id,
                            assignment.ams_id,
                            assignment.tray_id,
                            cur_color,
                            cur_type,
                            fp_color,
                            fp_type,
                            spool.rgba if spool else "?",
                            spool.material if spool else "?",
                        )
                        stale.append(assignment)  # Spool changed
            slot_unlink_grace.settle(printer_id, "inventory", held)
            unlinked_slots = [(a.ams_id, a.tray_id) for a in stale]
            for a in stale:
                await db.delete(a)
            if stale:
                logger.info("Auto-unlinked %d stale spool assignments for printer %d", len(stale), printer_id)
            # Commit any changes (stale deletions and/or fingerprint updates)
            await db.commit()
            for ams_id, tray_id in unlinked_slots:
                await ws_manager.broadcast(
                    {"type": "spool_assignment_changed", "printer_id": printer_id, "ams_id": ams_id, "tray_id": tray_id}
                )
    except Exception as e:
        logger.warning("Spool assignment cleanup failed: %s", e, exc_info=True)


async def _expire_spoolman_empty_slots(printer_id: int, ams_data: list, printing_now: bool) -> None:
    """Recheck local assignments without depending on a reachable Spoolman server."""
    from backend.app.api.routes.settings import get_setting
    from backend.app.services.spoolman_slot_cleanup import expire_empty_slots

    try:
        async with get_ams_assignment_lock(printer_id), async_session() as db:
            enabled = await get_setting(db, "spoolman_enabled")
            sync_mode = await get_setting(db, "spoolman_sync_mode")
            if not enabled or enabled.lower() != "true" or (sync_mode and sync_mode != "auto"):
                return
            expired = await expire_empty_slots(db, printer_id, ams_data, printing_now)
            await db.commit()
        for ams_id, tray_id in expired:
            await ws_manager.broadcast(
                {"type": "spool_assignment_changed", "printer_id": printer_id, "ams_id": ams_id, "tray_id": tray_id}
            )
    except Exception:
        logging.getLogger(__name__).exception("Spoolman slot removal check failed for printer %s", printer_id)


async def _recheck_held_unlinks(printer_id: int) -> None:
    """Confirm held removals against current connected state, even without another push."""
    from backend.app.services.usage_tracker import _active_sessions

    state = printer_manager.get_status(printer_id)
    if state is None or not state.connected:
        return
    raw = state.raw_data.get("ams")
    ams_data = raw.get("ams", []) if isinstance(raw, dict) else raw if isinstance(raw, list) else []
    printing = printer_id in _active_sessions or print_provenance.printer_is_printing(state)
    await _unlink_stale_assignments(printer_id, ams_data, printing)
    await _expire_spoolman_empty_slots(printer_id, ams_data, printing)


slot_unlink_grace.set_recheck(_recheck_held_unlinks)


async def on_assignment_verified(printer_id: int, ams_id: int, tray_id: int, verified: bool, detail: dict):
    """Report the printer's observed slot configuration through the existing event channel."""
    info = printer_manager.get_printer(printer_id)
    if ams_id == 255:
        slot = f"Ext {tray_id + 1}"
    elif ams_id >= 128:
        slot = f"AMS HT {ams_id - 127}"
    else:
        slot = f"AMS {chr(65 + ams_id)}{tray_id + 1}"
    await ws_manager.broadcast(
        {
            "type": "spool_assignment_verified",
            "printer_id": printer_id,
            "printer_name": info.name if info else f"Printer {printer_id}",
            "ams_id": ams_id,
            "tray_id": tray_id,
            "slot": slot,
            "verified": verified,
            "kprofile_applied": detail.get("kprofile_applied"),
        }
    )


async def on_ams_change(printer_id: int, ams_data: list):
    """Handle AMS data changes - sync to Spoolman if enabled and auto mode."""
    logger = logging.getLogger(__name__)

    # Snapshot BEFORE any await: if a print is active, skip weight sync later.
    # on_print_complete may pop _active_sessions during our awaits (#880).
    _print_active = printer_is_charging(printer_id) or print_provenance.printer_is_printing(
        printer_manager.get_status(printer_id)
    )

    # MQTT relay - publish AMS change
    try:
        printer_info = printer_manager.get_printer(printer_id)
        if printer_info:
            await mqtt_relay.on_ams_change(printer_id, printer_info.name, printer_info.serial_number, ams_data)
    except Exception:
        pass  # Don't fail AMS callback if MQTT fails

    # Broadcast AMS change via WebSocket (bypasses status_key deduplication)
    # This ensures frontend gets immediate updates when AMS slots are configured
    try:
        state = printer_manager.get_status(printer_id)
        if state:
            logger.info("[Printer %s] Broadcasting AMS change via WebSocket", printer_id)
            await ws_manager.send_printer_status(
                printer_id,
                printer_state_to_dict(
                    state,
                    printer_id,
                    printer_manager.get_model(printer_id),
                    printer_manager.get_drying_targets(printer_id),
                ),
            )
    except Exception as e:
        logger.warning("Failed to broadcast AMS change for printer %s: %s", printer_id, e)

    await _unlink_stale_assignments(printer_id, ams_data, _print_active)

    rfid_assigned: list[tuple[int, tuple[int, int, int]]] = []
    await _expire_spoolman_empty_slots(printer_id, ams_data, _print_active)

    # Auto-manage inventory spools from AMS tray data (skip if Spoolman manages AMS).
    # Serialised per-printer via services/ams_assignment_lock: MQTT bursts can deliver
    # two AMS pushes ~30 ms apart, and without the lock both callbacks read
    # "no existing assignment" for the same (printer, ams, tray) and race to
    # INSERT, hitting the spool_assignment_printer_id_ams_id_tray_id_key
    # unique constraint on Postgres. SQLite's WAL serialises writes so the
    # bug stayed latent there. See services/ams_assignment_lock for details.
    try:
        async with get_ams_assignment_lock(printer_id), async_session() as db:
            from sqlalchemy.orm import selectinload

            from backend.app.api.routes.settings import get_setting
            from backend.app.models.spool import Spool
            from backend.app.models.spool_assignment import SpoolAssignment as SA
            from backend.app.services.spool_tag_matcher import (
                auto_assign_spool,
                create_spool_from_tray,
                find_matching_untagged_spool,
                get_spool_by_tag,
                is_bambu_tag,
                is_valid_tag,
                link_tag_to_inventory_spool,
                tag_belongs_to_archived_spool,
            )

            _spoolman_on = await get_setting(db, "spoolman_enabled")
            _auto_add_raw = await get_setting(db, "auto_add_unknown_rfid")
            _auto_add_unknown = _auto_add_raw is None or _auto_add_raw.lower() == "true"
            if not _spoolman_on or _spoolman_on.lower() != "true":
                for ams_unit in ams_data:
                    if not isinstance(ams_unit, dict):
                        continue
                    ams_id = int(ams_unit.get("id", 0))
                    for tray in ams_unit.get("tray", []):
                        if not isinstance(tray, dict):
                            continue
                        tray_id = int(tray.get("id", 0))
                        tag_uid = tray.get("tag_uid", "")
                        tray_uuid = tray.get("tray_uuid", "")
                        tray_info_idx = tray.get("tray_info_idx", "")
                        if not tray.get("tray_type"):
                            # Slot reported empty — drop any cached unknown-tag
                            # broadcast so reinserting the same spool re-prompts.
                            _clear_unknown_tag_dedup(printer_id, ams_id, tray_id)
                            continue  # Empty slot
                        # Check if assignment already exists for this slot
                        existing = await db.execute(
                            select(SA)
                            .options(selectinload(SA.spool).selectinload(Spool.k_profiles))
                            .where(SA.printer_id == printer_id, SA.ams_id == ams_id, SA.tray_id == tray_id)
                        )
                        existing_assignment = existing.scalar_one_or_none()
                        if existing_assignment:
                            # Sync spool weight_used from AMS remain — only INCREASE, never decrease.
                            # The AMS remain% is low-resolution (integer %, i.e. 10g steps for 1kg spool)
                            # and must not overwrite precise values from the usage tracker (3MF/G-code).
                            # Skip during active prints: the usage tracker handles deduction
                            # precisely via 3MF data on print completion. Without this guard the
                            # AMS remain% SET and the usage tracker ADD both fire from the same
                            # MQTT message, doubling the deduction (#880).
                            if _print_active:
                                continue
                            if await sync_automatic_weight(db, existing_assignment, tray):
                                await ws_manager.broadcast({"type": "inventory_changed"})

                            # The idle drift check restores only a lost selection.
                            # Keep an intentional real profile or Default on AMS changes.
                            continue

                        if is_bambu_tag(tag_uid, tray_uuid, tray_info_idx):
                            # BL spool with RFID tag: auto-match → inventory match → auto-create
                            spool = await get_spool_by_tag(db, tag_uid, tray_uuid)
                            known_by_tag = spool is not None
                            if not spool and await tag_belongs_to_archived_spool(db, tag_uid, tray_uuid):
                                # An archived spool still in the AMS: the slot
                                # stays free rather than adopting its tag.
                                continue
                            if not spool:
                                # Try matching an untagged inventory spool (same material/color)
                                spool = await find_matching_untagged_spool(db, tray)
                                if spool:
                                    await link_tag_to_inventory_spool(db, spool, tray)
                                elif _auto_add_unknown:
                                    spool = await create_spool_from_tray(db, tray)
                                else:
                                    # Auto-add disabled: surface the slot so the
                                    # user can add it manually via the UI.
                                    await _broadcast_unknown_tag(
                                        printer_id=printer_id,
                                        ams_id=ams_id,
                                        tray_id=tray_id,
                                        tag_uid=tag_uid,
                                        tray_uuid=tray_uuid,
                                        tray_type=tray.get("tray_type"),
                                        tray_color=tray.get("tray_color"),
                                        tray_sub_brands=tray.get("tray_sub_brands"),
                                        tray_count=len(ams_unit.get("tray", [])),
                                    )
                                    continue
                            # Slot matched (existing tag, untagged inventory
                            # match, or freshly auto-created spool) — drop any
                            # stale dedup so a future tag swap re-prompts.
                            _clear_unknown_tag_dedup(printer_id, ams_id, tray_id)
                            await auto_assign_spool(
                                printer_id,
                                ams_id,
                                tray_id,
                                spool,
                                printer_manager,
                                db,
                                tray_info_idx=tray_info_idx,
                            )
                            await db.commit()
                            if known_by_tag:
                                rfid_assigned.append((spool.id, (printer_id, ams_id, tray_id)))
                            await ws_manager.broadcast(
                                {
                                    "type": "spool_auto_assigned",
                                    "printer_id": printer_id,
                                    "ams_id": ams_id,
                                    "tray_id": tray_id,
                                    "spool_id": spool.id,
                                }
                            )
                            logger.info(
                                "RFID auto-assigned spool %d to printer %d AMS%d-T%d",
                                spool.id,
                                printer_id,
                                ams_id,
                                tray_id,
                            )
                        elif is_valid_tag(tag_uid, tray_uuid) and not await tag_belongs_to_archived_spool(
                            db, tag_uid, tray_uuid
                        ):
                            # Non-BL spool with some tag — let user choose (not
                            # an archived one's, whose slot stays free)
                            await _broadcast_unknown_tag(
                                printer_id=printer_id,
                                ams_id=ams_id,
                                tray_id=tray_id,
                                tag_uid=tag_uid,
                                tray_uuid=tray_uuid,
                                tray_type=tray.get("tray_type"),
                                tray_color=tray.get("tray_color"),
                                tray_sub_brands=tray.get("tray_sub_brands"),
                                tray_count=len(ams_unit.get("tray", [])),
                            )
                        # No-tag slots (generic non-RFID filament) are left alone:
                        # nothing to identify, prompting "+ Add" would just create
                        # ghost spools with empty tags on every confirm.
    except Exception as e:
        logger.warning("RFID spool auto-assign failed: %s", e, exc_info=True)

    if rfid_assigned:
        from backend.app.services.spool_relocation import INTERNAL, release_other_slots

        for spool_id, slot in rfid_assigned:
            try:
                await release_other_slots(INTERNAL, spool_id, slot)
            except Exception as exc:
                logger.warning("Releasing spool %s from its other slots failed: %s", spool_id, exc, exc_info=True)

    try:
        async with async_session() as db:
            from backend.app.api.routes.settings import get_setting
            from backend.app.models.printer import Printer

            # Check if Spoolman is enabled
            spoolman_enabled = await get_setting(db, "spoolman_enabled")
            if not spoolman_enabled or spoolman_enabled.lower() != "true":
                return

            # Check sync mode
            sync_mode = await get_setting(db, "spoolman_sync_mode")
            if sync_mode and sync_mode != "auto":
                return  # Only sync on auto mode

            _auto_add_raw_sm = await get_setting(db, "auto_add_unknown_rfid")
            auto_add_unknown_rfid = _auto_add_raw_sm is None or _auto_add_raw_sm.lower() == "true"

            # `spoolman_disable_weight_sync` is deprecated (#1119) — weight is now
            # always owned by per-print tracking, never by AMS auto-sync. The
            # setting is still read by the settings UI for backwards compat but
            # has no effect on the sync path here.

            # Get Spoolman URL
            spoolman_url = await get_setting(db, "spoolman_url")
            if not spoolman_url:
                return

            # Get or create Spoolman client
            client = await get_spoolman_client()
            if not client:
                try:
                    client = await init_spoolman_client(spoolman_url)
                except ValueError as exc:
                    logger.warning("Spoolman URL %r rejected by SSRF guard: %s", spoolman_url, exc)
                    return

            # Check if Spoolman is reachable
            if not await client.health_check():
                logger.warning("Spoolman not reachable at %s", spoolman_url)
                return

            # Get printer name for location
            result = await db.execute(select(Printer).where(Printer.id == printer_id))
            printer = result.scalar_one_or_none()
            printer_name = printer.name if printer else f"Printer {printer_id}"

            # OPTIMIZATION: Fetch all spools once before processing trays
            # This eliminates redundant API calls (one per tray) when syncing multiple trays
            logger.debug("[Printer %s] Fetching spools cache for AMS sync...", printer_id)
            try:
                cached_spools = await client.get_spools()
                logger.debug("[Printer %s] Cached %d spools for batch sync", printer_id, len(cached_spools))
            except Exception as e:
                logger.error(
                    "[Printer %s] Failed to fetch spools cache after retries, aborting AMS sync: %s",
                    printer_id,
                    e,
                )
                return

            from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment

            # Internal assignments are intentionally not a fallback here. They
            # can now survive in this slot while Spoolman mode is active.
            inventory_weights: dict[tuple[int, int], float] = {}

            # Load existing Spoolman slot assignments for the no-RFID fallback path
            spoolman_slot_map: dict[tuple[int, int], int] = {}
            slot_map_read = False
            try:
                slot_result = await db.execute(
                    select(SpoolmanSlotAssignment).where(SpoolmanSlotAssignment.printer_id == printer_id)
                )
                for slot in slot_result.scalars().all():
                    spoolman_slot_map[(slot.ams_id, slot.tray_id)] = slot.spoolman_spool_id
                slot_map_read = True
            except Exception as e:
                logger.warning("Could not load Spoolman slot assignments for printer %s: %s", printer_id, e)

            # Sync each AMS tray and collect slot changes for DB persistence
            synced = 0
            slot_changes: list[tuple[int, int, int]] = []  # (ams_id, tray_id, spoolman_spool_id) to upsert
            preset_candidates = []
            for ams_unit in ams_data:
                if not isinstance(ams_unit, dict):
                    continue
                ams_id = int(ams_unit.get("id", 0))
                trays = ams_unit.get("tray", [])

                for tray_data in trays:
                    if not isinstance(tray_data, dict):
                        continue
                    tray_id_raw = int(tray_data.get("id", 0))
                    tray = client.parse_ams_tray(ams_id, tray_data)
                    if not tray:
                        # Empty tray slot — record for local assignment cleanup
                        # and drop any cached unknown-tag broadcast so a
                        # reinserted spool re-prompts.
                        # Local cleanup ran before sync and holds transient empty reports.
                        _clear_unknown_tag_dedup(printer_id, ams_id, tray_id_raw)
                        continue

                    spool_tag = (
                        tray.tray_uuid
                        if tray.tray_uuid and tray.tray_uuid != "00000000000000000000000000000000"
                        else tray.tag_uid
                    )

                    # Provide the hint only when no RFID is available
                    hint = spoolman_slot_map.get((ams_id, tray.tray_id)) if not spool_tag else None

                    try:
                        inv_remaining = inventory_weights.get((ams_id, tray.tray_id))
                        result = await client.sync_ams_tray(
                            tray,
                            printer_name,
                            db=db,
                            # Per-print tracking is the only weight writer (#1119).
                            # AMS auto-sync still maintains spool metadata / slot
                            # assignments but no longer touches remaining_weight.
                            disable_weight_sync=True,
                            cached_spools=cached_spools,
                            inventory_remaining=inv_remaining,
                            spoolman_spool_id_hint=hint,
                            auto_add_unknown_rfid=auto_add_unknown_rfid,
                        )
                        if result is None and spool_tag and not auto_add_unknown_rfid:
                            # Spoolman skipped auto-create per user setting — surface
                            # the slot so the UI can offer "+ Add to inventory".
                            await _broadcast_unknown_tag(
                                printer_id=printer_id,
                                ams_id=ams_id,
                                tray_id=tray.tray_id,
                                tag_uid=tray.tag_uid or "",
                                tray_uuid=tray.tray_uuid or "",
                                tray_type=tray.tray_type,
                                tray_color=tray.tray_color,
                                tray_sub_brands=tray.tray_sub_brands,
                                tray_count=len(trays),
                            )
                        elif result:
                            _clear_unknown_tag_dedup(printer_id, ams_id, tray.tray_id)
                        if result:
                            synced += 1
                            if result.get("id"):
                                slot_changes.append((ams_id, tray.tray_id, result["id"]))
                                # If a new spool was created, add it to the cache
                                # so subsequent trays can find it if they reference the same tag
                                spool_exists = any(s.get("id") == result["id"] for s in cached_spools)
                                if not spool_exists:
                                    cached_spools.append(result)
                                    logger.debug(
                                        "[Printer %s] Added newly created spool %s to cache",
                                        printer_id,
                                        result["id"],
                                    )
                                preset_candidates.append((printer_id, ams_id, tray.tray_id, result, tray))
                    except Exception as e:
                        logger.error("Error syncing AMS %s tray %s: %s", ams_id, tray.tray_id, e)

            if synced > 0:
                logger.info("Auto-synced %s AMS trays to Spoolman for printer %s", synced, printer_id)

            # Persist slot assignment changes to the local table
            if slot_changes:
                try:
                    await write_slot_results(
                        db,
                        {(printer_id, a, t): spool_id for (a, t), spool_id in spoolman_slot_map.items()}
                        if slot_map_read
                        else None,
                        [(printer_id, a, t, spool_id) for a, t, spool_id in slot_changes],
                        [],
                    )
                    await refresh_synced_presets(db, preset_candidates, reconcile=True)
                except Exception as e:
                    await db.rollback()
                    logger.error("Error persisting Spoolman slot assignments for printer %s: %s", printer_id, e)

    except Exception as e:
        logging.getLogger(__name__).error("Spoolman AMS sync failed for printer %s: %s", printer_id, e)


async def _capture_snapshot_for_notification(printer_id: int, printer, logger) -> bytes | None:
    """Capture a camera snapshot for notification image attachment.

    Returns JPEG bytes (max 2.5MB) or None if capture fails or is unavailable.
    Uses: external camera > buffered frame > fresh capture.
    """
    if not printer:
        return None

    try:
        from backend.app.api.routes.settings import get_setting

        async with async_session() as db:
            capture_enabled = await get_setting(db, "capture_finish_photo")

        if capture_enabled is not None and capture_enabled.lower() != "true":
            return None

        external_source = None
        # Try external camera first
        if printer.external_camera_enabled and printer.external_camera_url:
            external_source = (printer.external_camera_type or "mjpeg", printer.external_camera_url)
            logger.info("[SNAPSHOT] Capturing from external camera for printer %s", printer_id)
            from backend.app.services.external_camera import capture_frame

            frame_data = await capture_frame(
                printer.external_camera_url,
                printer.external_camera_type or "mjpeg",
                snapshot_url=printer.external_camera_snapshot_url,
                printer_id=printer_id,
            )
            if frame_data and len(frame_data) <= 2_500_000:
                logger.info("[SNAPSHOT] External camera frame: %s bytes", len(frame_data))
                return _apply_camera_rotation(frame_data, printer, logger)

        # Try buffered frame from active stream
        from backend.app.api.routes.camera import live_frame_for_capture

        watched, buffered_frame = await live_frame_for_capture(printer_id, external_source=external_source)
        if watched:
            if buffered_frame and len(buffered_frame) <= 2_500_000:
                logger.info("[SNAPSHOT] Using buffered frame for printer %s: %s bytes", printer_id, len(buffered_frame))
                return _apply_camera_rotation(buffered_frame, printer, logger)
            return None

        # Fresh capture from printer camera
        logger.info("[SNAPSHOT] Capturing fresh frame for printer %s", printer_id)
        from backend.app.services.camera import capture_camera_frame_bytes

        frame_data = await capture_camera_frame_bytes(
            printer.ip_address, printer.access_code, printer.model, timeout=15
        )
        if frame_data and len(frame_data) <= 2_500_000:
            logger.info("[SNAPSHOT] Fresh camera frame: %s bytes", len(frame_data))
            return _apply_camera_rotation(frame_data, printer, logger)

    except Exception as e:
        logger.warning("[SNAPSHOT] Failed to capture snapshot for printer %s: %s", printer_id, e)

    return None


def _apply_camera_rotation(image_data: bytes, printer, logger) -> bytes:
    """Apply camera rotation to snapshot image if configured."""
    from backend.app.services.camera import apply_camera_rotation

    return apply_camera_rotation(image_data, getattr(printer, "camera_rotation", 0), logger)


def _start_estimated_time(archive, printer_id):
    from backend.app.services.archive_plate_estimates import archive_run_estimate

    selected = _get_start_plate_id(printer_id, archive.id) or archive.plate_id
    seconds, _ = archive_run_estimate(archive, selected)
    return seconds


async def _send_print_start_notification(
    printer_id: int,
    data: dict,
    archive_data: dict | None = None,
    logger=None,
):
    """Helper to send print start notification with optional archive data."""
    if logger is None:
        logger = logging.getLogger(__name__)

    try:
        async with async_session() as db:
            from backend.app.models.printer import Printer

            result = await db.execute(select(Printer).where(Printer.id == printer_id))
            printer = result.scalar_one_or_none()
            printer_name = printer.name if printer else f"Printer {printer_id}"

            # Capture camera snapshot for notification image attachment
            image_data = await _capture_snapshot_for_notification(printer_id, printer, logger)
            if image_data:
                if archive_data is None:
                    archive_data = {}
                archive_data["image_data"] = image_data

            await notification_service.on_print_start(printer_id, printer_name, data, db, archive_data=archive_data)

            # Send user-specific email notification for print start
            if archive_data and archive_data.get("created_by_id"):
                await notification_service.send_user_print_email(
                    event_type="user_print_start",
                    created_by_id=archive_data["created_by_id"],
                    printer_name=printer_name,
                    filename=data.get("subtask_name") or data.get("filename", "Unknown"),
                    db=db,
                )
    except Exception as e:
        logger.warning("Notification on_print_start failed: %s", e)


async def _dispatch_user_print_email(
    status: str,
    created_by_id: int | None,
    printer_name: str,
    filename: str,
    db,
) -> None:
    """Send a user-specific print-completion email based on print status.

    Maps the normalised print status to the correct event type and delegates
    to :meth:`NotificationService.send_user_print_email`.  A single helper
    avoids duplicating the ``if status == "completed" / elif "failed" / elif
    "stopped"`` dispatch block at every call site.

    Does nothing if *created_by_id* is ``None``.
    """
    if created_by_id is None:
        return
    if status == "completed":
        event_type = "user_print_complete"
    elif status == "failed":
        event_type = "user_print_failed"
    elif status in ("stopped", "aborted", "cancelled"):
        event_type = "user_print_stopped"
    else:
        return
    await notification_service.send_user_print_email(
        event_type=event_type,
        created_by_id=created_by_id,
        printer_name=printer_name,
        filename=filename,
        db=db,
    )


def _load_objects_from_archive(archive, printer_id: int, logger) -> None:
    """Extract printable objects from an archive's 3MF file and store in printer state."""
    try:
        from backend.app.services.archive import extract_printable_objects_from_3mf

        client = printer_manager.get_client(printer_id)
        if not client:
            return

        file_path = app_settings.base_dir / archive.file_path
        if file_path.is_file() and str(file_path).endswith(".3mf"):
            with open(file_path, "rb") as f:
                threemf_data = f.read()
            printable_objects, bbox_all = extract_printable_objects_from_3mf(
                threemf_data,
                plate_number=resolve_plate_id(client.state),
                include_positions=True,
            )
            if printable_objects:
                client.state.printable_objects = printable_objects
                client.state.printable_objects_bbox_all = bbox_all
                client.state.skipped_objects = []
                logger.info("Loaded %s printable objects for printer %s", len(printable_objects), printer_id)
    except Exception as e:
        logger.debug("Failed to extract printable objects from archive: %s", e)


async def _store_start_tracking(printer_id, archive, db, data, spoolman_owns_print, logger):
    """Capture usage evidence and schedule the first full-print cost estimate."""
    archive_id, file_path = archive.id, archive.file_path
    mapping = _get_start_ams_mapping(data, printer_id, archive_id)
    plate_id = _get_start_plate_id(printer_id, archive_id)
    try:
        await _store_spoolman_print_data(
            printer_id,
            archive_id,
            file_path,
            db,
            printer_manager,
            ams_mapping=mapping,
            plate_id=plate_id,
            spoolman_owns_usage=spoolman_owns_print,
        )
    except Exception as exc:
        logger.warning("[SPOOLMAN] Failed to store tracking data: %s", exc)
    if file_path:
        schedule_archive_cost_estimate(
            printer_id,
            archive_id,
            printer_manager,
            ams_mapping=mapping,
            plate_id=plate_id,
            session_factory=async_session,
        )


async def _ignore_internal_printer_job(printer_id: int, data: dict, phase: str) -> bool:
    from backend.app.services.printer_job_identity import ignore_internal_event

    return await ignore_internal_event(
        printer_id,
        data,
        phase,
        expected=_expected_prints,
        registered_at=_expected_print_registered_at,
        ttl=_EXPECTED_PRINT_TTL_SECONDS,
        active=_active_prints,
        session_factory=async_session,
    )


@clear_state_if_printer_deleted
async def on_print_start(printer_id: int, data: dict):
    """Archive and record the start while the originating printer still exists."""
    from backend.app.core.printer_lifecycle import lock_existing_printer, printer_exists

    logger = logging.getLogger(__name__)
    detected_at = datetime.now(timezone.utc)
    async with async_session() as db:
        if not await printer_exists(db, printer_id):
            return
    if await _ignore_internal_printer_job(printer_id, data, "start"):
        return
    logger.info("[CALLBACK] on_print_start called for printer %s, data keys: %s", printer_id, list(data.keys()))

    # Clear any stale user-stopped flag from previous print cycles
    _user_stopped_printers.discard(printer_id)
    # Consecutive jobs may never report idle progress below five percent.
    _last_progress_milestone[printer_id] = 0
    _first_layer_notified[printer_id] = False

    # #1721: drop any leftover pre-captured finish frame from a prior print
    # so a never-consumed cache entry can't bleed into the new print's photo.
    _stage22_finish_frames.pop(printer_id, None)
    _stage22_finish_in_flight.pop(printer_id, None)

    # Cancel any active bed cooldown waiter for this printer
    if _bed_cool_waiters.pop(printer_id, None):
        logger.info("[BED-COOL] Cancelled bed cooldown waiter for printer %s (new print started)", printer_id)

    # Clear cached cover images so the new print's thumbnail is fetched fresh
    from backend.app.api.routes.printers import clear_cover_cache

    clear_cover_cache(printer_id)

    await ws_manager.send_print_start(printer_id, data)

    # Notify when the print-start AMS mapping references tray slots without spool assignments.
    await notify_missing_spool_assignments_on_print_start(printer_id, data, logger)

    # MQTT relay - publish print start
    try:
        printer_info = printer_manager.get_printer(printer_id)
        if printer_info:
            await mqtt_relay.on_print_start(
                printer_id,
                printer_info.name,
                printer_info.serial_number,
                data.get("filename", ""),
                data.get("subtask_name", ""),
            )
    except Exception:
        pass  # Don't fail print start callback if MQTT fails

    # Capture attribution evidence and restart-stable ownership for both modes.
    spoolman_owns_print: bool | None = None
    try:
        async with async_session() as db:
            if not await lock_existing_printer(db, printer_id):
                return
            spoolman_owns_print = await print_provenance.capture_print_start(printer_id, data, printer_manager, db)
    except Exception as e:
        logger.warning("Usage tracker on_print_start failed: %s", e)
    # Track if notification was sent (to avoid sending twice)
    notification_sent = False
    # Smart plug automation: turn on plug when print starts
    try:
        async with async_session() as db:
            await smart_plug_manager.on_print_start(printer_id, db)
    except Exception as e:
        logger.warning("Smart plug on_print_start failed: %s", e)

    async with async_session() as db:
        from backend.app.api.routes.settings import get_setting
        from backend.app.models.printer import Printer
        from backend.app.services.bambu_ftp import list_files_async

        result = await db.execute(select(Printer).where(Printer.id == printer_id))
        printer = result.scalar_one_or_none()

        if printer is None:
            return
        await check_print_start_plate(
            printer_id,
            printer,
            db,
            logger,
            printer_manager=printer_manager,
            ws_manager=ws_manager,
            notification_service=notification_service,
            _capture_snapshot_for_notification=_capture_snapshot_for_notification,
        )
        if not await printer_exists(db, printer_id):
            return

        from backend.app.services.print_completion_identity import _event_subtask_id
        from backend.app.services.running_print_archive import find_open_print

        filename = data.get("filename", "")
        subtask_name = data.get("subtask_name", "")
        subtask_id = _event_subtask_id(data)
        expected_keys = expected_print_keys(printer_id, filename, subtask_name)
        has_expected = any(key in _expected_prints for key in expected_keys)
        if subtask_id and not has_expected:
            running_archive, run = await find_open_print(db, printer_id, subtask_id)
            if run is not None:
                _bind_active_print(printer_id, running_archive.id, running_archive.filename, filename, subtask_name)
                _load_objects_from_archive(running_archive, printer_id, logger)
                if run.energy_start_kwh is None:
                    await _record_energy_start(running_archive, printer_id, db, context="run-resume", run=run)
                return

        global_auto_archive = await get_setting(db, "auto_archive")
        global_archiving = global_auto_archive is None or global_auto_archive.lower() == "true"
        archives_prints = printer.auto_archive and global_archiving
        if not archives_prints:
            # Keep tracking prints already dispatched by PrintOps.
            if not has_expected:
                # No expected print — truly external print (started from slicer/touchscreen)
                setting = f"auto-archive for printer {printer_id}" if global_archiving else "global auto-archive"
                logger.info("[CALLBACK] Skipping archive of external print: %s is disabled", setting)
                if not notification_sent:
                    await _send_print_start_notification(printer_id, data, logger=logger)
                return
            else:
                logger.info("[CALLBACK] auto_archive disabled but expected print found — promoting archive")

        logger.info("[CALLBACK] Print start detected - filename: %s, subtask: %s", filename, subtask_name)

        if not filename and not subtask_name:
            # Send notification without archive data (no filename)
            logger.info("[CALLBACK] Skipping archive - no filename or subtask_name")
            if not notification_sent:
                await _send_print_start_notification(printer_id, data, logger=logger)
            return

        expected_archive_id, fallback_creator = _consume_expected_print(printer_id, expected_keys)

        if expected_archive_id:
            # This is a reprint/scheduled print - use existing archive, don't create new one
            logger.info("Using expected archive %s for print (skipping duplicate)", expected_archive_id)
            from backend.app.models.archive import PrintArchive

            if not await lock_existing_printer(db, printer_id):
                return
            result = await db.execute(
                select(PrintArchive).where(PrintArchive.id == expected_archive_id, PrintArchive.deleted_at.is_(None))
            )
            archive = result.scalar_one_or_none()

            if archive:
                # Update archive status to printing
                archive.status = "printing"
                archive.started_at = detected_at
                archive.energy_start_kwh = archive.energy_start_plug_id = None
                from backend.app.services.print_confirmation import reset_current_outcome

                reset_current_outcome(archive)

                from backend.app.services.archive_timelapse import remove_reprint_video, reset_for_reprint

                stale_video = await reset_for_reprint(
                    archive, _get_start_plate_id(printer_id, expected_archive_id), base_dir=app_settings.base_dir
                )
                # Persist a restart-stable id so a later restart resumes this
                # archive by subtask_id instead of name-matching + duplicating
                # it (#1485). The printer often hasn't echoed subtask_id back
                # this soon after dispatch, so fall back to the id PrintOps
                # minted when it sent the print command. Scoped to this
                # expected-print branch on purpose: an expected match means
                # PrintOps dispatched this exact print in this process, so the
                # client's last-dispatch id genuinely belongs to it — using it
                # for an externally-started print could mis-tag the archive.
                effective_subtask_id = subtask_id
                if not effective_subtask_id:
                    _client = printer_manager.get_client(printer_id)
                    _dispatched = getattr(_client, "last_dispatch_subtask_id", None) if _client else None
                    if _dispatched:
                        effective_subtask_id = str(_dispatched).strip() or None
                # Update on first-set OR on reprint (the queue dispatcher mints
                # a fresh subtask_id per dispatch in bambu_mqtt:3647). Skipping
                # the rewrite for reprints leaves the archive holding the FIRST
                # run's id; if MQTT then reconnects mid-print, the reconciler
                # (#1542) compares the stale stored id against the printer's
                # live id, sees a mismatch, and synthesises a bogus PRINT
                # COMPLETE — exactly the false-positive "Print Stopped" reported
                # in #1807. Inequality check preserves the noop-on-stable-push
                # behaviour the earlier `not archive.subtask_id` guard provided.
                archive.subtask_id = effective_subtask_id
                # #1403 follow-up: VP-queue archives are created with
                # printer_id=None at queue-add time (we don't know which
                # printer will run the job yet). When the print actually
                # starts on a specific printer the expected-archive lookup
                # used to skip this assignment, leaving printer_id=None
                # forever — which then disables the "Scan for timelapse"
                # button in ArchivesPage (gated on !archive.printer_id).
                if archive.printer_id != printer_id:
                    archive.printer_id = printer_id
                await db.commit()
                await remove_reprint_video(
                    db,
                    archive,
                    stale_video,
                    settings=app_settings,
                    plate_id=_get_start_plate_id(printer_id, expected_archive_id),
                )

                if not await _bind_and_record_print_run(db, printer, archive, filename, subtask_name, logger):
                    return

                # Start timelapse session if external camera is enabled (#1353).
                # Queue / VP-dispatched prints land here in the expected-archive
                # branch and used to skip start_session entirely — frames were
                # never captured and the post-print stitch silently returned None.
                _maybe_start_layer_timelapse(printer, printer_id, archive.id)

                # Inject ams_mapping into usage tracker session — the session was created
                # before expected-print promotion, so it may have ams_mapping=None when
                # the MQTT request topic subscription failed (common on P1S/A1).
                _stored_map = _print_ams_mappings.get((printer_id, expected_archive_id))
                _stored_plate_id = _print_plate_ids.get((printer_id, expected_archive_id))
                if _stored_map or _stored_plate_id is not None or effective_subtask_id:
                    await print_provenance.enrich_print_session(
                        printer_id, _stored_map, _stored_plate_id, effective_subtask_id, db, logger
                    )

                # Set up energy tracking (#941: persist start on archive row)
                await _record_energy_start(archive, printer_id, db, context="expected-print")

                await ws_manager.send_archive_updated(
                    {
                        "id": archive.id,
                        "status": "printing",
                    }
                )

                # Send notification with archive data (reprint/scheduled)
                if not notification_sent:
                    archive_data = {
                        "print_time_seconds": _start_estimated_time(archive, printer_id),
                        "created_by_id": archive.created_by_id or fallback_creator,
                    }
                    await _send_print_start_notification(printer_id, data, archive_data, logger)

                # Extract printable objects from the archived 3MF file
                _load_objects_from_archive(archive, printer_id, logger)

                # Store Spoolman tracking data for per-filament usage reporting
                await _store_start_tracking(printer_id, archive, db, data, spoolman_owns_print, logger)

                # Capture timelapse file baseline for snapshot-diff on completion
                # (mirrors the new-archive branch). Queue / VP-dispatched prints
                # hit this branch — without the baseline the completion-time scan
                # falls into its "take baseline now" fallback, which snapshots
                # AFTER the new MP4 already exists and never matches a diff
                # (#1403 follow-up — see pwostran's 2026-05-18 support bundle).
                await _capture_timelapse_baseline_at_start(printer, printer_id, logger, archive_id=archive.id, db=db)

                return  # The expected archive was adopted.

            # The expected archive disappeared. Release the printer before FTP.
            await db.commit()
            if not archives_prints:
                if not notification_sent:
                    await _send_print_start_notification(printer_id, data, logger=logger)
                return
            logger.warning(
                "Expected archive %s is gone; archiving printer %s's print anew",
                expected_archive_id,
                printer_id,
            )

        # Check if there's already a "printing" archive for this printer/file
        # This prevents duplicates when backend restarts during an active print
        from backend.app.models.archive import PrintArchive

        existing_archive: PrintArchive | None = None

        # Resume only a live run. Terminal rows already passed completion.
        if subtask_id:
            by_id = await db.execute(
                select(PrintArchive)
                .where(PrintArchive.printer_id == printer_id)
                .where(PrintArchive.subtask_id == subtask_id)
                .where(PrintArchive.status == "printing")
                .where(PrintArchive.deleted_at.is_(None))
                .order_by(PrintArchive.created_at.desc())
                .limit(1)
            )
            existing_archive = by_id.scalar_one_or_none()

        # Fallback match: name-based lookup. Kept as-is for prints whose
        # subtask_id is missing ("0" / local / non-cloud prints).
        from backend.app.services.threemf_identity import subtask_is_printed_file

        if existing_archive is None:
            check_name = subtask_name or filename.split("/")[-1].replace(".gcode", "").replace(".3mf", "")
            archive_filenames = [f"{check_name}.3mf", f"{check_name}.gcode.3mf"]
            if subtask_is_printed_file(subtask_name, filename):
                archive_filenames.append(subtask_name)
            existing = await db.execute(
                select(PrintArchive)
                .where(PrintArchive.printer_id == printer_id)
                .where(PrintArchive.status == "printing")
                .where(PrintArchive.deleted_at.is_(None))
                .where(
                    or_(
                        PrintArchive.print_name == check_name,
                        PrintArchive.filename.in_(archive_filenames),
                    )
                )
                .order_by(PrintArchive.created_at.desc())
                .limit(1)
            )
            existing_archive = existing.scalar_one_or_none()

        if existing_archive:
            # Same identity resumes an existing live run after a restart.
            subtask_match = bool(subtask_id and existing_archive.subtask_id == subtask_id)

            if subtask_match:
                logger.info("Resuming archive %s on subtask_id match (%s)", existing_archive.id, subtask_id)
                if not await _bind_and_record_print_run(db, printer, existing_archive, filename, subtask_name, logger):
                    return
                if existing_archive.energy_start_kwh is None:
                    await _record_energy_start(existing_archive, printer_id, db, context="subtask-resume")
                if not notification_sent:
                    archive_data = {
                        "print_time_seconds": _start_estimated_time(existing_archive, printer_id),
                        "created_by_id": existing_archive.created_by_id,
                    }
                    await _send_print_start_notification(printer_id, data, archive_data, logger)
                _load_objects_from_archive(existing_archive, printer_id, logger)
                await _capture_timelapse_baseline_at_start(
                    printer, printer_id, logger, archive_id=existing_archive.id, db=db, skip_if_present=True
                )
                return

            # Name-match only (no subtask_id to anchor on): decide resume vs.
            # stale from the printer's *current* progress, not wall-clock age.
            # A genuinely long print used to trip a blind 4h cutoff and have its
            # live archive cancelled + duplicated on every backend restart
            # (#1485). If the printer reports real progress, this name-matched
            # 'printing' archive IS that ongoing print — resume it whatever its
            # age. Only treat it as a stale leftover when the printer clearly
            # shows a different, freshly-started print: near-0% progress on an
            # archive far too old to still be at 0%. Unknown progress (printer
            # not connected) never cancels — resuming is the safe default.
            archive_age = datetime.now(timezone.utc) - existing_archive.created_at.replace(tzinfo=timezone.utc)
            live_status = printer_manager.get_status(printer_id)
            live_progress = getattr(live_status, "progress", None) if live_status else None
            looks_stale = (
                live_progress is not None and live_progress < 1.0 and archive_age.total_seconds() > 2 * 60 * 60
            )
            if not looks_stale:
                from backend.app.services.print_start_identity import different_run

                looks_stale = await different_run(
                    db,
                    existing_archive,
                    printer_id,
                    subtask_id,
                    printer_manager.get_client(printer_id),
                )
            if looks_stale:
                logger.warning(
                    "Replacing stale printing archive %s (age %s, progress %s, old subtask %s, observed %s)",
                    existing_archive.id,
                    archive_age,
                    live_progress,
                    existing_archive.subtask_id,
                    subtask_id,
                )
                from backend.app.models.print_log import PrintLogEntry
                from backend.app.services.print_log_run import cancel_discarded_projection, discard_print_runs

                discarded = await discard_print_runs(
                    db, PrintLogEntry.archive_id == existing_archive.id, PrintLogEntry.printer_id == printer_id
                )
                await cancel_discarded_projection(db, existing_archive.id, printer_id, existing_archive.started_at)
                await db.commit()
                for run in discarded:
                    await mqtt_relay.on_run_event("discarded", run, printer)
                for key in [
                    key
                    for key, value in _active_prints.items()
                    if key[0] == printer_id and value == existing_archive.id
                ]:
                    _active_prints.pop(key, None)
                # Fall through to create new archive (don't return)
            else:
                logger.info(
                    f"Skipping duplicate - already have printing archive {existing_archive.id} for {check_name}"
                )
                # Track this as the active print
                if not await _bind_and_record_print_run(db, printer, existing_archive, filename, subtask_name, logger):
                    return
                # Attach subtask_id retroactively so future restarts can resume.
                # Compare for inequality (not "is empty") to also pick up reprint
                # dispatches that mint a fresh id — see #1807 for the bogus
                # "Print Stopped" the strict-empty guard caused on reconnect.
                if subtask_id and existing_archive.subtask_id != subtask_id:
                    existing_archive.subtask_id = subtask_id
                    await db.commit()
                # Also set up energy tracking if not already tracked (#941: persisted column)
                if existing_archive.energy_start_kwh is None:
                    await _record_energy_start(existing_archive, printer_id, db, context="existing-printing")
                # Send notification with archive data (existing archive)
                if not notification_sent:
                    archive_data = {
                        "print_time_seconds": _start_estimated_time(existing_archive, printer_id),
                        "created_by_id": existing_archive.created_by_id,
                    }
                    await _send_print_start_notification(printer_id, data, archive_data, logger)
                # Extract printable objects from the archived 3MF file
                _load_objects_from_archive(existing_archive, printer_id, logger)
                await _capture_timelapse_baseline_at_start(
                    printer, printer_id, logger, archive_id=existing_archive.id, db=db, skip_if_present=True
                )
                return

        # Build list of possible 3MF filenames to try
        possible_names = []

        # Bambu printers typically store files as "Name.gcode.3mf"
        # The subtask_name is usually the best source for the filename
        if subtask_name:
            if subtask_is_printed_file(subtask_name, filename):
                possible_names.append(subtask_name)
            else:
                possible_names.append(f"{subtask_name}.gcode.3mf")
                possible_names.append(f"{subtask_name}.3mf")

        # Try original filename with .3mf extension
        if filename:
            # Extract just the filename part, not the full path
            fname = filename.split("/")[-1] if "/" in filename else filename
            if fname.endswith(".3mf"):
                possible_names.append(fname)
            elif fname.endswith(".gcode"):
                base = fname.rsplit(".", 1)[0]
                possible_names.append(f"{base}.gcode.3mf")
                possible_names.append(f"{base}.3mf")
            else:
                possible_names.append(f"{fname}.gcode.3mf")
                possible_names.append(f"{fname}.3mf")

        # Also try with spaces converted to underscores (Bambu Studio may normalize filenames)
        space_variants = []
        for name in possible_names:
            if " " in name:
                space_variants.append(name.replace(" ", "_"))
        possible_names.extend(space_variants)

        # Remove duplicates while preserving order
        seen = set()
        possible_names = [x for x in possible_names if not (x in seen or seen.add(x))]

        logger.info("Trying filenames: %s", possible_names)

        from backend.app.services.print_start_file import find_start_file

        await db.close()  # Release the read transaction before printer I/O.
        ftp_retry_enabled, ftp_retry_count, ftp_retry_delay, ftp_timeout = await get_ftp_retry_settings()
        acquired = await find_start_file(
            printer,
            possible_names,
            subtask_name or filename,
            archive_dir=app_settings.archive_dir,
            retry_settings=(ftp_retry_enabled, ftp_retry_count, ftp_retry_delay, ftp_timeout),
            get_cached=get_cached_3mf,
            cache_file=cache_3mf_download,
            download=download_file_async,
            retry=with_ftp_retry,
            list_files=list_files_async,
        )
        temp_path, downloaded_filename = acquired.path, acquired.filename

        reused_3mf_from = None
        if not downloaded_filename and not acquired.listed_transfer_failed:
            from backend.app.services.repeat_print_source import archived_repeat_source, copy_repeat_source
            from backend.app.services.running_print_archive import local_archive_file
            from backend.app.utils.safe_path import safe_join_under

            earlier = await archived_repeat_source(
                db,
                printer_id,
                subtask_name,
                filename,
                (data.get("raw_data") or {}).get("total_layer_num"),
                base_dir=app_settings.base_dir,
                ams_mapping=data.get("ams_mapping") or None,
            )
            await db.close()
            if earlier is not None:
                source = local_archive_file(earlier, app_settings.base_dir)
                reuse_path = safe_join_under(
                    app_settings.archive_dir / "temp", f"repeat_{printer_id}_{secrets.token_hex(16)}.3mf", http=False
                )
                try:
                    reuse_path.parent.mkdir(parents=True, exist_ok=True)
                    await copy_repeat_source(source, reuse_path)
                except OSError as error:
                    logger.warning("Could not copy repeat source archive %s: %s", earlier.id, error)
                else:
                    temp_path = reuse_path
                    downloaded_filename = Path(earlier.filename).name
                    reused_3mf_from = earlier.id
                    cache_3mf_download(printer_id, downloaded_filename, temp_path)

        # Validate the downloaded 3MF actually matches the plate that's running
        # (#1204): subtask_name lags across consecutive plates of the same model,
        # so the first FTP candidate (built from subtask_name) can land on the
        # previous plate's still-resident upload. Cross-check the slice_info
        # plate index against the plate parsed from gcode_file (always fresh —
        # it's the field whose change triggered this callback).
        if downloaded_filename and temp_path:
            expected_plate = parse_plate_id(filename)
            actual_plate = peek_plate_index_in_3mf(temp_path) if expected_plate is not None else None
            if expected_plate is not None and actual_plate is not None and actual_plate != expected_plate:
                logger.warning(
                    "[CALLBACK] 3MF plate mismatch: downloaded %s reports plate %s but printer is "
                    "running plate %s — subtask_name=%r appears stale, retrying with corrected name",
                    downloaded_filename,
                    actual_plate,
                    expected_plate,
                    subtask_name,
                )
                corrected_subtask = swap_plate_suffix(subtask_name, expected_plate)
                retry_succeeded = False
                if corrected_subtask and corrected_subtask != subtask_name:
                    for try_filename in (f"{corrected_subtask}.gcode.3mf", f"{corrected_subtask}.3mf"):
                        from backend.app.utils.safe_path import safe_join_under

                        retry_temp_path = safe_join_under(
                            app_settings.archive_dir / "temp",
                            f"plate_{printer_id}_{secrets.token_hex(16)}.3mf",
                            http=False,
                        )
                        retry_temp_path.parent.mkdir(parents=True, exist_ok=True)
                        for remote_path in (
                            f"/{try_filename}",
                            f"/cache/{try_filename}",
                            f"/model/{try_filename}",
                            f"/data/{try_filename}",
                            f"/data/Metadata/{try_filename}",
                        ):
                            try:
                                if ftp_retry_enabled:
                                    downloaded = await with_ftp_retry(
                                        download_file_async,
                                        printer.ip_address,
                                        printer.access_code,
                                        remote_path,
                                        retry_temp_path,
                                        timeout=ftp_timeout,
                                        socket_timeout=ftp_timeout,
                                        printer_model=printer.model,
                                        max_retries=ftp_retry_count,
                                        retry_delay=ftp_retry_delay,
                                        operation_name=f"Re-download 3MF from {remote_path}",
                                        non_retry_exceptions=(FileNotOnPrinterError,),
                                    )
                                else:
                                    downloaded = await download_file_async(
                                        printer.ip_address,
                                        printer.access_code,
                                        remote_path,
                                        retry_temp_path,
                                        timeout=ftp_timeout,
                                        socket_timeout=ftp_timeout,
                                        printer_model=printer.model,
                                    )
                                if downloaded and peek_plate_index_in_3mf(retry_temp_path) == expected_plate:
                                    logger.info(
                                        "[CALLBACK] Re-download succeeded with corrected name %s "
                                        "(plate %s) — replacing wrong file",
                                        try_filename,
                                        expected_plate,
                                    )
                                    try:
                                        temp_path.unlink(missing_ok=True)
                                    except OSError:
                                        pass
                                    temp_path = retry_temp_path
                                    downloaded_filename = try_filename
                                    subtask_name = corrected_subtask
                                    cache_3mf_download(printer_id, try_filename, temp_path)
                                    retry_succeeded = True
                                    break
                                elif downloaded:
                                    # Wrong plate again — discard and keep trying
                                    try:
                                        retry_temp_path.unlink(missing_ok=True)
                                    except OSError:
                                        pass
                            except FileNotOnPrinterError:
                                continue
                            except Exception as e:
                                logger.debug("Re-download failed for %s: %s", remote_path, e)
                        if retry_succeeded:
                            break
                # If the retry didn't find a matching file, drop the wrong 3MF
                # so the no-3MF fallback below creates an archive whose name
                # at least reflects the right plate.
                if not retry_succeeded:
                    logger.warning(
                        "[CALLBACK] Could not re-download correct plate %s — falling back to no-3MF archive",
                        expected_plate,
                    )
                    try:
                        temp_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    temp_path = None
                    downloaded_filename = None
                    # Override the stale subtask_name so the fallback archive's
                    # print_name reflects the correct plate. Prefer the swapped
                    # name when we have one; otherwise let filename win.
                    if corrected_subtask:
                        subtask_name = corrected_subtask
                    else:
                        subtask_name = ""

        if not downloaded_filename or not temp_path:
            logger.warning("Could not find 3MF file for print: %s", filename or subtask_name)
            # Create a fallback archive without 3MF data so the print is still tracked.
            try:
                from backend.app.models.archive import PrintArchive

                print_name = fallback_recovery.fallback_print_name(filename, subtask_name)
                fallback_time = fallback_recovery.fallback_print_time(data)

                # Use live MQTT metadata, narrowed to used slots by slicer mapping (#1533).
                mqtt_filament_meta = _extract_filament_data_from_mqtt(data, data.get("ams_mapping") or None)

                # Create minimal archive entry
                fallback_archive = PrintArchive(
                    printer_id=printer_id,
                    filename=filename or f"{print_name}.3mf",
                    file_path="",  # Empty - no 3MF file available
                    file_size=0,
                    print_name=print_name,
                    print_time_seconds=fallback_time,
                    status="printing",
                    started_at=detected_at,
                    subtask_id=subtask_id,
                    plate_id=fallback_recovery.resolve_fallback_plate(printer_id, filename),
                    filament_type=mqtt_filament_meta.get("filament_type"),
                    filament_color=mqtt_filament_meta.get("filament_color"),
                    extra_data={"no_3mf_available": True, "original_subtask": subtask_name, "_print_data": data},
                )

                if not await lock_existing_printer(db, printer_id):
                    return
                db.add(fallback_archive)
                await db.commit()
                await db.refresh(fallback_archive)

                logger.info("Created fallback archive %s for %s (no 3MF available)", fallback_archive.id, print_name)

                _maybe_start_layer_timelapse(printer, printer_id, fallback_archive.id)

                if not await _bind_and_record_print_run(db, printer, fallback_archive, filename, subtask_name, logger):
                    return
                await _capture_timelapse_baseline_at_start(
                    printer, printer_id, logger, archive_id=fallback_archive.id, db=db
                )

                # Record starting energy if smart plug available (#941: persisted column)
                await _record_energy_start(fallback_archive, printer_id, db, context="fallback")

                # Send WebSocket notification
                await ws_manager.send_archive_created(
                    {
                        "id": fallback_archive.id,
                        "printer_id": fallback_archive.printer_id,
                        "filename": fallback_archive.filename,
                        "print_name": fallback_archive.print_name,
                        "status": fallback_archive.status,
                    }
                )

                # MQTT relay - publish archive created
                try:
                    await mqtt_relay.on_archive_created(
                        archive_id=fallback_archive.id,
                        print_name=fallback_archive.print_name,
                        printer_name=printer.name,
                        status=fallback_archive.status,
                    )
                except Exception:
                    pass  # Don't fail if MQTT fails

                # Store Spoolman tracking data (may not work for fallback since no 3MF)
                await _store_start_tracking(printer_id, fallback_archive, db, data, spoolman_owns_print, logger)

                # Send notification without archive data (file not found)
                if not notification_sent:
                    await _send_print_start_notification(printer_id, data, logger=logger)
                return
            except Exception as e:
                logger.error("Failed to create fallback archive: %s", e)
                # Send notification without archive data (file not found)
                if not notification_sent:
                    await _send_print_start_notification(printer_id, data, logger=logger)
                return

        try:
            # Archive the file with status "printing"
            service = ArchiveService(db)
            archive = await service.archive_print(
                printer_id=printer_id,
                source_file=temp_path,
                print_data={
                    **data,
                    "status": "printing",
                    **({"_3mf_from_archive": reused_3mf_from} if reused_3mf_from is not None else {}),
                },
                subtask_id=subtask_id,
                started_at=detected_at,
                original_filename=downloaded_filename,
            )

            if archive:
                if not await _bind_and_record_print_run(db, printer, archive, filename, subtask_name, logger):
                    return

                logger.info("Created archive %s for %s", archive.id, downloaded_filename)

                _maybe_start_layer_timelapse(printer, printer_id, archive.id)

                # Record starting energy from smart plug if available (#941: persisted column)
                await _record_energy_start(archive, printer_id, db, context="auto-archive")

                await ws_manager.send_archive_created(
                    {
                        "id": archive.id,
                        "printer_id": archive.printer_id,
                        "filename": archive.filename,
                        "print_name": archive.print_name,
                        "status": archive.status,
                    }
                )

                # MQTT relay - publish archive created
                try:
                    await mqtt_relay.on_archive_created(
                        archive_id=archive.id,
                        print_name=archive.print_name,
                        printer_name=printer.name,
                        status=archive.status,
                    )
                except Exception:
                    pass  # Don't fail if MQTT fails

                # Send notification with archive data (new archive created)
                if not notification_sent:
                    archive_data = {
                        "print_time_seconds": _start_estimated_time(archive, printer_id),
                        "created_by_id": archive.created_by_id,
                    }
                    await _send_print_start_notification(printer_id, data, archive_data, logger)

                # Extract printable objects for skip object functionality
                try:
                    from backend.app.services.archive import extract_printable_objects_from_3mf

                    client = printer_manager.get_client(printer_id)
                    if client:
                        with open(temp_path, "rb") as f:
                            threemf_data = f.read()
                        printable_objects, bbox_all = extract_printable_objects_from_3mf(
                            threemf_data,
                            plate_number=resolve_plate_id(client.state),
                            include_positions=True,
                        )
                        if printable_objects:
                            client.state.printable_objects = printable_objects
                            client.state.printable_objects_bbox_all = bbox_all
                            client.state.skipped_objects = []  # Reset skipped objects for new print
                            logger.info(
                                "Loaded %s printable objects for printer %s", len(printable_objects), printer_id
                            )
                except Exception as e:
                    logger.debug("Failed to extract printable objects: %s", e)

                # Store Spoolman tracking data for per-filament usage reporting
                await _store_start_tracking(printer_id, archive, db, data, spoolman_owns_print, logger)

                # Capture timelapse file baseline for snapshot-diff on completion
                await _capture_timelapse_baseline_at_start(printer, printer_id, logger, archive_id=archive.id, db=db)
        finally:
            # Keep temp_path around until print completes so the cover endpoint
            # can reuse it (#972). Cache eviction in on_print_complete deletes
            # the file. If the cache entry was evicted early (file vanished),
            # clean up any stragglers here to avoid leaking disk on retries.
            cached_now = get_cached_3mf(printer_id, downloaded_filename) if downloaded_filename else None
            if temp_path and temp_path.exists() and cached_now != temp_path:
                temp_path.unlink()


async def _list_timelapse_videos(printer) -> tuple[list[dict], str | None]:
    from backend.app.services.timelapse_baseline import list_videos

    return await list_videos(printer)


async def _capture_timelapse_baseline_at_start(
    printer,
    printer_id: int,
    logger: logging.Logger,
    *,
    archive_id: int | None = None,
    db=None,
    skip_if_present: bool = False,
    preserve_stored: bool = False,
    run_id: int | None = None,
) -> None:
    from backend.app.services.timelapse_baseline import capture

    await capture(
        printer,
        printer_id,
        baselines=_timelapse_baselines,
        list_videos=_list_timelapse_videos,
        get_status=printer_manager.get_status,
        session_factory=async_session,
        spawn=spawn_background_task,
        archive_id=archive_id,
        db=db,
        skip_if_present=skip_if_present,
        preserve_stored=preserve_stored,
        run_id=run_id,
    )


async def _scan_for_timelapse_with_retries(
    archive_id: int,
    baseline_names: set[str] | None = None,
    *,
    plate_id: int | None = None,
    run_id: int | None = None,
):
    """Compatibility wrapper; matching lives in the focused service module."""
    from backend.app.services.timelapse_archive import scan_for_timelapse_with_retries

    await scan_for_timelapse_with_retries(
        archive_id,
        baseline_names,
        session_factory=async_session,
        archive_service_factory=ArchiveService,
        list_videos=_list_timelapse_videos,
        websocket_manager=ws_manager,
        plate_id=plate_id,
        run_id=run_id,
    )


# Defaults for the finish-photo-from-timelapse polling loop (#1397). These are
# module-level so tests can monkeypatch them down to ~0 without timing out.
_FINISH_PHOTO_TIMELAPSE_POLL_INTERVAL_SECONDS: float = 3.0
_FINISH_PHOTO_TIMELAPSE_POLL_TIMEOUT_SECONDS: float = 60.0


async def _capture_finish_photo_from_timelapse(
    archive_id: int,
    archive_dir: Path,
    rotation: int = 0,
    *,
    run_id: int | None = None,
    timeout_seconds: float | None = None,
) -> str | None:
    """Wait for the per-print timelapse to land on the archive and extract its
    last frame as the finish photo (#1397).

    Bambu firmware stops timelapse recording after the toolhead parks but
    before the bed-drop end-gcode runs, so the last frame frames the finished
    print correctly. A live camera grab at gcode_state=FINISH captures the
    bed already lowered.

    ``_scan_for_timelapse_with_retries`` runs in parallel and writes
    ``archive.timelapse_path`` when the file lands. This function polls for
    that field. Returns the saved photo filename on success, or None if the
    timelapse never arrives within the timeout / extraction fails / no
    timelapse path was set — in which case the caller falls back to the
    existing live-camera capture chain.
    """
    import uuid

    from backend.app.models.archive import PrintArchive
    from backend.app.services.camera import apply_camera_rotation_to_file, extract_video_last_frame
    from backend.app.services.print_run_media import run_of
    from backend.app.utils.safe_path import safe_join_under

    logger = logging.getLogger(__name__)

    timeout = _FINISH_PHOTO_TIMELAPSE_POLL_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    deadline = asyncio.get_event_loop().time() + timeout
    poll_interval = _FINISH_PHOTO_TIMELAPSE_POLL_INTERVAL_SECONDS

    while True:
        async with async_session() as db:
            if run_id is None:
                source = (
                    await db.execute(select(PrintArchive).where(PrintArchive.id == archive_id))
                ).scalar_one_or_none()
            else:
                source = await run_of(db, archive_id, run_id)
            if source is None:
                return None
            timelapse_relpath = source.timelapse_path

        if timelapse_relpath:
            video_path = safe_join_under(app_settings.base_dir, timelapse_relpath)
            if video_path.exists() and video_path.stat().st_size > 0:
                photos_dir = archive_dir / "photos"
                photos_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"finish_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
                output_path = photos_dir / filename
                if await extract_video_last_frame(video_path, output_path):
                    await apply_camera_rotation_to_file(output_path, rotation, logger)
                    logger.info(
                        "[PHOTO-BG] Extracted finish photo from timelapse %s for archive %s",
                        video_path.name,
                        archive_id,
                    )
                    return filename
                logger.warning(
                    "[PHOTO-BG] Timelapse %s landed but last-frame extraction failed for archive %s; falling back",
                    video_path.name,
                    archive_id,
                )
                return None

        if asyncio.get_event_loop().time() >= deadline:
            logger.info(
                "[PHOTO-BG] Timelapse for archive %s didn't land within %.0fs; falling back to live camera",
                archive_id,
                timeout,
            )
            return None

        await asyncio.sleep(poll_interval)


async def _upgrade_finish_photo_from_timelapse(archive_id, run_id, archive_dir, rotation, original, logger):
    from backend.app.services.print_run_media import replace_finish_photo
    from backend.app.utils.safe_path import safe_join_under

    replacement = await _capture_finish_photo_from_timelapse(
        archive_id, archive_dir, rotation, run_id=run_id, timeout_seconds=180.0
    )
    if replacement is None:
        return
    try:
        async with async_session() as db:
            changed = await replace_finish_photo(db, archive_id, run_id, original, replacement, settings=app_settings)
        if changed:
            await ws_manager.send_archive_updated({"id": archive_id, "photo_updated": original})
    except Exception:
        logger.warning("Could not update the finish photo for run %s", run_id, exc_info=True)
    finally:
        path = safe_join_under(archive_dir, "photos", replacement)
        await asyncio.to_thread(path.unlink, missing_ok=True)


async def on_print_running_observed(printer_id: int, data: dict):
    """Restart-recovery: capture a fresh timelapse baseline for a print that
    started before PrintOps came up.

    bambu_mqtt.py suppresses ``on_print_start`` on the first RUNNING push
    after PrintOps startup (#1304 guard, prevents duplicate archive
    creation). Without that path, ``_capture_timelapse_baseline_at_start``
    never runs and ``_scan_for_timelapse_with_retries`` falls into its
    "take baseline now" fallback at completion time — but by then the
    printer has already uploaded the in-flight MP4, so the baseline
    includes it and no diff ever matches (#1485 follow-up).

    Fires once per session, in lieu of on_print_start when restart-recovery
    kicks in. The printer doesn't upload the timelapse until after PRINT
    COMPLETE, so a baseline captured any time during the print is still
    pre-upload.
    """
    logger = logging.getLogger(__name__)

    if await _ignore_internal_printer_job(printer_id, data, "restart observation"):
        return

    from backend.app.services.printer_archive_objects import restore_running_objects

    await restore_running_objects(
        printer_id,
        manager=printer_manager,
        bindings=_active_prints,
        session_factory=async_session,
        base_dir=app_settings.base_dir,
    )

    # Avoid double-capture: on_print_start may have run earlier in this
    # PrintOps process if the print started AFTER startup and we crashed
    # later in the same session. (Realistically this can't happen — the
    # MQTT client object would have been recreated — but the cheap guard
    # is correct regardless.)
    if printer_id in _timelapse_baselines:
        logger.debug(
            "[TIMELAPSE] on_print_running_observed: baseline already present for printer %s, skipping",
            printer_id,
        )
        return

    async with async_session() as db:
        from backend.app.models.printer import Printer

        await print_provenance.restore_from_manager(printer_id, printer_manager, db, logger)

        result = await db.execute(select(Printer).where(Printer.id == printer_id))
        printer = result.scalar_one_or_none()
        if not printer:
            logger.warning(
                "[TIMELAPSE] on_print_running_observed: printer %s not found in DB, skipping baseline",
                printer_id,
            )
            return

        from backend.app.services.running_print_archive import find_running_print

        state = printer_manager.get_status(printer_id)
        archive, run = await find_running_print(db, printer_id, state, bindings=_active_prints, by_name=True)
        if run is not None:
            _bind_active_print(printer_id, archive.id, archive.filename, data.get("filename"), data.get("subtask_name"))
            if run.energy_start_kwh is None:
                await _record_energy_start(archive, printer_id, db, context="running-observed", run=run)
        await _capture_timelapse_baseline_at_start(
            printer,
            printer_id,
            logger,
            archive_id=archive.id if archive and (run is not None or archive.printer_id == printer_id) else None,
            db=db,
            preserve_stored=True,
            run_id=run.id if run is not None else None,
        )


def _is_active_archive_stale(archive, state) -> tuple[bool, str]:
    """Return ``(is_stale, reason)`` for an archive in ``status="printing"``
    against the printer's current MQTT state.

    Reconciliation triggers (#1542 follow-up — recovers from missed PRINT
    COMPLETE events, typically a print finishing during an MQTT disconnect
    window followed by a smart-plug power cycle):

      1. Printer state is terminal (IDLE / FINISH / FAILED). The print is
         provably not running anymore — only branch that should fire under
         normal disconnect-then-reconnect timing.
      2. Printer has a different ``subtask_id`` than the archive. Bambu
         firmware mints a fresh ``subtask_id`` for each print, including the
         ghost replay it runs after a power cycle from a leftover SD file —
         so a mismatch unambiguously means the in-DB archive is no longer
         the print on the printer.
      3. Printer is running but ``subtask_name`` is empty. The printer
         doesn't know what it's running; the archive's reference to it is
         already broken.

    Conservative on purpose: PAUSE / PREPARE / SLICING and any RUNNING state
    with matching subtask_id+subtask_name is left alone. The cost of a false
    positive is a duplicate archive on the next real PRINT COMPLETE — the
    reactive handler uses ``_active_prints`` for lookup, which the reconcile
    clears on synthesis, so the real completion creates a fresh row instead
    of overwriting the synthesised one (#1679). The cost of a false negative
    is the ghost-print loop in #1542.

    Pre-push guard (#1679): when ``state.state`` is empty or ``"unknown"``,
    MQTT has connected but the first ``push_status`` response hasn't been
    applied yet — ``PrinterState`` is sitting on its construction defaults.
    The reconcile caller in ``on_printer_status_change`` is already gated
    on a real ``state.state``, so in normal operation this branch is
    unreachable; it's kept as belt-and-braces for future callers and for
    the narrow window where a partial state update could arrive
    (``state.state`` set but ``subtask_name`` not yet populated). Returning
    ``not stale`` on degenerate input is strictly conservative: a real
    stale archive will still be caught by the next push_status arriving
    with terminal state.
    """
    current_state = (state.state or "").upper()
    if current_state in ("", "UNKNOWN"):
        # No real push_status yet — PrinterState defaults are not evidence.
        return False, ""
    if current_state in ("IDLE", "FINISH", "FAILED"):
        return True, f"printer state {current_state}"
    # Below here the printer is in a running / pre-running state (RUNNING /
    # PAUSE / PREPARE / SLICING / etc.) — decide based on subtask identity.
    from backend.app.services.running_print_archive import job_id

    current_subtask_id = job_id(state.subtask_id)
    if archive.subtask_id and current_subtask_id and archive.subtask_id != current_subtask_id:
        return True, f"subtask_id changed ({archive.subtask_id!r} → {current_subtask_id!r})"
    current_subtask_name = (state.subtask_name or "").strip()
    if not current_subtask_name:
        return True, "printer subtask_name empty"
    return False, ""


async def reconcile_stale_active_prints(printer_id: int) -> int:
    """Synthesise ``on_print_complete`` for archives whose print can't be
    running on the printer anymore.

    Called once per MQTT (re)connection (from on_printer_status_change when
    the connected edge flips False → True) and at PrintOps startup (from
    the FastAPI lifespan). Without this, a print that completes during a
    disconnect window — followed by a smart-plug-driven power cycle — leaves
    the ``.3mf`` on the SD card, the firmware auto-replays it on next boot,
    and PrintOps fires a fresh PRINT START for the ghost rather than the
    SD cleanup that PRINT COMPLETE was supposed to run. Repeats every
    power cycle until the operator notices (#1542 follow-up). Reconciliation
    closes the loop by faking the missed PRINT COMPLETE — the existing
    cleanup chain handles SD-file deletion, status updates, usage tracking,
    and notifications.

    A matching real job ID preserves the printer's FINISH/FAILED outcome.
    Otherwise the end remains unknown and is labelled aborted. Estimated
    ends remain explicitly unmeasured and never become accuracy samples.

    Returns the number of archives reconciled.
    """
    state = printer_manager.get_status(printer_id)
    if not state:
        return 0
    # Don't reconcile while disconnected — we'd be making a decision against
    # stale cached state. The connected → reconcile edge handles this.
    if not state.connected:
        return 0

    from backend.app.services.print_reconciliation import (
        active_prints_to_reconcile,
        reconciled_outcome,
        reconciliation_payload,
    )

    reconciled = 0
    async with async_session() as db:
        active = await active_prints_to_reconcile(db, printer_id)

    if not active:
        return 0

    logger = logging.getLogger(__name__)
    for archive, run in active:
        is_stale, reason = _is_active_archive_stale(run if run is not None else archive, state)
        if not is_stale:
            continue
        logger.info(
            "[RECONCILE] Printer %s: synthesising missed PRINT COMPLETE for archive %s (%s) — %s",
            printer_id,
            archive.id,
            archive.filename,
            reason,
        )
        # Synthesised payload: minimal fields the on_print_complete chain
        # needs. `_reconciled` marker lets downstream code distinguish this
        # from a real MQTT-driven completion if it ever needs to (e.g. for
        # metrics / debug logging). raw_data is the live printer state so
        # the usage tracker can compare end-of-print remain% against the
        # captured start values.
        try:
            plate_id = None
            if run is None and reconciled_outcome(archive, state) == "completed":
                from backend.app.models.print_queue import PrintQueueItem

                async with async_session() as db:
                    plate_id = await db.scalar(
                        select(PrintQueueItem.plate_id)
                        .where(
                            PrintQueueItem.printer_id == printer_id,
                            PrintQueueItem.archive_id == archive.id,
                            PrintQueueItem.status == "printing",
                        )
                        .order_by(PrintQueueItem.id.desc())
                        .limit(1)
                    )
            payload = await reconciliation_payload(
                archive, state, datetime.now(timezone.utc), base_dir=app_settings.base_dir, plate_id=plate_id, run=run
            )
            await on_print_complete(printer_id, payload)
            reconciled += 1
        except Exception as e:
            # Catch-all: a reconciliation failure must not block the
            # printer's normal status flow. The archive stays in
            # ``status="printing"`` and the next reconnect retries.
            logger.warning(
                "[RECONCILE] on_print_complete synthesis failed for archive %s: %s",
                archive.id,
                e,
            )

    return reconciled


async def on_finish_photo_moment(printer_id: int, data: dict):
    """Pre-capture a finish photo when the printer enters stage 22 / FINISH (#1721).

    Fires either at the stage-22 ("Filament unloading") edge — toolhead
    parked, bed not yet dropped, optimal framing — or as a FINISH-state
    fallback for prints that skip stage 22 (cancel, external-spool-only,
    HMS halt, firmware variants). Grabs one frame via the same
    external-camera / RTSP path the post-completion fallback uses, stores
    the JPEG bytes in ``_stage22_finish_frames[printer_id]``, and lets
    ``_background_finish_photo`` consume the cached bytes when it runs.

    Replaces the #1397 "force timelapse on at dispatch" mechanism, which
    caused per-layer nozzle parking on slicer profiles with Timelapse Type
    set to Smooth (#1721). No force-on now means the user's explicit
    timelapse=off in the slicer send dialog is respected.
    """
    logger = logging.getLogger(__name__)
    trigger = data.get("trigger", "unknown")
    timelapse_was_active = bool(data.get("timelapse_was_active"))
    logger.info(
        "[FINISH-PHOTO-MOMENT] printer=%s trigger=%s timelapse_active=%s",
        printer_id,
        trigger,
        timelapse_was_active,
    )

    # If a timelapse is actively recording, skip the pre-capture — the
    # post-completion path will extract the last frame from the recorded
    # video, which still provides the best framing (toolhead parked,
    # before bed drop) without the per-layer parking side effects.
    if timelapse_was_active:
        logger.info(
            "[FINISH-PHOTO-MOMENT] timelapse active for printer %s — skipping pre-capture (last-frame extraction will run post-completion)",
            printer_id,
        )
        return

    # #1790: register the producer-done event BEFORE the first await so the
    # consumer in `_background_finish_photo` — which is dispatched back-to-back
    # with us on the FINISH-state fallback path — sees it as soon as it polls.
    # The `finally` below guarantees `set()` runs on every exit, including
    # early returns and exceptions, so the consumer's bounded wait can't hang.
    producer_done = asyncio.Event()
    _stage22_finish_in_flight[printer_id] = producer_done

    try:
        async with async_session() as db:
            from backend.app.api.routes.settings import get_setting
            from backend.app.models.printer import Printer

            capture_setting = await get_setting(db, "capture_finish_photo")
            if capture_setting is not None and capture_setting.lower() != "true":
                logger.info("[FINISH-PHOTO-MOMENT] capture_finish_photo disabled — skipping pre-capture")
                return

            result = await db.execute(select(Printer).where(Printer.id == printer_id))
            printer = result.scalar_one_or_none()
            if printer is None:
                logger.warning(
                    "[FINISH-PHOTO-MOMENT] printer %s not found in DB",
                    printer_id,
                )
                return

        frame_bytes: bytes | None = None

        async with automatic_camera_light(printer, wait=True):
            if printer.external_camera_enabled and printer.external_camera_url:
                from backend.app.services.external_camera import capture_frame

                frame_bytes = await capture_frame(
                    printer.external_camera_url,
                    printer.external_camera_type or "mjpeg",
                    snapshot_url=printer.external_camera_snapshot_url,
                    printer_id=printer_id,
                )
                if frame_bytes:
                    logger.info(
                        "[FINISH-PHOTO-MOMENT] captured external-camera frame (%d bytes)",
                        len(frame_bytes),
                    )
            else:
                from backend.app.api.routes.camera import live_frame_for_capture

                watched, buffered = await live_frame_for_capture(printer_id)
                if buffered:
                    frame_bytes = buffered
                    logger.info(
                        "[FINISH-PHOTO-MOMENT] used buffered RTSP frame (%d bytes)",
                        len(frame_bytes),
                    )
                elif not watched:
                    from backend.app.services.camera import capture_camera_frame_bytes

                    frame_bytes = await capture_camera_frame_bytes(
                        ip_address=printer.ip_address,
                        access_code=printer.access_code,
                        model=printer.model,
                        timeout=15,
                    )
                    if frame_bytes:
                        logger.info(
                            "[FINISH-PHOTO-MOMENT] captured RTSP frame (%d bytes)",
                            len(frame_bytes),
                        )

        if frame_bytes and _stage22_finish_in_flight.get(printer_id) is producer_done:
            frame_bytes = _apply_camera_rotation(frame_bytes, printer, logger)
            _stage22_finish_frames[printer_id] = frame_bytes
        elif not frame_bytes:
            logger.warning(
                "[FINISH-PHOTO-MOMENT] no frame captured for printer %s — post-completion fallback will retry",
                printer_id,
            )
    except Exception as e:
        logger.warning(
            "[FINISH-PHOTO-MOMENT] pre-capture failed for printer %s: %s",
            printer_id,
            e,
        )
    finally:
        # #1790: always unblock the consumer's bounded wait — whether we stored
        # a frame, gave up, or hit an exception. Local ref means cleanup of the
        # dict entry by the consumer doesn't affect signalling.
        producer_done.set()


@hold_completion_charges
async def on_print_complete(printer_id: int, data: dict):
    """Handle print completion - update the archive status."""
    import time

    from backend.app.services.layer_timelapse import get_session

    camera_session = get_session(printer_id)
    logger = logging.getLogger(__name__)
    start_time = time.time()

    def log_timing(section: str):
        elapsed = time.time() - start_time
        logger.info("[TIMING] %s: %.3fs elapsed", section, elapsed)

    logger.info("[CALLBACK] on_print_complete started for printer %s", printer_id)
    completion_session, internal_job = await prepare_print_completion(
        printer_id,
        data,
        logger,
        _timelapse_baselines,
        internal_job=await _ignore_internal_printer_job(printer_id, data, "completion"),
    )
    if internal_job:
        return
    filename = data.get("filename", "")
    subtask_name = data.get("subtask_name", "")

    # Build list of possible keys to try (matching how they were registered in on_print_start)
    possible_keys = []

    # Try subtask_name variations first (most reliable for matching)
    if subtask_name:
        possible_keys.append((printer_id, f"{subtask_name}.3mf"))
        possible_keys.append((printer_id, f"{subtask_name}.gcode.3mf"))
        possible_keys.append((printer_id, subtask_name))

    # Try filename variations
    if filename:
        # Extract just the filename if it's a path
        fname = filename.split("/")[-1] if "/" in filename else filename

        if fname.endswith(".3mf"):
            possible_keys.append((printer_id, fname))
        elif fname.endswith(".gcode"):
            base_name = fname.rsplit(".", 1)[0]
            possible_keys.append((printer_id, f"{base_name}.gcode.3mf"))
            possible_keys.append((printer_id, f"{base_name}.3mf"))
            possible_keys.append((printer_id, fname))
        else:
            possible_keys.append((printer_id, f"{fname}.gcode.3mf"))
            possible_keys.append((printer_id, f"{fname}.3mf"))
            possible_keys.append((printer_id, fname))

        # Also try full path versions
        if filename.endswith(".3mf"):
            possible_keys.append((printer_id, filename))
        elif filename.endswith(".gcode"):
            base_name = filename.rsplit(".", 1)[0]
            possible_keys.append((printer_id, f"{base_name}.3mf"))
            possible_keys.append((printer_id, filename))
        else:
            possible_keys.append((printer_id, f"{filename}.3mf"))
            possible_keys.append((printer_id, filename))

    from backend.app.core.database import run_with_retry
    from backend.app.services.print_completion_archive import take_completion_run

    async with async_session() as db:
        archive_id, active_run, previous_run = await take_completion_run(
            db, printer_id, data, _active_prints, possible_keys
        )
    if archive_id is None:
        if data.get("_reconciled_run_id") is not None:
            return
        if not filename and not subtask_name:
            logger.warning("Print complete without filename or subtask_name")
            await print_provenance.discard_print_session(printer_id, completion_session, logger)
            return

    try:
        ws_data = {
            "status": data.get("status"),
            "filename": data.get("filename"),
            "subtask_name": data.get("subtask_name"),
            "timelapse_was_active": data.get("timelapse_was_active"),
        }
        await ws_manager.send_print_complete(printer_id, ws_data)
        log_timing("WebSocket send_print_complete")
    except Exception as e:
        logger.warning("[CALLBACK] WebSocket send_print_complete failed: %s", e)

    _print_user_info = None
    if not previous_run:
        _print_user_info = printer_manager.get_current_print_user(printer_id)
        printer_manager.clear_current_print_user(printer_id)
        status = data.get("status", "completed")
        if printer_id in _user_stopped_printers and status in ("failed", "aborted"):
            data = {**data, "status": "cancelled"}
        _user_stopped_printers.discard(printer_id)
        if data.get("status", "completed") in ("completed", "failed", "aborted", "cancelled"):
            # Any terminal result may leave material on the plate (#961, #1171).
            printer_manager.set_awaiting_plate_clear(printer_id, True)

    # MQTT relay - publish print complete
    try:
        printer_info = printer_manager.get_printer(printer_id)
        if printer_info:
            await mqtt_relay.on_print_complete(
                printer_id,
                printer_info.name,
                printer_info.serial_number,
                data.get("filename", ""),
                data.get("subtask_name", ""),
                data.get("status", "completed"),
            )
    except Exception:
        pass  # Don't fail print complete callback if MQTT fails

    if not previous_run:
        from backend.app.services.print_sd_cleanup import cleanup_after_print

        await cleanup_after_print(
            printer_id,
            subtask_name,
            archive_id,
            logger,
            async_session,
            get_status=printer_manager.get_status,
        )

    log_timing("SD card cleanup")

    # Update queue item status early — must run before the archive_id early-return
    # so queue items don't get stuck in "printing" when archive lookup fails.
    # Uses run_with_retry to handle SQLite "database is locked" errors (#897).
    queue_item_id = None
    queue_status = None
    queue_auto_off = False
    try:
        from backend.app.models.print_queue import PrintQueueItem

        async def _update_queue_status(db):
            nonlocal queue_item_id, queue_status, queue_auto_off
            updated = await update_queue_status_for_completion(
                db,
                printer_id=printer_id,
                data=data,
                event_archive_id=archive_id if isinstance(archive_id, int) else None,
                failure_summary=_format_hms_error_summary(data.get("hms_errors") or []),
                bump_usage=_bump_library_file_usage_if_completed,
            )
            if updated:
                queue_item_id, queue_status, queue_auto_off = updated

        await run_with_retry(_update_queue_status, label="queue status update")

        # Post-commit side effects (notifications, MQTT relay, auto-off) use
        # their own sessions and have their own error handling — no retry needed.
        if queue_item_id is not None:
            # Batch orders (#342): this run may have been the last one an order
            # owed. Re-evaluate here rather than lazily on read, so a finished
            # order reports itself complete without someone opening the page.
            try:
                from backend.app.services.print_batch import refresh_batch_status_for_item

                async with async_session() as db:
                    await refresh_batch_status_for_item(db, queue_item_id)
                    await db.commit()
            except Exception as e:
                logger.warning("[BATCH] Failed to refresh batch status for queue item %s: %s", queue_item_id, e)

            # MQTT relay - publish queue job completed
            try:
                printer_info = printer_manager.get_printer(printer_id)
                await mqtt_relay.on_queue_job_completed(
                    job_id=queue_item_id,
                    filename=filename or subtask_name,
                    printer_id=printer_id,
                    printer_name=printer_info.name if printer_info else "Unknown",
                    status=queue_status,
                )
            except Exception:
                pass  # Don't fail if MQTT fails

            # Check if queue is now empty and send notification
            try:
                from sqlalchemy import func as sa_func

                async with async_session() as db:
                    count_result = await db.execute(
                        select(sa_func.count(PrintQueueItem.id)).where(PrintQueueItem.status == "pending")
                    )
                    pending_count = count_result.scalar() or 0

                    if pending_count == 0:
                        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                        completed_result = await db.execute(
                            select(sa_func.count(PrintQueueItem.id)).where(
                                PrintQueueItem.status.in_(["completed", "failed", "skipped"]),
                                PrintQueueItem.completed_at >= today_start,
                            )
                        )
                        completed_count = completed_result.scalar() or 1

                        await notification_service.on_queue_completed(
                            completed_count=completed_count,
                            db=db,
                        )
            except Exception:
                pass  # Don't fail if notification fails

            # Handle auto_off_after - power off printer if the queue item opted
            # in. Delegates to the smart-plug manager so the off honours each
            # plug's configured strategy (time delay or temperature threshold),
            # is cancelled if the printer starts printing again, and never cuts
            # power on a loaded print (#1890). Previously an inline block here
            # hardcoded a 50°C / 600s cooldown wait and powered off on the
            # timeout regardless of print state — cutting a touchscreen reprint.
            if queue_auto_off:
                try:
                    async with async_session() as db:
                        await smart_plug_manager.schedule_off_after_queue_job(printer_id, db)
                except Exception as e:
                    logger.warning("Failed to schedule queue auto-off for printer %s: %s", printer_id, e)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Queue item update failed: {e}")

    log_timing("Queue item update")

    # Register bed cooldown waiter (event-driven via on_bed_temp_update callback).
    # Must run before archive_id early-return so it fires for all prints (including
    # prints started from BambuStudio/touchscreen that have no archive).
    if data.get("status") == "completed":
        try:
            from backend.app.api.routes.settings import get_setting

            async with async_session() as db:
                threshold_str = await get_setting(db, "bed_cooled_threshold")
            threshold = float(threshold_str) if threshold_str else 35.0

            # Check if any provider has on_bed_cooled enabled (skip registration if none)
            async with async_session() as db:
                providers = await notification_service._get_providers_for_event(db, "on_bed_cooled", printer_id)
            if providers:
                _bed_cool_waiters[printer_id] = {
                    "threshold": threshold,
                    "filename": filename or subtask_name or "",
                    "registered_at": time.time(),
                }
                logger.info(
                    "[BED-COOL] Registered waiter for printer %s (threshold: %.0f°C)",
                    printer_id,
                    threshold,
                )
            else:
                logger.debug("[BED-COOL] No providers enabled for bed_cooled on printer %s", printer_id)
        except Exception as e:
            logger.warning("[BED-COOL] Failed to register waiter: %s", e)

    usage_results: list[dict] = []
    spoolman_run_cost: float | None = None
    # Prefer ams_mapping captured from MQTT request topic (works for all print sources)
    stored_ams_mapping = data.get("ams_mapping")
    registered_mapping = None
    if archive_id and not previous_run:
        registered_mapping = _print_ams_mappings.pop((printer_id, archive_id), None)
    if not stored_ams_mapping:
        stored_ams_mapping = registered_mapping

    # Always drain the plate_id register on completion — the session already
    # consumed it at print-start injection; leaving it would leak into the next
    # print on the same archive_id (rare but possible with reprints) (#1697).
    # Capture the popped value so the completion notification can scope the
    # archive-level (summed-across-plates per #1593) filament + time totals
    # down to the single plate that was actually printed (#1785).
    notify_plate_id: int | None = None
    if archive_id and not previous_run:
        notify_plate_id = _print_plate_ids.pop((printer_id, archive_id), None)
    run_plate = active_run.plate_id if active_run is not None else None
    if run_plate is None:
        run_plate = getattr(completion_session, "plate_id", None)
    if type(run_plate) is not int or run_plate <= 0:
        run_plate = notify_plate_id

    if archive_id:
        await settle_archive_cost_estimate(archive_id)

    # Keep completion on the inventory path fixed at print start.
    spoolman_owns_completion = await print_provenance.resolve_completed_print_owner(completion_session, async_session)
    try:
        if not spoolman_owns_completion:
            from backend.app.services.usage_tracker import on_print_complete as usage_on_print_complete

            async with async_session() as db:
                usage_results = await usage_on_print_complete(
                    printer_id,
                    data,
                    printer_manager,
                    db,
                    archive_id=archive_id,
                    ams_mapping=stored_ams_mapping,
                    claimed_session=completion_session,
                    session_claimed=True,
                )
                if usage_results:
                    await ws_manager.broadcast(
                        {
                            "type": "spool_usage_logged",
                            "printer_id": printer_id,
                            "usage": usage_results,
                        }
                    )
                    log_timing("Usage tracker")

    except Exception as e:
        logger.warning("Usage tracker on_print_complete failed: %s", e)

    await print_provenance.discard_print_session(printer_id, completion_session, logger)
    if archive_id and spoolman_owns_completion:
        if data.get("status") == "completed":
            try:
                spoolman_run_cost = await _report_spoolman_usage(
                    printer_id, archive_id, spool_change_log=getattr(completion_session, "spool_change_log", None)
                )
                log_timing("Spoolman usage report")
            except Exception as e:
                logger.warning("Spoolman usage reporting failed: %s", e)
        else:
            # Report partial usage if tracking data exists (only stored when weight sync is disabled)
            try:
                async with async_session() as db:
                    spoolman_run_cost = await _cleanup_spoolman_tracking(
                        printer_id,
                        archive_id,
                        db,
                        last_layer_num=data.get("last_layer_num"),
                        last_progress=data.get("last_progress"),
                        spool_change_log=getattr(completion_session, "spool_change_log", None),
                        status=data.get("status") or "failed",
                    )
            except Exception as e:
                logger.debug("[SPOOLMAN] Cleanup failed: %s", e)
        await _release_archived_spoolman_slots(printer_id)

    log_timing("Filament usage tracking")

    if not archive_id:
        logger.warning("Could not find archive for print complete: filename=%s, subtask=%s", filename, subtask_name)

        # Still send print-complete/failed/stopped notifications even without an archive.
        # Try to enrich with queue/library-file data so user-specific emails work too.
        async def _notify_no_archive():
            try:
                async with async_session() as db:
                    from backend.app.models.library import LibraryFile
                    from backend.app.models.print_queue import PrintQueueItem
                    from backend.app.models.printer import Printer

                    result = await db.execute(select(Printer).where(Printer.id == printer_id))
                    printer_obj = result.scalar_one_or_none()
                    p_name = printer_obj.name if printer_obj else f"Printer {printer_id}"

                    # Only the queue row closed by this completion can supply its owner and times.
                    no_archive_data: dict | None = None
                    try:
                        queue_item = await db.get(PrintQueueItem, queue_item_id) if queue_item_id else None
                        if queue_item:
                            no_archive_data = {"created_by_id": queue_item.created_by_id}
                            started = to_naive_utc(queue_item.started_at)
                            ended = to_naive_utc(queue_item.completed_at)
                            if not data.get("_reconciled") and started and ended and ended > started:
                                no_archive_data["actual_time_seconds"] = int((ended - started).total_seconds())
                            estimate = queue_item.print_time_seconds
                            if not estimate and queue_item.library_file_id:
                                library_file = await db.get(LibraryFile, queue_item.library_file_id)
                                if library_file:
                                    estimate = (library_file.file_metadata or {}).get("print_time_seconds")
                            if estimate:
                                no_archive_data["print_time_seconds"] = estimate
                    except Exception as lookup_err:
                        logger.debug(
                            "[NOTIFY-BG] Could not look up queue item for no-archive notification: %s", lookup_err
                        )

                    # Enrich with usage tracker results (captured in enclosing scope)
                    if usage_results:
                        if no_archive_data is None:
                            no_archive_data = {}
                        total_from_usage = sum(r.get("weight_used", 0) for r in usage_results)
                        if total_from_usage > 0:
                            no_archive_data["actual_filament_grams"] = round(total_from_usage, 1)
                        no_archive_data["usage_results"] = usage_results

                    # Try MQTT remaining_time for print duration when no queue/library data
                    if (
                        no_archive_data
                        and not data.get("_reconciled")
                        and not no_archive_data.get("print_time_seconds")
                    ):
                        mqtt_remaining = data.get("remaining_time")
                        if mqtt_remaining and isinstance(mqtt_remaining, (int, float)) and mqtt_remaining > 0:
                            no_archive_data["print_time_seconds"] = int(mqtt_remaining)

                    ps = data.get("status", "completed")
                    logger.info(
                        "[NOTIFY-BG] Sending notification without archive: printer=%s, status=%s", printer_id, ps
                    )
                    await notification_service.on_print_complete(
                        printer_id, p_name, ps, data, db, archive_data=no_archive_data
                    )

                    # Send user-specific email if we have a created_by_id
                    if no_archive_data and no_archive_data.get("created_by_id"):
                        raw_filename = data.get("subtask_name") or data.get("filename", "Unknown")
                        await _dispatch_user_print_email(
                            ps,
                            no_archive_data["created_by_id"],
                            p_name,
                            raw_filename,
                            db,
                        )
                    logger.info("[NOTIFY-BG] Completed (no-archive path)")
            except Exception as e:
                logger.warning("[NOTIFY-BG] Failed to send notification without archive: %s", e, exc_info=True)

        spawn_background_task(_notify_no_archive(), name="notify-no-archive")
        return

    log_timing("Archive lookup")

    status = data.get("status", "completed")
    hms_errors = data.get("hms_errors", []) if status == "failed" else None
    failure_reason = derive_failure_reason(status, hms_errors)
    if data.get("_reconciled") and (status == "aborted" or (status == "failed" and not failure_reason)):
        failure_reason = "noStatusUpdate"
    completed_at = data.get("_reconciled_completed_at") or datetime.now(timezone.utc)

    async def persist_completed_run(db):
        from backend.app.models.archive import PrintArchive
        from backend.app.models.print_log import INCLUDE_OPEN_RUNS, RUN_OPEN, PrintLogEntry
        from backend.app.models.printer import Printer
        from backend.app.services.print_account_ownership import existing_print_owner_id
        from backend.app.services.print_log import write_log_entry
        from backend.app.services.print_log_run import entry_of_run, project_latest_finished_run

        archive = await db.get(PrintArchive, archive_id, with_for_update=True)
        if archive:
            # Back-fill created_by_id on reprint (#730): reprint reuses the
            # source archive row rather than creating a new one, so an
            # archive that was auto-created from a printer-initiated
            # print (created_by_id=NULL) would otherwise stay unattributed
            # forever. When we have a print-session user AND the archive
            # has no attribution yet, credit the current user. Never
            # overwrite the original uploader.
            _print_user_id = await existing_print_owner_id(db, (_print_user_info or {}).get("user_id"))
            if archive.created_by_id is None and _print_user_id is not None:
                archive.created_by_id = _print_user_id
            p_info = printer_manager.get_printer(printer_id)
            # Per-run actuals — written to PrintLogEntry so stats reflect
            # what THIS print actually used, not the source archive's
            # first-run values (#1378). Helper handles the partial-print
            # math (failed / cancelled / stopped get scaled to progress
            # or to tracked spool deltas).
            from backend.app.services.print_cost_estimate import plate_scoped_run_estimate
            from backend.app.services.running_print_archive import local_archive_file

            plate_for_run = run_plate
            if plate_for_run is None and queue_item_id is not None:
                from backend.app.models.print_queue import PrintQueueItem

                item = await db.get(PrintQueueItem, queue_item_id)
                plate_for_run = item.plate_id if item is not None else None
            if plate_for_run is None and active_run is None and archive.printer_id == printer_id:
                plate_for_run = archive.plate_id
            estimate_grams, estimate_cost = await asyncio.to_thread(
                plate_scoped_run_estimate, archive, local_archive_file(archive, app_settings.base_dir), plate_for_run
            )
            _run_grams = _compute_run_filament_grams(
                status,
                estimate_grams,
                data.get("progress"),
                usage_results,
            )

            # Partial runs use measured spool usage without topping up to the estimate.
            _run_cost = resolve_print_log_cost(spoolman_run_cost, usage_results, status, estimate_cost)

            if active_run is not None:
                previous = await db.get(PrintLogEntry, active_run.id, execution_options={INCLUDE_OPEN_RUNS: True})
            else:
                previous = await entry_of_run(db, archive_id, printer_id, archive.started_at)
            announce_run = previous is None or previous.status == RUN_OPEN
            run = await write_log_entry(
                db,
                run_id=active_run.id if active_run is not None else None,
                archive_id=archive.id,
                # Captured by _update_queue_status above; None for
                # printer-initiated prints with no queue row. Batch
                # cost/energy roll-up joins on it (#342).
                queue_item_id=queue_item_id or (active_run.queue_item_id if active_run else None),
                status=status,
                print_name=active_run.print_name if active_run is not None else archive.print_name,
                printer_name=p_info.name if p_info else None,
                printer_id=printer_id,
                plate_id=plate_for_run,
                started_at=active_run.started_at if active_run is not None else archive.started_at,
                completed_at=completed_at,
                filament_type=active_run.filament_type if active_run is not None else archive.filament_type,
                filament_color=active_run.filament_color if active_run is not None else archive.filament_color,
                filament_used_grams=_run_grams,
                cost=_run_cost,
                failure_reason=failure_reason,
                thumbnail_path=archive.thumbnail_path,
                created_by_id=active_run.created_by_id if active_run is not None else archive.created_by_id,
                created_by_username=_print_user_info.get("username") if _print_user_id is not None else None,
                reconciled=bool(data.get("_reconciled")) and not data.get("_reconciled_completed_at"),
                duration_unmeasured=bool(data.get("_reconciled")),
            )
            archive_status = await project_latest_finished_run(db, archive)
            event_printer = await db.get(Printer, printer_id) if announce_run else None
            await db.commit()
            return run, archive_status, event_printer
        return None, None, None

    completed_run_id = None
    try:
        finished_run, archive_status, event_printer = await run_with_retry(
            persist_completed_run, label="print run completion", session_factory=async_session
        )
        if finished_run is not None:
            completed_run_id = finished_run.id
            if event_printer is not None:
                await mqtt_relay.on_run_event("completed", finished_run, event_printer)
        if archive_status is not None:
            await ws_manager.send_archive_updated({"id": archive_id, "status": archive_status})
            await mqtt_relay.on_archive_updated(
                archive_id=archive_id, print_name=filename or subtask_name, status=archive_status
            )
    except Exception:
        logger.warning("Could not finish or announce print run for archive %s", archive_id, exc_info=True)

    if completed_run_id is not None:
        try:
            async with async_session() as db:
                if status == "completed":
                    from backend.app.services.print_confirmation import send_outcome_confirmation_hint

                    await send_outcome_confirmation_hint(db, archive_id, completed_run_id, printer_id)
                if queue_item_id is not None:
                    from backend.app.services.print_batch import refresh_batch_status_for_item

                    await refresh_batch_status_for_item(db, queue_item_id)
                    await db.commit()
        except Exception:
            logger.warning("Could not process print run %s outcome", completed_run_id, exc_info=True)

    log_timing("Print log entry")

    # Slow operations run in the background so completion does not freeze the UI.

    async def _background_energy_calculation():
        await calculate_print_energy(
            printer_id,
            archive_id,
            logger,
            async_session=async_session,
            read_printer_energy=read_printer_energy,
            _get_plug_energy=_get_plug_energy,
            run_id=completed_run_id if not previous_run else None,
        )

    async def _background_finish_photo() -> str | None:
        """Capture finish photo in background. Returns photo filename if captured."""
        if previous_run:
            return None
        try:
            logger.info("[PHOTO-BG] Starting finish photo capture for archive %s", archive_id)

            from backend.app.api.routes.camera import live_frame_for_capture
            from backend.app.services.print_run_media import (
                later_print_on_printer,
                media_directory,
                record_finish_photo,
                run_of,
            )
            from backend.app.utils.safe_path import safe_join_under

            async with async_session() as db:
                from backend.app.api.routes.settings import get_setting

                capture_enabled = await get_setting(db, "capture_finish_photo")

                if capture_enabled is None or capture_enabled.lower() == "true":
                    from backend.app.models.printer import Printer

                    result = await db.execute(select(Printer).where(Printer.id == printer_id))
                    printer = result.scalar_one_or_none()

                    if printer and archive_id:
                        from backend.app.models.archive import PrintArchive

                        result = await db.execute(select(PrintArchive).where(PrintArchive.id == archive_id))
                        archive = result.scalar_one_or_none()

                        if archive:
                            import uuid
                            from datetime import datetime

                            archive_dir = media_directory(archive, app_settings)
                            photo_filename = None
                            from_timelapse = False
                            exact_run = (
                                await run_of(db, archive_id, completed_run_id, printer_id=printer_id)
                                if completed_run_id
                                else None
                            )

                            # Prefer the timelapse last-frame source when a timelapse was
                            # recording — it captures the moment after the toolhead parks
                            # but before the bed drops, which the live-camera grab below
                            # would miss (#1397). Skipped for external cameras (those have
                            # their own framing and don't see a Bambu timelapse). Only
                            # runs when the USER explicitly enabled timelapse for this
                            # print — #1721 removed PrintOps's force-on at dispatch
                            # because it caused per-layer nozzle parking on Smooth-mode
                            # slicer profiles.
                            prefer_timelapse_source = bool(data.get("timelapse_was_active")) and not (
                                printer.external_camera_enabled and printer.external_camera_url
                            )

                            if prefer_timelapse_source:
                                photo_filename = await _capture_finish_photo_from_timelapse(
                                    archive_id=archive_id,
                                    archive_dir=archive_dir,
                                    rotation=getattr(printer, "camera_rotation", 0) or 0,
                                    **({"run_id": completed_run_id} if completed_run_id is not None else {}),
                                )
                                from_timelapse = photo_filename is not None
                            if not from_timelapse and await later_print_on_printer(db, exact_run):
                                return None

                            # #1721: replacement framing path — on_finish_photo_moment
                            # pre-captured a frame at the stage-22 / FINISH edge (toolhead
                            # parked, bed not yet dropped) and cached the JPEG bytes in
                            # _stage22_finish_frames. Consume them now so the saved photo
                            # has the better framing instead of the post-bed-drop angle
                            # the live-camera fallback below would give.
                            if not photo_filename:
                                # #1790: on the FINISH-state fallback path the producer
                                # task is dispatched back-to-back with this consumer, so
                                # a bare pop would race past with an empty result and
                                # the RTSP fallback below would collide with the
                                # producer's still-in-flight grab (single-client RTSP
                                # on Bambu printers). Wait for the producer to finish
                                # or give up before touching the cache.
                                in_flight = _stage22_finish_in_flight.get(printer_id)
                                if in_flight is not None:
                                    try:
                                        await asyncio.wait_for(in_flight.wait(), timeout=20.0)
                                    except asyncio.TimeoutError:
                                        logger.warning(
                                            "[PHOTO-BG] timed out waiting for stage-22 producer for printer %s — proceeding to fallback",
                                            printer_id,
                                        )
                                cached_frame = None
                                if _stage22_finish_in_flight.get(printer_id) is in_flight:
                                    _stage22_finish_in_flight.pop(printer_id, None)
                                    cached_frame = _stage22_finish_frames.pop(printer_id, None)
                                if cached_frame:
                                    photos_dir = archive_dir / "photos"
                                    photos_dir.mkdir(parents=True, exist_ok=True)
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    photo_filename = f"finish_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
                                    photo_path = photos_dir / photo_filename
                                    await asyncio.to_thread(photo_path.write_bytes, cached_frame)
                                    logger.info(
                                        "[PHOTO-BG] Saved stage-22 pre-captured frame: %s (%d bytes)",
                                        photo_filename,
                                        len(cached_frame),
                                    )

                            # Fallback chain: external camera → buffered live frame →
                            # fresh RTSP capture. Only runs if the timelapse path above
                            # didn't already produce a photo.
                            if not photo_filename:
                                async with automatic_camera_light(printer, wait=True):
                                    if printer.external_camera_enabled and printer.external_camera_url:
                                        logger.info("[PHOTO-BG] Using external camera")
                                        from backend.app.services.external_camera import capture_frame

                                        frame_data = await capture_frame(
                                            printer.external_camera_url,
                                            printer.external_camera_type or "mjpeg",
                                            snapshot_url=printer.external_camera_snapshot_url,
                                            printer_id=printer_id,
                                        )
                                        if frame_data:
                                            frame_data = _apply_camera_rotation(frame_data, printer, logger)
                                            photos_dir = archive_dir / "photos"
                                            photos_dir.mkdir(parents=True, exist_ok=True)
                                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                            photo_filename = f"finish_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
                                            photo_path = photos_dir / photo_filename
                                            await asyncio.to_thread(photo_path.write_bytes, frame_data)
                                            logger.info("[PHOTO-BG] Saved external camera frame: %s", photo_filename)
                                    else:
                                        # Check if camera stream is active - use buffered frame to avoid freeze
                                        watched, buffered_frame = await live_frame_for_capture(printer_id)

                                        if buffered_frame:
                                            buffered_frame = _apply_camera_rotation(buffered_frame, printer, logger)
                                            # Use frame from active stream
                                            logger.info("[PHOTO-BG] Using buffered frame from active stream")
                                            photos_dir = archive_dir / "photos"
                                            photos_dir.mkdir(parents=True, exist_ok=True)
                                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                            photo_filename = f"finish_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
                                            photo_path = photos_dir / photo_filename
                                            await asyncio.to_thread(photo_path.write_bytes, buffered_frame)
                                            logger.info("[PHOTO-BG] Saved buffered frame: %s", photo_filename)
                                        elif not watched:
                                            # No active stream - capture new frame
                                            from backend.app.services.camera import capture_finish_photo

                                            photo_filename = await capture_finish_photo(
                                                printer_id=printer_id,
                                                ip_address=printer.ip_address,
                                                access_code=printer.access_code,
                                                model=printer.model,
                                                archive_dir=archive_dir,
                                                rotation=getattr(printer, "camera_rotation", 0) or 0,
                                            )

                            if photo_filename:
                                still_current = from_timelapse or not await later_print_on_printer(db, exact_run)
                                if still_current and await record_finish_photo(
                                    db, archive_id, photo_filename, run_id=completed_run_id, printer_id=printer_id
                                ):
                                    logger.info("[PHOTO-BG] Saved: %s", photo_filename)
                                    if completed_run_id is not None and prefer_timelapse_source and not from_timelapse:
                                        spawn_background_task(
                                            _upgrade_finish_photo_from_timelapse(
                                                archive_id,
                                                completed_run_id,
                                                archive_dir,
                                                getattr(printer, "camera_rotation", 0) or 0,
                                                photo_filename,
                                                logger,
                                            ),
                                            name=f"upgrade-finish-photo-{completed_run_id}",
                                        )
                                    return photo_filename
                                unclaimed = safe_join_under(archive_dir, "photos", photo_filename)
                                await asyncio.to_thread(unclaimed.unlink, missing_ok=True)
            return None
        except Exception as e:
            logger.warning("[PHOTO-BG] Failed: %s", e)
            return None

    spawn_background_task(_background_energy_calculation(), name="background-energy-calc")
    # Photo capture task - result will be used by notifications
    photo_task = spawn_background_task(_background_finish_photo(), name="background-finish-photo")
    log_timing("Background tasks scheduled (energy, photo)")

    # Also run smart plug, notifications, and maintenance as background tasks
    print_status = data.get("status", "completed")

    async def _background_smart_plug():
        """Handle smart plug automation in background."""
        try:
            logger.info("[AUTO-OFF-BG] Starting smart plug automation for printer %s", printer_id)
            async with async_session() as db:
                await smart_plug_manager.on_print_complete(printer_id, print_status, db)
                logger.info("[AUTO-OFF-BG] Completed")
        except Exception as e:
            logger.warning("[AUTO-OFF-BG] Failed: %s", e)

    async def _background_notifications(finish_photo_filename: str | None = None):
        """Send print complete notifications in background."""
        try:
            logger.info(
                "[NOTIFY-BG] Starting notifications for printer %s, photo=%s", printer_id, finish_photo_filename
            )
            async with async_session() as db:
                from backend.app.models.archive import PrintArchive
                from backend.app.models.print_log import PrintLogEntry
                from backend.app.models.printer import Printer
                from backend.app.services.archive_plate_estimates import archive_run_estimate

                result = await db.execute(select(Printer).where(Printer.id == printer_id))
                printer = result.scalar_one_or_none()
                printer_name = printer.name if printer else f"Printer {printer_id}"

                archive_data = None
                if archive_id:
                    archive_result = await db.execute(select(PrintArchive).where(PrintArchive.id == archive_id))
                    archive = archive_result.scalar_one_or_none()
                    if archive:
                        finished = await db.get(PrintLogEntry, completed_run_id) if completed_run_id else None
                        actual_time_seconds = (finished.duration_seconds or None) if finished is not None else None
                        plate_for_run = finished.plate_id if finished is not None else run_plate
                        estimated_seconds, _ = archive_run_estimate(archive, plate_for_run)
                        archive_data = {
                            "archive_id": archive.id,
                            "run_id": completed_run_id,
                            "print_time_seconds": estimated_seconds,
                            "actual_time_seconds": actual_time_seconds,
                            "actual_filament_grams": archive.filament_used_grams,
                            "failure_reason": finished.failure_reason if finished is not None else failure_reason,
                            "created_by_id": finished.created_by_id if finished is not None else archive.created_by_id,
                        }

                        # Scale filament usage for partial prints
                        if print_status != "completed" and archive.filament_used_grams:
                            progress = data.get("progress") or 0
                            scale = _partial_progress_scale(progress)
                            archive_data["actual_filament_grams"] = round(archive.filament_used_grams * scale, 1)
                            archive_data["progress"] = progress

                        # Pass per-slot data from archive.extra_data
                        if archive.extra_data and archive.extra_data.get("filament_slots"):
                            slots = archive.extra_data["filament_slots"]
                            if print_status != "completed":
                                scale = _partial_progress_scale(data.get("progress"))
                                slots = [{**s, "used_g": round(s["used_g"] * scale, 1)} for s in slots]
                            archive_data["filament_slots"] = slots

                        # Scope project-summed totals down to the plate that was
                        # actually printed — see _scope_notification_archive_data_to_plate
                        # for the why (#1785).
                        archive_data = _scope_notification_archive_data_to_plate(
                            archive_data,
                            archive.file_path,
                            plate_for_run,
                            print_status,
                            data.get("progress"),
                            app_settings.base_dir,
                        )

                        if finished is not None:
                            archive_data["actual_filament_grams"] = finished.filament_used_grams

                        # Enrich filament_grams from usage_results when archive has no 3MF data
                        if not archive_data.get("actual_filament_grams") and usage_results:
                            total_from_usage = sum(r.get("weight_used", 0) for r in usage_results)
                            if total_from_usage > 0:
                                archive_data["actual_filament_grams"] = round(total_from_usage, 1)

                        # Pass usage tracker results for AMS slot info in notifications
                        if usage_results:
                            archive_data["usage_results"] = usage_results
                        # Add finish photo URL and image bytes if available
                        if finish_photo_filename:
                            from backend.app.services.notification_photos import finish_photo_for_notification

                            try:
                                photo_url, photo_bytes = await finish_photo_for_notification(
                                    db, archive, finish_photo_filename
                                )
                                if photo_url:
                                    archive_data["finish_photo_url"] = photo_url
                                if photo_bytes:
                                    archive_data["image_data"] = photo_bytes
                            except Exception:
                                await db.rollback()
                                await db.refresh(archive)
                                logger.warning("[NOTIFY-BG] Could not prepare finish photo; sending text notification")

                await notification_service.on_print_complete(
                    printer_id, printer_name, print_status, data, db, archive_data=archive_data
                )

                if print_status == "completed" and completed_run_id is not None:
                    from backend.app.services.print_confirmation import dispatch_outcome_confirmation

                    try:
                        await dispatch_outcome_confirmation(
                            db, archive_id, printer_id, printer_name, run_id=completed_run_id, notify_user=False
                        )
                    except Exception:
                        # Inspection remains available in the archive UI. An
                        # optional prompt must not interrupt existing user emails.
                        logger.warning(
                            "[OUTCOME] Could not prompt inspection for archive %s", archive_id, exc_info=True
                        )

                # Send user-specific email notification
                if archive_data:
                    created_by_id = archive_data.get("created_by_id")
                    raw_filename = data.get("subtask_name") or data.get("filename", "Unknown")
                    await _dispatch_user_print_email(
                        print_status,
                        created_by_id,
                        printer_name,
                        raw_filename,
                        db,
                    )

                logger.info("[NOTIFY-BG] Completed")
        except Exception as e:
            logger.error("[NOTIFY-BG] Failed: %s", e, exc_info=True)

    async def _background_maintenance_check():
        await check_print_maintenance(
            printer_id,
            print_status,
            logger,
            async_session=async_session,
            ensure_default_types=ensure_default_types,
            _get_printer_maintenance_internal=_get_printer_maintenance_internal,
            notification_service=notification_service,
            mqtt_relay=mqtt_relay,
        )

    if not previous_run:
        spawn_background_task(_background_smart_plug(), name="background-smart-plug")
    spawn_background_task(_background_maintenance_check(), name="background-maintenance-check")

    # Notification task waits for photo capture to complete first (with timeout).
    # When a timelapse was recording, photo sourcing polls the per-print
    # timelapse for up to 60s (#1397) — extend the budget so the notification
    # carries the correct bed-up photo instead of falling through to the
    # live-cam grab. Adds ~30s of notification latency at worst on slow links.
    photo_wait_timeout = 75 if data.get("timelapse_was_active") else 45

    async def _photo_then_notify():
        """Wait for photo capture, then send notification with photo URL."""
        finish_photo = None
        try:
            finish_photo = await asyncio.wait_for(photo_task, timeout=photo_wait_timeout)
            logger.info("[PHOTO-NOTIFY] Photo task returned: %s", finish_photo)
        except TimeoutError:
            logger.warning(
                "[PHOTO-NOTIFY] Photo capture timed out after %ss, sending notification without photo",
                photo_wait_timeout,
            )
        except Exception as e:
            logger.warning("[PHOTO-NOTIFY] Photo task failed: %s", e)
        try:
            await _background_notifications(finish_photo)
        except Exception as e:
            logger.error("[PHOTO-NOTIFY] Notification sending failed: %s", e, exc_info=True)

    spawn_background_task(_photo_then_notify(), name="photo-then-notify")

    # Stitch external camera layer timelapse if session was active
    print_status = data.get("status", "completed")

    async def _background_layer_timelapse():
        await complete_layer_timelapse(
            printer_id,
            print_status,
            archive_id,
            logger,
            async_session=async_session,
            ArchiveService=ArchiveService,
            asyncio=asyncio,
            expected_session=camera_session,
            plate_id=run_plate,
            run_id=completed_run_id,
        )

    if camera_session is not None and not previous_run:
        spawn_background_task(_background_layer_timelapse(), name="background-layer-timelapse")

    log_timing("All background tasks scheduled")

    # Retire memory; the archive keeps the restart-safe snapshot.
    baseline = _timelapse_baselines.pop(printer_id, None) if not previous_run else None

    if archive_id and not previous_run and data.get("timelapse_was_active") and print_status == "completed":
        logger.info("[TIMELAPSE] Timelapse was active during print, scheduling auto-scan for archive %s", archive_id)
        # Schedule timelapse scan as background task with retries
        # The printer needs time to encode the video after print completion
        spawn_background_task(
            _scan_for_timelapse_with_retries(archive_id, baseline, plate_id=run_plate, run_id=completed_run_id),
            name=f"scan-timelapse-{archive_id}",
        )
        log_timing("Timelapse scan scheduled")

    logger.info("[CALLBACK] on_print_complete finished for printer %s, archive %s", printer_id, archive_id)


# AMS sensor history recording
_ams_history_task: asyncio.Task | None = None
AMS_HISTORY_INTERVAL = 300  # Record every 5 minutes
AMS_HISTORY_RETENTION_DAYS = 30  # Keep data for 30 days
_ams_cleanup_counter = 0  # Track recordings to trigger periodic cleanup
# Track alarm cooldowns (printer_id:ams_id:type -> last_alarm_time)
_ams_alarm_cooldown: dict[str, datetime] = {}
AMS_ALARM_COOLDOWN_MINUTES = 60  # Don't send same alarm more than once per hour


def _ams_has_filament(ams_data: dict) -> bool:
    """True if this AMS unit has at least one tray slot holding filament.

    Bambu firmware reports loaded slots via `tray_exist_bits`, a per-AMS hex
    bitmap (one bit per tray slot — bit set = spool present). Empty AMS units
    still report sensor readings, but those readings are ambient and not
    actionable: no filament to dry, no humidity to push down. #1619 — gate
    humidity/temperature alarms on this check so empty units don't generate
    hourly noise. Sensor history still records regardless so the UI charts
    stay continuous.

    Fallback path inspects the `tray` array's `tray_type` fields for setups
    where `tray_exist_bits` is missing (some early-connection pushall shapes).
    """
    bits = ams_data.get("tray_exist_bits")
    if isinstance(bits, str) and bits.strip():
        try:
            return int(bits, 16) > 0
        except ValueError:
            pass
    trays = ams_data.get("tray")
    if isinstance(trays, list):
        return any(
            isinstance(t, dict) and isinstance(t.get("tray_type"), str) and t["tray_type"].strip() for t in trays
        )
    return False


async def record_ams_history():
    """Background task to record AMS humidity and temperature data."""
    logger = logging.getLogger(__name__)

    # Wait a short time for MQTT connections to establish on startup
    await asyncio.sleep(10)

    while True:
        try:
            from backend.app.models.ams_history import AMSSensorHistory
            from backend.app.models.printer import Printer
            from backend.app.models.settings import Settings

            async with async_session() as db:
                # Get all active printers
                result = await db.execute(select(Printer).where(Printer.is_active.is_(True)))
                printers = result.scalars().all()

                # Get alarm thresholds from settings
                humidity_threshold = 60.0  # Default: fair threshold
                temp_threshold = 35.0  # Default: fair threshold
                result = await db.execute(select(Settings).where(Settings.key == "ams_humidity_fair"))
                setting = result.scalar_one_or_none()
                if setting:
                    try:
                        humidity_threshold = float(setting.value)
                    except (ValueError, TypeError):
                        pass  # Keep default threshold if stored value is invalid
                result = await db.execute(select(Settings).where(Settings.key == "ams_temp_fair"))
                setting = result.scalar_one_or_none()
                if setting:
                    try:
                        temp_threshold = float(setting.value)
                    except (ValueError, TypeError):
                        pass  # Keep default threshold if stored value is invalid

                # Per-filament humidity threshold overrides (#1605) — resolved
                # per-AMS below from the loaded tray types. Reuses the same
                # resolver as the auto-drying scheduler so behavior stays in
                # lockstep across both consumers.
                from backend.app.services.print_scheduler import PrintScheduler

                per_type_humidity_thresholds: dict[str, int] = {}
                result = await db.execute(select(Settings).where(Settings.key == "ams_humidity_thresholds"))
                setting = result.scalar_one_or_none()
                if setting and setting.value:
                    try:
                        raw = json.loads(setting.value)
                        if isinstance(raw, dict):
                            for k, v in raw.items():
                                try:
                                    per_type_humidity_thresholds[str(k).upper() if k != "default" else "default"] = int(
                                        v
                                    )
                                except (TypeError, ValueError):
                                    continue
                    except (ValueError, TypeError):
                        pass  # Invalid JSON → no overrides, fall through to global threshold

                recorded_count = 0
                for printer in printers:
                    # Get current state from printer manager
                    state = printer_manager.get_status(printer.id)
                    if not state or not state.connected or not state.raw_data:
                        continue  # Skip disconnected printers - don't use stale data

                    raw_data = state.raw_data
                    if "ams" not in raw_data or not isinstance(raw_data["ams"], list):
                        continue

                    # Record data for each AMS unit
                    for ams_data in raw_data["ams"]:
                        ams_id = int(ams_data.get("id", 0))

                        # Get humidity (prefer humidity_raw)
                        humidity_raw = ams_data.get("humidity_raw")
                        humidity_idx = ams_data.get("humidity")
                        humidity = None
                        if humidity_raw is not None:
                            try:
                                humidity = float(humidity_raw)
                            except (ValueError, TypeError):
                                pass  # Skip unparseable humidity; will try fallback
                        if humidity is None and humidity_idx is not None:
                            try:
                                humidity = float(humidity_idx)
                            except (ValueError, TypeError):
                                pass  # Skip unparseable humidity index value

                        # Get temperature
                        temperature = None
                        temp_str = ams_data.get("temp")
                        if temp_str is not None:
                            try:
                                temperature = float(temp_str)
                            except (ValueError, TypeError):
                                pass  # Skip unparseable temperature value

                        # Skip if no data
                        if humidity is None and temperature is None:
                            continue

                        # Record the data point
                        history = AMSSensorHistory(
                            printer_id=printer.id,
                            ams_id=ams_id,
                            humidity=humidity,
                            humidity_raw=float(humidity_raw) if humidity_raw else None,
                            temperature=temperature,
                        )
                        db.add(history)
                        recorded_count += 1

                        # Generate AMS label and determine if it's AMS-HT (A, B, C, D or HT-A for AMS-Lite/Hub)
                        is_ams_ht = ams_id >= 128
                        if is_ams_ht:
                            ams_label = f"HT-{chr(65 + (ams_id - 128))}"
                        else:
                            ams_label = f"AMS-{chr(65 + ams_id)}"

                        # Skip alarm dispatch for empty AMS units — humidity /
                        # temperature readings are ambient with no filament to
                        # protect, and the hourly notification just becomes
                        # noise. Sensor history was already recorded above so
                        # the UI charts stay continuous (#1619). Per-AMS check
                        # so a multi-AMS setup with one loaded + one empty
                        # still alarms on the loaded unit.
                        if not _ams_has_filament(ams_data):
                            continue

                        # Resolve per-filament humidity threshold for this AMS
                        # unit (#1605). Falls back to the global ams_humidity_fair
                        # when no per-type overrides are configured.
                        trays = ams_data.get("tray", []) or []
                        effective_humidity_threshold = float(
                            PrintScheduler.resolve_humidity_threshold(
                                trays, per_type_humidity_thresholds, int(humidity_threshold)
                            )
                        )

                        # Check humidity alarm (only if above threshold)
                        if humidity is not None and humidity > effective_humidity_threshold:
                            cooldown_key = f"{printer.id}:{ams_id}:humidity"
                            last_alarm = _ams_alarm_cooldown.get(cooldown_key)
                            now = datetime.now(timezone.utc)
                            if (
                                last_alarm is None
                                or (now - last_alarm).total_seconds() >= AMS_ALARM_COOLDOWN_MINUTES * 60
                            ):
                                _ams_alarm_cooldown[cooldown_key] = now
                                logger.info(
                                    f"Sending humidity alarm for {printer.name} {ams_label}: {humidity}% > {effective_humidity_threshold}%"
                                )
                                try:
                                    # Call different notification method based on AMS type
                                    if is_ams_ht:
                                        await notification_service.on_ams_ht_humidity_high(
                                            printer.id,
                                            printer.name,
                                            ams_label,
                                            humidity,
                                            effective_humidity_threshold,
                                            db,
                                        )
                                    else:
                                        await notification_service.on_ams_humidity_high(
                                            printer.id,
                                            printer.name,
                                            ams_label,
                                            humidity,
                                            effective_humidity_threshold,
                                            db,
                                        )
                                except Exception as e:
                                    logger.warning("Failed to send humidity alarm: %s", e)

                        # Check temperature alarm (only if above threshold)
                        if temperature is not None and temperature > temp_threshold:
                            cooldown_key = f"{printer.id}:{ams_id}:temperature"
                            last_alarm = _ams_alarm_cooldown.get(cooldown_key)
                            now = datetime.now(timezone.utc)
                            if (
                                last_alarm is None
                                or (now - last_alarm).total_seconds() >= AMS_ALARM_COOLDOWN_MINUTES * 60
                            ):
                                _ams_alarm_cooldown[cooldown_key] = now
                                logger.info(
                                    f"Sending temperature alarm for {printer.name} {ams_label}: {temperature}°C > {temp_threshold}°C"
                                )
                                try:
                                    # Call different notification method based on AMS type
                                    if is_ams_ht:
                                        await notification_service.on_ams_ht_temperature_high(
                                            printer.id, printer.name, ams_label, temperature, temp_threshold, db
                                        )
                                    else:
                                        await notification_service.on_ams_temperature_high(
                                            printer.id, printer.name, ams_label, temperature, temp_threshold, db
                                        )
                                except Exception as e:
                                    logger.warning("Failed to send temperature alarm: %s", e)

                await db.commit()
                if recorded_count > 0:
                    logger.info("Recorded %s AMS sensor history entries", recorded_count)

                # Periodic cleanup of old data (every ~288 recordings = ~24 hours at 5min interval)
                global _ams_cleanup_counter
                _ams_cleanup_counter += 1
                if _ams_cleanup_counter >= 288:
                    _ams_cleanup_counter = 0
                    from backend.app.models.settings import Settings

                    result = await db.execute(select(Settings).where(Settings.key == "ams_history_retention_days"))
                    setting = result.scalar_one_or_none()
                    cutoff = history_cutoff(
                        utcnow_naive(), setting.value if setting else None, AMS_HISTORY_RETENTION_DAYS
                    )
                    result = await db.execute(delete(AMSSensorHistory).where(AMSSensorHistory.recorded_at < cutoff))
                    await db.commit()
                    if result.rowcount > 0:
                        logger.info(
                            "Cleaned up %s old AMS sensor history entries before %s",
                            result.rowcount,
                            cutoff,
                        )

            # Wait until next recording interval
            await asyncio.sleep(AMS_HISTORY_INTERVAL)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("AMS history recording failed: %s", e)
            await asyncio.sleep(60)  # Wait a bit before retrying


def start_ams_history_recording():
    """Start the AMS history recording background task."""
    global _ams_history_task
    if _ams_history_task is None:
        _ams_history_task = asyncio.create_task(record_ams_history())
        logging.getLogger(__name__).info("AMS history recording started")


def stop_ams_history_recording():
    """Stop the AMS history recording background task."""
    global _ams_history_task
    if _ams_history_task:
        _ams_history_task.cancel()
        _ams_history_task = None
        logging.getLogger(__name__).info("AMS history recording stopped")


# Printer sensor history recording (nozzle / bed / chamber)
_printer_sensor_history_task: asyncio.Task | None = None
PRINTER_SENSOR_HISTORY_INTERVAL = 60  # Record every minute — heaters move faster than AMS humidity
PRINTER_SENSOR_HISTORY_RETENTION_DAYS = 30
_printer_sensor_cleanup_counter = 0
# Sensor kinds tracked in state.temperatures — these are the normalised keys the
# MQTT parser writes, so we don't need to handle per-model field aliases here
# (nozzle_temper / left_nozzle_temper / right_nozzle_temper / chamber_temper
# are all collapsed by services/bambu_mqtt.py before they reach this loop).
_SENSOR_KINDS = ("nozzle", "nozzle_2", "bed", "chamber")
_SENSOR_TARGET_KEYS = {
    "nozzle": "nozzle_target",
    "nozzle_2": "nozzle_2_target",
    "bed": "bed_target",
    "chamber": "chamber_target",
}


async def record_printer_sensor_history():
    """Background task to record nozzle / bed / chamber readings.

    Pulls from `state.temperatures` (already normalised across all printer
    models by the MQTT parser) rather than re-parsing raw_data, so we get
    free coverage of dual-nozzle H2D, sensor-only X1C chamber, etc.
    """
    logger = logging.getLogger(__name__)

    await asyncio.sleep(10)

    while True:
        try:
            from backend.app.models.printer import Printer
            from backend.app.models.printer_sensor_history import PrinterSensorHistory
            from backend.app.models.settings import Settings

            async with async_session() as db:
                result = await db.execute(select(Printer).where(Printer.is_active.is_(True)))
                printers = result.scalars().all()

                recorded_count = 0
                for printer in printers:
                    state = printer_manager.get_status(printer.id)
                    if not state or not state.connected:
                        continue

                    temps = getattr(state, "temperatures", None) or {}
                    if not isinstance(temps, dict):
                        continue

                    for kind in _SENSOR_KINDS:
                        if kind not in temps:
                            continue
                        try:
                            value = float(temps[kind])
                        except (ValueError, TypeError):
                            continue

                        target_raw = temps.get(_SENSOR_TARGET_KEYS[kind])
                        target_val: float | None = None
                        if target_raw is not None:
                            try:
                                target_val = float(target_raw)
                            except (ValueError, TypeError):
                                target_val = None

                        db.add(
                            PrinterSensorHistory(
                                printer_id=printer.id,
                                sensor_kind=kind,
                                value=value,
                                target=target_val,
                            )
                        )
                        recorded_count += 1

                await db.commit()
                if recorded_count > 0:
                    logger.debug("Recorded %s printer sensor history entries", recorded_count)

                # Periodic cleanup — once every ~24h at this interval.
                global _printer_sensor_cleanup_counter
                _printer_sensor_cleanup_counter += 1
                cleanup_every = max(1, (24 * 60 * 60) // PRINTER_SENSOR_HISTORY_INTERVAL)
                if _printer_sensor_cleanup_counter >= cleanup_every:
                    _printer_sensor_cleanup_counter = 0
                    result = await db.execute(
                        select(Settings).where(Settings.key == "printer_sensor_history_retention_days")
                    )
                    setting = result.scalar_one_or_none()
                    cutoff = history_cutoff(
                        utcnow_naive(), setting.value if setting else None, PRINTER_SENSOR_HISTORY_RETENTION_DAYS
                    )
                    cleanup = await db.execute(
                        delete(PrinterSensorHistory).where(PrinterSensorHistory.recorded_at < cutoff)
                    )
                    await db.commit()
                    if cleanup.rowcount > 0:
                        logger.info(
                            "Cleaned up %s old printer sensor history entries before %s",
                            cleanup.rowcount,
                            cutoff,
                        )

            await asyncio.sleep(PRINTER_SENSOR_HISTORY_INTERVAL)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("Printer sensor history recording failed: %s", e)
            await asyncio.sleep(60)


def start_printer_sensor_history_recording():
    global _printer_sensor_history_task
    if _printer_sensor_history_task is None:
        _printer_sensor_history_task = asyncio.create_task(record_printer_sensor_history())
        logging.getLogger(__name__).info("Printer sensor history recording started")


def stop_printer_sensor_history_recording():
    global _printer_sensor_history_task
    if _printer_sensor_history_task:
        _printer_sensor_history_task.cancel()
        _printer_sensor_history_task = None
        logging.getLogger(__name__).info("Printer sensor history recording stopped")


# Printer runtime tracking
_runtime_tracking_task: asyncio.Task | None = None
RUNTIME_TRACKING_INTERVAL = 30  # Update every 30 seconds
RUNTIME_STARTUP_GRACE_SECONDS = 120


async def track_printer_runtime():
    """Background task to track printer active runtime (RUNNING state only).

    PAUSE is intentionally excluded — the runtime counter feeds hours-based
    maintenance intervals (rod lubrication, belt checks, nozzle cleaning)
    which track mechanical wear. Pause time has no motion and no wear, so
    counting it inflates maintenance warnings (#1521).
    """
    logger = logging.getLogger(__name__)

    # Wait for MQTT connections to establish on startup.
    await asyncio.sleep(15)
    startup_deadline = time.monotonic() + RUNTIME_STARTUP_GRACE_SECONDS
    connections: dict[int, tuple[int, int] | None] = {}

    while True:
        try:
            from backend.app.models.printer import Printer

            # Fetch printer IDs in a short-lived read-only session
            async with async_session() as db:
                result = await db.execute(
                    select(Printer.id, Printer.name, Printer.runtime_seconds, Printer.last_runtime_update).where(
                        Printer.is_active.is_(True)
                    )
                )
                printer_rows = result.all()

            now = utcnow_naive()
            connections = {pid: connections[pid] for pid, *_ in printer_rows if pid in connections}

            # Keep each printer's write transaction short (#897).
            for pid, pname, runtime_secs, last_update in printer_rows:
                state = printer_manager.get_status(pid)
                online = state is not None and state.connected and state.state.upper() not in ("", "UNKNOWN")
                if online:
                    connection = (id(state), getattr(state, "connection_generation", 0))
                    continuous = pid not in connections or connections[pid] == connection
                    running = state.state == "RUNNING"
                else:
                    if pid not in connections and time.monotonic() < startup_deadline:
                        continue
                    # Remember an observed gap even if clearing the timestamp fails.
                    connections[pid] = None
                    connection = None
                    continuous = running = False

                if not running and last_update is None:
                    connections[pid] = connection
                    continue

                elapsed = 0
                if running and continuous and last_update is not None:
                    elapsed = max(0, int((now - to_naive_utc(last_update)).total_seconds()))
                try:
                    async with async_session() as db:
                        changed = await db.scalar(
                            update(Printer)
                            .where(
                                Printer.id == pid,
                                Printer.is_active.is_(True),
                                Printer.last_runtime_update == last_update,
                                Printer.runtime_seconds == runtime_secs,
                            )
                            .values(
                                runtime_seconds=runtime_secs + elapsed,
                                last_runtime_update=now if running else None,
                            )
                            .returning(Printer.id)
                        )
                        await db.commit()
                    if changed is not None:
                        connections[pid] = connection
                except Exception as exc:
                    logger.warning("[%s] Runtime tracking commit failed: %s", pname, exc)

        except asyncio.CancelledError:
            logger.info("Runtime tracking cancelled")
            break
        except Exception as e:
            logger.warning("Runtime tracking failed: %s", e)

        await asyncio.sleep(RUNTIME_TRACKING_INTERVAL)


def start_runtime_tracking():
    """Start the printer runtime tracking background task."""
    global _runtime_tracking_task
    if _runtime_tracking_task is None:
        _runtime_tracking_task = asyncio.create_task(track_printer_runtime())
        logging.getLogger(__name__).info("Printer runtime tracking started")


def stop_runtime_tracking():
    """Stop the printer runtime tracking background task."""
    global _runtime_tracking_task
    if _runtime_tracking_task:
        _runtime_tracking_task.cancel()
        _runtime_tracking_task = None
        logging.getLogger(__name__).info("Printer runtime tracking stopped")


# SpoolBuddy device watchdog
_spoolbuddy_watchdog_task: asyncio.Task | None = None
SPOOLBUDDY_WATCHDOG_INTERVAL = 15


async def _spoolbuddy_watchdog_loop():
    """Periodic check for SpoolBuddy devices that have gone offline."""
    from backend.app.api.routes.spoolbuddy import spoolbuddy_watchdog

    while True:
        try:
            await spoolbuddy_watchdog()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.getLogger(__name__).warning("SpoolBuddy watchdog failed: %s", e)
        await asyncio.sleep(SPOOLBUDDY_WATCHDOG_INTERVAL)


def start_spoolbuddy_watchdog():
    global _spoolbuddy_watchdog_task
    if _spoolbuddy_watchdog_task is None:
        _spoolbuddy_watchdog_task = asyncio.create_task(_spoolbuddy_watchdog_loop())
        logging.getLogger(__name__).info("SpoolBuddy watchdog started")


def stop_spoolbuddy_watchdog():
    global _spoolbuddy_watchdog_task
    if _spoolbuddy_watchdog_task:
        _spoolbuddy_watchdog_task.cancel()
        _spoolbuddy_watchdog_task = None
        logging.getLogger(__name__).info("SpoolBuddy watchdog stopped")


# Camera stream orphan cleanup
_camera_cleanup_task: asyncio.Task | None = None
CAMERA_CLEANUP_INTERVAL = 60


async def _camera_cleanup_loop():
    """Periodically clean up camera processes and abandoned frame directories."""
    from backend.app.api.routes.camera import cleanup_orphaned_streams
    from backend.app.services.layer_timelapse import cleanup_orphaned_timelapse_sessions

    rounds = 0
    while True:
        try:
            await cleanup_orphaned_streams()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.getLogger(__name__).warning("Camera stream cleanup failed: %s", e)
        if rounds % 60 == 0:
            try:
                await asyncio.to_thread(cleanup_orphaned_timelapse_sessions)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.getLogger(__name__).warning("Timelapse frame cleanup failed: %s", e)
        rounds += 1
        await asyncio.sleep(CAMERA_CLEANUP_INTERVAL)


def start_camera_cleanup():
    global _camera_cleanup_task
    if _camera_cleanup_task is None:
        _camera_cleanup_task = asyncio.create_task(_camera_cleanup_loop())
        logging.getLogger(__name__).info("Camera stream cleanup started")


def stop_camera_cleanup():
    global _camera_cleanup_task
    if _camera_cleanup_task:
        _camera_cleanup_task.cancel()
        _camera_cleanup_task = None
        logging.getLogger(__name__).info("Camera stream cleanup stopped")


# HA RTSP passthrough (Phase E) — opt-in, see Settings.enable_ha_rtsp_passthrough
_rtsp_passthrough_server: asyncio.Server | None = None


async def start_rtsp_passthrough():
    global _rtsp_passthrough_server
    if not app_settings.enable_ha_rtsp_passthrough or _rtsp_passthrough_server is not None:
        return
    from backend.app.services import rtsp_auth_proxy

    try:
        _rtsp_passthrough_server = await rtsp_auth_proxy.start("0.0.0.0", app_settings.ha_rtsp_passthrough_port)  # nosec B104 - opt-in feature explicitly meant to be reachable from the LAN (HA), token-gated per connection
    except OSError as e:
        logging.getLogger(__name__).error(
            "Failed to start RTSP passthrough on port %s: %s", app_settings.ha_rtsp_passthrough_port, e
        )


async def stop_rtsp_passthrough():
    global _rtsp_passthrough_server
    if _rtsp_passthrough_server is not None:
        _rtsp_passthrough_server.close()
        await _rtsp_passthrough_server.wait_closed()
        _rtsp_passthrough_server = None
        logging.getLogger(__name__).info("RTSP passthrough stopped")


# Expected-print TTL eviction


def _evict_stale_expected_prints() -> None:
    from backend.app.services.expected_print_lifecycle import expire_expectations

    expired = expire_expectations(
        _expected_prints,
        _expected_print_creators,
        _expected_print_registered_at,
        _active_prints,
        _print_ams_mappings,
        _print_plate_ids,
        time.monotonic() - _EXPECTED_PRINT_TTL_SECONDS,
    )
    if expired:
        logging.getLogger(__name__).info(
            "Evicted %d stale expected-print entries (TTL=%ds)", expired, _EXPECTED_PRINT_TTL_SECONDS
        )


async def _expected_prints_cleanup_loop() -> None:
    """Background task: periodically evict stale expected-print entries."""
    while True:
        try:
            _evict_stale_expected_prints()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.getLogger(__name__).warning("Expected prints cleanup failed: %s", e)
        await asyncio.sleep(_EXPECTED_PRINT_CLEANUP_INTERVAL)


def start_expected_prints_cleanup() -> None:
    global _expected_prints_cleanup_task
    if _expected_prints_cleanup_task is None:
        _expected_prints_cleanup_task = asyncio.create_task(_expected_prints_cleanup_loop())
        logging.getLogger(__name__).info("Expected prints cleanup started")


def stop_expected_prints_cleanup() -> None:
    global _expected_prints_cleanup_task
    if _expected_prints_cleanup_task:
        _expected_prints_cleanup_task.cancel()
        _expected_prints_cleanup_task = None
        logging.getLogger(__name__).info("Expected prints cleanup stopped")


# L-2: Periodic auth-token cleanup (stale TOTP + expired revoked JTIs)

_auth_cleanup_task: asyncio.Task | None = None
_AUTH_CLEANUP_INTERVAL = 3600  # seconds (hourly)


async def _run_auth_cleanup() -> None:
    """Single cleanup pass: remove stale TOTP records, expired revoked JTIs, and old rate-limit events."""
    from backend.app.core.database import async_session
    from backend.app.models.auth_ephemeral import AuthEphemeralToken, AuthRateLimitEvent
    from backend.app.models.user_totp import UserTOTP

    now = datetime.now(timezone.utc)

    # Remove unconfirmed (is_enabled=False) TOTP records older than 1 hour.
    try:
        async with async_session() as db:
            stale_cutoff = now - timedelta(hours=1)
            result = await db.execute(
                select(UserTOTP).where(
                    UserTOTP.is_enabled.is_(False),
                    UserTOTP.created_at < stale_cutoff,
                )
            )
            stale_records = result.scalars().all()
            if stale_records:
                for rec in stale_records:
                    await db.delete(rec)
                await db.commit()
                logging.info("Auth cleanup: removed %d stale unconfirmed TOTP record(s)", len(stale_records))
    except Exception as e:
        logging.warning("Auth cleanup: failed to purge stale TOTP records: %s", e)

    # Remove expired revoked-JTI entries (they are no longer needed once the
    # original token's exp has passed — the token would be rejected by JWT
    # signature verification regardless).
    try:
        async with async_session() as db:
            await db.execute(
                delete(AuthEphemeralToken).where(
                    AuthEphemeralToken.token_type == "revoked_jti",
                    AuthEphemeralToken.expires_at < now,
                )
            )
            await db.commit()
    except Exception as e:
        logging.warning("Auth cleanup: failed to purge expired revoked JTIs: %s", e)

    # L-R6-B: Purge AuthRateLimitEvent rows older than the lockout window (15 min).
    # Events outside this window can never affect rate-limit decisions — they only
    # consume DB space.  Use the same window constant as the rate limiter so the
    # two are always in sync.
    try:
        from backend.app.api.routes.mfa import LOCKOUT_WINDOW

        async with async_session() as db:
            await db.execute(
                delete(AuthRateLimitEvent).where(
                    AuthRateLimitEvent.occurred_at < now - LOCKOUT_WINDOW,
                )
            )
            await db.commit()
    except Exception as e:
        logging.warning("Auth cleanup: failed to purge stale rate-limit events: %s", e)


async def _auth_cleanup_loop() -> None:
    """Periodic background task: run auth cleanup every hour."""
    while True:
        try:
            await _run_auth_cleanup()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.warning("Auth cleanup loop error: %s", e)
        await asyncio.sleep(_AUTH_CLEANUP_INTERVAL)


def start_auth_cleanup() -> None:
    global _auth_cleanup_task
    if _auth_cleanup_task is None:
        _auth_cleanup_task = asyncio.create_task(_auth_cleanup_loop())
        logging.getLogger(__name__).info("Auth periodic cleanup started")


def stop_auth_cleanup() -> None:
    global _auth_cleanup_task
    if _auth_cleanup_task:
        _auth_cleanup_task.cancel()
        _auth_cleanup_task = None
        logging.getLogger(__name__).info("Auth periodic cleanup stopped")


def _register_printer_callbacks(loop):
    """Bind the printer event callbacks once during application startup."""
    printer_manager.set_event_loop(loop)
    printer_manager.set_status_change_callback(on_printer_status_change)
    printer_manager.set_print_start_callback(on_print_start)
    printer_manager.set_print_complete_callback(on_print_complete)
    printer_manager.set_print_running_observed_callback(on_print_running_observed)
    printer_manager.set_finish_photo_moment_callback(on_finish_photo_moment)
    printer_manager.set_ams_change_callback(on_ams_change)
    printer_manager.set_assignment_verified_callback(on_assignment_verified)

    printer_manager.set_tray_change_callback(print_provenance.persist_tray_change)


async def on_drying_complete(printer_id: int, ams_id: int):
    """Smart-plug auto-off-after-drying trigger (#1349).

    Fires once per AMS unit when ``dry_time`` falls from >0 to 0. The
    manager walks all plugs linked to this printer and turns off only
    the ones with ``auto_off_after_drying`` enabled, after their
    per-plug delay. Multiple AMS units finishing close together (e.g. a
    dual-AMS dry that ends within the same MQTT push) call this once
    per unit — the manager's ``_cancel_pending_off`` collapses
    repeated scheduling on the same plug to one timer, so duplicate
    fires are safe.
    """
    try:
        async with async_session() as db:
            await smart_plug_manager.on_drying_complete(printer_id, db)
    except Exception as e:
        logging.getLogger(__name__).warning(
            "Failed to schedule auto-off-after-drying for printer %d (AMS %d): %s",
            printer_id,
            ams_id,
            e,
        )


async def on_drying_cycle_end(printer_id: int, record):
    from backend.app.services.spool_drying import record_drying_cycle

    async with async_session() as db:
        await record_drying_cycle(db, printer_id, record)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # Install Windows-only asyncio Proactor cleanup-RST filter (#1113) before
    # anything else can spawn tasks that might trip it.
    from backend.app.core.asyncio_handlers import install_proactor_reset_filter
    from backend.app.core.fd_limit import raise_open_file_limit
    from backend.app.core.postgres_pool_capacity import check_pool_fits_server

    install_proactor_reset_filter()
    raise_open_file_limit()
    await init_db()
    await check_pool_fits_server()
    from backend.app.services.archive_plate_estimates import fill_archive_plate_estimates

    spawn_background_task(
        fill_archive_plate_estimates(async_session, app_settings.base_dir), name="archive-plate-estimates"
    )
    try:
        async with async_session() as db:
            from backend.app.core.oidc_env import apply_env_oidc_provider

            await apply_env_oidc_provider(db)
    except Exception as exc:
        logging.warning("Failed to apply PRINTOPS_OIDC_* provider: %s", type(exc).__name__)

    # A process may stop after atomically claiming a preview job. Requeue
    # those interrupted jobs on startup so no request remains stuck forever.
    try:
        async with async_session() as db:
            from backend.app.services.document_preview_jobs import DocumentPreviewJobService

            recovered = await DocumentPreviewJobService().recover_interrupted(db)
            await db.commit()
            if recovered:
                logging.info("Recovered %d interrupted document preview job(s)", recovered)
    except Exception as exc:
        logging.warning("Failed to recover document preview jobs: %s", exc)

    await backfill_completed_batches(async_session)

    # Register an app-scoped httpx client for Bambu Cloud services so
    # per-request BambuCloudService instances reuse the same connection pool
    # (important for routes like /cloud/filament-info that chain many
    # get_setting_detail calls). The shared client stores no region/token
    # state, so the per-request ownership pattern that fixed the region-bleed
    # bug is preserved.
    import httpx as _httpx

    from backend.app.services.bambu_cloud import set_shared_http_client
    from backend.app.services.makerworld import (
        set_shared_http_client as set_shared_makerworld_http_client,
    )
    from backend.app.services.orca_cloud import (
        set_shared_http_client as set_shared_orca_http_client,
    )

    _shared_cloud_http_client = _httpx.AsyncClient(timeout=30.0)
    set_shared_http_client(_shared_cloud_http_client)
    # Reuse the same connection pool for MakerWorld — different host, same
    # keep-alive pool saves a TLS handshake per request.
    set_shared_makerworld_http_client(_shared_cloud_http_client)
    # Same for Orca Cloud — without this the per-request OrcaCloudService()
    # each spun up (and never closed) its own client, leaking sockets.
    set_shared_orca_http_client(_shared_cloud_http_client)

    # Fix queue items stuck with invalid "aborted" status (should be "cancelled").
    # This can happen when a print was cancelled mid-print on versions before this fix.
    try:
        async with async_session() as db:
            from backend.app.models.print_queue import PrintQueueItem

            result = await db.execute(select(PrintQueueItem).where(PrintQueueItem.status == "aborted"))
            aborted_items = result.scalars().all()
            if aborted_items:
                for item in aborted_items:
                    item.status = "cancelled"
                await db.commit()
                logging.info("Fixed %d queue item(s) with invalid 'aborted' status → 'cancelled'", len(aborted_items))
    except Exception as e:
        logging.warning("Failed to fix aborted queue items: %s", e)

    # Restore debug logging state from previous session
    await init_debug_logging()

    loop = asyncio.get_event_loop()
    _register_printer_callbacks(loop)
    # Rehydrate persisted awaiting-plate-clear gate (#961) so prompts survive restarts
    await printer_manager.load_awaiting_plate_clear_from_db()

    # Layer change callback for external camera timelapse
    async def on_layer_change(printer_id: int, layer_num: int):
        """Capture timelapse frame on layer change + first layer notification."""
        from backend.app.services.layer_timelapse import on_layer_change as tl_layer_change

        await tl_layer_change(printer_id, layer_num)

        # First layer complete notification (layer_num >= 2 means layer 1 is done).
        # Gate on actual printing state — Bambu firmware ticks layer_num during
        # the pre-print calibration sequence (homing / mesh-level / bed scan /
        # nozzle clean), so a bare layer_num check can fire minutes before the
        # first real extrusion. We require gcode_state == RUNNING and
        # mc_print_sub_stage in (0 = "Printing", None) so calibration sub-stages
        # (1, 9, 14, ...) are excluded. The window widens to [2, 10] because if
        # the layer counter advanced past 2 during PREPARE, the next on_layer_change
        # edge fires later; _first_layer_notified stays clear until we actually send
        # so a deferred re-evaluation can win. See issue #1837.
        if 2 <= layer_num <= 10 and not _first_layer_notified.get(printer_id, False):
            client = printer_manager.get_client(printer_id)
            state = client.state if client else None
            if not state or state.state != "RUNNING":
                return
            if state.mc_print_sub_stage not in (None, 0):
                return
            _first_layer_notified[printer_id] = True
            try:
                async with async_session() as db:
                    from backend.app.models.printer import Printer

                    result = await db.execute(select(Printer).where(Printer.id == printer_id))
                    printer = result.scalar_one_or_none()
                    if not printer:
                        return
                    printer_name = printer.name
                    filename = (state.subtask_name or state.gcode_file or "Unknown") if state else "Unknown"
                    total_layers = state.total_layers if state else 0

                    image_data = await _capture_snapshot_for_notification(
                        printer_id, printer, logging.getLogger(__name__)
                    )
                    await notification_service.on_first_layer_complete(
                        printer_id, printer_name, filename, total_layers, db, image_data=image_data
                    )
            except Exception as e:
                logging.getLogger(__name__).warning("First layer notification failed: %s", e)

    printer_manager.set_layer_change_callback(on_layer_change)

    # Event-driven bed cooldown: fires whenever bed_temper arrives via MQTT
    async def on_bed_temp_update(printer_id: int, bed_temp: float):
        waiter = _bed_cool_waiters.get(printer_id)
        if not waiter:
            return
        threshold = waiter["threshold"]
        if bed_temp > threshold:
            return
        # Bed is at or below threshold — fire notification and remove waiter
        waiter_info = _bed_cool_waiters.pop(printer_id, None)
        if not waiter_info:
            return  # Another callback already handled it
        bed_cool_logger = logging.getLogger(__name__)
        bed_cool_logger.info(
            "[BED-COOL] Bed cooled to %.1f°C on printer %s (threshold: %.0f°C)",
            bed_temp,
            printer_id,
            threshold,
        )
        try:
            printer_info = printer_manager.get_printer(printer_id)
            p_name = printer_info.name if printer_info else "Unknown"
            async with async_session() as db:
                await notification_service.on_bed_cooled(
                    printer_id=printer_id,
                    printer_name=p_name,
                    bed_temp=bed_temp,
                    threshold=threshold,
                    filename=waiter_info["filename"],
                    db=db,
                )
        except Exception as e:
            bed_cool_logger.warning("[BED-COOL] Failed to send notification: %s", e)

    printer_manager.set_bed_temp_update_callback(on_bed_temp_update)

    printer_manager.set_drying_complete_callback(on_drying_complete)
    printer_manager.set_drying_cycle_end_callback(on_drying_cycle_end)

    # Initialize MQTT relay from settings
    async with async_session() as db:
        from backend.app.api.routes.settings import get_setting

        mqtt_settings = {
            "mqtt_enabled": (await get_setting(db, "mqtt_enabled") or "false") == "true",
            "mqtt_broker": await get_setting(db, "mqtt_broker") or "",
            "mqtt_port": int(await get_setting(db, "mqtt_port") or "1883"),
            "mqtt_username": await get_setting(db, "mqtt_username") or "",
            "mqtt_password": await get_setting(db, "mqtt_password") or "",
            "mqtt_topic_prefix": await get_setting(db, "mqtt_topic_prefix") or "printops",
            "mqtt_use_tls": (await get_setting(db, "mqtt_use_tls") or "false") == "true",
        }
        await mqtt_relay.configure(mqtt_settings)

        # Restore MQTT smart plug subscriptions
        if mqtt_settings.get("mqtt_enabled"):
            from backend.app.models.smart_plug import SmartPlug
            from backend.app.services.mqtt_smart_plug import subscribe_plug_to_mqtt

            result = await db.execute(select(SmartPlug).where(SmartPlug.plug_type == "mqtt"))
            mqtt_plugs = result.scalars().all()
            restored = 0
            for plug in mqtt_plugs:
                if subscribe_plug_to_mqtt(mqtt_relay.smart_plug_service, plug):
                    restored += 1
            if restored:
                logging.info("Restored %s MQTT smart plug subscriptions", restored)

    # Connect to all active printers
    async with async_session() as db:
        await init_printer_connections(db)

    # Auto-connect to Spoolman if enabled
    async with async_session() as db:
        from backend.app.api.routes.settings import get_setting

        spoolman_enabled = await get_setting(db, "spoolman_enabled")
        spoolman_url = await get_setting(db, "spoolman_url")

        if spoolman_enabled and spoolman_enabled.lower() == "true" and spoolman_url:
            try:
                client = await init_spoolman_client(spoolman_url)
                if await client.health_check():
                    logging.info("Auto-connected to Spoolman at %s", spoolman_url)
                    # Ensure the 'tag' extra field exists for RFID/UUID storage
                    field_ok = await client.ensure_tag_extra_field()
                    if not field_ok:
                        logging.error("Spoolman tag extra field registration failed — NFC tag links may not persist")
                    # Register the BambuStudio slicer-preset fields used by the
                    # spool-edit / assign flow. Spoolman rejects PATCHes with
                    # unknown extra keys, so these must exist before any update
                    # that touches them.
                    for field_name in ("bambu_slicer_filament", "bambu_slicer_filament_name"):
                        if not await client.ensure_extra_field(field_name):
                            logging.warning(
                                "Spoolman extra field %r registration failed — "
                                "spool slicer-preset edits will return 502",
                                field_name,
                            )
                else:
                    logging.warning("Spoolman at %s is not reachable", spoolman_url)
            except Exception as e:
                logging.warning("Failed to auto-connect to Spoolman: %s", e)

    # Start the print scheduler
    spawn_background_task(print_scheduler.run(), name="print-scheduler")

    # Start the smart plug scheduler for time-based on/off
    smart_plug_manager.start_scheduler()

    # Start the Home Assistant sensor poller (#1148)
    ha_sensor_manager.start()

    # Resume any pending auto-offs that were interrupted by restart
    await smart_plug_manager.resume_pending_auto_offs()

    # Start the notification digest scheduler
    notification_service.start_background()

    # Start the GitHub backup scheduler
    await github_backup_service.start_scheduler()

    # Start the local backup scheduler
    await business_runtime.start()
    await obico_detection_service.start()

    # Start the library trash sweeper (#1008)
    await library_trash_service.start_scheduler()

    # Start the archive auto-purge sweeper (#1008 follow-up)
    await archive_purge_service.start_scheduler()

    # Start AMS history recording
    start_ams_history_recording()

    # Start printer sensor (nozzle / bed / chamber) history recording
    start_printer_sensor_history_recording()

    # Start printer runtime tracking
    start_runtime_tracking()

    # Start SpoolBuddy device watchdog
    start_spoolbuddy_watchdog()

    # Start camera stream orphan cleanup
    start_camera_cleanup()

    # Start HA RTSP passthrough (opt-in, no-op unless enabled)
    await start_rtsp_passthrough()

    # Start expected-print TTL eviction (prevents memory leak when prints are
    # registered but on_print_start never fires)
    start_expected_prints_cleanup()

    # L-2: Start periodic auth cleanup (stale TOTP + expired revoked JTIs)
    start_auth_cleanup()

    # Event-loop stall watchdog: dumps all thread stacks to stderr if the loop
    # freezes (#1486 — silent "container hangs after adding a printer" reports).
    from backend.app.services.loop_watchdog import start_loop_watchdog

    start_loop_watchdog()

    # Initialize virtual printer manager and sync from DB
    from backend.app.services.virtual_printer import virtual_printer_manager

    virtual_printer_manager.set_session_factory(async_session)
    virtual_printer_manager.set_printer_manager(printer_manager)
    try:
        await virtual_printer_manager.sync_from_db()
        logging.info("Virtual printer manager synced from database")
    except Exception as e:
        logging.warning("Failed to sync virtual printers: %s", e)

    yield

    # Shutdown
    slot_unlink_grace.reset()
    from backend.app.services import kprofile_drift, timelapse_jobs

    await timelapse_jobs.cancel_all()
    kprofile_drift.reset()
    print_scheduler.stop()
    await print_scheduler.close_inventory_alerts()
    smart_plug_manager.stop_scheduler()
    ha_sensor_manager.stop()
    await notification_service.stop_background()
    github_backup_service.stop_scheduler()
    await business_runtime.stop()
    library_trash_service.stop_scheduler()
    archive_purge_service.stop_scheduler()
    obico_detection_service.stop()
    stop_ams_history_recording()
    stop_printer_sensor_history_recording()
    stop_runtime_tracking()
    stop_spoolbuddy_watchdog()
    stop_camera_cleanup()
    await stop_rtsp_passthrough()
    from backend.app.services.loop_watchdog import stop_loop_watchdog

    stop_loop_watchdog()
    # Tear down all camera fan-out broadcasters (#1089) so subscribers exit
    # cleanly rather than waiting on a queue that nothing will ever fill.
    try:
        from backend.app.services.camera_fanout import shutdown_all_broadcasters

        await shutdown_all_broadcasters()
    except Exception as e:
        logging.warning("Failed to shut down camera broadcasters: %s", e)
    stop_expected_prints_cleanup()
    stop_auth_cleanup()
    printer_manager.disconnect_all()
    await close_spoolman_client()

    # Stop all virtual printer services
    await virtual_printer_manager.stop_all()

    await mqtt_smart_plug_service.disconnect(timeout=2)

    await mqtt_relay.disconnect(timeout=2)

    # Drop the shared Bambu Cloud HTTP client we registered at startup.
    set_shared_http_client(None)
    set_shared_makerworld_http_client(None)
    set_shared_orca_http_client(None)
    await _shared_cloud_http_client.aclose()

    # Checkpoint WAL (SQLite only) and close all database connections
    from backend.app.core.db_dialect import is_sqlite

    if is_sqlite():
        try:
            async with engine.begin() as conn:
                await conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
            logging.info("WAL checkpoint completed")
        except Exception as e:
            logging.warning("WAL checkpoint failed: %s", e)
    await engine.dispose()


app = FastAPI(
    title=app_settings.app_name,
    description="Operate and manage local 3D printing workflows",
    version=APP_VERSION,
    lifespan=lifespan,
    exception_handlers={RequestValidationError: request_validation_error},
)

# Inside the middleware that re-streams HTTP responses.
app.add_middleware(RefusedHeaderResponseMask)


# Authentication Middleware - Secures ALL API routes by default
# Public routes that don't require authentication even when auth is enabled
PUBLIC_API_ROUTES = {
    "/api/v1/connect/token",  # Client-secret + single-use PKCE identity exchange.
    # Auth routes needed before/during login
    "/api/v1/auth/status",
    "/api/v1/auth/login",
    "/api/v1/auth/setup",  # Needed for initial setup and recovery
    # Advanced auth status needed for login page
    "/api/v1/auth/advanced-auth/status",
    "/api/v1/auth/forgot-password",  # Password reset for advanced auth
    "/api/v1/auth/forgot-password/confirm",  # Complete password reset with token (H-6)
    # 2FA routes that are called BEFORE a JWT is issued (pre-auth flow)
    "/api/v1/auth/2fa/verify",  # Exchange pre_auth_token + 2FA code for JWT
    "/api/v1/auth/2fa/email/send",  # Send OTP email (pre_auth_token based)
    # OIDC routes that must be reachable without a JWT
    "/api/v1/auth/oidc/providers",  # Public list of enabled providers
    "/api/v1/auth/oidc/callback",  # Redirect target from OIDC provider
    "/api/v1/auth/oidc/exchange",  # Exchange short-lived OIDC token for JWT
    # Version check for updates (no sensitive data)
    "/api/v1/updates/version",
    # Metrics endpoint handles its own prometheus_token authentication
    "/api/v1/metrics",
    # Appliance bootstrap (#1589 follow-up): the SPA's i18n setup polls
    # this BEFORE a JWT is available to pick up the firstboot wizard's
    # hostname / timezone / locale and the chrony NTP-gate state. The
    # response contains user-set defaults and a public sync flag — no
    # secrets. Without this entry the global auth middleware returns 401
    # before the route handler runs, regardless of the route's own
    # "no auth required" intent.
    "/api/v1/system/appliance",
    "/api/v1/camwall/printers",
}

# Route prefixes that are public (for routes with dynamic segments)
PUBLIC_API_PREFIXES = [
    # WebSocket connections handle their own auth
    "/api/v1/ws",
    # OIDC authorize redirects — include provider_id in path
    "/api/v1/auth/oidc/authorize/",
]

# Route patterns that are public (read-only display data)
# These are checked with "in path" - needed because browsers load images/videos
# via <img src> and <video src> which don't include Authorization headers
PUBLIC_API_PATTERNS = [
    # Thumbnails
    "/thumbnail",  # /archives/{id}/thumbnail, /library/files/{id}/thumbnail
    "/plate-thumbnail/",  # /archives/{id}/plate-thumbnail/{plate_id}
    # Images and media
    "/photos/",  # /archives/{id}/photos/{filename}
    "/project-image/",  # /archives/{id}/project-image/{path}
    "/qrcode",  # /archives/{id}/qrcode
    "/timelapse",  # /archives/{id}/timelapse (video)
    "/cover",  # /printers/{id}/cover
    "/icon",  # /external-links/{id}/icon
    # Camera (streams loaded via <img> tag)
    "/camera/stream",  # /printers/{id}/camera/stream
    "/camera/snapshot",  # /printers/{id}/camera/snapshot
    "/overlay-status",  # /printers/{id}/overlay-status
    # Slicer token-authenticated downloads — protocol handlers (bambustudioopen://,
    # orcaslicer://) cannot send auth headers. These endpoints validate a short-lived
    # download token in the URL path instead.
    "/dl/",  # /archives/{id}/dl/{token}/{filename}, /library/files/{id}/dl/{token}/{filename}
    # Obico ML API fetches JPEG frames by one-shot nonce (issue #172 follow-up).
    # The nonce itself is the credential: 32-byte random, single-use, ~30s TTL.
    "/obico/cached-frame/",  # /obico/cached-frame/{nonce}
]


_security_headers_logger = logging.getLogger("backend.app.main.security_headers")


def _parse_trusted_frame_origins() -> tuple[str, ...]:
    """Parse TRUSTED_FRAME_ORIGINS env var into a validated allowlist (#1191).

    Format: comma-separated list of ``scheme://host[:port]`` origins.

    Used by ``security_headers_middleware`` to relax ``frame-ancestors`` for
    trusted same-LAN deployments (e.g. Home Assistant Webpage panel embedding
    PrintOps from a different port). Defaults to empty — strict ``'none'``.

    Invalid entries are dropped with a warning rather than failing startup, so
    a typo in one origin doesn't take the whole deployment down.
    """
    raw = os.environ.get("TRUSTED_FRAME_ORIGINS", "").strip()
    if not raw:
        return ()
    valid: list[str] = []
    for item in raw.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        try:
            parsed = urlparse(candidate)
        except ValueError as e:
            _security_headers_logger.warning("TRUSTED_FRAME_ORIGINS: dropping %r — %s", candidate, e)
            continue
        if parsed.scheme not in ("http", "https"):
            _security_headers_logger.warning("TRUSTED_FRAME_ORIGINS: dropping %r — must be http(s)", candidate)
            continue
        if not parsed.netloc:
            _security_headers_logger.warning("TRUSTED_FRAME_ORIGINS: dropping %r — missing host", candidate)
            continue
        if parsed.path and parsed.path != "/":
            _security_headers_logger.warning("TRUSTED_FRAME_ORIGINS: dropping %r — paths not allowed", candidate)
            continue
        if parsed.query or parsed.fragment:
            _security_headers_logger.warning(
                "TRUSTED_FRAME_ORIGINS: dropping %r — query/fragment not allowed", candidate
            )
            continue
        if "*" in parsed.netloc:
            _security_headers_logger.warning("TRUSTED_FRAME_ORIGINS: dropping %r — wildcards not allowed", candidate)
            continue
        valid.append(f"{parsed.scheme}://{parsed.netloc}")
    if valid:
        _security_headers_logger.info("TRUSTED_FRAME_ORIGINS: %s", ", ".join(valid))
    return tuple(valid)


_TRUSTED_FRAME_ORIGINS: tuple[str, ...] = _parse_trusted_frame_origins()


def _frame_ancestors(default_value: str) -> str:
    """Compose the ``frame-ancestors`` CSP directive (#1191).

    ``default_value`` is the strict directive used when the operator has not
    configured ``TRUSTED_FRAME_ORIGINS`` — typically ``'none'`` (catch-all and
    docs) or ``'self'`` (gcode-viewer, served same-origin). When trusted origins
    are configured, ``'self'`` is always included so same-origin embedding never
    breaks even if an operator forgets to add their own origin to the list.
    """
    if _TRUSTED_FRAME_ORIGINS:
        return "frame-ancestors 'self' " + " ".join(_TRUSTED_FRAME_ORIGINS) + ";"
    return f"frame-ancestors {default_value};"


@app.middleware("http")
async def security_headers_middleware(request, call_next):
    """Add standard HTTP security headers to every response."""
    # Per-request CSP nonce lets Cloudflare's injected challenge script execute.
    # PrintOps has no inline scripts; SW registration lives in /sw-register.js.
    # Cloudflare copies this nonce to its script, avoiding 'unsafe-inline'.
    # https://developers.cloudflare.com/cloudflare-challenges/challenge-types/javascript-detections/#if-you-have-a-content-security-policy-csp
    csp_nonce = secrets.token_urlsafe(16)
    request.state.csp_nonce = csp_nonce
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    # X-Frame-Options is the legacy cross-origin embedding control. Modern
    # browsers honour CSP frame-ancestors instead, and the legacy
    # `ALLOW-FROM <url>` syntax is deprecated and inconsistent across vendors.
    # When operators have explicitly allowlisted trusted frame origins (#1191
    # — typically Home Assistant on a different port), drop X-Frame-Options
    # and let the CSP-side frame-ancestors directive govern embedding.
    if not _TRUSTED_FRAME_ORIGINS:
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Content-Security-Policy for the React SPA.
    # Notes:
    #   - 'unsafe-inline' for style-src: React and UI libs inject inline styles at runtime.
    #   - connect-src ws:/wss:: MQTT/printer WebSocket connections.
    #   - img-src data: / blob:: base64 thumbnails and Blob-URL timelapse previews.
    #   - media-src blob:: timelapse video player uses Blob URLs.
    #   - font-src data:: some icon fonts are embedded as data URIs.
    if (
        request.method == "GET"
        and response.status_code == 200
        and re.fullmatch(r"/assets/stepPreview\.worker-[A-Za-z0-9_-]+\.js", request.url.path)
        and response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        in {"application/javascript", "text/javascript"}
    ):
        # Emscripten embind requires dynamic functions; only this local worker
        # receives that capability. Inputs and WASM arrive from its parent.
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self' 'unsafe-eval'; "
            "connect-src 'none'; worker-src 'none'; object-src 'none'; base-uri 'none';"
        )
    elif request.url.path.startswith("/gcode-viewer"):
        # The gcode viewer is embedded in an iframe served by this same origin,
        # so frame-ancestors must allow 'self'.  prettygcode.js also uses eval()
        # internally, so script-src needs 'unsafe-eval'.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "media-src 'self' blob:; "
            "connect-src 'self' ws: wss:; "
            "font-src 'self' data:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-src 'self' http: https:; " + _frame_ancestors("'self'")
        )
    elif request.url.path in ("/docs", "/redoc", "/docs/oauth2-redirect"):
        # FastAPI's built-in Swagger UI / ReDoc pages load assets from
        # cdn.jsdelivr.net and bootstrap with an inline <script>, so the
        # default CSP would render a blank page.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
            "img-src 'self' data: blob: https://fastapi.tiangolo.com https://cdn.redoc.ly; "
            "connect-src 'self'; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "worker-src 'self' blob:; "
            "object-src 'none'; "
            "base-uri 'self'; " + _frame_ancestors("'none'")
        )
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{csp_nonce}'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "media-src 'self' blob:; "
            "connect-src 'self' ws: wss:; "
            "font-src 'self' data:; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-src 'self' http: https:; " + _frame_ancestors("'none'")
        )
    if request.url.path == "/connect/authorize":
        response.headers["Content-Security-Policy"] = re.sub(
            r"frame-ancestors [^;]+;", "frame-ancestors 'self';", response.headers["Content-Security-Policy"]
        )
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.middleware("http")
async def auth_middleware(request, call_next):
    """Enforce authentication on all API routes when auth is enabled.

    This middleware provides defense-in-depth by checking auth at the API gateway level,
    regardless of whether individual routes have auth dependencies.
    """
    from starlette.responses import JSONResponse

    path = request.url.path

    # Only apply to API routes
    if not path.startswith("/api/"):
        return await call_next(request)

    # Allow public routes
    if path in PUBLIC_API_ROUTES:
        return await call_next(request)

    # Allow public prefixes
    # Only the exact notification capability endpoints bypass session parsing.
    # Their indexed, expiring, single-run token grants only a good/reject answer.
    import re

    if request.method in {"GET", "POST"} and re.fullmatch(
        r"/api/v1/archives/outcome-link/[A-Za-z0-9_-]{43}/(?:good|reject)", path
    ):
        return await call_next(request)

    for prefix in PUBLIC_API_PREFIXES:
        if path.startswith(prefix):
            return await call_next(request)

    # Browser plate previews use URL credentials; the archive route enforces
    # media-token permission, ownership and printer scope itself.
    parts = path.split("/")
    if (
        request.method == "GET"
        and len(parts) == 6
        and parts[:4] == ["", "api", "v1", "archives"]
        and parts[4].isdigit()
        and parts[5] == "plate-preview"
    ):
        return await call_next(request)

    # Archive source handoffs validate an endpoint-bound slicer token. Only
    # this GET shape bypasses header auth; ordinary archive reads still require it.
    if (
        request.method == "GET"
        and len(parts) == 8
        and parts[:4] == ["", "api", "v1", "archives"]
        and parts[4].isdigit()
        and parts[5] == "source-dl"
        and all(parts[6:])
    ):
        return await call_next(request)

    # Allow public patterns (read-only display data like thumbnails)
    for pattern in PUBLIC_API_PATTERNS:
        if pattern in path:
            return await call_next(request)

    def unauthorized(detail: str) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": detail}, headers={"WWW-Authenticate": "Bearer"})

    # A failed auth probe must deny access. Route failures use the normal ASGI error handler.
    try:
        async with async_session() as db:
            from backend.app.core.auth import is_auth_enabled

            auth_enabled = await is_auth_enabled(db)
    except Exception:
        logging.getLogger(__name__).exception("auth_middleware: failing closed on auth-probe error from %s", path)
        return JSONResponse(
            status_code=503,
            content={"detail": "Authentication service temporarily unavailable"},
        )

    if not auth_enabled:
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if request.headers.get("X-API-Key") or (auth_header and auth_header.startswith("Bearer bb_")):
        return await call_next(request)  # The route validates the key and its permissions.

    if not auth_header or not auth_header.startswith("Bearer "):
        return unauthorized("Authentication required")

    import jwt

    from backend.app.core.auth import ALGORITHM, SECRET_KEY, _is_token_fresh, get_user_by_username, is_jti_revoked

    try:
        token = auth_header.removeprefix("Bearer ")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        jti = payload.get("jti")
        if not username or not jti:
            return unauthorized("Invalid token")
        iat = payload.get("iat")
    except jwt.ExpiredSignatureError:
        return unauthorized("Token has expired")
    except (jwt.InvalidTokenError, ValueError, TypeError, OverflowError):
        return unauthorized("Invalid token")

    try:
        async with async_session() as db:
            if await is_jti_revoked(jti, db):
                return unauthorized("Token has been revoked")
            user = await get_user_by_username(db, username)
            if not user or not user.is_active:
                return unauthorized("User not found or inactive")
            if not _is_token_fresh(iat, user):
                return unauthorized("Token no longer valid")
    except Exception:
        logging.getLogger(__name__).exception("auth_middleware: failing closed on token-check error from %s", path)
        return JSONResponse(
            status_code=503,
            content={"detail": "Authentication service temporarily unavailable"},
        )

    return await call_next(request)


@app.middleware("http")
async def trace_id_middleware(request, call_next):
    """Stamp every HTTP request with a trace ID and echo it back.

    Decorated AFTER auth_middleware on purpose: Starlette stacks
    @app.middleware decorators LIFO, so the last-decorated runs first
    inbound. Putting the trace stamp last makes it the OUTERMOST layer,
    which means auth-middleware log lines (and every line emitted on the
    way down to and back from the route handler) all carry the same
    trace ID. If we put it before auth, auth's logs would be stamped
    with the *previous* request's ID — useless for correlation.

    Honours an inbound ``X-Trace-Id`` header so callers running their
    own tracing can correlate their span IDs with our log lines, but
    only if the value passes the whitelist gate in
    ``backend.app.core.trace.normalise_inbound_trace_id`` — anything
    rejected (too long, contains control chars, etc.) silently triggers
    a freshly minted server-side ID rather than failing the request.

    The minted (or echoed) ID is set on a ContextVar so that every log
    record emitted during the request — application logs *and* uvicorn's
    access log — carries it via TraceIDFilter, and is also written to
    the ``X-Trace-Id`` response header so clients can pin a server-side
    log search to the exact request they made.
    """
    from backend.app.core.trace import (
        generate_trace_id,
        normalise_inbound_trace_id,
        trace_id_var,
    )

    inbound = normalise_inbound_trace_id(request.headers.get("X-Trace-Id"))
    trace_id = inbound if inbound is not None else generate_trace_id()

    token = trace_id_var.set(trace_id)
    try:
        response = await call_next(request)
    finally:
        # Reset the ContextVar so a record emitted in a totally
        # unrelated background task that just happens to inherit this
        # context doesn't keep referencing this request's ID forever.
        # In practice ContextVar.reset is best-effort under asyncio
        # task-spawn semantics, but the cost is one attribute write so
        # we may as well do it.
        trace_id_var.reset(token)

    response.headers["X-Trace-Id"] = trace_id
    return response


app.include_router(auth.router, prefix=app_settings.api_prefix)
app.include_router(mfa.router, prefix=app_settings.api_prefix)
app.include_router(bug_report.router, prefix=app_settings.api_prefix)
app.include_router(commerce_router, prefix=app_settings.api_prefix)
app.include_router(users.router, prefix=app_settings.api_prefix)
app.include_router(groups.router, prefix=app_settings.api_prefix)
app.include_router(printers.router, prefix=app_settings.api_prefix)
app.include_router(printer_files.router, prefix=app_settings.api_prefix)
app.include_router(archives_latest.router, prefix=app_settings.api_prefix)
app.include_router(archives.router, prefix=app_settings.api_prefix)
app.include_router(filaments.router, prefix=app_settings.api_prefix)
app.include_router(inventory.router, prefix=app_settings.api_prefix)
app.include_router(labels.router, prefix=app_settings.api_prefix)
app.include_router(settings_routes.router, prefix=app_settings.api_prefix)
app.include_router(cloud.router, prefix=app_settings.api_prefix)
app.include_router(orca_cloud.router, prefix=app_settings.api_prefix)
app.include_router(local_presets.router, prefix=app_settings.api_prefix)
app.include_router(smart_plugs.router, prefix=app_settings.api_prefix)
app.include_router(ha_sensors.router, prefix=app_settings.api_prefix)
app.include_router(storage_ha_sensors.router, prefix=app_settings.api_prefix)
app.include_router(print_log.router, prefix=app_settings.api_prefix)
app.include_router(queue_history.router, prefix=app_settings.api_prefix)
app.include_router(print_queue.router, prefix=app_settings.api_prefix)
app.include_router(kprofiles.router, prefix=app_settings.api_prefix)
app.include_router(notifications.router, prefix=app_settings.api_prefix)
app.include_router(notification_templates.router, prefix=app_settings.api_prefix)
app.include_router(user_notifications.router, prefix=app_settings.api_prefix)
app.include_router(spoolman.router, prefix=app_settings.api_prefix)
app.include_router(spoolman_inventory.router, prefix=app_settings.api_prefix)
app.include_router(updates.router, prefix=app_settings.api_prefix)
app.include_router(sponsor_prompt.router, prefix=app_settings.api_prefix)
app.include_router(maintenance.router, prefix=app_settings.api_prefix)
app.include_router(camera.router, prefix=app_settings.api_prefix)
app.include_router(camwall.router, prefix=app_settings.api_prefix)
app.include_router(external_links.router, prefix=app_settings.api_prefix)
app.include_router(projects.router, prefix=app_settings.api_prefix)
app.include_router(library.router, prefix=app_settings.api_prefix)
app.include_router(library_tags.router, prefix=app_settings.api_prefix)
app.include_router(library_trash.router, prefix=app_settings.api_prefix)
app.include_router(bulk.router, prefix=app_settings.api_prefix)
app.include_router(library_variants.router, prefix=app_settings.api_prefix)
app.include_router(slice_jobs.router, prefix=app_settings.api_prefix)
app.include_router(slicer_pipelines.router, prefix=app_settings.api_prefix)
app.include_router(pipeline_runs.pipeline_run_create_router, prefix=app_settings.api_prefix)
app.include_router(pipeline_runs.pipeline_run_router, prefix=app_settings.api_prefix)
app.include_router(slicer_presets.router, prefix=app_settings.api_prefix)
app.include_router(archive_purge.router, prefix=app_settings.api_prefix)
app.include_router(makerworld.router, prefix=app_settings.api_prefix)
app.include_router(api_keys.router, prefix=app_settings.api_prefix)
app.include_router(connected_apps.router, prefix=app_settings.api_prefix)
app.include_router(webhook.router, prefix=app_settings.api_prefix)
app.include_router(ams_history.router, prefix=app_settings.api_prefix)
app.include_router(printer_sensor_history.router, prefix=app_settings.api_prefix)
app.include_router(system.router, prefix=app_settings.api_prefix)
app.include_router(support.router, prefix=app_settings.api_prefix)
app.include_router(websocket.router, prefix=app_settings.api_prefix)
app.include_router(discovery.router, prefix=app_settings.api_prefix)
app.include_router(pending_uploads.router, prefix=app_settings.api_prefix)
app.include_router(firmware.router, prefix=app_settings.api_prefix)
app.include_router(github_backup.router, prefix=app_settings.api_prefix)
app.include_router(local_backup.router, prefix=app_settings.api_prefix)
app.include_router(obico.router, prefix=app_settings.api_prefix)
app.include_router(metrics.router, prefix=app_settings.api_prefix)
app.include_router(virtual_printers.router, prefix=app_settings.api_prefix)
app.include_router(spoolbuddy.router, prefix=app_settings.api_prefix)


# Serve static files (React build)
if app_settings.static_dir.exists() and any(app_settings.static_dir.iterdir()):
    app.mount(
        "/assets",
        AssetStaticFiles(directory=app_settings.static_dir / "assets"),
        name="assets",
    )
    if (app_settings.static_dir / "img").exists():
        app.mount(
            "/img",
            StaticFiles(directory=app_settings.static_dir / "img"),
            name="img",
        )
    if (app_settings.static_dir / "icons").exists():
        app.mount(
            "/icons",
            StaticFiles(directory=app_settings.static_dir / "icons"),
            name="icons",
        )
    # Self-hosted Inter woff2 files (#1460). Without this mount /fonts/*.woff2
    # falls through to the SPA catch-all and returns index.html, which the
    # browser's font sanitizer rejects ("downloadable font: rejected by
    # sanitizer").
    if (app_settings.static_dir / "fonts").exists():
        app.mount(
            "/fonts",
            StaticFiles(directory=app_settings.static_dir / "fonts"),
            name="fonts",
        )


@app.get("/")
async def serve_frontend():
    """Serve the React frontend."""
    index_file = app_settings.static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file, headers=_HTML_CACHE_HEADERS)
    return {
        "message": "PrintOps API",
        "docs": "/docs",
        "frontend": "Build and place React app in /static directory",
    }


# index.html must always be revalidated — Vite emits content-hashed JS/CSS
# bundles (e.g. `index-JRaF_JhW.js`), so the JS itself is safe to cache
# forever, but the HTML wrapping it is the only file that knows which hash
# is current. Without explicit cache-control headers Chromium decides
# heuristically (typically 10% of the time since Last-Modified) and on
# long-running kiosks happily serves stale HTML across browser restarts.
# That stale HTML references an old bundle hash, the old bundle is also
# in the disk cache, and the user ends up running pre-update JS forever
# without ever knowing why. ``no-cache`` (revalidate every time, but a
# 304 is cheap) is the correct setting for an SPA's entry HTML.
_HTML_CACHE_HEADERS = {"Cache-Control": "no-cache, must-revalidate"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


# PWA bootstrap files accept HEAD for scanners as well as GET.
@app.get("/manifest.json")
@app.head("/manifest.json")
async def serve_manifest():
    """Serve PWA manifest."""
    manifest_file = app_settings.static_dir / "manifest.json"
    if manifest_file.exists():
        return FileResponse(manifest_file, media_type="application/manifest+json")
    return {"error": "Manifest not found"}


@app.get("/sw.js")
@app.head("/sw.js")
async def serve_service_worker():
    """Serve service worker."""
    sw_file = app_settings.static_dir / "sw.js"
    if sw_file.exists():
        return FileResponse(
            sw_file,
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    return {"error": "Service worker not found"}


@app.get("/sw-register.js")
@app.head("/sw-register.js")
async def serve_sw_register():
    """Serve the service-worker registration bootstrap script.

    Served as a real JS file so the strict `script-src 'self'` CSP covers it
    without needing 'unsafe-inline' or per-build hashes on the inline tag.
    """
    reg_file = app_settings.static_dir / "sw-register.js"
    if reg_file.exists():
        return FileResponse(reg_file, media_type="application/javascript")
    return {"error": "sw-register.js not found"}


# ── GCode viewer static files ────────────────────────────────────────────────
# Served via explicit routes so ordering is guaranteed (app.mount() loses
# to the /{full_path:path} catch-all in some Starlette versions).
_gcode_viewer_dir = (app_settings.static_dir.parent / "gcode_viewer").resolve()

# Surface packaging gaps at startup instead of as silent runtime 404s. If the
# directory is missing the explicit @app.get("/gcode-viewer/...") routes below
# return bare HTTPException(404) which renders as {"detail":"Not Found"} in
# the 3D Preview iframe (#1218) — easy to miss in normal operation, easy to
# spot if the operator scans the startup log or a support bundle.
if not (_gcode_viewer_dir / "index.html").is_file():
    logging.getLogger(__name__).error(
        "Embedded GCode viewer assets missing at %s — /gcode-viewer/ will return 404 "
        "and 3D Preview will fail. This indicates a packaging bug; the gcode_viewer/ "
        "directory must be present alongside static/.",
        _gcode_viewer_dir,
    )


def _gcode_viewer_response(rel: str) -> FileResponse:
    from fastapi import HTTPException as _HTTPException

    safe = (_gcode_viewer_dir / rel).resolve()
    if not safe.is_relative_to(_gcode_viewer_dir):
        raise _HTTPException(status_code=403)
    if safe.is_file():
        mt, _ = _mimetypes.guess_type(str(safe))
        return FileResponse(str(safe), media_type=mt or "application/octet-stream")
    raise _HTTPException(status_code=404)


@app.get("/gcode-viewer/")
async def serve_gcode_viewer_index() -> FileResponse:
    """Raw PrettyGCode viewer for the iframe. The bare ``/gcode-viewer``
    (no trailing slash) intentionally falls through to the SPA catch-all so a
    full-page reload re-enters the React layout instead of serving the iframe
    contents standalone."""
    return _gcode_viewer_response("index.html")


@app.get("/gcode-viewer/{file_path:path}")
async def serve_gcode_viewer_file(file_path: str) -> FileResponse:
    return _gcode_viewer_response(file_path)


# Catch-all route for React Router (must be last)
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve React app for client-side routing."""
    # Don't intercept API routes - raise proper 404 so FastAPI can handle redirects
    if full_path.startswith("api/"):
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Not found")

    index_file = app_settings.static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file, headers=_HTML_CACHE_HEADERS)

    return {"error": "Frontend not built"}
