"""Client-visible addresses must agree without changing listener bindings."""

import asyncio
import io
import ipaddress
import re
import socket
import ssl
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography import x509
from pydantic import ValidationError

from backend.app.api.routes.virtual_printers import VirtualPrinterCreate, VirtualPrinterUpdate
from backend.app.models.virtual_printer import VirtualPrinter
from backend.app.services.virtual_printer.ftp_server import FTPSession, VirtualPrinterFTPServer
from backend.app.services.virtual_printer.manager import VirtualPrinterInstance, VirtualPrinterManager
from backend.app.services.virtual_printer.ssdp_server import SSDPProxy
from backend.app.services.virtual_printer.tcp_proxy import FTPTLSProxy, SlicerProxyManager


def make_instance(tmp_path, **config):
    return VirtualPrinterInstance(
        vp_id=1,
        name="NAT VP",
        mode="archive",
        model="BL-P001",
        access_code="12345678",
        serial_suffix="391800001",
        base_dir=tmp_path,
        bind_ip="172.20.0.2",
        **config,
    )


@pytest.mark.parametrize("schema", [VirtualPrinterCreate, VirtualPrinterUpdate])
@pytest.mark.parametrize(
    "address",
    [
        "printer.local",
        "::1",
        "0.0.0.0",
        "127.0.0.1",
        "169.254.1.2",
        "224.0.0.1",
        "255.255.255.255",
        "192.168.1.4:990",
        "192.168.1.4\r\nX: injected",
        "192.168.001.4",
    ],
)
def test_api_rejects_unusable_advertised_address(schema, address):
    with pytest.raises(ValidationError):
        schema(advertised_ip=address)


@pytest.mark.parametrize("schema", [VirtualPrinterCreate, VirtualPrinterUpdate])
@pytest.mark.parametrize(
    ("address", "expected"),
    [(None, None), ("", None), ("  ", None), (" 192.168.1.40 ", "192.168.1.40"), ("100.64.0.2", "100.64.0.2")],
)
def test_api_normalizes_optional_advertised_address(schema, address, expected):
    assert schema(advertised_ip=address).model_dump()["advertised_ip"] == expected


def test_runtime_rejects_invalid_database_override(tmp_path):
    with pytest.raises(ValueError):
        make_instance(tmp_path, advertised_ip="host.local")


def test_override_is_in_certificate_and_preserves_local_sans(tmp_path):
    instance = make_instance(tmp_path, advertised_ip="192.168.1.40", remote_interface_ip="100.64.0.2")
    cert_path, _, advertised = instance._resolve_cert_and_advertise()
    assert advertised == "192.168.1.40"
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    addresses = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(
        x509.IPAddress
    )
    assert ipaddress.IPv4Address("192.168.1.40") in addresses
    assert ipaddress.IPv4Address("172.20.0.2") in addresses
    assert ipaddress.IPv4Address("100.64.0.2") in addresses


@pytest.mark.parametrize(("remote", "expected"), [("", "172.20.0.2"), ("100.64.0.2", "100.64.0.2")])
def test_no_override_preserves_automatic_advertisement(tmp_path, remote, expected):
    assert make_instance(tmp_path, remote_interface_ip=remote)._resolve_cert_and_advertise()[2] == expected


@pytest.mark.asyncio
async def test_server_uses_same_override_for_discovery_and_upload(tmp_path, monkeypatch):
    monkeypatch.setenv("VIRTUAL_PRINTER_PASV_ADDRESS", "192.168.1.99")
    instance = make_instance(tmp_path, advertised_ip="192.168.1.40")

    # Leave construction and protocol serialization real; only socket listeners
    # are replaced because this test's NAT address isn't owned by the machine.
    async def ready_only(server):
        server.ready.set()
        await asyncio.Event().wait()

    with (
        patch("backend.app.services.virtual_printer.manager.VirtualPrinterFTPServer.start", ready_only),
        patch("backend.app.services.virtual_printer.manager.SimpleMQTTServer.start", ready_only),
        patch("backend.app.services.virtual_printer.manager.BindServer.start", ready_only),
        patch("backend.app.services.virtual_printer.manager.VirtualPrinterSSDPServer.start", ready_only),
    ):
        try:
            await instance.start_server()
            for message in (instance._ssdp._build_notify_message(), instance._ssdp._build_response_message()):
                assert b"Location: 192.168.1.40\r\n" in message
            assert instance._ftp.bind_address == "172.20.0.2"
            assert instance._ssdp._bind_ip == "172.20.0.2"
            writer = type("Writer", (), {"get_extra_info": lambda self, name: ("172.20.0.2", 990)})()
            session = FTPSession(
                asyncio.StreamReader(),
                writer,
                tmp_path,
                "12345678",
                None,
                None,
                pasv_address=instance._ftp._pasv_address,
            )
            responses = []
            session.send = AsyncMock(side_effect=lambda code, message: responses.append((code, message)))
            await session.cmd_PASV("")
            assert responses[-1][0] == 530
            session.authenticated = True
            session.data_port = 50000
            session._bind_passive_port = AsyncMock(return_value=True)
            await session.cmd_PASV("")
            assert responses[-1] == (227, "Entering Passive Mode (192,168,1,40,195,80)")
        finally:
            await instance.stop_server()


def test_legacy_pasv_env_remains_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("VIRTUAL_PRINTER_PASV_ADDRESS", "192.168.1.99")
    server = VirtualPrinterFTPServer(tmp_path, "12345678", tmp_path / "cert", tmp_path / "key")
    assert server._pasv_address == "192.168.1.99"


def test_invalid_legacy_pasv_env_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("VIRTUAL_PRINTER_PASV_ADDRESS", "192.168.1.40\r\nX: injected")
    with pytest.raises(ValueError):
        VirtualPrinterFTPServer(tmp_path, "12345678", tmp_path / "cert", tmp_path / "key")


@pytest.mark.asyncio
async def test_proxy_pasv_rewrite_uses_override_without_changing_bind(tmp_path):
    proxy = FTPTLSProxy(
        name="FTP",
        listen_port=990,
        target_host="10.0.0.2",
        target_port=990,
        server_cert_path=tmp_path / "cert",
        server_key_path=tmp_path / "key",
        bind_address="172.20.0.2",
        advertised_ip="192.168.1.40",
    )
    with patch.object(proxy, "_create_data_proxy", AsyncMock(return_value=50000)):
        rewritten = await proxy._maybe_rewrite_pasv(
            b"227 Entering Passive Mode (10,0,0,2,195,80)\r\n", "172.20.0.2", {}
        )
    assert rewritten == b"227 Entering Passive Mode (192,168,1,40,195,80)"
    assert proxy.bind_address == "172.20.0.2"


def test_ssdp_proxy_uses_override_without_binding_host_address():
    proxy = SSDPProxy(
        local_interface_ip="10.0.0.3",
        remote_interface_ip="172.20.0.2",
        advertised_ip="192.168.1.40",
        target_printer_ip="10.0.0.2",
    )
    rewritten = proxy._rewrite_ssdp(b"NOTIFY * HTTP/1.1\r\nLocation: 10.0.0.2\r\nDevBind.bambu.com: bound\r\n\r\n")
    assert b"Location: 192.168.1.40\r\n" in rewritten
    assert proxy.remote_interface_ip == "172.20.0.2"


@pytest.mark.asyncio
async def test_address_change_restarts_instance_and_unchanged_config_is_stable(tmp_path):
    manager = VirtualPrinterManager()
    manager._base_dir = tmp_path
    original = make_instance(tmp_path)
    manager._instances[1] = original
    config = VirtualPrinter(
        id=1,
        name="NAT VP",
        enabled=True,
        mode="archive",
        model="BL-P001",
        access_code="12345678",
        serial_suffix="391800001",
        bind_ip="172.20.0.2",
        target_printer_id=None,
        auto_dispatch=True,
        queue_force_color_match=False,
        gcode_injection=False,
        tailscale_disabled=True,
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [config]
    db = AsyncMock()
    db.__aenter__.return_value = db
    db.execute.return_value = result
    manager.set_session_factory(lambda: db)

    with patch.object(VirtualPrinterInstance, "start_server", AsyncMock()):
        await manager.sync_from_db()
        assert manager.get_instance(1) is original
        config.advertised_ip = "192.168.1.40"
        await manager.sync_from_db()
        restarted = manager.get_instance(1)
        assert restarted is not original
        assert restarted.advertised_ip == "192.168.1.40"
        assert restarted.bind_ip == "172.20.0.2"
        assert restarted.access_code == "12345678"
        await manager.sync_from_db()
        assert manager.get_instance(1) is restarted


@pytest.mark.asyncio
async def test_real_ftps_upload_checks_advertised_san_and_auth(tmp_path):
    instance = make_instance(tmp_path, advertised_ip="192.168.1.40")
    cert_path, key_path, address = instance._resolve_cert_and_advertise()
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        passive_port = reservation.getsockname()[1]
    server = VirtualPrinterFTPServer(
        instance.upload_dir,
        "12345678",
        cert_path,
        key_path,
        port=0,
        bind_address="127.0.0.1",
        advertised_ip=address,
        passive_port_min=passive_port,
        passive_port_max=passive_port,
    )
    task = asyncio.create_task(server.start())
    writer = None
    try:
        await asyncio.wait_for(server.ready.wait(), 5)
        context = ssl.create_default_context(cafile=str(instance._cert_service.ca_cert_path))
        # Match pre-3.13 OpenSSL defaults for the existing Bambu-compatible CA;
        # chain and advertised-IP hostname verification remain enabled.
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_2
        port = server._server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port, ssl=context, server_hostname="192.168.1.40")
        assert writer.get_extra_info("ssl_object").version() == "TLSv1.2"
        assert (await reader.readline()).startswith(b"220 ")

        async def command(text):
            writer.write(text.encode() + b"\r\n")
            await writer.drain()
            return await asyncio.wait_for(reader.readline(), 5)

        assert (await command("PASV")).startswith(b"530 ")
        assert (await command("USER bblp")).startswith(b"331 ")
        assert (await command("PASS wrong-code")).startswith(b"530 ")
        assert (await command("USER bblp")).startswith(b"331 ")
        assert (await command("PASS 12345678")).startswith(b"230 ")
        response = await command("PASV")
        match = re.search(rb"\(192,168,1,40,(\d+),(\d+)\)", response)
        assert match, response
        data_port = int(match[1]) * 256 + int(match[2])
        assert (await command("STOR upload.3mf")).startswith(b"150 ")
        _, data_writer = await asyncio.open_connection(
            "127.0.0.1", data_port, ssl=context, server_hostname="192.168.1.40"
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("Metadata/plate_1.gcode", "; IPv4 override upload\nG28\n")
        payload = buffer.getvalue()
        data_writer.write(payload)
        await data_writer.drain()
        data_writer.close()
        await data_writer.wait_closed()
        assert (await asyncio.wait_for(reader.readline(), 5)).startswith(b"226 ")
        assert (instance.upload_dir / "upload.3mf").read_bytes() == payload
    finally:
        if writer:
            writer.close()
            await writer.wait_closed()
        await server.stop()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
