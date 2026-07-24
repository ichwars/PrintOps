"""Security and persistence contracts for document-layout assets."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pikepdf
import pytest
from fontTools import subset
from fontTools.ttLib import TTFont
from PIL import Image

from backend.app.core.paths import resolve_data_dir, safe_join
from backend.app.models.business_profile import BusinessProfile
from backend.app.schemas.document_layout import (
    AssetLinkRequest,
    AssetUploadRequest,
    CreateLayoutRequest,
    LayoutScope,
)
from backend.app.services.document_layout_assets import (
    AssetAccessError,
    AssetError,
    AssetValidationError,
    delete_unreferenced_asset,
    link_asset,
    preflight_asset,
    read_asset,
    store_asset,
)
from backend.app.services.document_layouts import create_draft

FIXTURES = Path(__file__).parents[2] / "fixtures" / "document_layouts"


def _bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _png(color: str = "#336655") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 16), color).save(output, format="PNG", pnginfo=None)
    return output.getvalue()


def _upload(profile_id: int, asset_type: str, content: bytes, name: str, **kwargs):
    return AssetUploadRequest(
        business_profile_id=profile_id,
        asset_type=asset_type,
        original_name=name,
        declared_mime_type="application/octet-stream",
        declared_sha256=hashlib.sha256(content).hexdigest(),
        **kwargs,
    )


async def _profile(session, name: str) -> BusinessProfile:
    profile = BusinessProfile(
        name=name,
        legal_name=name,
        country_code="DE",
        default_currency="EUR",
    )
    session.add(profile)
    await session.flush()
    return profile


def test_safe_join_rejects_traversal(tmp_path):
    assert safe_join(tmp_path, "assets/file") == (tmp_path / "assets" / "file").resolve()
    with pytest.raises(ValueError, match="escapes"):
        safe_join(tmp_path, "../outside")
    with pytest.raises(ValueError, match="escapes"):
        safe_join(tmp_path, Path("C:/Windows/win.ini"))


def test_magic_bytes_win_over_name_and_declared_mime():
    result = preflight_asset("logo", _png())
    assert result.mime_type == "image/png"
    assert result.content.startswith(b"\x89PNG")
    with pytest.raises(AssetValidationError) as error:
        preflight_asset("logo", b"not-an-image")
    assert error.value.finding == "logo_type"


def test_logo_size_and_unsafe_svg_are_rejected():
    with pytest.raises(AssetValidationError) as error:
        preflight_asset("logo", b"x" * (5 * 1024 * 1024 + 1))
    assert error.value.finding == "size_limit"
    malicious = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    with pytest.raises(AssetValidationError) as error:
        preflight_asset("logo", malicious)
    assert error.value.finding == "svg_element"


def test_pdf_preflight_accepts_matching_single_page_and_rejects_letter_mismatch():
    result = preflight_asset("letterhead_first", _bytes("letterhead-a4.pdf"), page_format="A4")
    assert result.report == {
        "page_count": 1,
        "width_mm": "210.00",
        "height_mm": "297.00",
        "active_content": False,
    }
    with pytest.raises(AssetValidationError) as error:
        preflight_asset("letterhead_first", _bytes("letterhead-letter.pdf"), page_format="A4")
    assert error.value.finding == "pdf_page_format"


def test_pdf_preflight_rejects_active_encrypted_and_multipage_content():
    with pytest.raises(AssetValidationError) as error:
        preflight_asset("letterhead_first", _bytes("active-content.pdf"))
    assert error.value.finding == "pdf_active_content"

    encrypted = io.BytesIO()
    with pikepdf.open(io.BytesIO(_bytes("letterhead-a4.pdf"))) as pdf:
        pdf.save(encrypted, encryption=pikepdf.Encryption(owner="owner", user="user", R=4))
    with pytest.raises(AssetValidationError) as error:
        preflight_asset("letterhead_first", encrypted.getvalue())
    assert error.value.finding in {"pdf_encrypted", "pdf_parse"}

    multiple = io.BytesIO()
    with pikepdf.new() as pdf:
        pdf.add_blank_page(page_size=(595.2756, 841.8898))
        pdf.add_blank_page(page_size=(595.2756, 841.8898))
        pdf.save(multiple)
    with pytest.raises(AssetValidationError) as error:
        preflight_asset("letterhead_first", multiple.getvalue())
    assert error.value.finding == "pdf_pages"


def test_font_preflight_requires_rights_and_invoice_glyphs():
    font = _bytes("test-font.ttf")
    with pytest.raises(AssetValidationError) as error:
        preflight_asset("font", font)
    assert error.value.finding == "font_embedding"
    result = preflight_asset("font", font, font_embedding_rights_confirmed=True)
    assert result.report["font_family"] == "Bitstream Vera Sans"
    assert result.report["embedding_allowed"] is True

    source = TTFont(io.BytesIO(font))
    options = subset.Options()
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text="ABC123")
    subsetter.subset(source)
    incomplete = io.BytesIO()
    source.save(incomplete)
    source.close()
    with pytest.raises(AssetValidationError) as error:
        preflight_asset(
            "font", incomplete.getvalue(), font_embedding_rights_confirmed=True
        )
    assert error.value.finding == "font_glyphs"


@pytest.mark.asyncio
async def test_store_is_content_addressed_deduplicated_and_integrity_checked(db_session):
    profile = await _profile(db_session, "Asset Profile")
    content = _png()
    first = await store_asset(
        db_session,
        _upload(profile.id, "logo", content, "../../unsafe.jpg"),
        content,
        actor_id=None,
    )
    second = await store_asset(
        db_session,
        _upload(profile.id, "logo", content, "renamed.png"),
        content,
        actor_id=None,
    )
    assert second.id == first.id
    assert first.original_name == "unsafe.jpg"
    assert first.storage_key == (
        f"document-layout-assets/{profile.id}/logo/{first.sha256[:2]}/{first.sha256}"
    )
    stored = safe_join(resolve_data_dir(), first.storage_key)
    assert stored.read_bytes() == read_asset(first)
    stored.write_bytes(b"tampered")
    with pytest.raises(AssetError, match="integrity"):
        read_asset(first)


@pytest.mark.asyncio
async def test_declared_hash_and_cross_profile_link_are_rejected(db_session):
    first_profile = await _profile(db_session, "First Asset Profile")
    second_profile = await _profile(db_session, "Second Asset Profile")
    content = _png()
    invalid_request = _upload(first_profile.id, "logo", content, "logo.png")
    invalid_request = invalid_request.model_copy(update={"declared_sha256": "0" * 64})
    with pytest.raises(AssetValidationError) as error:
        await store_asset(db_session, invalid_request, content, actor_id=None)
    assert error.value.finding == "sha256"

    asset = await store_asset(
        db_session,
        _upload(first_profile.id, "logo", content, "logo.png"),
        content,
        actor_id=None,
    )
    layout = await create_draft(
        db_session,
        CreateLayoutRequest(
            scope=LayoutScope(business_profile_id=second_profile.id),
            reason="Cross profile test",
        ),
        actor_id=None,
    )
    with pytest.raises(AssetAccessError, match="another business profile"):
        await link_asset(
            db_session, layout.id, AssetLinkRequest(asset_id=asset.id, role="logo")
        )


@pytest.mark.asyncio
async def test_referenced_asset_cannot_be_deleted(db_session):
    profile = await _profile(db_session, "Reference Profile")
    content = _png()
    asset = await store_asset(
        db_session,
        _upload(profile.id, "logo", content, "logo.png"),
        content,
        actor_id=None,
    )
    layout = await create_draft(
        db_session,
        CreateLayoutRequest(
            scope=LayoutScope(business_profile_id=profile.id), reason="Asset link test"
        ),
        actor_id=None,
    )
    await link_asset(db_session, layout.id, AssetLinkRequest(asset_id=asset.id, role="logo"))
    with pytest.raises(AssetValidationError) as error:
        await link_asset(
            db_session,
            layout.id,
            AssetLinkRequest(asset_id=asset.id, role="font_regular"),
        )
    assert error.value.finding == "asset_role"
    with pytest.raises(AssetAccessError, match="referenced"):
        await delete_unreferenced_asset(db_session, asset.id)

    unreferenced_content = _png("#884422")
    unreferenced = await store_asset(
        db_session,
        _upload(profile.id, "logo", unreferenced_content, "unused.png"),
        unreferenced_content,
        actor_id=None,
    )
    unreferenced_path = safe_join(resolve_data_dir(), unreferenced.storage_key)
    await delete_unreferenced_asset(db_session, unreferenced.id)
    assert not unreferenced_path.exists()
