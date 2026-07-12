from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from backend.app.services.equipment_costs import calculate_hourly_rate, calculate_residual_value


class EquipmentBase(BaseModel):
    equipment_type: Literal["dryer"] = "dryer"
    name: str = Field(min_length=1, max_length=100)
    is_active: bool = True
    acquisition_date: date
    acquisition_value: Decimal = Field(ge=0)
    service_years: Decimal = Field(gt=0)
    annual_hours: Decimal = Field(gt=0)
    maintenance_rate: Decimal = Field(default=Decimal("0"), ge=0)
    nominal_power_watts: Decimal = Field(default=Decimal("0"), ge=0)


class EquipmentCreate(EquipmentBase):
    pass


class EquipmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
    acquisition_date: date | None = None
    acquisition_value: Decimal | None = Field(default=None, ge=0)
    service_years: Decimal | None = Field(default=None, gt=0)
    annual_hours: Decimal | None = Field(default=None, gt=0)
    maintenance_rate: Decimal | None = Field(default=None, ge=0)
    nominal_power_watts: Decimal | None = Field(default=None, ge=0)


class EquipmentRead(EquipmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def residual_value(self) -> Decimal:
        return calculate_residual_value(self.acquisition_value, self.acquisition_date, self.service_years)

    @computed_field
    @property
    def hourly_rate(self) -> Decimal:
        return calculate_hourly_rate(self.acquisition_value, self.service_years, self.annual_hours, self.maintenance_rate)
