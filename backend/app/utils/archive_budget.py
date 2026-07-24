"""Shared upload and ZIP/3MF resource budgets.

The limits are enforced before materialising archive members. Parser call
sites use these helpers instead of raw ZipFile.read calls.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import defusedxml.ElementTree as ET

MIB = 1024 * 1024
MAX_UPLOAD_BYTES = 256 * MIB
# Timelapse videos routinely exceed the ZIP/3MF budget on long prints. Keep a
# separate finite cap so video uploads work without becoming unbounded.
MAX_TIMELAPSE_UPLOAD_BYTES = 2 * 1024 * MIB
MAX_3MF_PLATES = 64
MAX_FILAMENT_SLOTS = 64
MAX_ARCHIVE_REFERENCES = 1024


class ArchiveBudgetError(ValueError):
    """An upload/archive exceeds a configured resource budget."""


@dataclass(frozen=True)
class ArchiveBudget:
    max_members: int = 4096
    max_member_bytes: int = 256 * MIB
    max_total_uncompressed_bytes: int = 512 * MIB
    max_compression_ratio: float = 200.0
    max_metadata_bytes: int = 32 * MIB
    max_json_depth: int = 64
    max_json_items: int = 50_000
    max_xml_nodes: int = 250_000
    max_xml_depth: int = 128


DEFAULT_ARCHIVE_BUDGET = ArchiveBudget()


def safe_archive_basename(filename: str) -> str:
    """Return a basename after normalising POSIX and Windows separators."""
    return Path(filename.replace("\\", "/")).name


async def read_upload_limited(upload: Any, *, max_bytes: int = MAX_UPLOAD_BYTES, chunk_size: int = MIB) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ArchiveBudgetError(f"upload exceeds {max_bytes} byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _normalised_member_name(name: str) -> str:
    return name.replace("\\", "/")


def validate_zip_archive(
    archive: zipfile.ZipFile,
    budget: ArchiveBudget = DEFAULT_ARCHIVE_BUDGET,
) -> tuple[zipfile.ZipInfo, ...]:
    cached = getattr(archive, "_printops_archive_budget", None)
    if cached == budget:
        return tuple(archive.infolist())
    infos = tuple(archive.infolist())
    if len(infos) > budget.max_members:
        raise ArchiveBudgetError(f"archive has too many members ({len(infos)} > {budget.max_members})")
    seen: set[str] = set()
    total = 0
    for info in infos:
        normalised = _normalised_member_name(info.filename)
        if normalised in seen:
            raise ArchiveBudgetError(f"archive contains duplicate member {normalised!r}")
        seen.add(normalised)
        parts = [part for part in normalised.split("/") if part]
        if normalised.startswith("/") or ".." in parts:
            raise ArchiveBudgetError(f"archive contains unsafe member {normalised!r}")
        if info.file_size > budget.max_member_bytes:
            raise ArchiveBudgetError(f"archive member exceeds {budget.max_member_bytes} bytes")
        if normalised.startswith("Metadata/") and info.file_size > budget.max_metadata_bytes:
            raise ArchiveBudgetError(f"metadata member exceeds {budget.max_metadata_bytes} bytes")
        total += info.file_size
        if total > budget.max_total_uncompressed_bytes:
            raise ArchiveBudgetError("archive exceeds aggregate uncompressed-byte limit")
        ratio = info.file_size / max(info.compress_size, 1)
        if ratio > budget.max_compression_ratio:
            raise ArchiveBudgetError(
                f"archive member compression ratio {ratio:.1f} exceeds {budget.max_compression_ratio:.1f}"
            )
    archive._printops_archive_budget = budget
    return infos


def read_zip_member(
    archive: zipfile.ZipFile,
    member: str | zipfile.ZipInfo,
    *,
    budget: ArchiveBudget = DEFAULT_ARCHIVE_BUDGET,
    max_bytes: int | None = None,
) -> bytes:
    validate_zip_archive(archive, budget)
    info = member if isinstance(member, zipfile.ZipInfo) else archive.getinfo(member)
    limit = min(budget.max_member_bytes, max_bytes) if max_bytes is not None else budget.max_member_bytes
    chunks: list[bytes] = []
    total = 0
    with archive.open(info, "r") as source:
        while True:
            chunk = source.read(min(MIB, limit - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ArchiveBudgetError(f"archive member {info.filename!r} exceeds {limit} bytes")
            chunks.append(chunk)
    return b"".join(chunks)


def read_text_member(
    archive: zipfile.ZipFile,
    member: str | zipfile.ZipInfo,
    *,
    budget: ArchiveBudget = DEFAULT_ARCHIVE_BUDGET,
    max_bytes: int | None = None,
    errors: str = "strict",
) -> str:
    return read_zip_member(archive, member, budget=budget, max_bytes=max_bytes).decode("utf-8", errors=errors)


def _validate_json_shape(value: Any, budget: ArchiveBudget) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    items = 0
    while stack:
        current, depth = stack.pop()
        if depth > budget.max_json_depth:
            raise ArchiveBudgetError("JSON exceeds maximum nesting depth")
        if isinstance(current, dict):
            items += len(current)
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            items += len(current)
            stack.extend((item, depth + 1) for item in current)
        if items > budget.max_json_items:
            raise ArchiveBudgetError("JSON exceeds maximum collection size")


def read_json_member(
    archive: zipfile.ZipFile,
    member: str,
    *,
    budget: ArchiveBudget = DEFAULT_ARCHIVE_BUDGET,
) -> Any:
    value = json.loads(read_text_member(archive, member, budget=budget, max_bytes=budget.max_metadata_bytes))
    _validate_json_shape(value, budget)
    return value


def read_xml_member(
    archive: zipfile.ZipFile,
    member: str,
    *,
    budget: ArchiveBudget = DEFAULT_ARCHIVE_BUDGET,
):
    root = ET.fromstring(read_zip_member(archive, member, budget=budget, max_bytes=budget.max_metadata_bytes))
    stack = [(root, 1)]
    nodes = 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > budget.max_xml_nodes:
            raise ArchiveBudgetError("XML exceeds maximum node count")
        if depth > budget.max_xml_depth:
            raise ArchiveBudgetError("XML exceeds maximum nesting depth")
        stack.extend((child, depth + 1) for child in list(node))
    return root
