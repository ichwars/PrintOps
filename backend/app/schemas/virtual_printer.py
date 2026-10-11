"""Schemas for virtual printer diagnostics."""

from pydantic import BaseModel, field_validator

from backend.app.schemas.printer import DiagnosticCheck
from backend.app.utils.advertised_address import validate_advertised_ip


class VPAddressConfig(BaseModel):
    """Per-printer NAT address; blank/null restores automatic advertisement."""

    advertised_ip: str | None = None

    _validate_advertised_ip = field_validator("advertised_ip")(validate_advertised_ip)


class VPDiagnosticResult(BaseModel):
    """Result of a virtual-printer setup diagnostic run.

    Mirrors ``PrinterDiagnosticResult`` but keyed to a virtual printer: the
    checks probe the VP's own bind IP and local services rather than a remote
    printer. ``checks[].id`` values are VP-specific (enabled, running,
    bind_interface, access_code, target_printer, port_ftps, port_mqtt,
    port_bind, certificate); the frontend renders the localized title and
    fix text from id + status.
    """

    vp_id: int
    vp_name: str
    mode: str
    overall: str  # "ok" | "warnings" | "problems"
    checks: list[DiagnosticCheck]
