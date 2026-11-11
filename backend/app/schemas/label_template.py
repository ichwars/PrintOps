"""Validate saved and temporary label sheet geometry consistently."""

import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.services.label_sheet_layout import (
    MAX_COLS,
    MAX_LENGTH_MM,
    MAX_ROWS,
    MIN_LABEL_H_MM,
    MIN_LABEL_W_MM,
    PageSize,
    SheetLayout,
)


class SheetLayoutSpec(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    page: PageSize
    label_w_mm: float = Field(ge=MIN_LABEL_W_MM, le=MAX_LENGTH_MM)
    label_h_mm: float = Field(ge=MIN_LABEL_H_MM, le=MAX_LENGTH_MM)
    cols: int = Field(ge=1, le=MAX_COLS, strict=True)
    rows: int = Field(ge=1, le=MAX_ROWS, strict=True)
    top_mm: float = Field(ge=0, le=MAX_LENGTH_MM)
    left_mm: float = Field(ge=0, le=MAX_LENGTH_MM)
    col_gap_mm: float = Field(default=0, ge=0, le=MAX_LENGTH_MM)
    row_gap_mm: float = Field(default=0, ge=0, le=MAX_LENGTH_MM)

    @model_validator(mode="after")
    def fits_on_paper(self):
        self.to_layout().validate()
        return self

    def to_layout(self) -> SheetLayout:
        return SheetLayout(**self.model_dump())


class LabelTemplateWrite(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    layout: SheetLayoutSpec

    @field_validator("name")
    @classmethod
    def normalize_name(cls, name: str) -> str:
        cleaned = unicodedata.normalize("NFC", name.strip())
        if not cleaned or len(cleaned) > 100 or len(cleaned.casefold()) > 300:
            raise ValueError("Template name must contain 1 to 100 characters")
        return cleaned


class LabelTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    layout: SheetLayoutSpec
