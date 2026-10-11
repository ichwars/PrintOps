from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.utils.printer_models import PRINTER_MODEL_ID_MAP, PRINTER_MODEL_MAP


def known_printer_model(value: str | None) -> str | None:
    """Canonicalize documented keys only; do not accept guessed model names."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    normalized = PRINTER_MODEL_ID_MAP.get(value, PRINTER_MODEL_MAP.get(value, value))
    return normalized if normalized in PRINTER_MODEL_MAP.values() else None


class SpoolFilamentPresetInput(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    printer_model: str = Field(max_length=60)
    slicer_filament: str | None = Field(default=None, max_length=128)
    slicer_filament_name: str | None = Field(default=None, max_length=255)

    @field_validator("printer_model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        normalized = known_printer_model(value)
        if normalized is None:
            raise ValueError("Unknown printer model")
        return normalized

    @field_validator("slicer_filament", "slicer_filament_name")
    @classmethod
    def trim_optional(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def clear_generic_name(self):
        if self.slicer_filament is None:
            self.slicer_filament_name = None
        return self
