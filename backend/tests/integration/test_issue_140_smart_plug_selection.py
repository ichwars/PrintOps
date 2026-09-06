"""API-level coverage for the printer card's primary smart plug (#140)."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

MAIN = "/api/v1/smart-plugs/by-printer/{}"
ENTITIES = "/api/v1/smart-plugs/by-printer/{}/scripts"


async def _ha(factory, printer, entity_id: str, **overrides):
    return await factory(
        plug_type="homeassistant",
        printer_id=printer.id,
        ha_entity_id=entity_id,
        **overrides,
    )


class TestPrinterCardPowerRow:
    async def test_first_created_accessory_does_not_displace_outlet(
        self,
        async_client: AsyncClient,
        printer_factory,
        smart_plug_factory,
    ):
        printer = await printer_factory()
        await _ha(
            smart_plug_factory,
            printer,
            "switch.exhaust_fan",
            name="Exhaust Fan",
            controls_printer_power=False,
        )
        await _ha(
            smart_plug_factory,
            printer,
            "switch.printer_outlet",
            name="Printer Outlet",
            ha_power_entity="sensor.printer_power",
        )

        response = await async_client.get(MAIN.format(printer.id))

        assert response.status_code == 200
        assert response.json()["name"] == "Printer Outlet"

    async def test_enabled_outlet_beats_disabled_outlet(
        self,
        async_client: AsyncClient,
        printer_factory,
        smart_plug_factory,
    ):
        printer = await printer_factory()
        await _ha(
            smart_plug_factory,
            printer,
            "switch.retired",
            name="Retired Outlet",
            enabled=False,
        )
        await _ha(
            smart_plug_factory,
            printer,
            "switch.live",
            name="Live Outlet",
        )

        response = await async_client.get(MAIN.format(printer.id))

        assert response.json()["name"] == "Live Outlet"

    async def test_switch_beats_ha_script_and_monitor_only_mqtt(
        self,
        async_client: AsyncClient,
        printer_factory,
        smart_plug_factory,
    ):
        printer = await printer_factory()
        await _ha(
            smart_plug_factory,
            printer,
            "script.start_accessories",
            name="Start Accessories",
        )
        await smart_plug_factory(
            name="MQTT Meter",
            plug_type="mqtt",
            printer_id=printer.id,
            mqtt_power_topic="tele/printer/SENSOR",
        )
        await _ha(
            smart_plug_factory,
            printer,
            "switch.printer",
            name="Printer Outlet",
        )

        response = await async_client.get(MAIN.format(printer.id))

        assert response.json()["name"] == "Printer Outlet"

    async def test_no_plugs_returns_null(
        self,
        async_client: AsyncClient,
        printer_factory,
    ):
        printer = await printer_factory()

        response = await async_client.get(MAIN.format(printer.id))

        assert response.status_code == 200
        assert response.json() is None


class TestAssociatedEntityRow:
    async def test_main_switch_is_not_rendered_twice_but_accessories_remain(
        self,
        async_client: AsyncClient,
        printer_factory,
        smart_plug_factory,
    ):
        printer = await printer_factory()
        await _ha(
            smart_plug_factory,
            printer,
            "switch.fan",
            name="Fan",
            controls_printer_power=False,
        )
        await _ha(
            smart_plug_factory,
            printer,
            "script.notify",
            name="Notify Script",
            controls_printer_power=False,
        )
        await _ha(
            smart_plug_factory,
            printer,
            "switch.outlet",
            name="Printer Outlet",
        )

        response = await async_client.get(ENTITIES.format(printer.id))

        assert response.status_code == 200
        assert sorted(plug["name"] for plug in response.json()) == ["Fan", "Notify Script"]

    async def test_script_only_fallback_keeps_one_click_scripts_visible(
        self,
        async_client: AsyncClient,
        printer_factory,
        smart_plug_factory,
    ):
        printer = await printer_factory()
        await _ha(smart_plug_factory, printer, "script.a", name="Script A")
        await _ha(smart_plug_factory, printer, "script.b", name="Script B")

        main = await async_client.get(MAIN.format(printer.id))
        entities = await async_client.get(ENTITIES.format(printer.id))

        assert main.json()["name"] == "Script A"
        assert sorted(plug["name"] for plug in entities.json()) == ["Script A", "Script B"]
