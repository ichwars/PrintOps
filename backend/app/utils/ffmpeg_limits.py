"""Resource limits for local FFmpeg captures and encodes."""

import asyncio
import logging

logger = logging.getLogger(__name__)

X264_BOUNDED_ARGS = ("-threads", "2", "-x264-params", "rc-lookahead=10")
# Limit pixel count while retaining portrait or landscape aspect ratios.
STITCH_SCALE_FILTER = "scale=w='if(gt(iw*ih,2073600),trunc(iw*sqrt(2073600/(iw*ih))/2)*2,trunc(iw/2)*2)':h=-2"


async def reap_ffmpeg(process, timeout: float = 10.0) -> None:
    """Stop a one-shot capture that is still alive when its caller exits."""
    if process is None or process.returncode is not None:
        return
    try:
        process.kill()
    except ProcessLookupError:
        pass
    except OSError as error:
        logger.warning("Could not stop FFmpeg process %s: %s", process.pid, error)
    try:
        await asyncio.wait_for(process.wait(), timeout)
    except TimeoutError:
        logger.warning("FFmpeg process %s did not close within %.0f s", process.pid, timeout)
    except OSError as error:
        logger.warning("Could not reap FFmpeg process %s: %s", process.pid, error)
