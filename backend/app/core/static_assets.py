"""Cache and compress public assets emitted by the frontend build."""

from __future__ import annotations

import gzip
import os
import re
from collections import OrderedDict
from collections.abc import Iterable

import anyio
from starlette.datastructures import Headers
from starlette.responses import FileResponse, Response
from starlette.staticfiles import NotModifiedResponse, StaticFiles
from starlette.types import Scope

_HASHED_ASSET = re.compile(r"^[^/\\]+-[A-Za-z0-9_-]{8}\.[A-Za-z0-9]+$")
_COMPRESSIBLE = (".js", ".mjs", ".css", ".json", ".svg", ".map", ".wasm", ".txt")
_MAX_INPUT_BYTES = 16 * 1024 * 1024
_MIN_INPUT_BYTES = 1024
_CACHE_BYTES = 32 * 1024 * 1024


def _accepts_gzip(encoding: str | None) -> bool:
    quality: dict[str, float] = {}
    for entry in (encoding or "").lower().split(","):
        coding, *parameters = entry.split(";")
        q = 1.0
        for parameter in parameters:
            key, _, value = parameter.partition("=")
            if key.strip() == "q":
                try:
                    q = float(value)
                except ValueError:
                    q = 0.0
        quality[coding.strip()] = q
    return 0 < quality.get("gzip", quality.get("*", 0)) <= 1


def _compress(path: str) -> bytes | None:
    try:
        with open(path, "rb") as source:
            content = source.read(_MAX_INPUT_BYTES + 1)
    except OSError:
        return None
    if len(content) > _MAX_INPUT_BYTES:
        return None
    return gzip.compress(content, compresslevel=6, mtime=0)


class _CompressedAssets:
    def __init__(self) -> None:
        self.cache: OrderedDict[tuple[str, int, int, int], bytes] = OrderedDict()
        self.size = 0
        self.workers = anyio.CapacityLimiter(2)

    async def read(self, path: str, stat: os.stat_result) -> bytes | None:
        key = (path, stat.st_size, stat.st_mtime_ns, stat.st_ino)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        body = await anyio.to_thread.run_sync(_compress, path, limiter=self.workers)
        if body is None:
            return None
        if key in self.cache:
            self.size -= len(self.cache.pop(key))
        self.cache[key] = body
        self.size += len(body)
        while self.size > _CACHE_BYTES:
            _, removed = self.cache.popitem(last=False)
            self.size -= len(removed)
        return body


def _without_validators(headers: Iterable[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    return [(name, value) for name, value in headers if name not in (b"if-none-match", b"if-modified-since")]


class AssetStaticFiles(StaticFiles):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.compressed = _CompressedAssets()

    async def get_response(self, path: str, scope: Scope) -> Response:
        # Apply validators after selecting the representation. Starlette's
        # default lookup would decide based on the uncompressed ETag.
        request = Headers(scope=scope)
        response = await super().get_response(path, {**scope, "headers": _without_validators(request.raw)})
        if not isinstance(response, FileResponse) or response.status_code != 200:
            return response

        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable" if _HASHED_ASSET.fullmatch(path) else "no-cache"
        )
        stat = response.stat_result
        compressible = (
            stat is not None
            and _MIN_INPUT_BYTES <= stat.st_size <= _MAX_INPUT_BYTES
            and path.lower().endswith(_COMPRESSIBLE)
        )
        if compressible:
            response.headers.add_vary_header("Accept-Encoding")
            if "range" not in request and _accepts_gzip(request.get("accept-encoding")):
                return await self._gzip_response(response, request, scope["method"])

        if request.get("if-none-match") == "*" or self.is_not_modified(response.headers, request):
            return NotModifiedResponse(response.headers)
        return response

    async def _gzip_response(self, response: FileResponse, request: Headers, method: str) -> Response:
        headers = dict(response.headers)
        headers["etag"] = headers["etag"].removesuffix('"') + '-gzip"'
        gzip_headers = Headers(headers)
        if request.get("if-none-match") == "*" or self.is_not_modified(gzip_headers, request):
            return NotModifiedResponse(gzip_headers)
        body = await self.compressed.read(str(response.path), response.stat_result)
        if body is None:
            return response
        headers["content-encoding"] = "gzip"
        headers["content-length"] = str(len(body))
        headers.pop("accept-ranges", None)
        return Response(content=b"" if method == "HEAD" else body, headers=headers)
