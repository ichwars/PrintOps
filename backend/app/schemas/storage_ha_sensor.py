"""Storage bindings intentionally have no printer or stock control fields."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StorageHASensorBase(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    name: str = Field(min_length=1, max_length=100)
    entity_id: str = Field(max_length=255, pattern=r"^sensor\.[a-z0-9_]+$")
    device_class: Literal["temperature", "humidity"]
    unit: Literal["°C", "°F", "K", "%"]
    alert_above: float | None = Field(default=None, allow_inf_nan=False)
    alert_below: float | None = Field(default=None, allow_inf_nan=False)
    notify_on_alert: bool = False

    @model_validator(mode="after")
    def validate_environmental_binding(self):
        if not self.name.strip():
            raise ValueError("name must not be blank")
        if (self.device_class == "humidity") != (self.unit == "%"):
            raise ValueError("unit must match the environmental device class")
        if self.alert_above is not None and self.alert_below is not None and self.alert_below >= self.alert_above:
            raise ValueError("alert_below must be lower than alert_above")
        if self.notify_on_alert and self.alert_above is None and self.alert_below is None:
            raise ValueError("notifications require an alert threshold")
        return self


class StorageHASensorCreate(StorageHASensorBase):
    location_id: int = Field(gt=0)


class StorageHASensorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    entity_id: str | None = Field(default=None, max_length=255, pattern=r"^sensor\.[a-z0-9_]+$")
    device_class: Literal["temperature", "humidity"] | None = None
    unit: Literal["°C", "°F", "K", "%"] | None = None
    alert_above: float | None = Field(default=None, allow_inf_nan=False)
    alert_below: float | None = Field(default=None, allow_inf_nan=False)
    notify_on_alert: bool | None = None


class StorageHASensorResponse(StorageHASensorCreate):
    id: int
    last_state: str | None
    last_changed: datetime | None
    last_checked: datetime | None
    last_read_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StorageHASensorReading(BaseModel):
    id: int
    location_id: int
    name: str
    entity_id: str
    device_class: str
    unit: str
    value: float | None
    alerting: bool
    status: Literal["fresh", "stale", "unavailable", "pending"]
    last_checked: datetime | None
    last_read_at: datetime | None
