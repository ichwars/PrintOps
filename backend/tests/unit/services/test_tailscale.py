"""Unit tests for TailscaleService — presence detection only.

Cert provisioning was removed: BambuStudio's printer-MQTT trust path validates
against its bundled BBL CA, not the system trust store, so a Tailscale-issued
LE cert was rejected regardless of hostname/IP. The Tailscale toggle is now
informational (surfacing the host's Tailscale IP/FQDN to guide the user).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestTailscaleService:
    """Tests for LocalAPI-first Tailscale presence detection."""

    @pytest.mark.asyncio
    async def test_get_status_prefers_mounted_localapi_socket(self, tmp_path):
        """A mounted host socket is queried without invoking a shipped CLI."""
        from backend.app.services.virtual_printer.tailscale import TailscaleService

        payload = {
            "Self": {
                "DNSName": "printops.example.ts.net.",
                "TailscaleIPs": ["100.64.0.8"],
            }
        }
        socket_path = tmp_path / "tailscaled.sock"
        socket_path.touch()
        svc = TailscaleService(socket_path=socket_path)

        with (
            patch.object(svc, "_query_localapi", new_callable=AsyncMock, return_value=payload) as localapi,
            patch.object(svc, "_run_tailscale", new_callable=AsyncMock) as cli,
        ):
            status = await svc.get_status()

        assert status.available is True
        assert status.fqdn == "printops.example.ts.net"
        localapi.assert_awaited_once_with()
        cli.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_status_falls_back_to_external_cli_when_localapi_fails(self, tmp_path):
        """Local installations retain a CLI fallback when the socket is unusable."""
        from backend.app.services.virtual_printer.tailscale import TailscaleService

        payload = {
            "Self": {
                "DNSName": "desktop.example.ts.net.",
                "TailscaleIPs": ["100.64.0.9"],
            }
        }
        socket_path = tmp_path / "tailscaled.sock"
        socket_path.touch()
        svc = TailscaleService(socket_path=socket_path)

        with (
            patch.object(svc, "_query_localapi", new_callable=AsyncMock, side_effect=OSError("socket denied")),
            patch("shutil.which", return_value="/usr/local/bin/tailscale"),
            patch.object(
                svc, "_run_tailscale", new_callable=AsyncMock, return_value=(0, json.dumps(payload).encode(), b"")
            ) as cli,
        ):
            status = await svc.get_status()

        assert status.available is True
        assert status.fqdn == "desktop.example.ts.net"
        cli.assert_awaited_once_with("status", "--json", timeout=5.0)

    @pytest.mark.asyncio
    async def test_query_localapi_uses_the_configured_unix_socket(self, tmp_path):
        """LocalAPI requests are bound to the configured UDS, never TCP."""
        from backend.app.services.virtual_printer.tailscale import TailscaleService

        socket_path = tmp_path / "tailscaled.sock"
        svc = TailscaleService(socket_path=socket_path)
        payload = {"Self": {"DNSName": "host.example.ts.net.", "TailscaleIPs": []}}
        response = MagicMock()
        response.json.return_value = payload
        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        client_context = MagicMock()
        client_context.__aenter__ = AsyncMock(return_value=client)
        client_context.__aexit__ = AsyncMock(return_value=None)
        transport = MagicMock()

        with (
            patch("httpx.AsyncHTTPTransport", return_value=transport) as transport_factory,
            patch("httpx.AsyncClient", return_value=client_context) as client_factory,
        ):
            result = await svc._query_localapi()

        assert result == payload
        transport_factory.assert_called_once_with(uds=str(socket_path))
        client_factory.assert_called_once_with(
            transport=transport,
            base_url="http://local-tailscaled.sock",
            timeout=5.0,
        )
        client.get.assert_awaited_once_with("/localapi/v0/status")
        response.raise_for_status.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_get_status_binary_not_found(self):
        """Returns available=False when the tailscale binary is absent from PATH."""
        from backend.app.services.virtual_printer.tailscale import TailscaleService

        svc = TailscaleService()
        with patch("shutil.which", return_value=None):
            status = await svc.get_status()

        assert status.available is False
        assert status.error is not None
        assert "not found" in status.error

    @pytest.mark.asyncio
    async def test_get_status_command_fails(self):
        """Returns available=False when `tailscale status` exits non-zero."""
        from backend.app.services.virtual_printer.tailscale import TailscaleService

        svc = TailscaleService()
        with (
            patch("shutil.which", return_value="/usr/bin/tailscale"),
            patch.object(svc, "_run_tailscale", new_callable=AsyncMock, return_value=(1, b"", b"permission denied")),
        ):
            status = await svc.get_status()

        assert status.available is False
        assert "permission denied" in (status.error or "")

    @pytest.mark.asyncio
    async def test_get_status_success(self):
        """Parses FQDN, hostname, tailnet_name, and IP list from JSON output."""
        from backend.app.services.virtual_printer.tailscale import TailscaleService

        payload = {
            "Self": {
                "DNSName": "myhost.example.ts.net.",
                "TailscaleIPs": ["100.1.2.3", "fd7a::1"],
            }
        }
        svc = TailscaleService()
        with (
            patch("shutil.which", return_value="/usr/bin/tailscale"),
            patch.object(
                svc, "_run_tailscale", new_callable=AsyncMock, return_value=(0, json.dumps(payload).encode(), b"")
            ),
        ):
            status = await svc.get_status()

        assert status.available is True
        assert status.fqdn == "myhost.example.ts.net"
        assert status.hostname == "myhost"
        assert status.tailnet_name == "example.ts.net"
        assert "100.1.2.3" in status.tailscale_ips

    @pytest.mark.asyncio
    async def test_get_status_empty_dnsname(self):
        """Returns available=False when Tailscale daemon reports no DNSName (not connected)."""
        from backend.app.services.virtual_printer.tailscale import TailscaleService

        payload = {"Self": {"DNSName": "", "TailscaleIPs": []}}
        svc = TailscaleService()
        with (
            patch("shutil.which", return_value="/usr/bin/tailscale"),
            patch.object(
                svc, "_run_tailscale", new_callable=AsyncMock, return_value=(0, json.dumps(payload).encode(), b"")
            ),
        ):
            status = await svc.get_status()

        assert status.available is False
        assert "no DNSName" in (status.error or "")

    @pytest.mark.asyncio
    async def test_get_status_malformed_json(self):
        """Returns available=False with a parse-error reason when stdout is not JSON."""
        from backend.app.services.virtual_printer.tailscale import TailscaleService

        svc = TailscaleService()
        with (
            patch("shutil.which", return_value="/usr/bin/tailscale"),
            patch.object(svc, "_run_tailscale", new_callable=AsyncMock, return_value=(0, b"not-json{", b"")),
        ):
            status = await svc.get_status()

        assert status.available is False
        assert "JSON parse error" in (status.error or "")
