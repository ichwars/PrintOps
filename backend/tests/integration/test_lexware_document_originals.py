"""Original evidence survives disconnect/backup; failed downloads never change the cache."""

import sqlite3
from hashlib import sha256
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import undefer

from backend.app.models.lexware import LexwareConnection
from backend.app.models.lexware_documents import LexwareOriginal
from backend.app.services.lexware_client import LexwareClient
from backend.app.services.lexware_document_originals import MAX_ORIGINAL_BYTES
from backend.app.services.lexware_documents import file_sources, replace_vouchers
from backend.tests.integration.test_lexware_documents import BASE, document_client, seed, snapshot


def transport(monkeypatch, responder):
    monkeypatch.setattr("backend.app.services.lexware_client._throttle", AsyncMock())
    monkeypatch.setattr(
        "backend.app.services.lexware_document_originals.LexwareClient",
        lambda key, **kw: LexwareClient(key, transport=httpx.MockTransport(responder), **kw),
    )


def booking_snapshot(file_id):
    row = snapshot(kind="purchaseinvoice")
    row["detail"]["files"] = [file_id]
    return row


async def test_original_cached_once_survives_disconnect_and_sqlite_backup(
    document_client, db_session, test_engine, monkeypatch
):
    file_id = str(uuid4())
    connection, documents = await seed(db_session, [booking_snapshot(file_id)])
    pdf = b"%PDF-1.7\nmock original evidence\n%%EOF"
    requests = []

    def respond(request):
        requests.append(request)
        assert request.method == "GET" and request.url.path == f"/v1/files/{file_id}"
        return httpx.Response(
            200,
            content=pdf,
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": 'attachment; filename="../../evil.html"',
            },
        )

    transport(monkeypatch, respond)
    url = f"{BASE}/documents/{documents[0].id}/files/{file_id}"
    first = await document_client.get(url)
    assert first.status_code == 200, first.text
    assert first.content == pdf
    assert first.headers["content-disposition"] == f'attachment; filename="lexware-{file_id}.pdf"'
    assert first.headers["etag"] == f'"{sha256(pdf).hexdigest()}"'
    assert first.headers["x-content-type-options"] == "nosniff"
    await db_session.execute(
        update(LexwareConnection)
        .where(LexwareConnection.id == connection.id)
        .values(enabled=False, encrypted_api_key=None, version=2)
    )
    await db_session.commit()
    second = await document_client.get(url)
    assert second.status_code == 200 and second.content == pdf and len(requests) == 1
    detail = (await document_client.get(f"{BASE}/documents/{documents[0].id}")).json()
    assert detail["files"][0]["sha256"] == sha256(pdf).hexdigest()
    assert detail["files"][0]["cached"]
    # Exercise SQLite's real backup/restore API. Binary evidence is wholly inside the DB.
    restored = sqlite3.connect(":memory:", check_same_thread=False)
    async with test_engine.connect() as sql_connection:
        raw = await sql_connection.get_raw_connection()
        await raw.driver_connection.backup(restored)
    row = restored.execute("SELECT content,sha256,source_path FROM lexware_originals").fetchone()
    restored.close()
    assert row == (pdf, sha256(pdf).hexdigest(), f"/v1/files/{file_id}")


@pytest.mark.parametrize(
    "content,media",
    [
        (b"<script>alert(1)</script>", "text/html"),
        (b"<script>alert(1)</script>", "application/pdf"),
        (b"", "application/pdf"),
        (b"%PDF-" + b"x" * MAX_ORIGINAL_BYTES, "application/pdf"),
        (b'<!DOCTYPE a [<!ENTITY secret SYSTEM "file:///etc/passwd">]><a>&secret;</a>', "application/xml"),
    ],
    ids=["html", "mismatched-type", "empty", "oversized", "xml-entity"],
)
async def test_rejects_unsafe_empty_or_oversized_original(document_client, db_session, monkeypatch, content, media):
    file_id = str(uuid4())
    _, documents = await seed(db_session, [booking_snapshot(file_id)])
    transport(monkeypatch, lambda request: httpx.Response(200, content=content, headers={"Content-Type": media}))
    response = await document_client.get(f"{BASE}/documents/{documents[0].id}/files/{file_id}")
    assert response.status_code == 502
    assert "test-only-key" not in response.text
    assert await db_session.scalar(select(func.count()).select_from(LexwareOriginal)) == 0


async def test_disconnect_during_download_prevents_cache_publication(
    document_client, db_session, test_engine, monkeypatch
):
    file_id = str(uuid4())
    connection, documents = await seed(db_session, [booking_snapshot(file_id)])
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    connection_id = connection.id

    async def respond(request):
        async with sessions() as db:
            await db.execute(
                update(LexwareConnection)
                .where(LexwareConnection.id == connection_id)
                .values(enabled=False, encrypted_api_key=None, version=2)
            )
            await db.commit()
        return httpx.Response(200, content=b"%PDF-1.7\noriginal", headers={"Content-Type": "application/pdf"})

    transport(monkeypatch, respond)
    response = await document_client.get(f"{BASE}/documents/{documents[0].id}/files/{file_id}")
    assert response.status_code == 409
    assert await db_session.scalar(select(func.count()).select_from(LexwareOriginal)) == 0


async def test_unknown_file_and_disconnected_cache_miss_do_not_make_requests(document_client, db_session, monkeypatch):
    file_id = str(uuid4())
    connection, documents = await seed(db_session, [booking_snapshot(file_id)])

    def fail(request):
        pytest.fail("Unexpected network request")

    transport(monkeypatch, fail)
    url = f"{BASE}/documents/{documents[0].id}/files"
    assert (await document_client.get(f"{url}/{uuid4()}")).status_code == 404
    connection.enabled = False
    connection.encrypted_api_key = None
    await db_session.commit()
    assert (await document_client.get(f"{url}/{file_id}")).status_code == 409


@pytest.mark.parametrize(
    "kind,endpoint",
    [
        ("invoice", "invoices"),
        ("creditnote", "credit-notes"),
        ("quotation", "quotations"),
        ("orderconfirmation", "order-confirmations"),
    ],
)
@pytest.mark.parametrize("legacy_metadata", [False, True], ids=["absent-files", "legacy-files"])
async def test_sales_original_always_uses_direct_file_subresource(
    document_client, db_session, monkeypatch, kind, endpoint, legacy_metadata
):
    legacy_file_id = str(uuid4())
    row = snapshot(kind=kind, file_id=legacy_file_id)
    if not legacy_metadata:
        row["detail"].pop("files")
    _, documents = await seed(db_session, [row])
    sources = file_sources(documents[0].payload)
    file_id = next(iter(sources))
    assert file_id != legacy_file_id
    assert sources[file_id] == f"/v1/{endpoint}/{row['summary']['id']}/file"
    paths = []

    def respond(request):
        paths.append(request.url.path)
        assert request.headers["Accept"] == "*/*"
        return httpx.Response(200, content=b"%PDF-1.7\noriginal", headers={"Content-Type": "application/pdf"})

    transport(monkeypatch, respond)
    response = await document_client.get(f"{BASE}/documents/{documents[0].id}/files/{file_id}")
    assert response.status_code == 200, response.text
    assert paths == [sources[file_id]]


async def test_xrechnung_direct_xml_is_cached_instead_of_legacy_pdf_preview(document_client, db_session, monkeypatch):
    legacy_file_id = str(uuid4())
    row = snapshot(file_id=legacy_file_id)
    row["detail"]["electronicDocumentProfile"] = "XRECHNUNG"
    _, documents = await seed(db_session, [row])
    source = file_sources(documents[0].payload)
    file_id = next(iter(source))
    direct_path = f"/v1/invoices/{row['summary']['id']}/file"
    xml = b'<?xml version="1.0" encoding="UTF-8"?><Invoice><ID>LEX-42</ID></Invoice>'
    paths = []

    def respond(request):
        paths.append(request.url.path)
        assert request.headers["Accept"] == "*/*"
        if request.url.path == f"/v1/files/{legacy_file_id}":
            return httpx.Response(
                200, content=b"%PDF-1.7\nXRechnung preview only", headers={"Content-Type": "application/pdf"}
            )
        assert request.url.path == direct_path
        return httpx.Response(200, content=xml, headers={"Content-Type": "application/xml"})

    transport(monkeypatch, respond)
    url = f"{BASE}/documents/{documents[0].id}/files/{file_id}"
    response = await document_client.get(url)
    assert response.status_code == 200, response.text
    assert response.content == xml
    assert response.headers["content-type"] == "application/xml"
    assert response.headers["content-disposition"].endswith('.xml"')
    original = await db_session.scalar(select(LexwareOriginal).options(undefer(LexwareOriginal.content)))
    assert original.content == xml
    assert original.media_type == "application/xml"
    assert original.source_path == direct_path
    assert original.sha256 == sha256(xml).hexdigest()
    assert (await document_client.get(url)).content == xml
    assert paths == [direct_path]
    assert (await document_client.get(f"{BASE}/documents/{documents[0].id}/files/{legacy_file_id}")).status_code == 404


async def test_sales_revision_retains_previous_original_evidence(document_client, db_session, monkeypatch):
    row = snapshot()
    row["detail"]["version"] = 1
    connection, documents = await seed(db_session, [row])
    file_id = next(iter(file_sources(documents[0].payload)))
    transport(
        monkeypatch,
        lambda request: httpx.Response(
            200, content=b"%PDF-1.7\nversion 1", headers={"Content-Type": "application/pdf"}
        ),
    )
    assert (await document_client.get(f"{BASE}/documents/{documents[0].id}/files/{file_id}")).status_code == 200
    row["detail"]["version"] = 2
    await replace_vouchers(db_session, connection.id, [row])
    await db_session.commit()
    detail = (await document_client.get(f"{BASE}/documents/{documents[0].id}")).json()
    assert len(detail["files"]) == 2
    assert any(file["file_id"] == file_id and file["cached"] for file in detail["files"])


async def test_corrupt_cache_is_not_served_or_replaced(document_client, db_session, monkeypatch):
    file_id = str(uuid4())
    _, documents = await seed(db_session, [booking_snapshot(file_id)])
    db_session.add(
        LexwareOriginal(
            document_id=documents[0].id,
            file_id=file_id,
            source_path=f"/v1/files/{file_id}",
            filename="original.pdf",
            media_type="application/pdf",
            content=b"corrupted",
            size_bytes=9,
            sha256=sha256(b"expected").hexdigest(),
        )
    )
    await db_session.commit()

    def fail(request):
        pytest.fail("Corrupt stored evidence must not be silently replaced from upstream")

    transport(monkeypatch, fail)
    response = await document_client.get(f"{BASE}/documents/{documents[0].id}/files/{file_id}")
    assert response.status_code == 409


async def test_cached_original_is_immutable(db_session):
    _, documents = await seed(db_session, [snapshot()])
    original = LexwareOriginal(
        document_id=documents[0].id,
        file_id=str(uuid4()),
        source_path="/v1/files/original",
        filename="original.pdf",
        media_type="application/pdf",
        content=b"%PDF-",
        size_bytes=5,
        sha256=sha256(b"%PDF-").hexdigest(),
    )
    db_session.add(original)
    await db_session.commit()
    original.filename = "rewritten.pdf"
    with pytest.raises(ValueError, match="immutable"):
        await db_session.flush()
    await db_session.rollback()
