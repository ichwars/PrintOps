"""Coverage, safety and determinism tests for document preview semantics."""

from __future__ import annotations

from backend.app.services.document_catalog import DOCUMENT_CAPABILITIES
from backend.app.services.document_layout_defaults import TEMPLATE_DEFAULTS
from backend.app.services.document_layout_samples import (
    load_all_samples,
    load_sample,
    sample_catalog,
)
from backend.app.services.document_view_model import (
    build_document_view_model,
    canonicalize_view_model,
    render_context_sha256,
)


def test_catalog_contains_every_document_type_in_both_languages():
    catalog = sample_catalog()
    pairs = {(item.document_type, item.language) for item in catalog}
    expected = {
        (document_type, language)
        for document_type in DOCUMENT_CAPABILITIES
        for language in ("de", "en")
    }
    assert pairs == expected
    assert len(catalog) == len(expected) == 26
    assert len({item.key for item in catalog}) == 26
    view_models = {
        key: build_document_view_model(snapshot)
        for key, snapshot in load_all_samples().items()
    }
    assert len(view_models) == 26
    assert {model.language for model in view_models.values()} == {"de", "en"}


def test_document_capabilities_control_tax_payment_and_delivery_amounts():
    delivery = build_document_view_model(load_sample("delivery-note-de-standard"))
    reminder = build_document_view_model(load_sample("payment-reminder-de-standard"))
    invoice = build_document_view_model(load_sample("invoice-de-standard"))
    assert delivery.capabilities.show_amounts is False
    assert delivery.taxes == ()
    assert delivery.payment.term_text is None
    assert reminder.capabilities.show_amounts is True
    assert reminder.taxes == ()
    assert invoice.capabilities.has_tax is True
    assert invoice.payment.term_text == "Zahlbar innerhalb von 14 Tagen."


def test_samples_cover_layout_and_commercial_edge_cases():
    samples = load_all_samples()
    invoice = samples["invoice-de-standard"]
    assert invoice.issue_date.isoformat() == "2026-07-23"
    assert len(invoice.lines) == 26
    assert len(invoice.lines[0].description) > 100
    assert invoice.lines[0].metadata["technical"]["printer"] == "Bambu Lab X1 Carbon"
    assert {line.tax_rate for line in invoice.lines[:2]} == {7, 19}
    assert invoice.lines[0].metadata["discount_percent"] == "5.00"
    assert invoice.payment["discount_percent"] == "2.00"
    assert invoice.payment["iban"].startswith("DE")
    assert invoice.metadata["small_business_note_available"] is True
    assert all("example.invalid" in value for value in (invoice.seller["email"], invoice.buyer["email"]))


def test_de_and_en_formatting_is_explicit_and_locale_independent():
    de = build_document_view_model(load_sample("invoice-de-standard"))
    en = build_document_view_model(load_sample("invoice-en-standard"))
    assert de.header.issue_date == "23.07.2026"
    assert en.header.issue_date == "July 23, 2026"
    assert de.positions[0].quantity == "4,000"
    assert en.positions[0].quantity == "4.000"
    assert de.positions[0].unit == "Stück"
    assert en.positions[0].unit == "pc"
    assert de.totals.payable == "179,13 €"
    assert en.totals.payable == "€179.13"


def test_untrusted_markup_and_unicode_remain_plain_view_model_text():
    snapshot = load_sample("invoice-de-standard")
    hostile = "<script>alert('x')</script><b>ÄÖÜ 😀</b>"
    line = snapshot.lines[0].model_copy(update={"description": hostile})
    snapshot = snapshot.model_copy(update={"lines": (line, *snapshot.lines[1:])})
    view_model = build_document_view_model(snapshot)
    assert view_model.positions[0].description == hostile
    assert "<script>" in canonicalize_view_model(view_model).decode("utf-8")


def test_same_snapshot_layout_and_assets_produce_identical_context_hash():
    snapshot = load_sample("invoice-de-standard")
    layout = TEMPLATE_DEFAULTS["classic"]
    assets = {"logo": {"asset_id": 7, "sha256": "a" * 64}}
    first = build_document_view_model(snapshot)
    second = build_document_view_model(snapshot.model_validate_json(snapshot.model_dump_json()))
    assert canonicalize_view_model(first) == canonicalize_view_model(second)
    assert render_context_sha256(first, layout, assets) == render_context_sha256(
        second, layout, {"logo": {"sha256": "a" * 64, "asset_id": 7}}
    )


def test_view_model_exposes_all_semantic_sections_without_paths_or_urls():
    view_model = build_document_view_model(load_sample("invoice-de-standard"))
    assert view_model.sender.name
    assert view_model.recipient.customer_number
    assert view_model.header.number
    assert view_model.positions[0].technical is not None
    assert len(view_model.taxes) >= 2
    assert view_model.payment.iban
    assert view_model.texts
    assert view_model.footer.company
    assert all("path" not in name and "url" not in name for name in view_model.model_fields)


def test_view_model_accepts_the_production_snapshot_shape():
    snapshot = load_sample("invoice-de-standard").model_copy(
        update={
            "seller": {
                "name": "Produktionsprofil",
                "country_code": "DE",
                "address": {
                    "line1": "Produktionsweg 1",
                    "postal_code": "10115",
                    "city": "Berlin",
                    "country_code": "DE",
                },
                "contact": {"email": "profil@example.invalid"},
                "tax_id": "DEMO",
            },
            "buyer": {
                "name": "Produktionskunde",
                "country_code": "DE",
                "address": {
                    "line1": "Kundenweg 2",
                    "postal_code": "20095",
                    "city": "Hamburg",
                    "country_code": "DE",
                },
                "registration_id": "KD-77",
            },
            "payment": {"account_name": "Produktionsprofil", "term_days": 14},
            "references": ({"kind": "order", "identifier": "PO-77"},),
            "text_blocks": ({"purpose": "intro", "body": "Produktionsform"},),
        }
    )
    view_model = build_document_view_model(snapshot)
    assert view_model.sender.address.street == "Produktionsweg 1"
    assert view_model.recipient.customer_number == "KD-77"
    assert view_model.payment.account_holder == "Produktionsprofil"
    assert view_model.references == ("order: PO-77",)
    assert view_model.texts[0].text == "Produktionsform"
