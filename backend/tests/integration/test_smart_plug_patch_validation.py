async def test_invalid_merged_plug_keeps_the_previous_state(async_client, smart_plug_factory):
    plug = await smart_plug_factory(name="Fixture plug", ip_address="192.168.1.101")
    url = f"/api/v1/smart-plugs/{plug.id}"
    rejected = await async_client.patch(url, json={"ip_address": "invalid-host"})
    assert rejected.status_code == 422
    assert "invalid-host" not in rejected.text
    saved = await async_client.get(url)
    assert saved.status_code == 200
    assert saved.json()["ip_address"] == "192.168.1.101"


async def test_tasmota_type_change_checks_current_printer_and_preserves_legacy_edits(
    async_client, printer_factory, smart_plug_factory
):
    printer = await printer_factory()
    await smart_plug_factory(printer_id=printer.id, plug_type="tasmota")
    existing = await smart_plug_factory(printer_id=printer.id, plug_type="tasmota")
    other = await smart_plug_factory(printer_id=printer.id, plug_type="homeassistant")
    updated = await async_client.patch(f"/api/v1/smart-plugs/{existing.id}", json={"name": "Renamed legacy plug"})
    assert updated.status_code == 200
    collision = await async_client.patch(
        f"/api/v1/smart-plugs/{other.id}", json={"plug_type": "tasmota", "ip_address": "192.168.1.101"}
    )
    assert collision.status_code == 400
    assert (await async_client.get(f"/api/v1/smart-plugs/{other.id}")).json()["plug_type"] == "homeassistant"
