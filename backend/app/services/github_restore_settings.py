"""Validate Git settings backups using the editors' accepted values."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes._url_safety import assert_safe_lan_service_url
from backend.app.core.group_permission_backfills import GROUP_PERMISSION_BACKFILL_KEYS
from backend.app.core.printer_associations import VIRTUAL_PRINTER_MIGRATION_KEY
from backend.app.core.user_printer_scope import USER_PRINTER_SCOPE_MIGRATION_KEY
from backend.app.models.settings import Settings
from backend.app.schemas.auth import SMTPSettings
from backend.app.schemas.settings import (
    ADMIN_ONLY_SETTING_KEYS,
    LAN_SERVICE_URL_SETTINGS,
    AppSettings,
    AppSettingsUpdate,
)
from backend.app.services.secret_fields import is_secret_setting_key

_PROTECTED_SETTING_KEYS = {
    *GROUP_PERMISSION_BACKFILL_KEYS,
    USER_PRINTER_SCOPE_MIGRATION_KEY,
    VIRTUAL_PRINTER_MIGRATION_KEY,
    "auth_enabled",
    "advanced_auth_enabled",
    "calculation_defaults",
    "local_login_enabled",
    "setup_completed",
}
_PROTECTED_SETTING_PREFIXES = ("ldap_", "orders.", "documents.", "calculations.")
_EMAIL_2FA_KEY = re.compile(r"user_[0-9]+_email_2fa_enabled", re.IGNORECASE)

_COMPANION_CREDENTIALS = {
    "prometheus_enabled": "prometheus_token",
    "mqtt_enabled": "mqtt_password",
    "ha_enabled": "ha_token",
    "virtual_printer_enabled": "virtual_printer_access_code",
}
_COMPANION_CREDENTIAL_ENV = {"ha_token": "HA_TOKEN"}
_COMPANION_EXPOSURE_TOGGLES = frozenset({"prometheus_enabled"})

_DESTINATION_KEYS = frozenset(
    {
        *LAN_SERVICE_URL_SETTINGS,
        "external_url",
        "local_backup_path",
        "mqtt_broker",
        "mqtt_port",
        "mqtt_use_tls",
        "smtp_host",
        "smtp_port",
        "smtp_security",
        "smtp_use_tls",
        "spoolman_url",
    }
)
_STORED_NULL_KEYS = frozenset({"default_printer_id", "open_in_slicer"})
_SMTP_FIELD_TYPES = {
    key: TypeAdapter(smtp_field.rebuild_annotation()) for key, smtp_field in SMTPSettings.model_fields.items()
}
_DEFAULT_SETTINGS = AppSettings()


def _is_protected_setting_key(key: str) -> bool:
    return (
        key in _PROTECTED_SETTING_KEYS
        or key.lower().startswith(_PROTECTED_SETTING_PREFIXES)
        or _EMAIL_2FA_KEY.fullmatch(key) is not None
    )


def is_git_backup_setting_key(key: str) -> bool:
    """Whether an editable setting is eligible for the Git settings export."""
    return not _is_protected_setting_key(key) and (key in AppSettingsUpdate.model_fields or key in _SMTP_FIELD_TYPES)


def _setting_value_is_true(value: object) -> bool:
    return value is True or isinstance(value, str) and value.strip().lower() == "true"


def _is_usable_credential(value: object) -> bool:
    return value is not None and bool(str(value).strip())


def _setting_text(value: object) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


def _checked_setting_value(key: str, value: object) -> str:
    if key in _SMTP_FIELD_TYPES:
        return _setting_text(_SMTP_FIELD_TYPES[key].validate_python(value))
    candidate = None if value == "None" and key in _STORED_NULL_KEYS else value
    validated = getattr(AppSettingsUpdate.model_validate({key: candidate}), key)
    if key == "spoolman_url" and validated:
        assert_safe_lan_service_url(validated, label="Spoolman URL")
    return _setting_text(validated)


@dataclass(frozen=True)
class _SettingsPlan:
    """Classifications and normalized writes shared by preview and restore."""

    blocked: tuple[str, ...] = ()
    protected: tuple[str, ...] = ()
    companion: tuple[str, ...] = ()
    internal: tuple[str, ...] = ()
    invalid: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()
    address: tuple[str, ...] = ()
    stored: dict[str, str] = field(default_factory=dict)

    @property
    def refused(self) -> frozenset[str]:
        return frozenset(
            self.blocked + self.protected + self.companion + self.internal + self.invalid + self.unknown + self.address
        )

    @property
    def refused_count(self) -> int:
        return len(self.refused)


async def plan_git_settings(db: AsyncSession, values: dict, *, as_admin: bool = True) -> _SettingsPlan:
    blocked: list[str] = []
    protected: list[str] = []
    internal: list[str] = []
    invalid: list[str] = []
    unknown: list[str] = []
    stored: dict[str, str] = {}
    for key, value in values.items():
        if not isinstance(key, str) or not key:
            continue
        if is_secret_setting_key(key):
            blocked.append(key)
        elif _is_protected_setting_key(key) or (
            not as_admin and (key in ADMIN_ONLY_SETTING_KEYS or key.lower().startswith("smtp_"))
        ):
            protected.append(key)
        elif key == "library_archive_mode":
            continue
        elif key.startswith("_"):
            internal.append(key)
        elif not is_git_backup_setting_key(key):
            unknown.append(key)
        elif value is not None:
            try:
                stored[key] = _checked_setting_value(key, value)
            except (TypeError, ValueError):
                invalid.append(key)

    candidates = {
        key: credential
        for key, credential in _COMPANION_CREDENTIALS.items()
        if _setting_value_is_true(stored.get(key))
        and is_secret_setting_key(credential)
        and (key in _COMPANION_EXPOSURE_TOGGLES or _is_usable_credential(values.get(credential)))
    }
    addresses = stored.keys() & _DESTINATION_KEYS
    wanted = candidates.keys() | set(candidates.values()) | addresses
    local = {}
    if wanted:
        rows = await db.execute(select(Settings.key, Settings.value).where(Settings.key.in_(wanted)))
        local = dict(rows.all())

    companion = tuple(
        toggle
        for toggle, credential in candidates.items()
        if not _is_usable_credential(local.get(credential))
        and not _is_usable_credential(os.environ.get(_COMPANION_CREDENTIAL_ENV.get(credential, "")))
        and not _setting_value_is_true(local.get(toggle))
    )
    # Keep even matching destinations out of the write set so a concurrent
    # settings edit cannot be overwritten with the value seen during planning.
    address_changes = []
    for key in sorted(addresses):
        restored = stored.pop(key)
        current = local.get(key, getattr(_DEFAULT_SETTINGS, key, None))
        if restored != _setting_text(current):
            address_changes.append(key)
    return _SettingsPlan(
        blocked=tuple(blocked),
        protected=tuple(protected),
        companion=companion,
        internal=tuple(internal),
        invalid=tuple(invalid),
        unknown=tuple(unknown),
        address=tuple(address_changes),
        stored=stored,
    )
