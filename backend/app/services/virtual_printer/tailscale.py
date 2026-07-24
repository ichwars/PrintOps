"""Tailscale presence detection for virtual printers.

Reports whether tailscaled is reachable and surfaces the host's Tailscale IPs
and FQDN so the UI can show users which IP to paste into the slicer when
they want to reach a VP over Tailscale.

Historical note: this module previously provisioned Let's Encrypt certs via
`tailscale cert` so the slicer would not need a manual CA import. That path
was removed because LE-signed certs can't help on two independent dimensions:
(1) BambuStudio / OrcaSlicer printer-MQTT trust validates only against the
bundled BBL CA, not the system trust store, so non-BBL chains are rejected
at the issuer check; (2) both slicers' Add Printer dialog accepts only an
IP address (not a hostname), so even if the trust store accepted the LE
issuer, the cert's hostname (`*.<tailnet>.ts.net`) couldn't match the
`100.x.x.x` connection target. The self-signed CA flow (one-time `bbl_ca.crt`
import into the slicer) is the only viable trust mechanism; Tailscale's role
is now strictly network reach.
"""

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_SOCKET_PATH = Path("/var/run/tailscale/tailscaled.sock")
_LOCALAPI_STATUS_URL = "/localapi/v0/status"

# Minimal environment for tailscale subprocess — passes OS/shell variables that
# tailscale needs to locate its socket and config, but strips application secrets
# (JWT keys, DB URLs, SMTP passwords, etc.) that the subprocess has no need for.
_SUBPROCESS_ENV: dict[str, str] = {
    k: v
    for k, v in os.environ.items()
    if k
    in {
        "PATH",
        "HOME",
        "USER",
        "USERNAME",
        "LOGNAME",
        # Windows equivalents
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "SYSTEMROOT",
        "WINDIR",
        "COMPUTERNAME",
        "TEMP",
        "TMP",
        # Linux XDG dirs used by tailscale for socket/config
        "XDG_RUNTIME_DIR",
        "XDG_CONFIG_HOME",
    }
}


@dataclass
class TailscaleStatus:
    """Runtime Tailscale availability and identity."""

    available: bool
    hostname: str  # "myhost"
    tailnet_name: str  # "tailnetname.ts.net"
    fqdn: str  # "myhost.tailnetname.ts.net"
    tailscale_ips: list[str] = field(default_factory=list)
    error: str | None = None


class TailscaleService:
    """Queries tailscaled through LocalAPI with an external-CLI fallback.

    All methods are safe to call when Tailscale is absent — they return
    sensible defaults and never raise exceptions.
    """

    _docker_hint_logged: bool = False

    def __init__(self, socket_path: Path = _DEFAULT_SOCKET_PATH) -> None:
        self._socket_path = socket_path

    def _log_docker_socket_hint(self) -> None:
        """Log a one-time hint when running in Docker without the Tailscale socket mounted."""
        if self._docker_hint_logged:
            return
        if Path("/.dockerenv").exists() and not self._socket_path.exists():
            logger.info(
                "Running in Docker but /var/run/tailscale/tailscaled.sock is not mounted. "
                "Add `- /var/run/tailscale/tailscaled.sock:/var/run/tailscale/tailscaled.sock` "
                "to docker-compose.yml (under volumes:) and run Tailscale on the host to "
                "expose virtual printers over your tailnet."
            )
            self._docker_hint_logged = True

    async def _query_localapi(self) -> dict[str, object]:
        """Read daemon status through the mounted Unix socket."""
        transport = httpx.AsyncHTTPTransport(uds=str(self._socket_path))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://local-tailscaled.sock",
            timeout=5.0,
        ) as client:
            response = await client.get(_LOCALAPI_STATUS_URL)
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, dict):
            raise ValueError("Tailscale LocalAPI returned a non-object response")
        return payload

    async def _run_tailscale(self, *args: str, timeout: float = 30.0) -> tuple[int | None, bytes, bytes]:
        """Run a tailscale subcommand and return (returncode, stdout, stderr).

        Resolves the binary to an absolute path to guard against PATH hijacking.
        """
        binary = shutil.which("tailscale")
        if not binary:
            raise OSError("tailscale binary not found")
        process = await asyncio.create_subprocess_exec(
            binary,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_SUBPROCESS_ENV,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise
        return process.returncode, stdout, stderr

    async def get_status(self) -> TailscaleStatus:
        """Query Tailscale status and return machine identity.

        The mounted host-daemon socket is preferred so the PrintOps image does
        not need to ship Tailscale executables. A locally installed CLI remains
        a fallback for non-container installations.
        """
        localapi_error: str | None = None
        if self._socket_path.exists():
            try:
                return self._status_from_payload(await self._query_localapi())
            except (httpx.HTTPError, OSError, ValueError) as exc:
                localapi_error = str(exc) or "Tailscale LocalAPI request failed"
                logger.warning("Tailscale LocalAPI status failed; trying external CLI: %s", localapi_error)

        if not shutil.which("tailscale"):
            self._log_docker_socket_hint()
            return TailscaleStatus(
                available=False,
                hostname="",
                tailnet_name="",
                fqdn="",
                error=localapi_error or "Tailscale socket and external CLI not found",
            )

        try:
            returncode, stdout, stderr = await self._run_tailscale("status", "--json", timeout=5.0)
        except (OSError, asyncio.TimeoutError) as e:
            # asyncio.TimeoutError covers the case where ``_run_tailscale``
            # killed a stuck subprocess and re-raised. Without this branch
            # the timeout escaped into the FastAPI route handler and could
            # crash the VP management UI for users with a lagging
            # tailscaled daemon.
            return TailscaleStatus(
                available=False,
                hostname="",
                tailnet_name="",
                fqdn="",
                error=str(e) or "tailscale status timed out",
            )

        if returncode is None or returncode != 0:
            self._log_docker_socket_hint()
            return TailscaleStatus(
                available=False,
                hostname="",
                tailnet_name="",
                fqdn="",
                error=stderr.decode(errors="replace").strip(),
            )

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            return TailscaleStatus(
                available=False,
                hostname="",
                tailnet_name="",
                fqdn="",
                error=f"JSON parse error: {e}",
            )

        return self._status_from_payload(data)

    @staticmethod
    def _status_from_payload(data: dict[str, object]) -> TailscaleStatus:
        """Convert a LocalAPI/CLI status payload into the public result."""
        self_info = data.get("Self", {})
        if not isinstance(self_info, dict):
            self_info = {}

        # DNSName includes trailing dot: "myhost.tailnetname.ts.net."
        dns_name = self_info.get("DNSName", "")
        fqdn = dns_name.rstrip(".") if isinstance(dns_name, str) else ""
        if not fqdn:
            return TailscaleStatus(
                available=False,
                hostname="",
                tailnet_name="",
                fqdn="",
                error="Tailscale not connected (no DNSName)",
            )

        parts = fqdn.split(".", 1)
        hostname = parts[0]
        tailnet_name = parts[1] if len(parts) > 1 else ""

        raw_ips = self_info.get("TailscaleIPs", [])
        tailscale_ips = [ip for ip in raw_ips if isinstance(ip, str)] if isinstance(raw_ips, list) else []

        logger.debug("Tailscale available: fqdn=%s, ips=%s", fqdn, tailscale_ips)
        return TailscaleStatus(
            available=True,
            hostname=hostname,
            tailnet_name=tailnet_name,
            fqdn=fqdn,
            tailscale_ips=tailscale_ips,
        )


# Module-level singleton — import this in other modules
tailscale_service = TailscaleService()
