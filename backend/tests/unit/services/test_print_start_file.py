"""Real paths, exact names and transfer outcomes at print start."""

from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.app.services.bambu_ftp import DownloadDeadlineExceeded, FileNotOnPrinterError
from backend.app.services.print_start_file import find_start_file, matching_paths

NAME = "Part.gcode.3mf"


async def acquire(tmp_path, download, listing, *, names=None, pid=1):
    return await find_start_file(
        SimpleNamespace(id=pid, ip_address="192.0.2.1", access_code="test", model="A1"),
        names or [NAME],
        "Part",
        archive_dir=tmp_path,
        retry_settings=(False, 0, 0, 30),
        get_cached=lambda *args: None,
        cache_file=Mock(),
        download=download,
        retry=AsyncMock(),
        list_files=listing,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, TimeoutError("slow")])
async def test_walk_never_retries_a_failed_path_or_uses_its_lookalike(tmp_path, failure):
    attempts = []

    async def download(ip, code, path, local, **kwargs):
        attempts.append(path)
        if path == f"/{NAME}":
            if isinstance(failure, Exception):
                raise failure
            return False
        raise FileNotOnPrinterError(path)

    async def listing(ip, code, directory, **kwargs):
        return [{"name": name} for name in (f"Other_{NAME}", NAME)] if directory == "/" else []

    result = await acquire(tmp_path, download, listing)
    assert result.path is None and result.listed_transfer_failed
    assert attempts.count(f"/{NAME}") == 1
    assert not any("Other_" in path for path in attempts)
    assert not list((tmp_path / "temp").iterdir())


@pytest.mark.asyncio
async def test_missing_sweep_path_can_be_found_later_and_only_failed_path_is_skipped(tmp_path):
    attempts = Counter()

    async def download(ip, code, path, local, **kwargs):
        attempts[path] += 1
        if path == f"/{NAME}":
            return False
        if path == f"/cache/{NAME}" and attempts[path] == 2:
            local.write_bytes(b"valid transfer")
            return True
        raise FileNotOnPrinterError(path)

    async def listing(ip, code, directory, **kwargs):
        return [{"name": NAME}]

    result = await acquire(tmp_path, download, listing)
    assert result.filename == NAME and result.path.read_bytes() == b"valid transfer"
    assert attempts[f"/{NAME}"] == 1 and attempts[f"/cache/{NAME}"] == 2


def test_exact_name_across_directories_excludes_earlier_substring_match():
    assert matching_paths([f"/cache/Other_{NAME}", f"/{NAME}"], "Part") == [f"/{NAME}"]


def test_ambiguous_substring_matches_are_not_selected():
    assert matching_paths(["/Part_large.3mf", "/cache/Part_small.3mf"], "Part") == []


@pytest.mark.asyncio
async def test_unfinished_worker_ends_candidate_search(tmp_path):
    download = AsyncMock(side_effect=DownloadDeadlineExceeded("worker still alive"))
    listing = AsyncMock()
    result = await acquire(tmp_path, download, listing)
    assert result.path is None and result.listed_transfer_failed
    assert download.await_count == 1
    listing.assert_not_awaited()


@pytest.mark.asyncio
async def test_printer_supplied_paths_never_choose_a_local_temp_filename(tmp_path):
    async def download(ip, code, remote, local, **kwargs):
        local.write_bytes(b"ok")
        return True

    listing = AsyncMock(return_value=[{"name": "../../escape.3mf"}, {"name": "/absolute.3mf"}])
    result = await acquire(tmp_path, download, listing, names=["../escape.3mf", "/absolute.3mf", NAME])
    assert result.filename == NAME
    assert result.path.parent == tmp_path / "temp"
    assert result.path.name.startswith("start_1_")
