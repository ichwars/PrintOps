from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.services.number_sequence import validate_number_pattern

NumberSequenceKey = Literal["customer", "offer", "order", "invoice"]
NumberSequenceResetPolicy = Literal["none", "yearly"]


class NumberSequenceValues(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    prefix: str = Field(default="", max_length=20)
    pattern: str = Field(min_length=1, max_length=100)
    next_value: int = Field(ge=1)
    reset_policy: NumberSequenceResetPolicy = "none"

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, value: str) -> str:
        validate_number_pattern(value)
        return value


class NumberSequenceCreate(NumberSequenceValues):
    key: NumberSequenceKey


class NumberSequenceUpdate(NumberSequenceValues):
    version: int = Field(ge=1)


class NumberSequenceResponse(NumberSequenceValues):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: int
    business_profile_id: int
    key: NumberSequenceKey
    current_period: str | None
    version: int
    created_at: datetime
    updated_at: datetime
