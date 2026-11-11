import logging
import sys

from uvicorn.logging import AccessFormatter

from backend.app.core.logging_filters import SensitiveLogRedactFilter, redact_query_tokens
from backend.app.services import log_reader


def test_query_token_names_and_encoding_preserve_other_parameters():
    path = "/media?plate=2&%74oken=a%26b&Access_Token=c&api-key=d&empty=&api_key=&next=/ws?token=e"
    expected = (
        "/media?plate=2&%74oken=[REDACTED]&Access_Token=[REDACTED]"
        "&api-key=[REDACTED]&empty=&api_key=&next=/ws?token=[REDACTED]"
    )
    assert redact_query_tokens(path) == expected
    assert redact_query_tokens(expected) == expected


def test_uvicorn_access_token_is_masked_without_losing_access_arguments():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1234", "GET", "/media?token=fixture-media-token&plate=2", "1.1", 200),
        None,
    )
    assert SensitiveLogRedactFilter().filter(record)
    formatted = AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s').format(record)
    assert formatted == '127.0.0.1:1234 - "GET /media?token=[REDACTED]&plate=2 HTTP/1.1" 200 OK'


def test_websocket_acceptance_and_tracebacks_mask_query_tokens():
    try:
        raise RuntimeError("/ws?api_key=fixture-error-key")
    except RuntimeError:
        record = logging.LogRecord(
            "uvicorn.error",
            logging.INFO,
            "",
            0,
            '%s - "WebSocket %s" [accepted]',
            ("127.0.0.1:1234", "/ws?access_token=fixture-websocket-token"),
            sys.exc_info(),
        )
    assert SensitiveLogRedactFilter().filter(record)
    formatted = logging.Formatter().format(record)
    assert '"WebSocket /ws?access_token=[REDACTED]" [accepted]' in formatted
    assert "RuntimeError: /ws?api_key=[REDACTED]" in formatted
    assert "fixture-" not in formatted


def test_historical_query_token_is_masked_before_search_and_support_export(monkeypatch, tmp_path):
    monkeypatch.setattr(log_reader.settings, "log_dir", tmp_path)
    old = '2026-11-11 09:33:00,000 INFO [uvicorn.error] "WebSocket /ws?%74oken=fixture-saved-token&view=wall" [accepted]\n'
    (tmp_path / "printops.log").write_text(old)

    entries, total = log_reader.read_log_entries(search="view=wall")
    assert total == len(entries) == 1
    assert '/ws?%74oken=[REDACTED]&view=wall" [accepted]' in entries[0].message
    assert not log_reader.read_log_entries(search="fixture-saved-token")[0]
    assert "fixture-saved-token" not in log_reader.sanitize_log_content(old)
