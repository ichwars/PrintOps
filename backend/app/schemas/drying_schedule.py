from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator

from backend.app.services.drying_schedule_time import daily_occurrence


class DryingScheduleWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    ams_id: StrictInt = Field(ge=0, le=135)
    local_time: str = Field(max_length=5)
    timezone: str = Field(min_length=1, max_length=100)
    filament: str = Field(min_length=1, max_length=100)
    temperature: StrictInt = Field(ge=45, le=85)
    duration_hours: StrictInt = Field(ge=1, le=24)
    rotate_tray: StrictBool = False
    enabled: StrictBool = False

    @field_validator("local_time")
    @classmethod
    def valid_time(cls, value):
        daily_occurrence(date(2026, 1, 1), value, "UTC")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        daily_occurrence(date(2026, 1, 1), "00:00", value)
        return value

    @field_validator("filament")
    @classmethod
    def valid_filament(cls, value):
        value = value.strip()
        if not value or any(ord(character) < 32 for character in value):
            raise ValueError("Use a material name without control characters")
        return value


class DryingScheduleResponse(DryingScheduleWrite):
    id: int
    printer_id: int


class DryingRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    schedule_id: int
    printer_id: int
    ams_id: int
    occurrence_day: str
    status: str
    reason: str | None
    active_printer_id: int | None
    due_at: datetime
    claimed_at: datetime
    publication_at: datetime | None
    observed_running_at: datetime | None
    finished_at: datetime | None

    @field_validator("due_at", "claimed_at", "publication_at", "observed_running_at", "finished_at")
    @classmethod
    def utc_timestamp(cls, value):
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value
