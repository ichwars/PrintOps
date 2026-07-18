from datetime import date

import pytest

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.calculation import Calculation
from backend.app.models.printer import Printer
from backend.app.models.settings import Settings


def _payload(profile_id: int) -> dict:
    return {
        "business_profile_id": profile_id,
        "customer_id": None,
        "project_id": None,
        "request_kind": "series",
        "quantity": 10,
        "title": "Ten mounting brackets",
        "position_description": "Printed PETG mounting bracket",
        "special_terms": "Deliver in two batches",
        "commercial_overrides": {"scrap_rate": "0.08", "material_markup_rate": "0.15"},
        "currency": "eur",
        "notes": "Customer request by phone",
        "variants": [
            {
                "name": "PETG standard",
                "is_preferred": True,
                "price_method": "target_margin",
                "price_rate": "0.35",
                "lines": [
                    {
                        "kind": "printed_part",
                        "description": "Mounting bracket",
                        "quantity": "10",
                        "unit_code": "C62",
                        "unit_price": "4.50",
                    }
                ],
                "operations": [
                    {
                        "kind": "printing",
                        "title": "Plate 1",
                        "good_parts": 10,
                        "parts_per_run": 4,
                        "scrap_runs": 1,
                        "material_grams_per_run": "100",
                        "print_hours_per_run": "2.5",
                        "provenance": {"source": "slicer", "plate": 1, "printer_hourly_rate": "2.50"},
                        "labor": [
                            {"kind": "operator", "hours": "0.5", "hourly_rate": "30", "allocation_basis": "request"}
                        ],
                    }
                ],
            }
        ],
    }


async def _profile(db_session) -> BusinessProfile:
    profile = BusinessProfile(
        name="Calculation API issuer",
        legal_name="Calculation API issuer GmbH",
        country_code="DE",
        default_currency="EUR",
        is_active=True,
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    return profile


async def test_create_list_update_and_approve_calculation(async_client, db_session):
    profile = await _profile(db_session)

    created = await async_client.post("/api/v1/calculations/", json=_payload(profile.id))
    assert created.status_code == 201, created.text
    calculation = created.json()
    assert calculation["customer_id"] is None
    assert calculation["request_kind"] == "series"
    assert calculation["quantity"] == 10
    assert calculation["commercial_overrides"]["scrap_rate"] == "0.08"
    assert calculation["currency"] == "EUR"
    assert calculation["version"] == 1
    assert calculation["variants"][0]["operations"][0]["scrap_runs"] == 1

    listed = await async_client.get("/api/v1/calculations/")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    update_payload = _payload(profile.id)
    update_payload["expected_version"] = 1
    update_payload["title"] = "Revised mounting brackets"
    updated = await async_client.put(f"/api/v1/calculations/{calculation['id']}", json=update_payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2

    stale = await async_client.put(f"/api/v1/calculations/{calculation['id']}", json=update_payload)
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"

    approved = await async_client.post(
        f"/api/v1/calculations/{calculation['id']}/approve",
        json={"expected_version": 2, "warning_reasons": {}},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["revision_number"] == 1
    assert float(approved.json()["production_cost"]) > 0
    assert float(approved.json()["selling_price"]) > float(approved.json()["production_cost"])
    assert approved.json()["snapshot"]["calculation"]["customer_id"] is None
    assert approved.json()["snapshot"]["calculation"]["position_description"] == "Printed PETG mounting bracket"

    revisions = await async_client.get(f"/api/v1/calculations/{calculation['id']}/revisions")
    assert revisions.status_code == 200, revisions.text
    assert [item["revision_number"] for item in revisions.json()] == [1]
    assert revisions.json()[0]["selling_price"] == approved.json()["selling_price"]

    revised = await async_client.post(f"/api/v1/calculations/{calculation['id']}/revise")
    assert revised.status_code == 201, revised.text
    assert revised.json()["status"] == "draft"
    assert revised.json()["title"] == "Revised mounting brackets"
    original = await async_client.get(f"/api/v1/calculations/{calculation['id']}")
    assert original.json()["status"] == "superseded"


async def test_approval_warnings_require_reasons(async_client, db_session):
    profile = await _profile(db_session)
    payload = _payload(profile.id)
    payload["variants"][0]["operations"][0]["provenance"] = {"source": "manual"}
    created = await async_client.post("/api/v1/calculations/", json=payload)
    calculation = created.json()

    validation = await async_client.get(f"/api/v1/calculations/{calculation['id']}/validation")
    assert validation.status_code == 200
    assert set(validation.json()["warnings"]) == {"manual_source_values", "missing_machine_rate"}

    rejected = await async_client.post(
        f"/api/v1/calculations/{calculation['id']}/approve", json={"expected_version": 1, "warning_reasons": {}}
    )
    assert rejected.status_code == 422
    accepted = await async_client.post(
        f"/api/v1/calculations/{calculation['id']}/approve",
        json={
            "expected_version": 1,
            "warning_reasons": {
                "manual_source_values": "Checked against slicer",
                "missing_machine_rate": "Introductory quote",
            },
        },
    )
    assert accepted.status_code == 200, accepted.text


async def test_template_excludes_customer_context(async_client, db_session):
    profile = await _profile(db_session)
    created = await async_client.post("/api/v1/calculations/", json=_payload(profile.id))
    calculation_id = created.json()["id"]

    response = await async_client.post(
        f"/api/v1/calculations/{calculation_id}/templates",
        json={"name": "Bracket template"},
    )

    assert response.status_code == 201, response.text
    assert "customer_id" not in response.json()["definition"]["calculation"]
    templates = await async_client.get("/api/v1/calculations/templates")
    assert templates.status_code == 200
    instantiated = await async_client.post(
        f"/api/v1/calculations/templates/{response.json()['id']}/instantiate", json={"title": "From template"}
    )
    assert instantiated.status_code == 201, instantiated.text
    assert instantiated.json()["title"] == "From template"
    assert instantiated.json()["customer_id"] is None
    assert instantiated.json()["variants"][0]["operations"][0]["source_file"] is None
    assert instantiated.json()["variants"][0]["operations"][0]["labor"][0]["hours"] == "0.500000"
    assert response.json()["definition"]["variants"][0]["operations"][0]["provenance"] == {"source": "template"}


async def test_approval_uses_configured_default_printer_costs(async_client, db_session):
    profile = await _profile(db_session)
    printer = Printer(
        name="Costed printer",
        serial_number="COSTED-1",
        ip_address="127.0.0.1",
        access_code="",
        acquisition_date=date.today(),
        acquisition_value="1200",
        service_years="4",
        annual_hours="1000",
        maintenance_rate="0.10",
        nominal_power_watts="200",
    )
    db_session.add(printer)
    await db_session.flush()
    db_session.add(Settings(key="calculation_defaults", value=f'{{"defaultPrinterId":{printer.id}}}'))
    await db_session.commit()
    payload = _payload(profile.id)
    payload["variants"][0]["operations"][0]["provenance"] = {"source": "slicer"}
    created = await async_client.post("/api/v1/calculations/", json=payload)
    approved = await async_client.post(
        f"/api/v1/calculations/{created.json()['id']}/approve",
        json={"expected_version": 1, "warning_reasons": {"missing_machine_rate": "Configured default printer"}},
    )
    assert approved.status_code == 200, approved.text
    assert float(approved.json()["production_cost"]) > 20


async def test_invalid_provenance_is_a_validation_blocker(async_client, db_session):
    profile = await _profile(db_session)
    payload = _payload(profile.id)
    payload["variants"][0]["operations"][0]["provenance"]["printer_hourly_rate"] = "not-a-number"
    created = await async_client.post("/api/v1/calculations/", json=payload)
    validation = await async_client.get(f"/api/v1/calculations/{created.json()['id']}/validation")
    assert validation.status_code == 200
    assert "invalid_provenance" in validation.json()["blockers"]


async def test_preview_returns_complete_commercial_breakdown(async_client):
    response = await async_client.post(
        "/api/v1/calculations/preview",
        json={
            "good_parts": 4,
            "parts_per_run": 2,
            "material_grams_per_run": "100",
            "material_price_per_kg": "20",
            "additional_costs": "6",
            "risk_rate": "0.10",
            "price_method": "explicit_price",
            "explicit_price": "40",
            "discount_rate": "0.10",
            "shipping": "5",
            "tax_rate": "0.19",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "total_runs": 2,
        "material_cost": "4.00",
        "material_markup": "0.00",
        "machine_cost": "0.00",
        "energy_cost": "0.00",
        "labor_cost": "0.00",
        "consumables": "0.00",
        "packaging": "0.00",
        "additional_costs": "6.00",
        "additive_materials": "0.00",
        "scrap_cost": "0.00",
        "risk_cost": "1.00",
        "production_cost": "11.00",
        "shipping": "5.00",
        "selling_price": "41.00",
        "net_price": "41.00",
        "contribution": "25.00",
        "effective_margin": "0.694444",
        "tax": "7.79",
        "gross_price": "48.79",
        "unit_price": "10.25",
        "breakdown": [
            {"code": "machine", "label": "Machine", "basis": "2 runs", "amount": "0.00"},
            {"code": "labor", "label": "Labor", "basis": "allocated time", "amount": "0.00"},
            {"code": "material", "label": "Material", "basis": "2 runs", "amount": "4.00"},
            {"code": "energy", "label": "Energy", "basis": "printer and dryer", "amount": "0.00"},
            {"code": "additive_materials", "label": "Additional materials", "basis": "line items", "amount": "0.00"},
            {"code": "consumables", "label": "Consumables", "basis": "flat amount", "amount": "0.00"},
            {"code": "scrap", "label": "Scrap", "basis": "0%", "amount": "0.00"},
            {"code": "risk", "label": "Risk", "basis": "10.00%", "amount": "1.00"},
            {"code": "packaging", "label": "Packaging", "basis": "flat amount", "amount": "0.00"},
            {"code": "shipping", "label": "Shipping", "basis": "flat amount", "amount": "5.00"},
        ],
    }


async def test_batch_preview_aggregates_operations_before_pricing(async_client):
    operation = {
        "good_parts": 2,
        "parts_per_run": 1,
        "material_grams_per_run": "100",
        "material_price_per_kg": "20",
        "price_method": "markup",
    }
    commercial = {
        "good_parts": 4,
        "parts_per_run": 1,
        "additional_costs": "2",
        "risk_rate": "0.10",
        "price_method": "markup",
        "price_rate": "0.25",
        "tax_rate": "0.19",
    }
    response = await async_client.post(
        "/api/v1/calculations/preview-batch", json={"operations": [operation, operation], "commercial": commercial}
    )
    assert response.status_code == 200, response.text
    assert response.json()["total_runs"] == 4
    assert response.json()["material_cost"] == "8.00"
    assert response.json()["additional_costs"] == "2.00"
    assert response.json()["production_cost"] == "11.00"
    assert response.json()["net_price"] == "13.75"


async def test_delete_calculation_enforces_version_and_not_found(async_client, db_session):
    profile = await _profile(db_session)
    created = await async_client.post("/api/v1/calculations/", json=_payload(profile.id))
    calculation = created.json()

    stale = await async_client.delete(
        f"/api/v1/calculations/{calculation['id']}", params={"expected_version": 99}
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"

    missing = await async_client.delete(
        "/api/v1/calculations/999999", params={"expected_version": 1}
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "not_found"


@pytest.mark.parametrize("blocked_status", ["approved", "superseded", "archived"])
async def test_delete_calculation_rejects_every_non_draft_status(
    async_client, db_session, blocked_status
):
    profile = await _profile(db_session)
    created = await async_client.post("/api/v1/calculations/", json=_payload(profile.id))
    calculation_id = created.json()["id"]
    calculation = await db_session.get(Calculation, calculation_id)
    calculation.status = blocked_status
    await db_session.commit()

    response = await async_client.delete(
        f"/api/v1/calculations/{calculation_id}", params={"expected_version": 1}
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_state"
    assert await db_session.get(Calculation, calculation_id) is not None
