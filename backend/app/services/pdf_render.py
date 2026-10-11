"""Bounded, serialized PDF rasterization for labels and Library thumbnails."""

from __future__ import annotations

import io
import math
import threading
from contextlib import closing

import pypdfium2 as pdfium

_PDFIUM_LOCK = threading.Lock()
MAX_PDF_BYTES = 100 * 1024 * 1024
MAX_PAGES = 500
MAX_PAGE_PIXELS = 40_000_000
MAX_TOTAL_PIXELS = 192_000_000
MAX_OUTPUT_BYTES = 100 * 1024 * 1024


def _render(pdf: bytes, *, dpi: int, thumbnail_size: int | None = None) -> list[bytes]:
    if not pdf or len(pdf) > MAX_PDF_BYTES:
        raise ValueError("PDF input exceeds the supported size")
    if not isinstance(dpi, int) or isinstance(dpi, bool) or not 36 <= dpi <= 600:
        raise ValueError("PDF resolution must be between 36 and 600 dpi")
    result: list[bytes] = []
    pixels = output_bytes = 0
    with _PDFIUM_LOCK:
        try:
            with pdfium.PdfDocument(pdf) as document:
                count = len(document)
                if not count or (thumbnail_size is None and count > MAX_PAGES):
                    raise ValueError("PDF page count exceeds the supported limit")
                for index in range(1 if thumbnail_size is not None else count):
                    with closing(document[index]) as page:
                        width, height = page.get_size()
                        if not all(math.isfinite(v) and v > 0 for v in (width, height)):
                            raise ValueError("Invalid PDF page geometry")
                        scale = thumbnail_size / max(width, height) if thumbnail_size is not None else dpi / 72
                        page_pixels = math.ceil(width * scale) * math.ceil(height * scale)
                        pixels += page_pixels
                        if page_pixels > MAX_PAGE_PIXELS or pixels > MAX_TOTAL_PIXELS:
                            raise ValueError("PDF images exceed the supported pixel budget; reduce dpi or batch size")
                        with closing(page.render(scale=scale, no_smoothimage=True)) as bitmap:
                            image = bitmap.to_pil().convert("RGB")
                        try:
                            stream = io.BytesIO()
                            image.save(stream, "PNG", dpi=(dpi, dpi), optimize=True)
                            png = stream.getvalue()
                        finally:
                            image.close()
                    output_bytes += len(png)
                    if output_bytes > MAX_OUTPUT_BYTES:
                        raise ValueError("PDF images exceed the supported output size")
                    result.append(png)
        except pdfium.PdfiumError as exc:
            raise ValueError("PDF could not be rendered") from exc
    return result


def pdf_to_pngs(pdf: bytes, dpi: int = 300) -> list[bytes]:
    """Render every page at print resolution without smoothing QR modules."""
    return _render(pdf, dpi=dpi)


def render_pdf_thumbnail(pdf: bytes, *, max_size: int = 256) -> bytes:
    """Render only the first page within a bounded thumbnail rectangle."""
    if type(max_size) is not int or not 16 <= max_size <= 1024:
        raise ValueError("Thumbnail size must be between 16 and 1024 pixels")
    return _render(pdf, dpi=72, thumbnail_size=max_size)[0]
