"""Small, deliberately read-only Lexware Office transport.

The origin, methods and resource paths cannot be changed by a saved connection.
See https://developers.lexware.io/docs/ for the resource contracts.
"""

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from uuid import UUID

import httpx

API_ORIGIN = "https://api.lexware.io"
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PAGES = 1000
_rate_lock = asyncio.Lock()
_next_request_at = 0.0
_COLLECTIONS = {"contacts", "articles", "voucherlist", "profile", "payment-conditions"}
_RESOURCES = {
    "contacts",
    "articles",
    "vouchers",
    "invoices",
    "credit-notes",
    "quotations",
    "order-confirmations",
    "delivery-notes",
    "down-payment-invoices",
    "payments",
    "files",
}


class LexwareError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, *, code: str = "lexware_error"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def validate_path(path: str) -> None:
    parts = path.split("/")
    if len(parts) < 3 or parts[:2] != ["", "v1"]:
        raise LexwareError("Lexware resource path is not permitted")
    if len(parts) == 3 and parts[2] in _COLLECTIONS:
        return
    if len(parts) not in {4, 5} or parts[2] not in _RESOURCES:
        raise LexwareError("Lexware resource path is not permitted")
    try:
        if str(UUID(parts[3])) != parts[3].lower():
            raise ValueError
    except ValueError:
        raise LexwareError("Lexware resource identifier is invalid") from None
    if len(parts) == 5 and (
        parts[4] != "file"
        or parts[2]
        not in {
            "invoices",
            "credit-notes",
            "quotations",
            "order-confirmations",
            "delivery-notes",
            "down-payment-invoices",
        }
    ):
        raise LexwareError("Lexware resource path is not permitted")


async def _throttle() -> None:
    global _next_request_at
    async with _rate_lock:
        delay = _next_request_at - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        _next_request_at = time.monotonic() + 0.6


class LexwareClient:
    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        before_request: Callable[[], Awaitable[None]] | None = None,
    ):
        if not api_key or len(api_key) > 4096 or any(c.isspace() for c in api_key):
            raise LexwareError("Invalid Lexware API key")
        self._client = httpx.AsyncClient(
            base_url=API_ORIGIN,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(30.0),
            follow_redirects=False,
            transport=transport,
        )
        self._before_request = before_request

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    async def _get(self, path: str, params: dict | None, *, binary: bool) -> tuple[bytes, httpx.Headers]:
        validate_path(path)
        cap = MAX_FILE_BYTES if binary else MAX_JSON_BYTES
        for attempt in range(3):
            await _throttle()
            if self._before_request:
                await self._before_request()
            try:
                async with self._client.stream(
                    "GET", path, params=params, headers={"Accept": "*/*" if binary else "application/json"}
                ) as response:
                    if response.status_code in {429, 502, 503, 504} and attempt < 2:
                        retry = response.headers.get("Retry-After", "")
                        delay = min(float(retry), 30) if retry.isdigit() else 2**attempt
                        await asyncio.sleep(max(0, delay))
                        continue
                    if response.status_code != 200:
                        raise LexwareError(
                            f"Lexware request failed (HTTP {response.status_code})", response.status_code
                        )
                    length = response.headers.get("Content-Length", "")
                    if length.isdigit() and int(length) > cap:
                        raise LexwareError("Lexware response exceeds the size limit")
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(chunks) + len(chunk) > cap:
                            raise LexwareError("Lexware response exceeds the size limit")
                        chunks.extend(chunk)
                    return bytes(chunks), response.headers
            except httpx.HTTPError:
                if attempt == 2:
                    raise LexwareError("Lexware is not reachable; previous data is unchanged") from None
                await asyncio.sleep(2**attempt)
        raise LexwareError("Lexware request did not complete")

    async def get_json(self, path: str, params: dict | None = None) -> dict | list:
        content, _ = await self._get(path, params, binary=False)
        try:
            # Preserve the upstream decimal representation in JSON-safe snapshots.
            value = json.loads(content, parse_float=str)
        except (ValueError, UnicodeError):
            raise LexwareError("Lexware returned invalid JSON") from None
        if not isinstance(value, dict | list):
            raise LexwareError("Lexware returned an invalid resource")
        return value

    async def get_file(self, path: str) -> tuple[bytes, str, str]:
        content, headers = await self._get(path, None, binary=True)
        media_type = headers.get("Content-Type", "").split(";")[0].strip().lower()
        suffixes = {
            "application/pdf": "pdf",
            "application/xml": "xml",
            "text/xml": "xml",
            "image/png": "png",
            "image/jpeg": "jpg",
        }
        if media_type not in suffixes or not content:
            raise LexwareError("Unsupported or empty Lexware document")
        # Never trust upstream filenames or Content-Disposition paths.
        identifier = next((part for part in path.split("/") if re.fullmatch(r"[0-9a-fA-F-]{36}", part)), "document")
        return content, media_type, f"lexware-{identifier}.{suffixes[media_type]}"

    async def list_pages(self, path: str, params: dict | None = None) -> list[dict]:
        rows: list[dict] = []
        seen: set[str] = set()
        for page in range(MAX_PAGES):
            data = await self.get_json(path, {**(params or {}), "page": page, "size": 100})
            if not isinstance(data, dict) or not isinstance(data.get("content"), list):
                raise LexwareError("Lexware returned an invalid page")
            content = data["content"]
            for row in content:
                if not isinstance(row, dict) or not row.get("id"):
                    raise LexwareError("Lexware returned an invalid page entry")
                key = str(row["id"])
                if key in seen:
                    raise LexwareError("Lexware listing changed during paging; retry the complete sync")
                seen.add(key)
                rows.append(row)
            if data.get("last") is True:
                return rows
            if data.get("last") is None:
                raise LexwareError("Lexware page is missing completion information")
            if not content:
                raise LexwareError("Lexware returned an incomplete listing")
        raise LexwareError("Lexware listing exceeds the page limit; no partial import was published")
