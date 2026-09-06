"""Regression coverage for deterministic printer power-plug selection (#140)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.services.smart_plug_selection import (
    can_be_switched,
    pick_power_plug,
    plugs_for_printer,
    rank_power_plugs,
    reports_power,
    select_energy_reading,
)

pytestmark = pytest.mark.unit


def _plug(plug_id: int = 1, **overrides) -> SimpleNamespace:
    defaults = {
        "id": plug_id,
        "name": f"Plug {plug_id}",
        "plug_type": "tasmota",
        "ha_entity_id": None,
        "ha_power_entity": None,
        "mqtt_topic": None,
        "mqtt_power_topic": None,
        "rest_power_path": None,
        "controls_printer_power": True,
        "enabled": True,
        "show_on_printer_card": True,
    }
    return SimpleNamespace(**(defaults | overrides))


class TestSharedPowerPlugRanking:
    def test_earlier_accessory_does_not_displace_printer_outlet(self):
        fan = _plug(
            1,
            name="Exhaust Fan",
            plug_type="homeassistant",
            ha_entity_id="switch.exhaust_fan",
            controls_printer_power=False,
        )
        outlet = _plug(
            2,
            name="Printer Outlet",
            plug_type="homeassistant",
            ha_entity_id="switch.printer_outlet",
            ha_power_entity="sensor.printer_power",
        )

        assert pick_power_plug([fan, outlet]) is outlet
        assert pick_power_plug([outlet, fan]) is outlet

    def test_switch_beats_ha_script_and_monitor_only_mqtt(self):
        script = _plug(
            1,
            plug_type="homeassistant",
            ha_entity_id="script.start_accessories",
        )
        monitor = _plug(2, plug_type="mqtt", mqtt_power_topic="tele/printer/SENSOR")
        switch = _plug(3, plug_type="homeassistant", ha_entity_id="switch.printer")

        assert rank_power_plugs([script, monitor, switch]) == [switch, monitor, script]

    def test_printer_power_flag_outranks_accessory_measurement(self):
        metered_fan = _plug(
            1,
            controls_printer_power=False,
            ha_power_entity="sensor.fan_power",
        )
        unmetered_outlet = _plug(
            2,
            plug_type="homeassistant",
            ha_entity_id="switch.printer",
        )

        assert pick_power_plug([metered_fan, unmetered_outlet]) is unmetered_outlet

    def test_enabled_plug_beats_disabled_plug(self):
        disabled = _plug(1, enabled=False)
        enabled = _plug(2)

        assert pick_power_plug([disabled, enabled]) is enabled

    def test_measurement_breaks_an_otherwise_equal_tie(self):
        unmetered = _plug(
            1,
            plug_type="homeassistant",
            ha_entity_id="switch.a",
        )
        metered = _plug(
            2,
            plug_type="homeassistant",
            ha_entity_id="switch.b",
            ha_power_entity="sensor.b_power",
        )

        assert pick_power_plug([unmetered, metered]) is metered

    def test_equal_plugs_resolve_by_lowest_id(self):
        first = _plug(1)
        second = _plug(2)

        assert pick_power_plug([second, first]) is first

    def test_nullable_legacy_flags_rank_last_without_raising(self):
        legacy = _plug(
            1,
            controls_printer_power=None,
            enabled=None,
            show_on_printer_card=None,
        )
        ordinary = _plug(2)

        assert pick_power_plug([legacy, ordinary]) is ordinary
        assert pick_power_plug([legacy]) is legacy

    def test_empty_and_script_only_fallbacks_remain_supported(self):
        script = _plug(
            1,
            plug_type="homeassistant",
            ha_entity_id="script.start_accessories",
        )

        assert pick_power_plug([]) is None
        assert pick_power_plug([script]) is script


class TestCapabilities:
    @pytest.mark.parametrize(
        ("plug", "expected"),
        [
            (_plug(plug_type="tasmota"), True),
            (_plug(plug_type="rest"), True),
            (_plug(plug_type="homeassistant", ha_entity_id="switch.outlet"), True),
            (_plug(plug_type="homeassistant", ha_entity_id="light.chamber"), True),
            (_plug(plug_type="homeassistant", ha_entity_id="script.start"), False),
            (_plug(plug_type="mqtt"), False),
        ],
    )
    def test_switchability_matches_control_support(self, plug, expected):
        assert can_be_switched(plug) is expected

    @pytest.mark.parametrize(
        ("plug", "expected"),
        [
            (_plug(plug_type="tasmota"), True),
            (_plug(plug_type="homeassistant", ha_entity_id="switch.a"), False),
            (_plug(plug_type="homeassistant", ha_power_entity="sensor.power"), True),
            (_plug(plug_type="mqtt"), False),
            (_plug(plug_type="mqtt", mqtt_topic="zigbee2mqtt/plug"), True),
            (_plug(plug_type="rest"), False),
            (_plug(plug_type="rest", rest_power_path="apower"), True),
        ],
    )
    def test_configured_power_measurement_is_part_of_the_rank(self, plug, expected):
        assert reports_power(plug) is expected


class TestPrinterPlugQuery:
    @pytest.mark.asyncio
    async def test_returns_only_requested_printer_in_business_order(
        self,
        db_session,
        printer_factory,
        smart_plug_factory,
    ):
        printer = await printer_factory(name="P1S")
        other = await printer_factory(name="X1C")
        accessory = await smart_plug_factory(
            name="Fan",
            plug_type="homeassistant",
            printer_id=printer.id,
            controls_printer_power=False,
        )
        outlet = await smart_plug_factory(
            name="P1S Outlet",
            plug_type="homeassistant",
            printer_id=printer.id,
            controls_printer_power=True,
        )
        await smart_plug_factory(name="X1C Outlet", printer_id=other.id)
        await smart_plug_factory(name="Bench Plug", printer_id=None)

        candidates = await plugs_for_printer(db_session, printer.id)

        assert [plug.id for plug in candidates] == [outlet.id, accessory.id]

    @pytest.mark.asyncio
    async def test_none_printer_id_does_not_borrow_unlinked_plugs(
        self,
        db_session,
        smart_plug_factory,
    ):
        await smart_plug_factory(name="Bench Plug", printer_id=None)

        assert await plugs_for_printer(db_session, None) == []


class TestEnergySelection:
    @pytest.mark.asyncio
    async def test_does_not_bill_a_metered_accessory_when_outlet_has_no_counter(self):
        outlet = _plug(1, name="Printer Outlet")
        accessory = _plug(2, name="Fan", controls_printer_power=False)
        read = AsyncMock(side_effect=lambda plug, _db: {"power": 120.0} if plug is outlet else {"total": 8.5})

        selected = await select_energy_reading([outlet, accessory], read, db=None)

        assert selected is None
        read.assert_awaited_once_with(outlet, None)

    @pytest.mark.asyncio
    async def test_can_fall_back_within_same_printer_power_assignment(self):
        unavailable = _plug(1, name="Offline meter")
        available = _plug(2, name="Online meter")

        async def read(plug, _db):
            return None if plug is unavailable else {"total": 8.5}

        selected = await select_energy_reading([unavailable, available], read, db=None)

        assert selected == (available, {"total": 8.5})

    @pytest.mark.asyncio
    async def test_multiple_meters_choose_deterministically_and_poll_once(self):
        first = _plug(1, name="First meter")
        second = _plug(2, name="Second meter")
        read = AsyncMock(return_value={"total": 0.0})

        selected = await select_energy_reading(
            rank_power_plugs([second, first]),
            read,
            db=None,
        )

        assert selected == (first, {"total": 0.0})
        read.assert_awaited_once_with(first, None)

    @pytest.mark.asyncio
    async def test_missing_counters_return_none_instead_of_inventing_usage(self):
        read = AsyncMock(return_value={"power": 4.0, "total": None})

        assert await select_energy_reading([_plug()], read, db=None) is None

    @pytest.mark.asyncio
    async def test_record_energy_start_handles_multiple_linked_plugs(
        self,
        db_session,
        printer_factory,
        smart_plug_factory,
        archive_factory,
    ):
        printer = await printer_factory()
        await smart_plug_factory(
            name="Fan",
            plug_type="homeassistant",
            printer_id=printer.id,
            controls_printer_power=False,
        )
        await smart_plug_factory(
            name="Printer Outlet",
            plug_type="homeassistant",
            printer_id=printer.id,
            controls_printer_power=True,
        )
        archive = await archive_factory(printer.id)

        from backend.app.main import _record_energy_start

        async def read(plug, _db):
            if plug.name == "Printer Outlet":
                return {"total": 41.5}
            return {"power": 2.0}

        with patch("backend.app.main._get_plug_energy", side_effect=read):
            recorded = await _record_energy_start(archive, printer.id, db_session)

        assert recorded is True
        assert archive.energy_start_kwh == 41.5
