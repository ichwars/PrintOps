"""File-manager document previews exercise bounded, scoped consumer routes."""

import io
import zipfile

import pytest
from openpyxl import Workbook

from backend.app.models.library import LibraryFile


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "base_dir", tmp_path)
    monkeypatch.setattr(settings, "archive_dir", tmp_path / "archive")


async def _upload(client, name, data):
    response = await client.post("/api/v1/library/files", files={"file": (name, data, "application/octet-stream")})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("kind", ["csv", "xlsx", "ods"])
async def test_spreadsheet_preview_preserves_text_without_evaluating_formulas(async_client, kind):
    if kind == "csv":
        data = b'name,value\n"<script>text</script>","=SUM(1,2)"\n'
    elif kind == "xlsx":
        workbook = Workbook()
        workbook.active.append(["name", "value"])
        workbook.active.append(["<script>text</script>", "=SUM(1,2)"])
        stream = io.BytesIO()
        workbook.save(stream)
        data = stream.getvalue()
    else:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr(
                "content.xml",
                """<office:document-content
                xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
                xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
                <office:body><office:spreadsheet><table:table table:name="Sheet1">
                <table:table-row><table:table-cell><text:p>name</text:p></table:table-cell>
                <table:table-cell><text:p>value</text:p></table:table-cell></table:table-row>
                <table:table-row><table:table-cell><text:p>&lt;script&gt;text&lt;/script&gt;</text:p></table:table-cell>
                <table:table-cell><text:p>=SUM(1,2)</text:p></table:table-cell></table:table-row>
                </table:table></office:spreadsheet></office:body></office:document-content>""",
            )
        data = stream.getvalue()
    uploaded = await _upload(async_client, f"table.{kind}", data)
    preview = await async_client.get(f"/api/v1/library/files/{uploaded['id']}/spreadsheet-preview")
    assert preview.status_code == 200, preview.text
    assert preview.json()["sheets"][0]["rows"] == [["name", "value"], ["<script>text</script>", "=SUM(1,2)"]]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_spreadsheet_preview_is_bounded_by_actual_disk_bytes(async_client, db_session, tmp_path):
    path = tmp_path / "large.csv"
    with path.open("wb") as handle:
        handle.truncate(20 * 1024 * 1024 + 1)
    row = LibraryFile(filename=path.name, file_path=str(path), file_type="csv", file_size=1)
    db_session.add(row)
    await db_session.commit()
    response = await async_client.get(f"/api/v1/library/files/{row.id}/spreadsheet-preview")
    assert response.status_code == 413


@pytest.mark.asyncio
@pytest.mark.integration
async def test_pdf_upload_gets_a_first_page_thumbnail(async_client):
    from reportlab.pdfgen.canvas import Canvas

    stream = io.BytesIO()
    canvas = Canvas(stream)
    canvas.drawString(40, 700, "Library PDF first page")
    canvas.save()
    uploaded = await _upload(async_client, "instructions.pdf", stream.getvalue())
    assert uploaded["thumbnail_path"]
    thumbnail = await async_client.get(f"/api/v1/library/files/{uploaded['id']}/thumbnail")
    assert thumbnail.status_code == 200
    assert thumbnail.content.startswith(b"\x89PNG")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_ods_repeated_cells_cannot_expand_preview_output(async_client):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "content.xml",
            '<o xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
            '<table:table table:name="Large"><table:table-row table:number-rows-repeated="1000000">'
            '<table:table-cell table:number-columns-repeated="10000"><text:p>'
            + "x"
            * 2000
            + "</text:p></table:table-cell>"
            "</table:table-row></table:table></o>",
        )
    uploaded = await _upload(async_client, "repeated.ods", stream.getvalue())
    response = await async_client.get(f"/api/v1/library/files/{uploaded['id']}/spreadsheet-preview")
    assert response.status_code == 200
    assert len(response.content) < 3 * 1024 * 1024
    assert response.json()["truncated"] is True


@pytest.mark.asyncio
@pytest.mark.integration
async def test_pdf_inside_zip_gets_thumbnail(async_client):
    from reportlab.pdfgen.canvas import Canvas

    pdf = io.BytesIO()
    canvas = Canvas(pdf)
    canvas.drawString(40, 700, "Zipped document")
    canvas.save()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("document.pdf", pdf.getvalue())
    response = await async_client.post(
        "/api/v1/library/files/extract-zip", files={"file": ("documents.zip", stream.getvalue(), "application/zip")}
    )
    assert response.status_code == 200, response.text
    file_id = response.json()["files"][0]["file_id"]
    detail = await async_client.get(f"/api/v1/library/files/{file_id}")
    assert detail.json()["thumbnail_path"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_batch_thumbnail_backfills_pdf_and_reports_corrupt_pdf_failure(async_client, db_session, tmp_path):
    from reportlab.pdfgen.canvas import Canvas

    stream = io.BytesIO()
    canvas = Canvas(stream)
    canvas.drawString(40, 700, "PDF backfill")
    canvas.save()
    good = tmp_path / "good.pdf"
    good.write_bytes(stream.getvalue())
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"broken PDF")
    rows = [
        LibraryFile(filename=p.name, file_path=str(p), file_type="pdf", file_size=p.stat().st_size) for p in [good, bad]
    ]
    db_session.add_all(rows)
    await db_session.commit()
    response = await async_client.post(
        "/api/v1/library/generate-stl-thumbnails", json={"file_ids": [row.id for row in rows]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["processed"] == 2
    assert response.json()["succeeded"] == 1
    assert response.json()["failed"] == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_spreadsheet_preview_and_snapshot_keep_owner_and_update_permissions(async_client, db_session):
    from PIL import Image

    from backend.tests.integration.test_media_tokens import _admin_token, _make_user

    uploaded = await _upload(async_client, "owned.csv", b"part,count\nBolt,4\n")
    row = await db_session.get(LibraryFile, uploaded["id"])
    admin = await _admin_token(async_client, "previewowner")
    owner, owner_id = await _make_user(
        async_client, admin, username="preview_owner", permissions=["library:read_own", "library:update_own"]
    )
    other, _ = await _make_user(
        async_client, admin, username="preview_other", permissions=["library:read_own", "library:update_own"]
    )
    reader, _ = await _make_user(async_client, admin, username="preview_reader", permissions=["library:read_all"])
    row.created_by_id = owner_id
    await db_session.commit()
    url = f"/api/v1/library/files/{row.id}"
    assert (
        await async_client.get(url + "/spreadsheet-preview", headers={"Authorization": f"Bearer {owner}"})
    ).status_code == 200
    assert (
        await async_client.get(url + "/spreadsheet-preview", headers={"Authorization": f"Bearer {other}"})
    ).status_code == 404
    image = io.BytesIO()
    Image.new("RGB", (512, 512)).save(image, "PNG")
    data = {"thumbnail": ("snapshot.png", image.getvalue(), "image/png")}
    assert (
        await async_client.post(url + "/preview-thumbnail", headers={"Authorization": f"Bearer {other}"}, files=data)
    ).status_code == 404
    assert (
        await async_client.post(url + "/preview-thumbnail", headers={"Authorization": f"Bearer {reader}"}, files=data)
    ).status_code == 403
    response = await async_client.post(
        url + "/preview-thumbnail", headers={"Authorization": f"Bearer {owner}"}, files=data
    )
    assert response.status_code == 200, response.text
    assert response.json()["stored"] is True
    await db_session.refresh(row)
    original = row.thumbnail_path
    assert original
    response = await async_client.post(
        url + "/preview-thumbnail", headers={"Authorization": f"Bearer {owner}"}, files=data
    )
    assert response.status_code == 200
    assert response.json()["stored"] is False
    await db_session.refresh(row)
    assert row.thumbnail_path == original


@pytest.mark.asyncio
@pytest.mark.integration
async def test_preview_thumbnail_rejects_nonraster_content(async_client):
    uploaded = await _upload(async_client, "table.csv", b"part,count\nBolt,4\n")
    response = await async_client.post(
        f"/api/v1/library/files/{uploaded['id']}/preview-thumbnail",
        files={"thumbnail": ("snapshot.png", b'<svg onload="alert(1)"/>', "image/png")},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("kind", ["xlsx", "ods"])
async def test_spreadsheet_preview_rejects_xml_entities_without_exposing_paths(async_client, kind):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "content.xml" if kind == "ods" else "xl/workbook.xml",
            '<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><x>&secret;</x>',
        )
    uploaded = await _upload(async_client, f"hostile.{kind}", stream.getvalue())
    response = await async_client.get(f"/api/v1/library/files/{uploaded['id']}/spreadsheet-preview")
    assert response.status_code == 400
    assert "root:" not in response.text
    assert "passwd" not in response.text


@pytest.mark.asyncio
@pytest.mark.integration
async def test_spreadsheet_preview_reuses_archive_compression_budget(async_client):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("content.xml", "<x>" + "x" * 300_000 + "</x>")
    uploaded = await _upload(async_client, "compressed.ods", stream.getvalue())
    response = await async_client.get(f"/api/v1/library/files/{uploaded['id']}/spreadsheet-preview")
    assert response.status_code == 413


@pytest.mark.asyncio
@pytest.mark.integration
async def test_external_background_thumbnail_backfills_pdf(db_session, tmp_path, monkeypatch):
    from contextlib import asynccontextmanager

    from reportlab.pdfgen.canvas import Canvas

    from backend.app.api.routes import library
    from backend.app.models.library import LibraryFolder

    path = tmp_path / "external.pdf"
    canvas = Canvas(str(path))
    canvas.drawString(40, 700, "External PDF")
    canvas.save()
    folder = LibraryFolder(name="External", is_external=True, external_path=str(tmp_path))
    db_session.add(folder)
    await db_session.flush()
    row = LibraryFile(
        folder_id=folder.id,
        filename=path.name,
        file_path=str(path),
        file_type="pdf",
        file_size=path.stat().st_size,
        is_external=True,
    )
    db_session.add(row)
    await db_session.commit()

    @asynccontextmanager
    async def session():
        yield db_session

    monkeypatch.setattr(library, "async_session", session)
    await library._backfill_external_stl_thumbnails([folder.id])
    await db_session.refresh(row)
    assert row.thumbnail_path
    assert library.to_absolute_path(row.thumbnail_path).read_bytes().startswith(b"\x89PNG")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cell_text_limit_is_reported_as_truncated(async_client):
    uploaded = await _upload(async_client, "long-cell.csv", ("x" * 3000 + "\n").encode())
    response = await async_client.get(f"/api/v1/library/files/{uploaded['id']}/spreadsheet-preview")
    assert response.status_code == 200
    assert len(response.json()["sheets"][0]["rows"][0][0]) == 2000
    assert response.json()["truncated"] is True
