"""Regression tests for credential-safe URL logging."""

from backend.app.utils.safe_logging import url_for_log


def test_url_for_log_removes_all_credential_bearing_components():
    raw = "https://user:password@example.test:8443/vendor/hook/opaque-token?api_key=secret#fragment"

    result = url_for_log(raw)

    assert result == "https://[HOST]:8443/[REDACTED]"
    for secret in ("user", "password", "example.test", "opaque-token", "api_key", "secret", "fragment"):
        assert secret not in result


def test_url_for_log_fails_closed_for_malformed_or_relative_values():
    assert url_for_log("not-a-url?token=secret") == "[INVALID_URL]"
    assert url_for_log("https://host.test:invalid/token") == "[INVALID_URL]"
