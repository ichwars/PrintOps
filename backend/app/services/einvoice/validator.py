"""Offline validation against the pinned official E-invoice rule bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from lxml import etree
from saxonche import PySaxonProcessor

MAX_XML_BYTES = 10 * 1024 * 1024

_RESOURCE_ROOT = Path(__file__).resolve().parents[2] / "resources" / "einvoice"
_SVRL_NS = {"svrl": "http://purl.oclc.org/dsdl/svrl"}


@dataclass(frozen=True, slots=True)
class EInvoiceValidationFinding:
    rule_id: str
    severity: Literal["error", "warning"]
    message: str
    location: str
    field_path: str
    source: str


@dataclass(frozen=True, slots=True)
class EInvoiceValidationReport:
    standard: str
    syntax: str
    profile: str
    rule_versions: Mapping[str, str]
    findings: tuple[EInvoiceValidationFinding, ...]
    processing_error: str | None = None

    @property
    def blockers(self) -> tuple[EInvoiceValidationFinding, ...]:
        return tuple(item for item in self.findings if item.severity == "error")

    @property
    def valid(self) -> bool:
        return self.processing_error is None and not self.blockers

    def to_dict(self) -> dict:
        return {
            "standard": self.standard,
            "syntax": self.syntax,
            "profile": self.profile,
            "valid": self.valid,
            "processing_error": self.processing_error,
            "rule_versions": dict(self.rule_versions),
            "findings": [asdict(item) for item in self.findings],
        }


@dataclass(frozen=True, slots=True)
class _ValidationTarget:
    xsd: str
    stylesheets: tuple[tuple[str, str], ...]
    rule_versions: Mapping[str, str]
    credit_note_xsd: str | None = None


_RULE_VERSIONS = MappingProxyType(
    {
        "en16931": "1.3.16",
        "xrechnung": "3.0.2-2026-01-31",
        "zugferd": "2.5",
        "factur_x": "1.09",
    }
)


def pinned_rule_versions() -> dict[str, str]:
    """Return the immutable validator bundle versions used by this build."""

    return dict(_RULE_VERSIONS)


_TARGETS: Mapping[tuple[str, str, str], _ValidationTarget] = MappingProxyType(
    {
        ("xrechnung", "ubl-2.1", "xrechnung"): _ValidationTarget(
            xsd="xrechnung/3.0.2-2026-01-31/ubl/xsd/maindoc/UBL-Invoice-2.1.xsd",
            credit_note_xsd="xrechnung/3.0.2-2026-01-31/ubl/xsd/maindoc/UBL-CreditNote-2.1.xsd",
            stylesheets=(
                ("en16931", "en16931/1.3.16/ubl/EN16931-UBL-validation.xslt"),
                (
                    "xrechnung",
                    "xrechnung/3.0.2-2026-01-31/rules/XRechnung-UBL-validation.xsl",
                ),
            ),
            rule_versions={
                "en16931": _RULE_VERSIONS["en16931"],
                "xrechnung": _RULE_VERSIONS["xrechnung"],
            },
        ),
        ("xrechnung", "cii-d16b", "xrechnung"): _ValidationTarget(
            xsd="xrechnung/3.0.2-2026-01-31/cii/xsd/CrossIndustryInvoice_100pD16B.xsd",
            stylesheets=(
                ("en16931", "en16931/1.3.16/cii/EN16931-CII-validation.xslt"),
                (
                    "xrechnung",
                    "xrechnung/3.0.2-2026-01-31/rules/XRechnung-CII-validation.xsl",
                ),
            ),
            rule_versions={
                "en16931": _RULE_VERSIONS["en16931"],
                "xrechnung": _RULE_VERSIONS["xrechnung"],
            },
        ),
        ("zugferd", "cii-d22b", "en16931"): _ValidationTarget(
            xsd="zugferd/2.5/cii-d22b/CrossIndustryInvoice_100pD22B.xsd",
            stylesheets=(("factur_x", "zugferd/2.5/en16931/xslt/FACTUR-X_EN16931.xslt"),),
            rule_versions={
                "en16931": _RULE_VERSIONS["en16931"],
                "zugferd": _RULE_VERSIONS["zugferd"],
                "factur_x": _RULE_VERSIONS["factur_x"],
            },
        ),
        ("zugferd", "cii-d22b", "xrechnung"): _ValidationTarget(
            xsd="zugferd/2.5/cii-d22b/CrossIndustryInvoice_100pD22B.xsd",
            stylesheets=(
                ("en16931", "en16931/1.3.16/cii/EN16931-CII-validation.xslt"),
                (
                    "xrechnung",
                    "xrechnung/3.0.2-2026-01-31/rules/XRechnung-CII-validation.xsl",
                ),
            ),
            rule_versions={
                "en16931": _RULE_VERSIONS["en16931"],
                "xrechnung": _RULE_VERSIONS["xrechnung"],
                "zugferd": _RULE_VERSIONS["zugferd"],
                "factur_x": _RULE_VERSIONS["factur_x"],
            },
        ),
    }
)

_SYNTAX_ALIASES = MappingProxyType(
    {
        "ubl": "ubl-2.1",
        "ubl_2_1": "ubl-2.1",
        "cii": "cii-d16b",
        "cii_d16b": "cii-d16b",
        "cii_d22b": "cii-d22b",
    }
)


def _finding(
    rule_id: str,
    message: str,
    *,
    source: str,
    location: str = "",
    severity: Literal["error", "warning"] = "error",
) -> EInvoiceValidationFinding:
    return EInvoiceValidationFinding(
        rule_id=rule_id,
        severity=severity,
        message=" ".join(message.split()),
        location=location,
        field_path=_field_path(rule_id, location),
        source=source,
    )


def _field_path(rule_id: str, location: str) -> str:
    explicit = {
        "BR-DE-15": "buyer.reference",
        "BR-06": "seller.name",
        "BR-07": "buyer.name",
        "BR-09": "seller.address.country_code",
        "BR-11": "buyer.address.country_code",
    }
    if rule_id in explicit:
        return explicit[rule_id]
    hints = (
        ("BuyerReference", "buyer.reference"),
        ("AccountingSupplierParty", "seller"),
        ("SellerTradeParty", "seller"),
        ("AccountingCustomerParty", "buyer"),
        ("BuyerTradeParty", "buyer"),
        ("InvoiceLine", "lines"),
        ("IncludedSupplyChainTradeLineItem", "lines"),
        ("PaymentMeans", "payment"),
        ("ApplicableHeaderTradeSettlement", "payment"),
        ("TaxTotal", "totals.tax"),
        ("LegalMonetaryTotal", "totals"),
    )
    for token, field_path in hints:
        if token in location:
            return field_path
    return "document"


def _parse(xml: bytes) -> tuple[etree._Element | None, EInvoiceValidationFinding | None]:
    if len(xml) > MAX_XML_BYTES:
        return None, _finding(
            "XML-SIZE",
            f"XML input exceeds the {MAX_XML_BYTES}-byte limit",
            source="parser",
        )
    if b"<!doctype" in xml.lower():
        return None, _finding(
            "XML-PARSE",
            "Document type declarations are not permitted",
            source="parser",
        )
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
        recover=False,
    )
    try:
        return etree.fromstring(xml, parser=parser), None
    except (etree.XMLSyntaxError, ValueError) as exc:
        return None, _finding("XML-PARSE", str(exc), source="parser")


def _xsd_findings(root: etree._Element, xsd_path: Path) -> list[EInvoiceValidationFinding]:
    schema_parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    schema = etree.XMLSchema(etree.parse(str(xsd_path), parser=schema_parser))
    if schema.validate(root):
        return []
    return [
        _finding(
            "XSD",
            entry.message,
            source="xsd",
            location=f"line:{entry.line}",
        )
        for entry in schema.error_log
    ]


def _svrl_findings(svrl_xml: str, source: str) -> list[EInvoiceValidationFinding]:
    root, parse_finding = _parse(svrl_xml.encode("utf-8"))
    if parse_finding is not None or root is None:
        return [
            _finding(
                "VALIDATOR-OUTPUT",
                parse_finding.message if parse_finding else "Validator returned no report",
                source=source,
            )
        ]
    findings: list[EInvoiceValidationFinding] = []
    for node in root.xpath("//svrl:failed-assert | //svrl:successful-report", namespaces=_SVRL_NS):
        role = str(node.get("flag") or node.get("role") or "").lower()
        severity: Literal["error", "warning"] = (
            "warning" if role in {"warning", "warn", "information", "info"} else "error"
        )
        message = " ".join(node.xpath("string(svrl:text)", namespaces=_SVRL_NS).split())
        findings.append(
            _finding(
                str(node.get("id") or "SCHEMATRON"),
                message or "E-invoice business rule failed",
                source=source,
                location=str(node.get("location") or ""),
                severity=severity,
            )
        )
    return findings


def _xslt_findings(xml: bytes, stylesheets: tuple[tuple[str, str], ...]) -> list[EInvoiceValidationFinding]:
    findings: list[EInvoiceValidationFinding] = []
    with PySaxonProcessor(license=False) as processor:
        source = processor.parse_xml(xml_text=xml.decode("utf-8"))
        xslt_processor = processor.new_xslt30_processor()
        for source_name, relative_path in stylesheets:
            executable = xslt_processor.compile_stylesheet(stylesheet_file=str(_RESOURCE_ROOT / relative_path))
            result = executable.transform_to_string(xdm_node=source)
            findings.extend(_svrl_findings(result, source_name))
    return findings


def validate_xml(
    xml: bytes,
    standard: str,
    syntax: str,
    profile: str,
) -> EInvoiceValidationReport:
    """Validate XML offline and return stable, serialisable findings."""
    normalized_standard = standard.strip().lower()
    normalized_syntax = _SYNTAX_ALIASES.get(syntax.strip().lower(), syntax.strip().lower())
    normalized_profile = profile.strip().lower()
    target = _TARGETS.get((normalized_standard, normalized_syntax, normalized_profile))
    if target is None:
        raise ValueError(f"Unsupported E-invoice validation target: {standard!r}/{syntax!r}/{profile!r}")

    root, parse_finding = _parse(xml)
    if parse_finding is not None or root is None:
        return EInvoiceValidationReport(
            standard=normalized_standard,
            syntax=normalized_syntax,
            profile=normalized_profile,
            rule_versions=target.rule_versions,
            findings=(parse_finding,) if parse_finding else (),
        )

    try:
        root_name = etree.QName(root).localname
        xsd = target.credit_note_xsd if root_name == "CreditNote" and target.credit_note_xsd else target.xsd
        findings = _xsd_findings(root, _RESOURCE_ROOT / xsd)
        if not findings:
            findings.extend(_xslt_findings(xml, target.stylesheets))
        ordered = tuple(
            sorted(
                findings,
                key=lambda item: (item.severity != "error", item.source, item.rule_id, item.location),
            )
        )
        return EInvoiceValidationReport(
            standard=normalized_standard,
            syntax=normalized_syntax,
            profile=normalized_profile,
            rule_versions=target.rule_versions,
            findings=ordered,
        )
    except Exception as exc:
        return EInvoiceValidationReport(
            standard=normalized_standard,
            syntax=normalized_syntax,
            profile=normalized_profile,
            rule_versions=target.rule_versions,
            findings=(),
            processing_error=f"{type(exc).__name__}: {exc}",
        )


__all__ = [
    "EInvoiceValidationFinding",
    "EInvoiceValidationReport",
    "MAX_XML_BYTES",
    "pinned_rule_versions",
    "validate_xml",
]
