import io

import pytest
from PIL import Image
from reportlab.pdfgen import canvas

from backend.app.services import pdf_render


def document(width=200, height=300, pages=1):
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=(width, height))
    for index in range(pages):
        pdf.drawString(10, 20, str(index))
        pdf.showPage()
    pdf.save()
    return output.getvalue()


def test_thumbnail_renders_first_page_even_if_print_batch_is_too_large(monkeypatch):
    monkeypatch.setattr(pdf_render, "MAX_PAGES", 1)
    pdf = document(pages=2)
    with pytest.raises(ValueError, match="page count"):
        pdf_render.pdf_to_pngs(pdf)
    with Image.open(io.BytesIO(pdf_render.render_pdf_thumbnail(pdf))) as image:
        assert max(image.size) == 256


def test_print_resolution_rejects_huge_geometry_before_allocating():
    with pytest.raises(ValueError, match="pixel budget"):
        pdf_render.pdf_to_pngs(document(10000, 10000), 600)


def test_total_pixel_budget_is_shared_across_pages(monkeypatch):
    monkeypatch.setattr(pdf_render, "MAX_TOTAL_PIXELS", 100_000)
    with pytest.raises(ValueError, match="pixel budget"):
        pdf_render.pdf_to_pngs(document(pages=2), 72)


@pytest.mark.parametrize("pdf", [b"", b"corrupt pdf"])
def test_corrupt_pdf_is_reported_as_validation_error(pdf):
    with pytest.raises(ValueError):
        pdf_render.render_pdf_thumbnail(pdf)
