from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.schemas.spool import SpoolKProfileBase
from backend.app.schemas.spool_filament_preset import SpoolFilamentPresetInput


class ProfileProduct(BaseModel):
    brand: str = Field(default="", max_length=100)
    material: str = Field(min_length=1, max_length=50)
    subtype: str = Field(default="", max_length=50)
    color_name: str = Field(default="", max_length=100)

    @field_validator("brand", "material", "subtype", "color_name", mode="before")
    @classmethod
    def trim_product(cls, value):
        return value.strip() if isinstance(value, str) else value


class ProfileCalibration(SpoolKProfileBase):
    printer_id: Annotated[int, Field(gt=0)]
    extruder: Annotated[int, Field(ge=0, le=1)] = 0
    nozzle_diameter: Annotated[str, Field(min_length=1, max_length=10)] = "0.4"
    nozzle_type: str | None = Field(default=None, max_length=50)
    name: str | None = Field(default=None, max_length=100)
    k_value: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    cali_idx: int | None = Field(default=None, ge=-1)
    setting_id: str | None = Field(default=None, max_length=50)


class FilamentProfileWrite(ProfileProduct):
    model_config = ConfigDict(extra="forbid")

    slicer_filament: str | None = Field(default=None, max_length=128)
    slicer_filament_name: str | None = Field(default=None, max_length=255)
    presets: list[SpoolFilamentPresetInput] = Field(default_factory=list)
    k_profiles: list[ProfileCalibration] = Field(default_factory=list)
