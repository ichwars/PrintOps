"""Collect subprocess output while bounding its lifetime and cleanup."""

import asyncio
import logging
import os
import signal
from contextlib import suppress

logger = logging.getLogger(__name__)
TERMINATE_GRACE = 5.0
KILL_GRACE = 10.0


class StepDeadlineExceeded(TimeoutError):
    def __init__(self, step: str, timeout: float):
        self.step = step
        super().__init__(f"{step} timed out after {timeout:.0f} s")


def _signal_process(process, *, force: bool, grouped: bool) -> None:
    with suppress(ProcessLookupError):
        if grouped and os.name == "posix" and isinstance(process.pid, int) and process.pid > 1:
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        elif force:
            process.kill()
        else:
            process.terminate()


async def _stop(process, output, grouped: bool, step: str) -> None:
    try:
        for force, grace in ((False, TERMINATE_GRACE), (True, KILL_GRACE)):
            _signal_process(process, force=force, grouped=grouped)
            try:
                await asyncio.wait_for(asyncio.shield(output), grace)
                return
            except TimeoutError:
                continue
        logger.warning("%s did not close its output after termination", step)
    finally:
        if not output.done():
            output.cancel()
            with suppress(asyncio.CancelledError):
                await output


async def communicate_with_deadline(process, *, timeout: float, step: str, grouped: bool = False):
    output = asyncio.create_task(process.communicate())
    try:
        return await asyncio.wait_for(asyncio.shield(output), timeout)
    except TimeoutError:
        await _stop(process, output, grouped, step)
        raise StepDeadlineExceeded(step, timeout) from None
    except asyncio.CancelledError:
        await _stop(process, output, grouped, step)
        raise


async def run_step(*args, cwd: str, step: str, timeout: float):
    grouped = os.name == "posix"
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=grouped,
    )
    stdout, stderr = await communicate_with_deadline(process, timeout=timeout, step=step, grouped=grouped)
    return process, stdout, stderr
