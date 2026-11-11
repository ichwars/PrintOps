"""Credential handling for settings and slicer preset exports."""

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SECRET_PLACEHOLDER = "********"
URL_USERINFO_PATTERN = re.compile(r"""(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]{0,63}://)[^/\s?#"'<>]*@""")
_SLICER_SECRET_KEYS = frozenset({"printhost_apikey", "printhost_password", "printhost_user"})
_SECRET_SETTING_KEY_HINTS = ("token", "secret", "password", "access_code", "api_key", "passphrase", "verifier")


def is_secret_setting_key(key: str) -> bool:
    lowered = key.lower()
    return any(hint in lowered for hint in _SECRET_SETTING_KEY_HINTS)


def mask_slicer_preset(content: Any) -> Any:
    """Copy preset data with printer credentials and URL userinfo masked."""
    if isinstance(content, dict):
        masked = {}
        for key, value in content.items():
            if isinstance(key, str) and key.lower() in _SLICER_SECRET_KEYS:
                masked[key] = SECRET_PLACEHOLDER if value else value
            else:
                masked[key] = mask_slicer_preset(value)
        return masked
    if isinstance(content, list):
        return [mask_slicer_preset(value) for value in content]
    if isinstance(content, str):
        return URL_USERINFO_PATTERN.sub(r"\g<scheme>********@", content)
    return content


SETTINGS_SECRETS = {
    "mqtt_password": ("mqtt_broker", "mqtt_port", "mqtt_use_tls"),
    "ha_token": ("ha_url",),
    "obico_ml_token": ("obico_ml_url",),
    "prometheus_token": (),
    "virtual_printer_access_code": (),
    "ldap_bind_password": ("ldap_server_url", "ldap_security"),
}
SETTINGS_CREDENTIAL_FIELDS = frozenset(SETTINGS_SECRETS) | frozenset(
    field for destinations in SETTINGS_SECRETS.values() for field in destinations
)
SMTP_DESTINATIONS = ("smtp_host", "smtp_port", "smtp_security")
REST_PLUG_URLS = ("rest_on_url", "rest_off_url", "rest_status_url", "rest_power_url", "rest_energy_url")
SMART_PLUG_SECRETS = {
    "password": ("plug_type", "ip_address"),
    "rest_headers": ("plug_type", *REST_PLUG_URLS),
}

_NOTIFICATION_SECRETS = frozenset(
    {
        "apikey",
        "auth_token",
        "user_key",
        "app_token",
        "bot_token",
        "password",
        "webhook_url",
        "auth_header",
        "device_key",
    }
)
_NOTIFICATION_DESTINATIONS = {
    "email": ("smtp_server", "smtp_port", "security"),
    "ntfy": ("server",),
    "bark": ("server",),
    "webhook": ("webhook_url",),
}
_NOTIFICATION_DEFAULTS = {
    ("email", "smtp_port"): 587,
    ("email", "security"): "starttls",
    ("ntfy", "server"): "https://ntfy.sh",
    ("bark", "server"): "https://api.day.app",
}


class SecretConfigError(ValueError):
    """The requested edit cannot reuse a saved credential."""


def secret_is_set(value: Any) -> bool:
    return bool(value and value != SECRET_PLACEHOLDER)


def same_value(first: Any, second: Any) -> bool:
    """Compare form values with typed settings and absent optional fields."""
    return ("" if first is None else str(first)) == ("" if second is None else str(second))


def reject_placeholder(values: dict[str, Any]) -> None:
    if SECRET_PLACEHOLDER in values.values():
        raise SecretConfigError("Enter the secret values for this new configuration")


async def lock_settings_credentials(db: AsyncSession) -> None:
    """Serialize destination and credential edits, including missing setting rows."""
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('printops.settings_credentials'))"))
    else:
        await db.execute(text("UPDATE settings SET value = value WHERE 0"))


def merge_secret_update(
    stored: dict[str, Any], update: dict[str, Any], secrets: dict[str, tuple[str, ...]]
) -> dict[str, Any]:
    """Validate a partial update and omit placeholders to keep saved values."""
    result = dict(update)
    for secret, destinations in secrets.items():
        if secret in result:
            if result[secret] != SECRET_PLACEHOLDER:
                continue
            if not secret_is_set(stored.get(secret)):
                raise SecretConfigError(f"Enter {secret} because there is no saved value")
            del result[secret]
        if not secret_is_set(stored.get(secret)):
            continue
        changed = [
            field for field in destinations if field in update and not same_value(update[field], stored.get(field))
        ]
        if changed:
            raise SecretConfigError(f"Enter {secret} again because {', '.join(changed)} changed")
    return result


def _notification_secret(key: str, value: Any) -> bool:
    return (
        key.lower() in _NOTIFICATION_SECRETS
        or is_secret_setting_key(key)
        or isinstance(value, str)
        and URL_USERINFO_PATTERN.search(value) is not None
    )


def mask_notification_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        key: SECRET_PLACEHOLDER if value and _notification_secret(key, value) else value
        for key, value in config.items()
    }


def merge_notification_config(
    previous_type: str, stored: dict[str, Any], new_type: str, incoming: dict[str, Any]
) -> dict[str, Any]:
    """Resolve retained fields only within the provider type and destination that own them."""
    result = dict(incoming)
    kept = [key for key, value in incoming.items() if value == SECRET_PLACEHOLDER]
    if not kept:
        return result
    if previous_type != new_type:
        raise SecretConfigError("Enter the secret values again for the new provider type")
    for key in kept:
        value = stored.get(key)
        if not _notification_secret(key, value) or not secret_is_set(value):
            raise SecretConfigError("Enter the secret values because there is no matching saved value")
        result[key] = value
    for field in _NOTIFICATION_DESTINATIONS.get(previous_type, ()):
        fallback = _NOTIFICATION_DEFAULTS.get((previous_type, field))
        if not same_value(result.get(field, fallback), stored.get(field, fallback)):
            raise SecretConfigError("Enter the secret values again because the destination changed")
    return result
