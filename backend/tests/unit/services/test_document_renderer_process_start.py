"""Enforce PDF worker budgets after Linux has replaced the forked parent image."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest

from backend.app.services import document_renderer
from backend.app.services.document_renderer import DocumentRenderer, DocumentRendererError, RenderLimits
from backend.tests.unit.services.test_document_renderer import _pdf, _request

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux fork/exec startup boundary")
MIB = 1024 * 1024


@pytest.fixture
def launch_renderer(tmp_path, monkeypatch):
    def launch(phases, *, parent_readable=True, timeout=1):
        state = SimpleNamespace(index=-1, killed=False, returncode=None, clock=0.0)
        cli = tmp_path / "weasyprint"
        cli.touch()

        def phase():
            return phases[min(max(state.index, 0), len(phases) - 1)]

        def poll():
            if state.killed:
                return -9
            state.index += 1
            if state.index >= len(phases):
                state.returncode = 0
                running.returncode = 0
                return 0
            return None

        def kill():
            state.killed = True

        running = SimpleNamespace(
            pid=123,
            returncode=None,
            poll=poll,
            kill=kill,
            wait=lambda **_kwargs: -9,
            communicate=lambda **_kwargs: (b"", b""),
        )

        def popen(command, **_kwargs):
            Path(command[-1]).write_bytes(_pdf())
            return running

        class Child:
            def cmdline(self):
                if phase()[0] == "denied":
                    raise psutil.AccessDenied()
                return {"parent": ["pytest"], "engine": ["weasyprint"], "empty": []}[phase()[0]]

            def memory_info(self):
                return SimpleNamespace(rss=phase()[1] * MIB)

            def children(self, **_kwargs):
                return [SimpleNamespace(memory_info=lambda: SimpleNamespace(rss=phase()[2] * MIB), kill=kill)]

        class Parent:
            def cmdline(self):
                if not parent_readable:
                    raise psutil.AccessDenied()
                return ["pytest"]

        def process(pid=None):
            return Parent() if pid is None else Child()

        def sleep(seconds):
            state.clock += seconds

        # Model only the operating-system boundary; the renderer pipeline stays real.
        monkeypatch.setattr(document_renderer.subprocess, "Popen", popen)
        monkeypatch.setattr(
            document_renderer,
            "psutil",
            SimpleNamespace(Process=process, Error=psutil.Error, wait_procs=lambda *_args, **_kwargs: ([], [])),
        )
        monkeypatch.setattr(
            document_renderer,
            "time",
            SimpleNamespace(
                monotonic=lambda: state.clock,
                perf_counter=lambda: state.clock,
                time=lambda: state.clock,
                sleep=sleep,
            ),
        )
        renderer = DocumentRenderer(
            engine_cli=cli,
            cache_dir=tmp_path / "cache",
            artifact_dir=tmp_path / "artifacts",
            limits=RenderLimits(timeout_seconds=timeout),
            validator=False,
        )
        return renderer, state

    return launch


@pytest.mark.parametrize("initial_command", ["parent", "empty"])
def test_large_inherited_parent_does_not_reject_a_small_pdf_worker(launch_renderer, initial_command):
    renderer, _state = launch_renderer([(initial_command, 1024, 0), ("engine", 32, 0)])

    assert renderer.render_preview(_request()).content.startswith(b"%PDF-")


@pytest.mark.parametrize(
    "phases",
    [
        [("engine", 513, 0)],
        [("parent", 1024, 0), ("engine", 513, 0)],
        [("engine", 300, 300)],
        [("engine", 32, 0), ("parent", 1024, 0)],
        [("denied", 513, 0)],
    ],
    ids=[
        "worker-budget",
        "budget-after-exec",
        "descendant-budget",
        "no-reentry-to-startup",
        "unreadable-child-arguments",
    ],
)
def test_real_worker_memory_limit_still_kills_the_process_tree(launch_renderer, phases):
    renderer, state = launch_renderer(phases)

    with pytest.raises(DocumentRendererError, match="^RENDER_MEMORY_LIMIT$"):
        renderer.render_preview(_request())
    assert state.killed


def test_missing_exec_transition_is_bounded_by_the_existing_timeout(launch_renderer):
    renderer, state = launch_renderer([("parent", 1024, 0)] * 100, timeout=0.05)

    with pytest.raises(DocumentRendererError, match="^RENDER_TIMEOUT$"):
        renderer.render_preview(_request())
    assert state.killed


def test_unreadable_parent_arguments_keep_immediate_memory_enforcement(launch_renderer):
    renderer, state = launch_renderer([("engine", 513, 0)], parent_readable=False)

    with pytest.raises(DocumentRendererError, match="^RENDER_MEMORY_LIMIT$"):
        renderer.render_preview(_request())
    assert state.killed
