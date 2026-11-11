"""An expired step releases its pipes, including a subprocess's children."""

import asyncio
import os
import sys
from types import SimpleNamespace

import pytest

from backend.app.services.subprocess_deadline import StepDeadlineExceeded, communicate_with_deadline


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
async def test_timeout_closes_pipes_inherited_by_an_update_child():
    source = 'import subprocess,sys; subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])'
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        source,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    async with asyncio.timeout(3):
        while process.returncode is None:
            await asyncio.sleep(0.01)
    with pytest.raises(StepDeadlineExceeded, match="git fetch timed out"):
        await asyncio.wait_for(communicate_with_deadline(process, timeout=0.1, step="git fetch", grouped=True), 3)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stalled", ["git fetch", "git verify-tag", "git reset", "pip install", "PDF validator install", "npm install"]
)
async def test_native_update_recovers_from_timed_out_steps(stalled, monkeypatch, tmp_path):
    from backend.app.api.routes import updates

    (tmp_path / "frontend").mkdir()
    monkeypatch.setattr(updates.settings, "app_dir", tmp_path)
    monkeypatch.setattr(updates, "_load_update_trust_config", lambda: (tmp_path / "signers", "test"))
    monkeypatch.setattr(updates, "_find_executable", lambda name: name)
    monkeypatch.setattr(updates, "_update_status", {"progress": 0, "status": "idle"})
    seen = []

    async def step(*args, cwd, step, timeout):
        seen.append(step)
        if step == stalled:
            raise StepDeadlineExceeded(step, timeout)
        output = {
            "git remote get-url": b"https://github.com/ichwars/PrintOps.git",
            "git cat-file": b"tag",
            "git rev-parse": b"1" * 40,
        }
        return SimpleNamespace(returncode=0), output.get(step, b""), b""

    monkeypatch.setattr(updates, "run_step", step)
    await updates._perform_update("v1.0.0")
    if stalled == "npm install":
        assert updates._update_status["status"] == "complete"
        assert "npm run build" not in seen and seen[-1] == "PDF validator install"
    else:
        assert updates._update_status["status"] == "error"
        assert stalled in updates._update_status["message"] and seen[-1] == stalled
