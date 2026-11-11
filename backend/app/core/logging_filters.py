"""Logging filters for the PrintOps log pipeline.

Masks credentials in log messages and tracebacks. ``WriteRequestsOnlyFilter`` keeps the file-side
uvicorn access log focused on state-changing HTTP methods, and
``CancelledPoolNoiseFilter`` drops SQLAlchemy connection-pool log noise
caused by Starlette's ``BaseHTTPMiddleware`` cancellation propagation
(see the filter's docstring for details). These live here so tests can
import them without pulling in ``backend.app.main``'s startup graph.
"""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import unquote

# Keep the scheme bounded for long FFmpeg stderr lines. Userinfo can also
# be a token on its own or contain unencoded question marks and hash signs.
URL_CREDENTIALS_PATTERN = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]{0,63}://)(?P<login>[^/\s]+)@")
_CAMERA_TEST_QUERY = re.compile(r"""(/camera/external/test/?)\?[^"'\s]+""")


def _masked_login(login: str) -> str:
    username, separator, _ = login.partition(":")
    return f"{username}:[REDACTED]" if separator else "[REDACTED]"


def redact_url_credentials(text: str | None) -> str | None:
    """Mask passwords and single-value logins in URLs embedded in log text."""
    if not text or "://" not in text or "@" not in text:
        return text
    return URL_CREDENTIALS_PATTERN.sub(lambda match: f"{match['scheme']}{_masked_login(match['login'])}@", text)


def redact_camera_url(url: str | None) -> str | None:
    """Mask the login of one stored camera URL, including legacy whitespace."""
    if not url:
        return url
    scheme, delimiter, remainder = url.partition("://")
    authority, slash, path = remainder.partition("/")
    if not delimiter or "@" not in authority:
        return url
    login, _, host = authority.rpartition("@")
    return f"{scheme}{delimiter}{_masked_login(login)}@{host}{slash}{path}"


def redact_camera_test_query(text: str) -> str:
    """Hide query parameters of the legacy external camera test endpoint."""
    return _CAMERA_TEST_QUERY.sub(r"\1?[REDACTED]", text)


_QUERY_PARAMETER = re.compile(r"[?&](?P<name>[A-Za-z0-9_.%~-]+)=")
_QUERY_VALUE = re.compile(r"""[^&"'\s]+""")
_QUERY_TOKEN_NAMES = frozenset({"token", "access_token", "access-token", "accesstoken", "api_key", "api-key", "apikey"})


def redact_query_tokens(text: str) -> str:
    """Mask query credentials, including percent-encoded parameter names."""
    if "=" not in text:
        return text
    parts = []
    consumed = 0
    for parameter in _QUERY_PARAMETER.finditer(text):
        if parameter.start() < consumed or unquote(parameter["name"]).casefold() not in _QUERY_TOKEN_NAMES:
            continue
        value = _QUERY_VALUE.match(text, parameter.end())
        if value:
            parts.extend((text[consumed : value.start()], "[REDACTED]"))
            consumed = value.end()
    if not parts:
        return text
    parts.append(text[consumed:])
    return "".join(parts)


_REFUSED_HEADER = re.compile(r"(Illegal header (?:value|name) )[^\r\n]*", re.IGNORECASE)


def redact_refused_headers(text: str | None) -> str | None:
    """Mask values and names quoted by HTTP libraries after rejecting a header."""
    return _REFUSED_HEADER.sub(r"\1[REDACTED]", text) if text else text


def redact_log_secrets(text: str) -> str:
    """Hide request query credentials and errors that quote rejected headers."""
    query_masked = redact_query_tokens(redact_camera_test_query(text))
    return redact_refused_headers(query_masked) or ""


class SensitiveLogRedactFilter(logging.Filter):
    """Scrub the rendered message and chained tracebacks before writing logs."""

    _formatter = logging.Formatter()

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) == 5:
            # AccessFormatter needs the original positional argument structure.
            record.args = tuple(redact_log_secrets(arg) if isinstance(arg, str) else arg for arg in record.args)
        else:
            try:
                message = record.getMessage()
            except (TypeError, ValueError):
                message = ""
            masked = redact_log_secrets(message)
            if masked != message:
                record.msg, record.args = masked, ()
        if record.exc_info and not record.exc_text:
            record.exc_text = self._formatter.formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact_log_secrets(record.exc_text)
        return True


class WriteRequestsOnlyFilter(logging.Filter):
    """Keep uvicorn access log records for state-changing HTTP methods only.

    Uvicorn's access logger emits one record per HTTP request, formatted as

        ``<client_addr> - "<METHOD> <path> HTTP/<ver>" <status>``

    On a typical PrintOps install the bulk of that traffic is GETs — the
    frontend status-polling loop, the camera stream, snapshots, websocket
    upgrades. None of those can change server state on their own, so for
    incident triage ("who hit ``/print/stop`` at 09:23?") they're noise that
    just rotates the log file faster.

    This filter accepts only POST / PUT / PATCH / DELETE — the verbs that
    actually mutate state — and drops everything else. Match anchors on the
    surrounding ``" `` and trailing space so an unrelated literal substring
    in a URL (e.g. ``GET /api/posts/POST``) cannot false-match.

    Attach to ``logging.getLogger("uvicorn.access")`` (and only there — the
    pattern is uvicorn's specific format string and would silently drop
    everything if applied to a generic logger).
    """

    _WRITE_VERB_TOKENS: tuple[str, ...] = (
        ' "POST ',
        ' "PUT ',
        ' "PATCH ',
        ' "DELETE ',
    )

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 — stdlib API name
        message = record.getMessage()
        return any(token in message for token in self._WRITE_VERB_TOKENS)


class ShutdownCancelledRequestFilter(logging.Filter):
    """Downgrade uvicorn's own graceful shutdown cancellation records."""

    _REASON = "timeout graceful shutdown exceeded"

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        error = record.exc_info[1] if record.exc_info else None
        if isinstance(error, asyncio.CancelledError) and str(error) == self._REASON:
            record.msg = "Request closed when the server shutdown grace period expired"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
        elif error is not None or not isinstance(record.msg, str) or not record.msg.endswith(self._REASON):
            return True
        record.levelno = logging.INFO
        record.levelname = "INFO"
        return True


class CancelledPoolNoiseFilter(logging.Filter):
    """Drop SQLAlchemy connection-pool log records driven by request cancellation.

    Starlette's ``BaseHTTPMiddleware`` (used under the hood by FastAPI's
    ``@app.middleware("http")`` decorator) cancels the inner task scope when a
    client disconnects mid-request. The cancellation propagates into
    SQLAlchemy's connection-pool cleanup and surfaces as two distinct ERROR
    records — both expected on disconnect, neither actionable for the user:

    1. ``Exception terminating connection ... CancelledError`` — fires every
       time ``do_terminate`` is interrupted by the same cancel scope that's
       unwinding the request. The ``CancelledError`` traceback always
       attributes the cancel to ``BaseHTTPMiddleware.call_next``.

    2. ``The garbage collector is trying to clean up non-checked-in
       connection`` — fires later when the GC reclaims the session that
       couldn't return its connection to the pool because of (1). It's
       symptomatic of the cancellation, not a separate bug.

    These pile up under heavy upload load (long multipart uploads where the
    client times out before the server's response). Real connection-pool
    issues — pool exhaustion, broken connections from network hiccups, etc.
    — surface through DIFFERENT messages and a non-cancellation
    ``exc_info`` chain, so they keep flowing through this filter unchanged.

    Attach to ``logging.getLogger("sqlalchemy.pool")`` (and only there).
    """

    _GC_CLEANUP_PREFIX = "The garbage collector is trying to clean up non-checked-in connection"
    _TERMINATE_PREFIX = "Exception terminating connection"

    @staticmethod
    def _has_cancelled_in_chain(exc: BaseException | None) -> bool:
        """True if `exc` is `CancelledError` or has one in its cause chain."""
        seen: set[int] = set()
        cur: BaseException | None = exc
        while cur is not None and id(cur) not in seen:
            seen.add(id(cur))
            if isinstance(cur, asyncio.CancelledError):
                return True
            cur = cur.__cause__ or cur.__context__
        return False

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 — stdlib API name
        message = record.getMessage()
        # GC-cleanup records have no exc_info — match by prefix only. Always
        # symptomatic of the cancellation cascade, never independently useful.
        if message.startswith(self._GC_CLEANUP_PREFIX):
            return False
        # Terminate-connection records carry a traceback; only drop those
        # that are cancellation-driven. A real terminate failure (broken
        # connection, network hiccup) keeps a non-CancelledError exc_info
        # chain and surfaces normally.
        if message.startswith(self._TERMINATE_PREFIX) and record.exc_info:
            exc = record.exc_info[1]
            if self._has_cancelled_in_chain(exc):
                return False
        return True
