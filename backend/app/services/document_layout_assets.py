"""Private, content-addressed storage and strict preflight for layout assets."""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pikepdf
from defusedxml import ElementTree
from fontTools.ttLib import TTFont
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.paths import resolve_data_dir, safe_join
from backend.app.models.document_layout import (
    DocumentLayoutAsset,
    DocumentLayoutAssetLink,
    DocumentLayoutConfiguration,
)
from backend.app.schemas.document_layout import AssetLinkRequest, AssetUploadRequest

AssetType = Literal["logo", "letterhead_first", "letterhead_following", "font"]
PAGE_MM = {"A4": (Decimal("210"), Decimal("297")), "Letter": (Decimal("215.9"), Decimal("279.4"))}
UPLOAD_LIMITS = {
    "logo": 5 * 1024 * 1024,
    "letterhead_first": 20 * 1024 * 1024,
    "letterhead_following": 20 * 1024 * 1024,
    "font": 10 * 1024 * 1024,
}
_DANGEROUS_PDF_NAMES = frozenset(
    {
        "/AA",
        "/AcroForm",
        "/EmbeddedFiles",
        "/Filespec",
        "/JavaScript",
        "/JS",
        "/Launch",
        "/OpenAction",
        "/RichMedia",
        "/URI",
        "/XFA",
    }
)
_SVG_ELEMENTS = frozenset(
    {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
)
_SVG_ATTRIBUTES = frozenset(
    {
        "viewBox",
        "width",
        "height",
        "x",
        "y",
        "x1",
        "y1",
        "x2",
        "y2",
        "cx",
        "cy",
        "r",
        "rx",
        "ry",
        "points",
        "d",
        "fill",
        "fill-opacity",
        "stroke",
        "stroke-width",
        "stroke-opacity",
        "opacity",
        "transform",
    }
)
_REQUIRED_GLYPHS = frozenset(
    ord(char)
    for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    " .,;:!?+-/%()[]{}@#&€ÄÖÜäöüß"
)
_DLL_DIRECTORY_HANDLES: list[object] = []


class AssetError(RuntimeError):
    code = "LAYOUT_ASSET_ERROR"


class AssetValidationError(AssetError):
    code = "LAYOUT_ASSET_INVALID"

    def __init__(self, message: str, *, finding: str) -> None:
        self.finding = finding
        super().__init__(message)


class AssetAccessError(AssetError):
    code = "LAYOUT_ASSET_ACCESS_DENIED"


@dataclass(frozen=True)
class AssetPreflight:
    content: bytes
    mime_type: str
    report: dict


def _detect_magic(content: bytes) -> str:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"\x00\x01\x00\x00", b"OTTO")):
        return "font/ttf" if content.startswith(b"\x00\x01\x00\x00") else "font/otf"
    if content.startswith(b"ttcf"):
        return "font/collection"
    probe = content[:1024].lstrip(b"\xef\xbb\xbf\x00\t\r\n ").lower()
    if probe.startswith(b"<?xml") or probe.startswith(b"<svg"):
        return "image/svg+xml"
    return "application/octet-stream"


def _normalize_raster(content: bytes) -> AssetPreflight:
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            if image.width <= 0 or image.height <= 0:
                raise AssetValidationError("logo has invalid dimensions", finding="logo_dimensions")
            if image.width > 10_000 or image.height > 10_000 or image.width * image.height > 25_000_000:
                raise AssetValidationError("logo exceeds pixel limits", finding="logo_pixel_limit")
            normalized = image.convert("RGBA")
            output = io.BytesIO()
            normalized.save(output, format="PNG", optimize=True)
            return AssetPreflight(
                content=output.getvalue(),
                mime_type="image/png",
                report={"width_px": image.width, "height_px": image.height, "metadata_removed": True},
            )
    except (UnidentifiedImageError, OSError) as exc:
        raise AssetValidationError("logo cannot be decoded", finding="logo_decode") from exc


def _normalize_svg(content: bytes) -> AssetPreflight:
    try:
        root = ElementTree.fromstring(content)
    except Exception as exc:
        raise AssetValidationError("SVG is malformed or unsafe", finding="svg_parse") from exc
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag not in _SVG_ELEMENTS:
            raise AssetValidationError(f"SVG element {tag!r} is not allowed", finding="svg_element")
        for raw_name, value in element.attrib.items():
            name = raw_name.rsplit("}", 1)[-1]
            lowered = value.lower()
            if name not in _SVG_ATTRIBUTES or "url(" in lowered or "javascript:" in lowered:
                raise AssetValidationError("SVG attribute is not allowed", finding="svg_attribute")
    try:
        if os.name == "nt" and hasattr(os, "add_dll_directory"):
            cli = os.environ.get("WEASYPRINT_CLI")
            if cli:
                runtime_dir = Path(cli).resolve().parent
                for candidate in (runtime_dir, runtime_dir / "_internal"):
                    if candidate.is_dir():
                        _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(candidate))
        import cairosvg

        png = cairosvg.svg2png(bytestring=ElementTree.tostring(root), output_width=2048)
    except (Exception, OSError) as exc:
        raise AssetValidationError("SVG cannot be rasterized", finding="svg_rasterize") from exc
    return _normalize_raster(png)


def _walk_pdf(value, seen: set[tuple[int, int]]) -> None:
    if isinstance(value, pikepdf.Object):
        try:
            object_id = value.objgen
            if object_id != (0, 0):
                if object_id in seen:
                    return
                seen.add(object_id)
        except Exception:
            pass
    if isinstance(value, (pikepdf.Dictionary, pikepdf.Stream)):
        for key, child in value.items():
            if str(key) in _DANGEROUS_PDF_NAMES:
                raise AssetValidationError(
                    f"PDF contains active content {key}", finding="pdf_active_content"
                )
            _walk_pdf(child, seen)
    elif isinstance(value, pikepdf.Array):
        for child in value:
            _walk_pdf(child, seen)


def _preflight_pdf(content: bytes, page_format: str) -> AssetPreflight:
    try:
        with pikepdf.open(io.BytesIO(content)) as pdf:
            if pdf.is_encrypted:
                raise AssetValidationError("encrypted PDFs are not allowed", finding="pdf_encrypted")
            if len(pdf.pages) != 1:
                raise AssetValidationError("letterhead PDF must have exactly one page", finding="pdf_pages")
            _walk_pdf(pdf.Root, set())
            media_box = [Decimal(str(value)) for value in pdf.pages[0].MediaBox]
            width_mm = (media_box[2] - media_box[0]) * Decimal("25.4") / Decimal("72")
            height_mm = (media_box[3] - media_box[1]) * Decimal("25.4") / Decimal("72")
            expected_width, expected_height = PAGE_MM[page_format]
            if abs(width_mm - expected_width) > 1 or abs(height_mm - expected_height) > 1:
                raise AssetValidationError(
                    f"letterhead is {width_mm:.1f} x {height_mm:.1f} mm, expected {page_format}",
                    finding="pdf_page_format",
                )
            output = io.BytesIO()
            pdf.save(output, deterministic_id=True, compress_streams=True)
    except AssetValidationError:
        raise
    except pikepdf.PasswordError as exc:
        raise AssetValidationError("encrypted PDFs are not allowed", finding="pdf_encrypted") from exc
    except (pikepdf.PdfError, ValueError, KeyError) as exc:
        raise AssetValidationError("PDF is damaged or unsupported", finding="pdf_parse") from exc
    return AssetPreflight(
        content=output.getvalue(),
        mime_type="application/pdf",
        report={
            "page_count": 1,
            "width_mm": str(width_mm.quantize(Decimal("0.01"))),
            "height_mm": str(height_mm.quantize(Decimal("0.01"))),
            "active_content": False,
        },
    )


def _name_record(font: TTFont, name_id: int) -> str | None:
    name_table = font["name"]
    values = name_table.getName(name_id, 3, 1) or name_table.getName(name_id, 1, 0)
    return values.toUnicode() if values else None


def _preflight_font(content: bytes, *, embedding_rights_confirmed: bool) -> AssetPreflight:
    if content.startswith(b"ttcf"):
        raise AssetValidationError("font collections are not allowed", finding="font_collection")
    try:
        font = TTFont(io.BytesIO(content), lazy=False, recalcBBoxes=False, recalcTimestamp=False)
    except Exception as exc:
        raise AssetValidationError("font is damaged or unsupported", finding="font_parse") from exc
    try:
        forbidden_tables = {"fvar", "SVG ", "Silf", "Sill", "Glat", "Gloc"} & set(font.keys())
        if forbidden_tables:
            raise AssetValidationError("variable or executable font tables are not allowed", finding="font_tables")
        fs_type = int(getattr(font.get("OS/2"), "fsType", 0))
        embedding_allowed = not bool(fs_type & 0x0202)
        if not embedding_allowed or not embedding_rights_confirmed:
            raise AssetValidationError(
                "font embedding rights are missing or restricted", finding="font_embedding"
            )
        cmap = font.getBestCmap() or {}
        missing = sorted(_REQUIRED_GLYPHS - set(cmap))
        if missing:
            raise AssetValidationError(
                "font does not cover required invoice glyphs", finding="font_glyphs"
            )
        flavor = "font/otf" if content.startswith(b"OTTO") else "font/ttf"
        return AssetPreflight(
            content=content,
            mime_type=flavor,
            report={
                "font_family": _name_record(font, 1) or "Unknown",
                "font_style": _name_record(font, 2) or "Regular",
                "font_weight": int(getattr(font.get("OS/2"), "usWeightClass", 400)),
                "glyph_count": len(cmap),
                "embedding_allowed": True,
            },
        )
    finally:
        font.close()


def preflight_asset(
    asset_type: AssetType,
    content: bytes,
    *,
    page_format: str = "A4",
    font_embedding_rights_confirmed: bool = False,
) -> AssetPreflight:
    if len(content) == 0:
        raise AssetValidationError("asset is empty", finding="empty")
    if len(content) > UPLOAD_LIMITS[asset_type]:
        raise AssetValidationError("asset exceeds its upload limit", finding="size_limit")
    magic = _detect_magic(content)
    if asset_type == "logo":
        if magic in {"image/png", "image/jpeg"}:
            return _normalize_raster(content)
        if magic == "image/svg+xml":
            return _normalize_svg(content)
        raise AssetValidationError("logo must be PNG, JPEG or safe SVG", finding="logo_type")
    if asset_type.startswith("letterhead"):
        if magic != "application/pdf":
            raise AssetValidationError("letterhead must be a PDF", finding="pdf_type")
        if page_format not in PAGE_MM:
            raise AssetValidationError("unsupported page format", finding="pdf_page_format")
        return _preflight_pdf(content, page_format)
    if magic not in {"font/ttf", "font/otf", "font/collection"}:
        raise AssetValidationError("font must be TTF or OTF", finding="font_type")
    return _preflight_font(
        content, embedding_rights_confirmed=font_embedding_rights_confirmed
    )


def _relative_key(profile_id: int, asset_type: str, digest: str) -> Path:
    return Path("document-layout-assets") / str(profile_id) / asset_type / digest[:2] / digest  # SEC-PATH-OK: profile_id is an integer, asset_type is a closed Literal, and digest is a server-computed lowercase SHA-256


def _atomic_write(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".asset-", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != hashlib.sha256(content).hexdigest():
            raise AssetError("asset hash changed while writing")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


async def store_asset(
    session: AsyncSession,
    request: AssetUploadRequest,
    content: bytes,
    *,
    actor_id: int | None,
    page_format: str = "A4",
) -> DocumentLayoutAsset:
    incoming_digest = hashlib.sha256(content).hexdigest()
    if incoming_digest != request.declared_sha256:
        raise AssetValidationError("declared SHA-256 does not match upload", finding="sha256")
    preflight = preflight_asset(
        request.asset_type,
        content,
        page_format=page_format,
        font_embedding_rights_confirmed=request.font_embedding_rights_confirmed,
    )
    digest = hashlib.sha256(preflight.content).hexdigest()
    existing = await session.scalar(
        select(DocumentLayoutAsset).where(
            DocumentLayoutAsset.business_profile_id == request.business_profile_id,
            DocumentLayoutAsset.sha256 == digest,
        )
    )
    if existing is not None:
        return existing
    relative_key = _relative_key(request.business_profile_id, request.asset_type, digest)
    target = safe_join(resolve_data_dir(), relative_key)
    _atomic_write(target, preflight.content)
    report = dict(preflight.report)
    asset = DocumentLayoutAsset(
        business_profile_id=request.business_profile_id,
        asset_type=request.asset_type,
        original_name=Path(request.original_name).name,
        mime_type=preflight.mime_type,
        size_bytes=len(preflight.content),
        sha256=digest,
        storage_key=relative_key.as_posix(),
        preflight_status="valid",
        preflight_report=report,
        pdf_width_mm=Decimal(report["width_mm"]) if "width_mm" in report else None,
        pdf_height_mm=Decimal(report["height_mm"]) if "height_mm" in report else None,
        pdf_page_count=report.get("page_count"),
        font_family=report.get("font_family"),
        font_style=report.get("font_style"),
        font_weight=report.get("font_weight"),
        font_glyph_count=report.get("glyph_count"),
        font_embedding_allowed=report.get("embedding_allowed"),
        created_by_id=actor_id,
    )
    session.add(asset)
    await session.flush()
    return asset


def read_asset(asset: DocumentLayoutAsset) -> bytes:
    path = safe_join(resolve_data_dir(), asset.storage_key)
    content = path.read_bytes()
    if len(content) != asset.size_bytes or hashlib.sha256(content).hexdigest() != asset.sha256:
        raise AssetError("stored asset failed its integrity check")
    return content


async def link_asset(
    session: AsyncSession,
    layout_id: int,
    request: AssetLinkRequest,
) -> DocumentLayoutAssetLink:
    layout = await session.get(DocumentLayoutConfiguration, layout_id)
    asset = await session.get(DocumentLayoutAsset, request.asset_id)
    if layout is None or asset is None:
        raise LookupError("layout or asset was not found")
    if layout.status != "draft":
        raise AssetAccessError("assets can only be linked to draft layouts")
    if asset.business_profile_id != layout.business_profile_id:
        raise AssetAccessError("asset belongs to another business profile")
    role_matches_type = (
        (request.role == "logo" and asset.asset_type == "logo")
        or (request.role == "letterhead_first" and asset.asset_type == "letterhead_first")
        or (
            request.role == "letterhead_following"
            and asset.asset_type == "letterhead_following"
        )
        or (request.role.startswith("font_") and asset.asset_type == "font")
    )
    if not role_matches_type:
        raise AssetValidationError(
            "asset type does not match its layout role", finding="asset_role"
        )
    if asset.preflight_status != "valid":
        raise AssetValidationError("asset preflight is not valid", finding="preflight_status")
    existing = await session.scalar(
        select(DocumentLayoutAssetLink).where(
            DocumentLayoutAssetLink.configuration_id == layout.id,
            DocumentLayoutAssetLink.role == request.role,
        )
    )
    if existing is not None:
        existing._allow_layout_lifecycle_mutation = True
        existing.asset_id = asset.id
        await session.flush()
        return existing
    link = DocumentLayoutAssetLink(
        configuration_id=layout.id, asset_id=asset.id, role=request.role
    )
    session.add(link)
    await session.flush()
    return link


async def delete_unreferenced_asset(session: AsyncSession, asset_id: int) -> None:
    asset = await session.get(DocumentLayoutAsset, asset_id)
    if asset is None:
        raise LookupError("asset was not found")
    references = await session.scalar(
        select(func.count(DocumentLayoutAssetLink.id)).where(
            DocumentLayoutAssetLink.asset_id == asset.id
        )
    )
    if references:
        raise AssetAccessError("referenced assets cannot be deleted")
    path = safe_join(resolve_data_dir(), asset.storage_key)
    await session.delete(asset)
    await session.flush()
    path.unlink(missing_ok=True)
