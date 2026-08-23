"""Camera-source abstraction: resolves a printer's configured camera into
whatever go2rtc needs to ingest it.

Every camera PrintOps knows how to show — a built-in Bambu RTSP feed, a
built-in Bambu chamber-image feed, or a user-configured external camera —
ultimately needs to become one of two things for go2rtc_registry to
register:

1. One or more source strings go2rtc can ingest directly (an ``rtsp://``
   URL, a plain MJPEG/JPEG-snapshot HTTP URL, or an ``ffmpeg:`` producer
   string).
2. The above, plus a local shim server that must stay alive for the
   registration's lifetime (the chamber-image protocol bridge, or a TLS
   proxy for an ``rtsps://`` source — go2rtc's own RTSP client talks
   plain ``rtsp://``, so anything using TLS needs a local terminator
   first; see ``camera.create_tls_proxy``).

``CameraSource.resolve()`` is the seam a future printer backend (Klipper/
Moonraker's webcam config, OctoPrint's MJPEG proxy, PrusaLink's snapshot
API, ...) would implement to get the exact same go2rtc-backed pipeline —
fan-out, MJPEG delivery, MSE where applicable, diagnostics — that Bambu
cameras get today, without touching go2rtc_registry or the camera routes
at all. No such backend exists yet; this module only formalizes the seam
for the sources PrintOps already has.

Not every configured camera can be resolved this way. USB/v4l2 cameras
need direct device access, and giving go2rtc that inside PrintOps's
container is a genuinely separate problem (device passthrough is a
deployment-time decision, not something this abstraction can paper over).
``get_camera_source()`` returns ``None`` for those; callers fall back to
external_camera.py's existing direct-ffmpeg path unchanged.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlparse

from backend.app.services.camera import create_tls_proxy, get_camera_port, is_chamber_image_model

if TYPE_CHECKING:
    from backend.app.models.printer import Printer


@dataclass
class CameraSourceResult:
    """What go2rtc_registry needs to register one printer's stream."""

    go2rtc_sources: list[str]
    # A shim this source needed to start (TLS proxy, chamber-image bridge)
    # and that must be torn down alongside the go2rtc registration. None
    # for sources go2rtc can reach directly (plain rtsp://, MJPEG/snapshot
    # HTTP URLs).
    local_server: asyncio.Server | None = field(default=None)


class CameraSource(Protocol):
    """Resolves one printer's camera into a go2rtc-ingestible source.

    Implementations do the (possibly async, possibly stateful) work of
    getting from "however this camera is configured" to a source string
    go2rtc understands — opening a TLS proxy, starting a protocol bridge,
    or just handing back a URL. Called once per go2rtc registration (see
    go2rtc_registry.acquire), not once per viewer.
    """

    # Upper bound on requested fps for this source. Bambu's chamber-image
    # protocol tops out around 5fps in practice; external cameras are
    # capped lower than built-in RTSP to keep browser-side load sane for
    # sources PrintOps has no firmware-level knowledge of.
    max_fps: int

    # True iff go2rtc ends up with a real H.264 producer for this source —
    # i.e. MSE (camera_mse_stream) has something to stream-copy. False for
    # anything whose only producer is JPEG-derived (chamber-image, external
    # MJPEG/snapshot): go2rtc could still transcode JPEG→H.264 for those,
    # but that's a real re-encode cost nobody's asked for (see
    # chamber_image_bridge.py's docstring), so MSE stays MJPEG-only-source
    # gated on this flag instead.
    has_h264: bool

    # i18n key under `camera.diagnose.info.pipelineName.*` (frontend) — see
    # /camera/stream-info, which reports this verbatim so the Diagnose panel
    # doesn't need its own copy of this classification logic.
    pipeline_label: str

    async def resolve(self, go2rtc_name: str) -> CameraSourceResult: ...


class BambuRtspSource:
    """X1/X1E/X2D/H2*/P2S — RTSPS on port 322, via a local TLS proxy."""

    max_fps = 30
    has_h264 = True
    pipeline_label = "go2rtc"

    def __init__(self, ip_address: str, access_code: str, model: str | None) -> None:
        self.ip_address = ip_address
        self.access_code = access_code
        self.model = model

    async def resolve(self, go2rtc_name: str) -> CameraSourceResult:
        port = get_camera_port(self.model)
        proxy_port, proxy_server = await create_tls_proxy(self.ip_address, port)
        camera_url = f"rtsp://bblp:{self.access_code}@127.0.0.1:{proxy_port}/streaming/live/1"
        # See generate_go2rtc_mjpeg_stream for why both producers are
        # always registered together (MSE only needs the raw RTSP
        # producer, but a later MJPEG viewer must not have to re-register
        # and swap the proxy port out from under an already-connected MSE
        # consumer).
        return CameraSourceResult(
            go2rtc_sources=[camera_url, f"ffmpeg:{go2rtc_name}#video=mjpeg"],
            local_server=proxy_server,
        )


class BambuChamberImageSource:
    """A1/A1 Mini/P1P/P1S — proprietary binary protocol, bridged to MJPEG."""

    max_fps = 5
    has_h264 = False
    pipeline_label = "go2rtc_chamber_bridge"

    def __init__(self, ip_address: str, access_code: str) -> None:
        self.ip_address = ip_address
        self.access_code = access_code

    async def resolve(self, go2rtc_name: str) -> CameraSourceResult:
        from backend.app.services import chamber_image_bridge

        bridge_port, bridge_server = await chamber_image_bridge.start_bridge(self.ip_address, self.access_code)
        return CameraSourceResult(
            go2rtc_sources=[f"http://127.0.0.1:{bridge_port}/stream.mjpeg"],
            local_server=bridge_server,
        )


class ExternalRtspSource:
    """User-configured external RTSP(S) camera."""

    max_fps = 15
    has_h264 = True
    pipeline_label = "external_rtsp"

    def __init__(self, url: str) -> None:
        self.url = url

    async def resolve(self, go2rtc_name: str) -> CameraSourceResult:
        if not self.url.lower().startswith("rtsps://"):
            return CameraSourceResult(go2rtc_sources=[self.url, f"ffmpeg:{go2rtc_name}#video=mjpeg"])

        # Same TLS-proxy rewrite external_camera.py's own RTSP path used to
        # do inline — go2rtc's RTSP client speaks plain rtsp://, so an
        # rtsps:// source needs a local TLS terminator first, same as
        # BambuRtspSource above.
        parsed = urlparse(self.url)
        target_port = parsed.port or 322
        proxy_port, proxy_server = await create_tls_proxy(parsed.hostname or "", target_port)
        userinfo = ""
        if parsed.username:
            userinfo = parsed.username
            if parsed.password:
                userinfo += f":{parsed.password}"
            userinfo += "@"
        rewritten = f"rtsp://{userinfo}127.0.0.1:{proxy_port}{parsed.path}"
        if parsed.query:
            rewritten += f"?{parsed.query}"
        return CameraSourceResult(
            go2rtc_sources=[rewritten, f"ffmpeg:{go2rtc_name}#video=mjpeg"],
            local_server=proxy_server,
        )


class ExternalHttpSource:
    """User-configured external MJPEG stream or HTTP JPEG snapshot link.

    go2rtc's HTTP source auto-detects both — a continuous MJPEG stream is
    proxied without modification, and a still-image snapshot link is
    polled and converted to an MJPEG stream, matching go2rtc's own
    documented behaviour for these source kinds.
    """

    max_fps = 15
    has_h264 = False

    def __init__(self, url: str, pipeline_label: str = "external_mjpeg") -> None:
        self.url = url
        self.pipeline_label = pipeline_label

    async def resolve(self, go2rtc_name: str) -> CameraSourceResult:
        return CameraSourceResult(go2rtc_sources=[self.url])


def get_camera_source(printer: Printer) -> CameraSource | None:
    """Resolve a printer's configured camera to a CameraSource, or None.

    None means "this camera type isn't go2rtc-ingestible" (USB/v4l2 today)
    — callers fall back to external_camera.py's existing direct-ffmpeg
    path for those.
    """
    if printer.external_camera_enabled and printer.external_camera_url:
        camera_type = printer.external_camera_type
        if camera_type == "rtsp":
            return ExternalRtspSource(printer.external_camera_url)
        if camera_type == "snapshot":
            url = printer.external_camera_snapshot_url or printer.external_camera_url
            return ExternalHttpSource(url, pipeline_label="external_snapshot")
        if camera_type == "mjpeg":
            return ExternalHttpSource(printer.external_camera_url, pipeline_label="external_mjpeg")
        return None  # usb, or an unrecognised type — not go2rtc-ingestible

    if is_chamber_image_model(printer.model):
        return BambuChamberImageSource(printer.ip_address, printer.access_code)

    return BambuRtspSource(printer.ip_address, printer.access_code, printer.model)
