from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from backend.app.services.einvoice.validator import MAX_XML_BYTES, validate_xml
from backend.app.services.einvoice.xrechnung import render_xrechnung
from backend.app.services.einvoice.zugferd import render_zugferd

_ZUGFERD_EXAMPLES = (
    Path(__file__).resolve().parents[4] / "app" / "resources" / "einvoice" / "zugferd" / "2.5" / "examples"
)


def test_valid_xrechnung_passes_official_schema_and_rules(canonical_invoice):
    report = validate_xml(
        render_xrechnung(canonical_invoice, "ubl"),
        standard="xrechnung",
        syntax="ubl-2.1",
        profile="xrechnung",
    )

    assert report.valid is True
    assert report.blockers == ()
    assert report.rule_versions["xrechnung"] == "3.0.2-2026-01-31"
    assert report.rule_versions["en16931"] == "1.3.16"


def test_missing_buyer_reference_has_stable_rule_and_field_path(canonical_invoice):
    invoice = replace(canonical_invoice, buyer_reference=None)

    report = validate_xml(
        render_xrechnung(invoice, "ubl"),
        standard="xrechnung",
        syntax="ubl-2.1",
        profile="xrechnung",
    )

    assert report.valid is False
    assert any(
        finding.rule_id == "BR-DE-15" and finding.field_path == "buyer.reference" and finding.severity == "error"
        for finding in report.findings
    )


@pytest.mark.parametrize("profile", ("en16931", "xrechnung"))
def test_valid_zugferd_passes_official_schema_and_profile_rules(canonical_invoice, profile):
    report = validate_xml(
        render_zugferd(canonical_invoice, profile),
        standard="zugferd",
        syntax="cii-d22b",
        profile=profile,
    )

    assert report.valid is True, report.to_dict()
    assert report.blockers == ()
    assert report.rule_versions["zugferd"] == "2.5"
    assert report.rule_versions["factur_x"] == "1.09"


@pytest.mark.parametrize(
    ("filename", "profile"),
    (("EN16931_Einfach.xml", "en16931"), ("XRECHNUNG_Einfach.xml", "xrechnung")),
)
def test_official_ferd_25_examples_pass_the_pinned_rules(filename, profile):
    report = validate_xml(
        (_ZUGFERD_EXAMPLES / filename).read_bytes(),
        standard="zugferd",
        syntax="cii-d22b",
        profile=profile,
    )

    assert report.valid is True, report.to_dict()


@pytest.mark.parametrize(
    "xml, expected_rule",
    [
        (b"<!DOCTYPE x [<!ENTITY secret SYSTEM 'file:///etc/passwd'>]><x>&secret;</x>", "XML-PARSE"),
        (b"x" * (MAX_XML_BYTES + 1), "XML-SIZE"),
    ],
    ids=("doctype", "size-limit"),
)
def test_unsafe_or_oversized_input_is_rejected_without_processing(xml, expected_rule):
    report = validate_xml(
        xml,
        standard="xrechnung",
        syntax="ubl-2.1",
        profile="xrechnung",
    )

    assert report.valid is False
    assert report.findings[0].rule_id == expected_rule


def test_asset_selection_rejects_unknown_values_instead_of_building_paths(canonical_invoice):
    with pytest.raises(ValueError, match="Unsupported E-invoice validation target"):
        validate_xml(
            render_xrechnung(canonical_invoice, "ubl"),
            standard="../../escape",
            syntax="ubl-2.1",
            profile="xrechnung",
        )
