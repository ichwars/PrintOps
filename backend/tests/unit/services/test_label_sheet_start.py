"""Inspect actual PDF pages and placement for partially used Avery sheets."""

import io

import pikepdf
import pytest
from reportlab.lib.units import mm

from backend.app.services.label_renderer import LabelData, render_labels


def label(spool_id=1, rgba="00000000", extra_colors=None):
    return LabelData(
        spool_id=spool_id,
        name="Transparent PLA",
        material="PLA",
        rgba=rgba,
        extra_colors=extra_colors,
        deeplink_url=f"https://example.test/inventory?spool={spool_id}",
    )


def boxes(page, width_mm, height_mm):
    return [
        tuple(float(v) for v in operands)
        for operands, operator in pikepdf.parse_content_stream(page)
        if str(operator) == "re"
        and len(operands) == 4
        and float(operands[2]) == pytest.approx(width_mm * mm, abs=0.001)
        and float(operands[3]) == pytest.approx(height_mm * mm, abs=0.001)
    ]


@pytest.mark.parametrize(
    "template,capacity,width,height,left,top,gap,page_width,page_height",
    [
        ("avery_l7160", 21, 63.5, 38.1, 7, 15.15, 2.5, 210 * mm, 297 * mm),
        ("avery_5160", 30, 66.675, 25.4, 4.76, 12.7, 3.175, 612, 792),
    ],
)
@pytest.mark.parametrize("start", [1, 2, 4, "last"])
def test_first_sheet_offset_and_full_following_sheets(
    template, capacity, width, height, left, top, gap, page_width, page_height, start
):
    position = capacity if start == "last" else start
    labels = [label(i) for i in range(1, capacity + 3)]
    pdf_bytes = render_labels(template, labels, start_position=position)
    with pikepdf.Pdf.open(io.BytesIO(pdf_bytes)) as pdf:
        rectangles = [boxes(page, width, height) for page in pdf.pages]
        first_count = capacity - position + 1
        remaining = len(labels) - first_count
        expected_counts = [first_count] + [min(capacity, remaining - i) for i in range(0, remaining, capacity)]
        assert list(map(len, rectangles)) == expected_counts
        row, col = divmod(position - 1, 3)
        assert rectangles[0][0][:2] == pytest.approx(
            ((left + col * (width + gap)) * mm, page_height - (top + (row + 1) * height) * mm), abs=0.001
        )
        for page, page_boxes in zip(pdf.pages, rectangles, strict=True):
            assert [float(value) for value in page.MediaBox][2:] == pytest.approx((page_width, page_height), abs=0.001)
            for x, y, w, h in page_boxes:
                assert 0 <= x <= x + w <= page_width
                assert 0 <= y <= y + h <= page_height
        assert rectangles[1][0][:2] == pytest.approx((left * mm, page_height - (top + height) * mm), abs=0.001)


@pytest.mark.parametrize(
    "template,position",
    [
        ("avery_l7160", 22),
        ("avery_5160", 31),
        ("avery_l7160", 0),
        ("avery_5160", -1),
        ("box_62x29", 2),
        ("avery_l7160", 1.5),
        ("avery_l7160", True),
        ("avery_5160", "2"),
    ],
)
def test_invalid_start_position_is_rejected(template, position):
    with pytest.raises(ValueError, match="start_position"):
        render_labels(template, [label()], start_position=position)


@pytest.mark.parametrize(
    "template", ["avery_l7160", "avery_5160", "box_62x29", "box_40x30", "ams_holder_74x33", "ams_holder_75x55"]
)
def test_transparent_swatch_does_not_change_or_mask_black_white_qr(template):
    images = []
    for rgba, extras in (("00000000", None), ("00000080", None), ("FF0000FF", ["00000000"]), ("FF0000FF", None)):
        with pikepdf.Pdf.open(io.BytesIO(render_labels(template, [label(rgba=rgba, extra_colors=extras)]))) as pdf:
            # The embedded bitmap can be correct while the PDF paints it with
            # zero opacity inherited from a transparent swatch.
            alpha, stack = 1.0, []
            painted = []
            for operands, operator in pikepdf.parse_content_stream(pdf.pages[0]):
                if str(operator) == "q":
                    stack.append(alpha)
                elif str(operator) == "Q":
                    alpha = stack.pop()
                elif str(operator) == "gs":
                    state = pdf.pages[0].Resources.ExtGState[operands[0]]
                    alpha = float(state.get("/ca", alpha))
                elif str(operator) == "Do":
                    painted.append(alpha)
            assert painted == [1.0]
            image = next(iter(pdf.pages[0].images.values()))
            assert "/SMask" not in image
            bitmap = pikepdf.PdfImage(image).as_pil_image().convert("RGB")
            assert set(bitmap.getdata()) == {(0, 0, 0), (255, 255, 255)}
            assert bitmap.getpixel((0, 0)) == (255, 255, 255)
            images.append(bitmap.tobytes())
    assert all(image == images[0] for image in images)
