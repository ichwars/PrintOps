from backend.app.models.business_profile import BusinessProfile


def _payload(profile_id: int) -> dict:
    return {
        "business_profile_id": profile_id,
        "customer_id": None,
        "title": "Ten mounting brackets",
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
                        "provenance": {"source": "slicer", "plate": 1},
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
    assert calculation["currency"] == "EUR"
    assert calculation["version"] == 1
    assert calculation["variants"][0]["operations"][0]["scrap_runs"] == 1

    listed = await async_client.get("/api/v1/calculations/")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    update_payload = _payload(profile.id)
    update_payload["expected_version"] = 1
    update_payload["title"] = "Revised mounting brackets"
    updated = await async_client.put(
        f"/api/v1/calculations/{calculation['id']}", json=update_payload
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2

    stale = await async_client.put(
        f"/api/v1/calculations/{calculation['id']}", json=update_payload
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"

    approved = await async_client.post(
        f"/api/v1/calculations/{calculation['id']}/approve",
        json={"expected_version": 2, "warning_reasons": {}},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["revision_number"] == 1
    assert float(approved.json()["production_cost"]) > 0
    assert approved.json()["selling_price"] == "45.000000"
    assert approved.json()["snapshot"]["calculation"]["customer_id"] is None


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
