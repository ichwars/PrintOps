"""Generate deterministic binary fixtures for layout-asset preflight tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pikepdf
import reportlab
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "backend" / "tests" / "fixtures" / "document_layouts"


def _letterhead(path: Path, page_size: tuple[float, float], title: str) -> None:
    canvas = Canvas(str(path), pagesize=page_size, invariant=True, pageCompression=1)
    width, height = page_size
    canvas.setFillColorRGB(0.15, 0.35, 0.25)
    canvas.rect(0, height - 42, width, 42, fill=1, stroke=0)
    canvas.setFillColorRGB(1, 1, 1)
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(24, height - 27, title)
    canvas.setFillColorRGB(0.35, 0.35, 0.35)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(24, 18, "PrintOps test fixture - no customer data")
    canvas.save()


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    a4 = TARGET / "letterhead-a4.pdf"
    _letterhead(a4, A4, "PrintOps A4")
    _letterhead(TARGET / "letterhead-letter.pdf", LETTER, "PrintOps Letter")
    with pikepdf.open(a4) as source:
        source.Root.OpenAction = pikepdf.Dictionary(
            S=pikepdf.Name.JavaScript,
            JS=pikepdf.String("app.alert('blocked')"),
        )
        source.save(TARGET / "active-content.pdf", deterministic_id=True)
    font = Path(reportlab.__file__).resolve().parent / "fonts" / "Vera.ttf"
    shutil.copyfile(font, TARGET / "test-font.ttf")


if __name__ == "__main__":
    main()
