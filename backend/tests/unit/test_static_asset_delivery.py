import gzip

import httpx
import pytest
from starlette.applications import Starlette

from backend.app.core.static_assets import AssetStaticFiles

BUNDLE = "/assets/index-Aa1Bb2Cc.js"
CONTENT = b"const value = 'example';\n" * 200


@pytest.fixture
async def asset_client(tmp_path):
    (tmp_path / "index-Aa1Bb2Cc.js").write_bytes(CONTENT)
    (tmp_path / "pdfjs").mkdir()
    (tmp_path / "pdfjs" / "worker.mjs").write_bytes(CONTENT)
    (tmp_path / "tiny-Jj1Kk2Ll.js").write_bytes(b"console.log(1);")
    app = Starlette()
    app.mount("/assets", AssetStaticFiles(directory=tmp_path))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_gzip_has_separate_validators_and_preserves_range_and_head(asset_client):
    identity = await asset_client.get(BUNDLE, headers={"Accept-Encoding": "gzip;q=0, *"})
    async with asset_client.stream("GET", BUNDLE, headers={"Accept-Encoding": "gzip"}) as zipped:
        raw = b"".join([chunk async for chunk in zipped.aiter_raw()])
    assert identity.content == CONTENT
    assert "content-encoding" not in identity.headers
    assert gzip.decompress(raw) == CONTENT
    assert len(raw) == int(zipped.headers["content-length"])
    assert zipped.headers["content-encoding"] == "gzip"
    assert identity.headers["etag"] != zipped.headers["etag"]
    for response in (identity, zipped):
        assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert response.headers["vary"] == "Accept-Encoding"

    same = await asset_client.get(BUNDLE, headers={"Accept-Encoding": "gzip", "If-None-Match": zipped.headers["etag"]})
    different = await asset_client.get(
        BUNDLE, headers={"Accept-Encoding": "gzip", "If-None-Match": identity.headers["etag"]}
    )
    assert same.status_code == 304
    assert same.headers["vary"] == "Accept-Encoding"
    assert same.content == b""
    assert different.status_code == 200

    head = await asset_client.head(BUNDLE, headers={"Accept-Encoding": "gzip"})
    assert head.headers["etag"] == zipped.headers["etag"]
    assert head.headers["content-length"] == str(len(raw))
    assert head.content == b""

    partial = await asset_client.get(BUNDLE, headers={"Accept-Encoding": "gzip", "Range": "bytes=0-9"})
    assert partial.status_code == 206
    assert partial.content == CONTENT[:10]
    assert "content-encoding" not in partial.headers


async def test_unversioned_and_tiny_assets_and_missing_chunks(asset_client):
    pdfjs = await asset_client.get("/assets/pdfjs/worker.mjs")
    assert pdfjs.headers["cache-control"] == "no-cache"
    assert pdfjs.headers["content-encoding"] == "gzip"

    small = await asset_client.get("/assets/tiny-Jj1Kk2Ll.js")
    assert "immutable" in small.headers["cache-control"]
    assert "content-encoding" not in small.headers
    assert "vary" not in small.headers

    missing = await asset_client.get("/assets/old-Mm1Nn2Oo.js")
    assert missing.status_code == 404
    assert "content-encoding" not in missing.headers
    assert "cache-control" not in missing.headers
