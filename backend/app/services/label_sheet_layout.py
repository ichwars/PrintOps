"""Physical geometry shared by the label editor and PDF renderer."""

from dataclasses import dataclass
from math import isfinite
from typing import Literal

from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm

PageSize = Literal["a4", "letter"]
PAGE_SIZES = {"a4": A4, "letter": letter}
MIN_LABEL_W_MM = 40.0
MIN_LABEL_H_MM = 20.0
MAX_LENGTH_MM = 300.0
MAX_COLS = 20
MAX_ROWS = 40


@dataclass(frozen=True)
class SheetLayout:
    page: PageSize
    label_w_mm: float
    label_h_mm: float
    cols: int
    rows: int
    top_mm: float
    left_mm: float
    col_gap_mm: float = 0
    row_gap_mm: float = 0

    @property
    def capacity(self) -> int:
        return self.cols * self.rows

    @property
    def page_size(self) -> tuple[float, float]:
        return PAGE_SIZES[self.page]

    def validate(self) -> None:
        lengths = (
            self.label_w_mm,
            self.label_h_mm,
            self.top_mm,
            self.left_mm,
            self.col_gap_mm,
            self.row_gap_mm,
        )
        if self.page not in PAGE_SIZES or not all(isfinite(value) and 0 <= value <= MAX_LENGTH_MM for value in lengths):
            raise ValueError("Invalid sheet dimensions")
        if self.label_w_mm < MIN_LABEL_W_MM or self.label_h_mm < MIN_LABEL_H_MM:
            raise ValueError(f"Labels must be at least {MIN_LABEL_W_MM:g} × {MIN_LABEL_H_MM:g} mm")
        if type(self.cols) is not int or type(self.rows) is not int:
            raise ValueError("Sheet columns and rows must be integers")
        if not 1 <= self.cols <= MAX_COLS or not 1 <= self.rows <= MAX_ROWS:
            raise ValueError("Invalid sheet grid size")
        width, height = self.page_size
        grid_width = self.left_mm + self.cols * self.label_w_mm + (self.cols - 1) * self.col_gap_mm
        grid_height = self.top_mm + self.rows * self.label_h_mm + (self.rows - 1) * self.row_gap_mm
        if grid_width > width / mm + 0.01 or grid_height > height / mm + 0.01:
            raise ValueError("The label grid and margins must fit on the selected paper")
