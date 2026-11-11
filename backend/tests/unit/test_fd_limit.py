"""Process descriptor limits and support output."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.app.core import fd_limit


@pytest.mark.parametrize(
    ("soft", "hard", "targets", "expected"),
    [
        (1024, 4096, [(4096, 4096)], 4096),
        (4096, 4096, [], 4096),
        (-1, -1, [], "unlimited"),
        (1024, -1, [(65536, -1), (10240, -1)], 10240),
    ],
)
def test_raise_open_file_limit_never_lowers_or_uses_an_unlimited_target(monkeypatch, soft, hard, targets, expected):
    def raise_limit(_name, limits):
        if limits[0] == 65536:
            raise ValueError("system ceiling")

    resource = SimpleNamespace(
        RLIMIT_NOFILE=1,
        RLIM_INFINITY=-1,
        getrlimit=Mock(return_value=(soft, hard)),
        setrlimit=Mock(side_effect=raise_limit),
    )
    monkeypatch.setitem(sys.modules, "resource", resource)
    monkeypatch.setattr(fd_limit, "startup_status", None)

    fd_limit.raise_open_file_limit()

    assert [call.args[1] for call in resource.setrlimit.call_args_list] == targets
    assert fd_limit.startup_status["soft"] == expected
    assert fd_limit.startup_status["raised"] == bool(targets)


def test_unavailable_limit_update_records_only_the_error_type(monkeypatch):
    resource = SimpleNamespace(
        RLIMIT_NOFILE=1,
        RLIM_INFINITY=-1,
        getrlimit=Mock(return_value=(1024, 4096)),
        setrlimit=Mock(side_effect=OSError("sensitive environment details")),
    )
    monkeypatch.setitem(sys.modules, "resource", resource)
    monkeypatch.setattr(fd_limit, "startup_status", None)
    fd_limit.raise_open_file_limit()
    assert fd_limit.startup_status == {
        "soft_at_start": 1024,
        "hard": 4096,
        "soft": 1024,
        "raised": False,
        "error": "OSError",
    }


def test_support_counts_descriptors_without_targets(monkeypatch):
    targets = {
        "1": "socket:[4871]",
        "2": "pipe:[882]",
        "3": "anon_inode:[eventpoll]",
        "4": "/dev/null",
        "5": "/private/fixture.sqlite3",
        "6": "/private/fixture.sqlite3-wal",
        "7": "/private/fixture.sqlite3-shm (deleted)",
        "8": "/private/other-fixture",
    }

    def readlink(path):
        name = path.rsplit("/", 1)[1]
        if name == "9":
            raise FileNotFoundError(path)
        return targets[name]

    monkeypatch.setattr(fd_limit.os, "listdir", lambda _path: [*targets, "9"])
    monkeypatch.setattr(fd_limit.os, "readlink", readlink)
    usage = fd_limit.collect_fd_usage()
    assert usage["num_fds"] == 8
    assert usage["fds_by_type"] == {
        "socket": 1,
        "pipe": 1,
        "anon_inode": 1,
        "device": 1,
        "database": 1,
        "database_wal": 1,
        "database_shm": 1,
        "file": 1,
    }
    assert "fixture" not in str(usage)
