"""Deterministic PDF/A-3u preparation and conservative structural checks."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from typing import Literal

import pikepdf
from lxml import etree

from backend.app.services.einvoice.zugferd import (
    FACTUR_X_FILENAME,
    FACTUR_X_XMP_NAMESPACE,
    factur_x_metadata,
)

_ICC_PACKAGE = "backend.app.resources.pdf"
_ICC_FILENAME = "sRGB.icc"
_PRODUCER = "PrintOps document renderer / WeasyPrint 69.0 / pikepdf 10.10.0"
_BOX_TOLERANCE_PT = 0.1
_RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_PDFA_EXTENSION_NS = "http://www.aiim.org/pdfa/ns/extension/"
_PDFA_SCHEMA_NS = "http://www.aiim.org/pdfa/ns/schema#"
_PDFA_PROPERTY_NS = "http://www.aiim.org/pdfa/ns/property#"


class PdfaError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PdfaFinding:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class PdfaStructureReport:
    valid: bool
    findings: tuple[PdfaFinding, ...]
    fonts_checked: int


_STRUCTURE_BACK_REFERENCES = frozenset({"/P", "/Pg", "/ParentTree"})


def _walk_structure(value, visit, seen: set[tuple[int, int]]) -> None:
    if isinstance(value, pikepdf.Object):
        object_id = value.objgen
        if object_id != (0, 0):
            if object_id in seen:
                return
            seen.add(object_id)
    if isinstance(value, (pikepdf.Dictionary, pikepdf.Stream)):
        visit(value)
        for key, child in list(value.items()):
            if str(key) not in _STRUCTURE_BACK_REFERENCES:
                _walk_structure(child, visit, seen)
    elif isinstance(value, pikepdf.Array):
        visit(value)
        for child in list(value):
            _walk_structure(child, visit, seen)


def _normalize_structure_ids(pdf: pikepdf.Pdf) -> None:
    root = pdf.Root.get("/StructTreeRoot")
    if not root:
        return
    found: list[str] = []

    def collect(value) -> None:
        if isinstance(value, (pikepdf.Dictionary, pikepdf.Stream)):
            identifier = value.get("/ID")
            if isinstance(identifier, pikepdf.String):
                text = str(identifier)
                if text not in found:
                    found.append(text)

    _walk_structure(root, collect, set())
    mapping = {old: f"printops-struct-{index:06d}" for index, old in enumerate(found, start=1)}

    def replace(value) -> None:
        if isinstance(value, (pikepdf.Dictionary, pikepdf.Stream)):
            for key, child in list(value.items()):
                if isinstance(child, pikepdf.String) and str(child) in mapping:
                    value[key] = pikepdf.String(mapping[str(child)])
        elif isinstance(value, pikepdf.Array):
            for index, child in enumerate(list(value)):
                if isinstance(child, pikepdf.String) and str(child) in mapping:
                    value[index] = pikepdf.String(mapping[str(child)])

    _walk_structure(root, replace, set())


def canonicalize_source_pdf(content: bytes) -> bytes:
    """Remove engine-specific volatile envelopes while preserving page content."""
    output = io.BytesIO()
    try:
        with pikepdf.open(io.BytesIO(content)) as pdf:
            _normalize_structure_ids(pdf)
            for key in ("/Metadata", "/OutputIntents"):
                if key in pdf.Root:
                    del pdf.Root[key]
            for key in list(pdf.docinfo.keys()):
                del pdf.docinfo[key]
            if "/ID" in pdf.trailer:
                del pdf.trailer["/ID"]
            pdf.save(
                output,
                force_version="1.7",
                static_id=True,
                compress_streams=True,
            )
    except (pikepdf.PdfError, ValueError, KeyError) as exc:
        raise PdfaError("PDFA_PREPARATION_FAILED") from exc
    return output.getvalue()


def canonical_source_sha256(content: bytes) -> str:
    return hashlib.sha256(canonicalize_source_pdf(content)).hexdigest()


def _box(page: pikepdf.Page, name: str) -> tuple[float, float, float, float]:
    value = page.get(name) or page.MediaBox
    return tuple(float(item) for item in value)


def _same_page_geometry(foreground: pikepdf.Page, background: pikepdf.Page) -> bool:
    for name in ("/MediaBox", "/CropBox"):
        left = _box(foreground, name)
        right = _box(background, name)
        if any(abs(a - b) > _BOX_TOLERANCE_PT for a, b in zip(left, right, strict=True)):
            return False
    return int(foreground.get("/Rotate", 0)) % 360 == int(background.get("/Rotate", 0)) % 360


def merge_letterheads(
    foreground: bytes,
    *,
    first: bytes | None = None,
    following: bytes | None = None,
) -> bytes:
    """Place single-page stationery below page content without rasterizing it."""
    if first is None and following is None:
        return foreground
    output = io.BytesIO()
    try:
        with pikepdf.open(io.BytesIO(foreground)) as document:
            first_pdf = pikepdf.open(io.BytesIO(first)) if first is not None else None
            following_pdf = pikepdf.open(io.BytesIO(following)) if following is not None else None
            try:
                for index, page in enumerate(document.pages):
                    background_pdf = first_pdf if index == 0 else following_pdf
                    if background_pdf is None:
                        continue
                    if len(background_pdf.pages) != 1 or not _same_page_geometry(page, background_pdf.pages[0]):
                        raise PdfaError("PDFA_LETTERHEAD_PAGE_MISMATCH")
                    page.add_underlay(background_pdf.pages[0], shrink=False, expand=False)
                document.save(output, deterministic_id=True, compress_streams=True)
            finally:
                if first_pdf is not None:
                    first_pdf.close()
                if following_pdf is not None:
                    following_pdf.close()
    except PdfaError:
        raise
    except (pikepdf.PdfError, ValueError, KeyError) as exc:
        raise PdfaError("PDFA_LETTERHEAD_INVALID") from exc
    return output.getvalue()


def _pdf_date(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("D:%Y%m%d%H%M%S+00'00'")


def _apply_metadata(
    pdf: pikepdf.Pdf,
    *,
    language: str,
    timestamp: datetime,
    document_id: str,
) -> None:
    language_tag = "de-DE" if language.lower().startswith("de") else "en-US"
    pdf.Root["/Lang"] = pikepdf.String(language_tag)
    pdf.Root["/MarkInfo"] = pikepdf.Dictionary(Marked=True)
    pdf.Root["/ViewerPreferences"] = pikepdf.Dictionary(DisplayDocTitle=True)

    icc = resources.files(_ICC_PACKAGE).joinpath(_ICC_FILENAME).read_bytes()
    profile = pdf.make_stream(icc)
    profile["/N"] = 3
    intent = pikepdf.Dictionary(
        Type=pikepdf.Name("/OutputIntent"),
        S=pikepdf.Name("/GTS_PDFA1"),
        OutputConditionIdentifier=pikepdf.String("sRGB2014"),
        Info=pikepdf.String("sRGB2014 (color.org)"),
        RegistryName=pikepdf.String("https://www.color.org"),
        DestOutputProfile=profile,
    )
    pdf.Root["/OutputIntents"] = pikepdf.Array([pdf.make_indirect(intent)])

    iso_time = timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as metadata:
        metadata["pdfaid:part"] = "3"
        metadata["pdfaid:conformance"] = "U"
        metadata["xmp:CreateDate"] = iso_time
        metadata["xmp:ModifyDate"] = iso_time
        metadata["pdf:Producer"] = _PRODUCER
        metadata["xmpMM:DocumentID"] = f"urn:sha256:{document_id}"
        metadata["xmpMM:InstanceID"] = f"urn:sha256:{document_id}"
    pdf.docinfo["/CreationDate"] = _pdf_date(timestamp)
    pdf.docinfo["/ModDate"] = _pdf_date(timestamp)
    pdf.docinfo["/Producer"] = _PRODUCER


def prepare_pdfa3u(
    content: bytes,
    *,
    language: str,
    timestamp: datetime,
    document_id: str,
    letterhead_first: bytes | None = None,
    letterhead_following: bytes | None = None,
) -> bytes:
    """Merge stationery and apply a deterministic PDF/A-3u metadata envelope."""
    if timestamp.tzinfo is None or len(document_id) != 64:
        raise PdfaError("PDFA_INPUT_INVALID")
    merged = merge_letterheads(
        canonicalize_source_pdf(content),
        first=letterhead_first,
        following=letterhead_following,
    )
    output = io.BytesIO()
    try:
        with pikepdf.open(io.BytesIO(merged)) as pdf:
            _apply_metadata(
                pdf,
                language=language,
                timestamp=timestamp,
                document_id=document_id,
            )
            pdf.save(
                output,
                min_version="1.7",
                force_version="1.7",
                preserve_pdfa=True,
                deterministic_id=True,
                compress_streams=True,
            )
    except PdfaError:
        raise
    except (pikepdf.PdfError, ValueError, KeyError) as exc:
        raise PdfaError("PDFA_PREPARATION_FAILED") from exc
    return output.getvalue()


def _factur_x_property(
    sequence: etree._Element,
    name: str,
    description: str,
) -> None:
    item = etree.SubElement(
        sequence,
        etree.QName(_RDF_NS, "li"),
        {etree.QName(_RDF_NS, "parseType"): "Resource"},
    )
    etree.SubElement(item, etree.QName(_PDFA_PROPERTY_NS, "name")).text = name
    etree.SubElement(item, etree.QName(_PDFA_PROPERTY_NS, "valueType")).text = "Text"
    etree.SubElement(item, etree.QName(_PDFA_PROPERTY_NS, "category")).text = "external"
    etree.SubElement(item, etree.QName(_PDFA_PROPERTY_NS, "description")).text = description


def _apply_factur_x_metadata(
    pdf: pikepdf.Pdf,
    *,
    profile: Literal["en16931", "xrechnung"],
) -> None:
    try:
        root = etree.fromstring(bytes(pdf.Root.Metadata))
        rdf = root.find(f".//{{{_RDF_NS}}}RDF")
        if rdf is None:
            raise ValueError("XMP RDF container is missing")

        values = etree.SubElement(
            rdf,
            etree.QName(_RDF_NS, "Description"),
            nsmap={"fx": FACTUR_X_XMP_NAMESPACE},
        )
        values.set(etree.QName(_RDF_NS, "about"), "")
        metadata = factur_x_metadata(profile)
        for name, value in metadata.items():
            etree.SubElement(values, etree.QName(FACTUR_X_XMP_NAMESPACE, name)).text = value

        extension = etree.SubElement(
            rdf,
            etree.QName(_RDF_NS, "Description"),
            nsmap={
                "pdfaExtension": _PDFA_EXTENSION_NS,
                "pdfaSchema": _PDFA_SCHEMA_NS,
                "pdfaProperty": _PDFA_PROPERTY_NS,
            },
        )
        extension.set(etree.QName(_RDF_NS, "about"), "")
        schemas = etree.SubElement(extension, etree.QName(_PDFA_EXTENSION_NS, "schemas"))
        bag = etree.SubElement(schemas, etree.QName(_RDF_NS, "Bag"))
        schema = etree.SubElement(
            bag,
            etree.QName(_RDF_NS, "li"),
            {etree.QName(_RDF_NS, "parseType"): "Resource"},
        )
        etree.SubElement(schema, etree.QName(_PDFA_SCHEMA_NS, "schema")).text = "Factur-X PDFA Extension Schema"
        etree.SubElement(schema, etree.QName(_PDFA_SCHEMA_NS, "namespaceURI")).text = FACTUR_X_XMP_NAMESPACE
        etree.SubElement(schema, etree.QName(_PDFA_SCHEMA_NS, "prefix")).text = "fx"
        properties = etree.SubElement(schema, etree.QName(_PDFA_SCHEMA_NS, "property"))
        sequence = etree.SubElement(properties, etree.QName(_RDF_NS, "Seq"))
        _factur_x_property(sequence, "DocumentFileName", "name of the embedded XML invoice file")
        _factur_x_property(sequence, "DocumentType", "INVOICE")
        _factur_x_property(
            sequence,
            "Version",
            "The actual version of the Factur-X XML schema",
        )
        _factur_x_property(
            sequence,
            "ConformanceLevel",
            "The conformance level of the embedded Factur-X data",
        )
        packet = (
            b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
            + etree.tostring(root, encoding="UTF-8", xml_declaration=False)
            + b'\n<?xpacket end="w"?>'
        )
        pdf.Root.Metadata.write(packet)
    except (AttributeError, KeyError, TypeError, ValueError, etree.XMLSyntaxError) as exc:
        raise PdfaError("ZUGFERD_XMP_FAILED") from exc


def attach_zugferd_xml(
    content: bytes,
    xml: bytes,
    *,
    xml_sha256: str,
    profile: Literal["en16931", "xrechnung"],
    timestamp: datetime,
) -> bytes:
    """Embed the byte-identical validated CII artifact in a PDF/A-3u envelope."""
    if timestamp.tzinfo is None or hashlib.sha256(xml).hexdigest() != xml_sha256:
        raise PdfaError("ZUGFERD_XML_HASH_MISMATCH")
    output = io.BytesIO()
    try:
        with pikepdf.open(io.BytesIO(content)) as pdf:
            if FACTUR_X_FILENAME in pdf.attachments:
                raise PdfaError("ZUGFERD_ATTACHMENT_EXISTS")
            pdf.attachments[FACTUR_X_FILENAME] = xml
            specification = pdf.attachments[FACTUR_X_FILENAME]
            specification.relationship = pikepdf.Name.Alternative
            embedded = specification.get_file()
            embedded.mime_type = "text/xml"
            embedded.creation_date = timestamp.astimezone(timezone.utc)
            embedded.mod_date = timestamp.astimezone(timezone.utc)
            pdf.Root["/AF"] = pikepdf.Array([specification.obj])
            _apply_factur_x_metadata(pdf, profile=profile)
            if hashlib.sha256(embedded.read_bytes()).hexdigest() != xml_sha256:
                raise PdfaError("ZUGFERD_XML_HASH_MISMATCH")
            pdf.save(
                output,
                min_version="1.7",
                force_version="1.7",
                preserve_pdfa=True,
                deterministic_id=True,
                compress_streams=True,
            )
    except PdfaError:
        raise
    except (pikepdf.PdfError, ValueError, KeyError) as exc:
        raise PdfaError("ZUGFERD_ATTACHMENT_FAILED") from exc
    result = output.getvalue()
    try:
        with pikepdf.open(io.BytesIO(result)) as pdf:
            if hashlib.sha256(pdf.attachments[FACTUR_X_FILENAME].get_file().read_bytes()).hexdigest() != xml_sha256:
                raise PdfaError("ZUGFERD_XML_HASH_MISMATCH")
    except PdfaError:
        raise
    except (pikepdf.PdfError, KeyError) as exc:
        raise PdfaError("ZUGFERD_ATTACHMENT_FAILED") from exc
    return result


def _font_objects(pdf: pikepdf.Pdf):
    seen: set[tuple[int, int]] = set()
    for page in pdf.pages:
        resources_dict = page.get("/Resources")
        if not resources_dict:
            continue
        fonts = resources_dict.get("/Font")
        if not fonts:
            continue
        for font in fonts.values():
            object_id = font.objgen
            if object_id in seen:
                continue
            seen.add(object_id)
            yield font


def _font_descriptor(font):
    descendants = font.get("/DescendantFonts")
    target = descendants[0] if descendants else font
    return target.get("/FontDescriptor")


def inspect_pdfa3u(content: bytes) -> PdfaStructureReport:
    """Find obvious PDF/A-3u defects before the independent veraPDF check."""
    findings: list[PdfaFinding] = []
    fonts_checked = 0
    try:
        with pikepdf.open(io.BytesIO(content)) as pdf:
            try:
                metadata = pdf.open_metadata()
                if metadata.get("pdfaid:part") != "3" or metadata.get("pdfaid:conformance") != "U":
                    findings.append(PdfaFinding("PDFA_XMP_MISSING", "PDF/A-3u identification is missing"))
            except (KeyError, ValueError, pikepdf.PdfError):
                findings.append(PdfaFinding("PDFA_XMP_MISSING", "PDF/A-3u identification is missing"))
            intents = pdf.Root.get("/OutputIntents")
            if not intents or not intents[0].get("/DestOutputProfile"):
                findings.append(PdfaFinding("PDFA_OUTPUT_INTENT_MISSING", "sRGB output intent is missing"))
            if not pdf.Root.get("/Lang"):
                findings.append(PdfaFinding("PDFA_LANGUAGE_MISSING", "document language is missing"))
            mark_info = pdf.Root.get("/MarkInfo")
            if not mark_info or not bool(mark_info.get("/Marked", False)):
                findings.append(PdfaFinding("PDFA_TAGGING_MISSING", "marked-content flag is missing"))
            for font in _font_objects(pdf):
                fonts_checked += 1
                name = str(font.get("/BaseFont", "unknown"))
                if not font.get("/ToUnicode"):
                    findings.append(PdfaFinding("PDFA_FONT_TOUNICODE_MISSING", f"{name} lacks ToUnicode"))
                descriptor = _font_descriptor(font)
                embedded = descriptor and any(descriptor.get(key) for key in ("/FontFile", "/FontFile2", "/FontFile3"))
                if not embedded:
                    findings.append(PdfaFinding("PDFA_FONT_NOT_EMBEDDED", f"{name} is not embedded"))
    except pikepdf.PdfError:
        findings.append(PdfaFinding("PDFA_PARSE_FAILED", "PDF cannot be parsed"))
    return PdfaStructureReport(
        valid=not findings,
        findings=tuple(findings),
        fonts_checked=fonts_checked,
    )
