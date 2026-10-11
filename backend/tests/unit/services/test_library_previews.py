"""Real spreadsheet parsing keeps compact shared strings from expanding in memory."""

import io
import tracemalloc
import zipfile
from xml.etree import ElementTree

from openpyxl import Workbook

from backend.app.services.library_previews import spreadsheet_preview


def test_xlsx_shared_strings_are_bounded_while_rows_are_projected(tmp_path):
    workbook = Workbook()
    for index in range(5):
        worksheet = workbook.active if index == 0 else workbook.create_sheet()
        worksheet.title = f"Repeated {index + 1}"
        for _ in range(100):
            worksheet.append(["shared"] * 40)
    source = io.BytesIO()
    workbook.save(source)
    workbook.close()
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    result = io.BytesIO()
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(result, "w") as archive:
        for name in original.namelist():
            content = original.read(name)
            if name.startswith("xl/worksheets/sheet"):
                tree = ElementTree.fromstring(content)
                for cell in tree.iter(f"{{{namespace}}}c"):
                    cell.set("t", "s")
                    for child in list(cell):
                        cell.remove(child)
                    ElementTree.SubElement(cell, f"{{{namespace}}}v").text = "0"
                content = ElementTree.tostring(tree)
            elif name == "[Content_Types].xml":
                content = content.replace(
                    b"</Types>",
                    b'<Override PartName="/xl/sharedStrings.xml" '
                    b'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
                    b"</Types>",
                )
            archive.writestr(name, content)
        archive.writestr(
            "xl/sharedStrings.xml",
            f'<sst xmlns="{namespace}" count="20000" uniqueCount="1"><si><t>'
            + "x" * 3000
            + "</t></si></sst>",
        )
    path = tmp_path / "shared.xlsx"
    path.write_bytes(result.getvalue())
    assert path.stat().st_size < 2 * 1024 * 1024

    # A post-hoc JSON trim still passes output assertions but first allocates
    # 20,000 separate 2,000-character slices (~40 MiB). Allow the existing
    # bounded 20 MiB read buffer, but measure the real parser's transient peak.
    tracemalloc.start()
    try:
        preview = spreadsheet_preview(path, "xlsx")
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak_bytes < 24 * 1024 * 1024, f"Peak parser allocation: {peak_bytes} bytes"
    assert preview["truncated"] is True
    assert [(sheet["totalRows"], sheet["totalCols"]) for sheet in preview["sheets"]] == [(100, 40)] * 5
    assert sum(len(cell) for sheet in preview["sheets"] for row in sheet["rows"] for cell in row) == 300_000
    assert preview["sheets"][0]["rows"][0][0] == "x" * 2000
    assert all(sheet["rows"] == [] for sheet in preview["sheets"][1:])
