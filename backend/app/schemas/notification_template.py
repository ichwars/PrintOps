"""Pydantic schemas for notification templates."""

from datetime import datetime

from pydantic import BaseModel, Field

from backend.app.core.compat import StrEnum
from backend.app.schemas.not_null import IgnoresNullForRequiredColumns


class EventType(StrEnum):
    """Supported notification event types."""

    PRINT_START = "print_start"
    PRINT_COMPLETE = "print_complete"
    PRINT_FAILED = "print_failed"
    PRINT_STOPPED = "print_stopped"
    PRINT_PROGRESS = "print_progress"
    PRINT_PAUSE_UPCOMING = "print_pause_upcoming"
    PRINT_CONFIRM_REQUEST = "print_confirm_request"
    PRINT_MISSING_SPOOL_ASSIGNMENT = "print_missing_spool_assignment"
    PRINTER_OFFLINE = "printer_offline"
    PRINTER_ERROR = "printer_error"
    FILAMENT_LOW = "filament_low"
    MAINTENANCE_DUE = "maintenance_due"
    AMS_HUMIDITY_HIGH = "ams_humidity_high"
    AMS_TEMPERATURE_HIGH = "ams_temperature_high"
    BED_COOLED = "bed_cooled"
    HA_SENSOR_ALERT = "ha_sensor_alert"
    STORAGE_SENSOR_ALERT = "storage_sensor_alert"
    TEST = "test"


# Available variables for each event type
EVENT_VARIABLES: dict[str, list[str]] = {
    "print_start": ["printer", "filename", "estimated_time", "eta", "timestamp", "app_name"],
    "print_complete": [
        "archive_id",
        "run_id",
        "printer",
        "filename",
        "duration",
        "filament_grams",
        "filament_details",
        "finish_photo_url",
        "timestamp",
        "app_name",
    ],
    "print_failed": [
        "archive_id",
        "run_id",
        "printer",
        "filename",
        "duration",
        "filament_grams",
        "filament_details",
        "progress",
        "reason",
        "finish_photo_url",
        "timestamp",
        "app_name",
    ],
    "print_stopped": [
        "archive_id",
        "run_id",
        "printer",
        "filename",
        "duration",
        "filament_grams",
        "filament_details",
        "progress",
        "finish_photo_url",
        "timestamp",
        "app_name",
    ],
    "print_progress": ["printer", "filename", "progress", "remaining_time", "eta", "timestamp", "app_name"],
    "print_confirm_request": ["printer", "filename", "confirm_url", "archive_id", "run_id", "timestamp", "app_name"],
    "ai_failure_detection": ["printer", "task_name", "confidence", "action", "timestamp", "app_name"],
    "plate_not_empty": ["printer", "difference_percent", "timestamp", "app_name"],
    "print_pause_upcoming": [
        "printer",
        "filename",
        "time_to_pause",
        "eta",
        "layer",
        "total_layers",
        "timestamp",
        "app_name",
    ],
    "first_layer_complete": ["printer", "filename", "total_layers", "timestamp", "app_name"],
    "stock_reorder_alert": ["material", "brand", "stock_g", "rate_g_day", "days_left", "timestamp", "app_name"],
    "stock_break_alert": [
        "material",
        "brand",
        "stock_g",
        "rate_g_day",
        "days_left",
        "lead_time_days",
        "timestamp",
        "app_name",
    ],
    "print_missing_spool_assignment": [
        "printer",
        "missing_slots",
        "missing_slot_details",
        "timestamp",
        "app_name",
    ],
    "printer_offline": ["printer", "timestamp", "app_name"],
    "printer_error": ["printer", "error_type", "error_detail", "timestamp", "app_name"],
    "filament_low": ["printer", "slot", "remaining_percent", "color", "timestamp", "app_name"],
    "maintenance_due": ["printer", "items", "timestamp", "app_name"],
    "ams_humidity_high": ["printer", "ams_label", "humidity", "threshold", "timestamp", "app_name"],
    "ams_temperature_high": ["printer", "ams_label", "temperature", "threshold", "timestamp", "app_name"],
    "bed_cooled": ["printer", "bed_temp", "threshold", "filename", "timestamp", "app_name"],
    "storage_sensor_alert": ["location", "sensor", "state", "timestamp", "app_name"],
    "ha_sensor_alert": ["printer", "sensor", "state", "timestamp", "app_name"],
    "test": ["app_name", "timestamp"],
    # Queue notifications
    "queue_job_added": ["job_name", "target", "timestamp", "app_name"],
    "queue_job_assigned": ["job_name", "printer", "target_model", "timestamp", "app_name"],
    "queue_job_started": ["printer", "job_name", "estimated_time", "eta", "timestamp", "app_name"],
    "queue_job_waiting": ["job_name", "target_model", "waiting_reason", "timestamp", "app_name"],
    "queue_job_skipped": ["printer", "job_name", "reason", "timestamp", "app_name"],
    "queue_job_failed": ["printer", "job_name", "reason", "timestamp", "app_name"],
    "queue_completed": ["completed_count", "timestamp", "app_name"],
    # User management notifications
    "user_created": ["username", "login_url", "app_name", "timestamp"],
    "password_reset": ["username", "app_name", "timestamp"],
    # User email print notifications
    "user_print_start": ["username", "printer", "filename", "timestamp", "app_name"],
    "user_print_complete": ["username", "printer", "filename", "timestamp", "app_name"],
    "user_print_failed": ["username", "printer", "filename", "timestamp", "app_name"],
    "user_print_stopped": ["username", "printer", "filename", "timestamp", "app_name"],
}

# Sample data for previewing templates
SAMPLE_DATA: dict[str, dict[str, str]] = {
    "print_start": {
        "printer": "Bambu X1C",
        "filename": "Benchy.3mf",
        "estimated_time": "1h 23m",
        "eta": "15:53",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "print_complete": {
        "archive_id": "42",
        "run_id": "108",
        "printer": "Bambu X1C",
        "filename": "Benchy.3mf",
        "duration": "1h 18m",
        "filament_grams": "15.2",
        "filament_details": "AMS-A T1 PLA: 12.4g | AMS-A T3 PETG: 2.8g",
        "finish_photo_url": "/api/v1/archives/123/photos/finish_20240115_154800_abc12345.jpg",
        "timestamp": "2024-01-15 15:48",
        "app_name": "PrintOps",
    },
    "print_failed": {
        "archive_id": "42",
        "run_id": "108",
        "printer": "Bambu X1C",
        "filename": "Benchy.3mf",
        "duration": "0h 45m",
        "filament_grams": "7.6",
        "filament_details": "AMS-A T1 PLA: 7.6g",
        "progress": "50",
        "reason": "Filament runout",
        "finish_photo_url": "/api/v1/archives/123/photos/finish_20240115_151500_def67890.jpg",
        "timestamp": "2024-01-15 15:15",
        "app_name": "PrintOps",
    },
    "print_stopped": {
        "archive_id": "42",
        "run_id": "108",
        "printer": "Bambu X1C",
        "filename": "Benchy.3mf",
        "duration": "0h 30m",
        "filament_grams": "4.6",
        "filament_details": "AMS-A T2 PLA: 4.6g",
        "progress": "30",
        "finish_photo_url": "/api/v1/archives/123/photos/finish_20240115_150000_ghi11223.jpg",
        "timestamp": "2024-01-15 15:00",
        "app_name": "PrintOps",
    },
    "print_confirm_request": {
        "printer": "Workshop printer",
        "filename": "Mounting bracket",
        "confirm_url": "https://printops.example/archives?confirm=42&run=19",
        "archive_id": "42",
        "run_id": "19",
        "timestamp": "2026-11-09 12:00",
        "app_name": "PrintOps",
    },
    "ai_failure_detection": {
        "printer": "Workshop printer",
        "task_name": "Mounting bracket",
        "confidence": "0.87",
        "action": "Paused",
    },
    "plate_not_empty": {"printer": "Workshop printer", "difference_percent": "12.5"},
    "print_pause_upcoming": {
        "printer": "Workshop printer",
        "filename": "Mounting bracket",
        "time_to_pause": "5m",
        "eta": "16:05",
        "layer": "42",
        "total_layers": "120",
    },
    "first_layer_complete": {"printer": "Workshop printer", "filename": "Mounting bracket", "total_layers": "126"},
    "stock_reorder_alert": {
        "material": "PLA",
        "brand": "Example",
        "stock_g": "320",
        "rate_g_day": "80",
        "days_left": "4",
    },
    "stock_break_alert": {
        "material": "PLA",
        "brand": "Example",
        "stock_g": "160",
        "rate_g_day": "80",
        "days_left": "2",
        "lead_time_days": "5",
    },
    "print_progress": {
        "printer": "Bambu X1C",
        "filename": "Benchy.3mf",
        "progress": "50",
        "remaining_time": "0h 41m",
        "eta": "15:41",
        "timestamp": "2024-01-15 15:00",
        "app_name": "PrintOps",
    },
    "print_missing_spool_assignment": {
        "printer": "Bambu X1C",
        "missing_slots": "A1, A3",
        "missing_slot_details": "- A1: PLA Basic\n- A3: PETG HF",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "printer_offline": {
        "printer": "Bambu X1C",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "printer_error": {
        "printer": "Bambu X1C",
        "error_type": "AMS Error",
        "error_detail": "Filament slot 1 jammed",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "filament_low": {
        "printer": "Bambu X1C",
        "slot": "1",
        "remaining_percent": "15",
        "color": "Black PLA",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "maintenance_due": {
        "printer": "Bambu X1C",
        "items": "• Nozzle cleaning (OVERDUE)\n• Carbon rod lubrication (Soon)",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "ams_humidity_high": {
        "printer": "Bambu X1C",
        "ams_label": "AMS-A",
        "humidity": "75",
        "threshold": "60",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "ams_temperature_high": {
        "printer": "Bambu X1C",
        "ams_label": "AMS-A",
        "temperature": "42",
        "threshold": "35",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "bed_cooled": {
        "printer": "Bambu X1C",
        "bed_temp": "34",
        "threshold": "35",
        "filename": "Benchy",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "storage_sensor_alert": {"location": "Dry box", "sensor": "Humidity", "state": "65 %"},
    "ha_sensor_alert": {
        "printer": "Bambu X1C",
        "sensor": "Enclosure Door",
        "state": "open",
        "timestamp": "2024-01-15 14:30",
        "app_name": "Bambuddy",
    },
    "test": {
        "app_name": "PrintOps",
        "timestamp": "2024-01-15 14:30",
    },
    # Queue notifications
    "queue_job_added": {
        "job_name": "Benchy.3mf",
        "target": "Bambu X1C",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "queue_job_assigned": {
        "job_name": "Benchy.3mf",
        "printer": "Bambu X1C #1",
        "target_model": "X1C",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "queue_job_started": {
        "printer": "Bambu X1C",
        "job_name": "Benchy.3mf",
        "estimated_time": "1h 23m",
        "eta": "15:53",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "queue_job_waiting": {
        "job_name": "Benchy.3mf",
        "target_model": "X1C",
        "waiting_reason": "Printer1 (needs PLA)",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "queue_job_skipped": {
        "printer": "Bambu X1C",
        "job_name": "Benchy.3mf",
        "reason": "Previous print failed",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "queue_job_failed": {
        "printer": "Bambu X1C",
        "job_name": "Benchy.3mf",
        "reason": "Upload failed: connection timeout",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "queue_completed": {
        "completed_count": "5",
        "timestamp": "2024-01-15 18:30",
        "app_name": "PrintOps",
    },
    # User management notifications
    "user_created": {
        "username": "john_doe",
        "login_url": "https://printops.example.com/login",
        "app_name": "PrintOps",
        "timestamp": "2024-01-15 14:30",
    },
    "password_reset": {
        "username": "john_doe",
        "app_name": "PrintOps",
        "timestamp": "2024-01-15 14:30",
    },
    # User email print notifications
    "user_print_start": {
        "username": "john_doe",
        "printer": "Bambu X1C",
        "filename": "Benchy.3mf",
        "timestamp": "2024-01-15 14:30",
        "app_name": "PrintOps",
    },
    "user_print_complete": {
        "username": "john_doe",
        "printer": "Bambu X1C",
        "filename": "Benchy.3mf",
        "timestamp": "2024-01-15 15:48",
        "app_name": "PrintOps",
    },
    "user_print_failed": {
        "username": "john_doe",
        "printer": "Bambu X1C",
        "filename": "Benchy.3mf",
        "timestamp": "2024-01-15 15:15",
        "app_name": "PrintOps",
    },
    "user_print_stopped": {
        "username": "john_doe",
        "printer": "Bambu X1C",
        "filename": "Benchy.3mf",
        "timestamp": "2024-01-15 15:15",
        "app_name": "PrintOps",
    },
}


class NotificationTemplateBase(BaseModel):
    """Base schema for notification templates."""

    title_template: str = Field(..., min_length=1, max_length=200)
    body_template: str = Field(..., min_length=1, max_length=2000)


class NotificationTemplateUpdate(IgnoresNullForRequiredColumns):
    """Schema for updating a notification template."""

    __orm_table__ = "notification_templates"

    title_template: str | None = Field(default=None, min_length=1, max_length=200)
    body_template: str | None = Field(default=None, min_length=1, max_length=2000)


class NotificationTemplateResponse(NotificationTemplateBase):
    """Schema for notification template API responses."""

    id: int
    event_type: str
    name: str
    is_default: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TemplateVariableInfo(BaseModel):
    """Information about a template variable."""

    name: str
    description: str


class EventVariablesResponse(BaseModel):
    """Response for available variables per event type."""

    event_type: str
    event_name: str
    variables: list[str]


class TemplatePreviewRequest(BaseModel):
    """Request to preview a template with sample data."""

    event_type: str
    title_template: str
    body_template: str


class TemplatePreviewResponse(BaseModel):
    """Response with rendered template preview."""

    title: str
    body: str
