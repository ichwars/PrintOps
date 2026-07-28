from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.rest_smart_plug import RESTSmartPlugService


@pytest.fixture
def service():
    return RESTSmartPlugService(timeout=5.0)


@pytest.fixture
def mock_plug():
    plug = MagicMock()
    plug.name = "Test REST Plug"
    plug.plug_type = "rest"
    plug.rest_headers = None
    plug.rest_status_url = "http://192.168.1.50/api/plug/status"
    plug.rest_power_url = None
    plug.rest_power_path = "power"
    plug.rest_power_multiplier = 1.0
    plug.rest_energy_url = None
    plug.rest_energy_path = "energy.today"
    plug.rest_energy_multiplier = 1.0
    plug.rest_energy_total_path = None
    plug.rest_energy_total_multiplier = 1.0
    return plug


class TestGetEnergyLifetimeCounter:
    SHELLY = {"apower": 84.0, "aenergy": {"total": 2620.197}}

    @pytest.fixture
    def shelly(self, mock_plug):
        mock_plug.rest_power_path = "apower"
        mock_plug.rest_power_multiplier = 1.0
        mock_plug.rest_energy_path = None
        mock_plug.rest_energy_total_path = "aenergy.total"
        mock_plug.rest_energy_total_multiplier = 0.001
        return mock_plug

    @pytest.mark.asyncio
    async def test_lifetime_counter_lands_in_total_not_today(self, service, shelly):
        response = MagicMock()
        response.json.return_value = self.SHELLY

        with patch.object(service, "_send_request", new_callable=AsyncMock, return_value=response):
            result = await service.get_energy(shelly)

        assert result["power"] == 84.0
        assert result["total"] == pytest.approx(2.620197)
        assert "today" not in result

    @pytest.mark.asyncio
    async def test_today_and_total_counters_stay_separate(self, service, mock_plug):
        mock_plug.rest_power_path = "power"
        mock_plug.rest_energy_path = "energy.today"
        mock_plug.rest_energy_multiplier = 1.0
        mock_plug.rest_energy_total_path = "energy.total"
        mock_plug.rest_energy_total_multiplier = 1.0

        response = MagicMock()
        response.json.return_value = {"power": 42.5, "energy": {"today": 1.23, "total": 987.6}}

        with patch.object(service, "_send_request", new_callable=AsyncMock, return_value=response):
            result = await service.get_energy(mock_plug)

        assert result["today"] == 1.23
        assert result["total"] == 987.6

    @pytest.mark.asyncio
    async def test_total_path_alone_is_enough_to_read_energy(self, service, mock_plug):
        mock_plug.rest_power_path = None
        mock_plug.rest_energy_path = None
        mock_plug.rest_energy_total_path = "aenergy.total"
        mock_plug.rest_energy_total_multiplier = 0.001

        response = MagicMock()
        response.json.return_value = self.SHELLY

        with patch.object(service, "_send_request", new_callable=AsyncMock, return_value=response):
            result = await service.get_energy(mock_plug)

        assert result == {"total": pytest.approx(2.620197)}

    @pytest.mark.asyncio
    async def test_shared_url_is_fetched_once(self, service, shelly):
        shelly.rest_energy_path = "aenergy.total"

        response = MagicMock()
        response.json.return_value = self.SHELLY

        with patch.object(service, "_send_request", new_callable=AsyncMock, return_value=response) as send:
            await service.get_energy(shelly)

        assert send.await_count == 1

    @pytest.mark.asyncio
    async def test_energy_no_status_url_no_separate_urls(self, service, mock_plug):
        mock_plug.rest_status_url = None
        mock_plug.rest_power_url = None
        mock_plug.rest_energy_url = None
        mock_plug.rest_power_path = None
        mock_plug.rest_energy_path = None
        mock_plug.rest_energy_total_path = "aenergy.total"

        result = await service.get_energy(mock_plug)

        assert result is None
