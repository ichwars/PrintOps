import json

import pytest

from backend.app.models.github_backup import GitHubBackupConfig
from backend.app.models.settings import Settings
from backend.app.services.github_backup import GitHubBackupService
from backend.app.services.github_restore import SETTINGS_PATH
from backend.app.services.github_restore_settings import plan_git_settings
from backend.app.services.secret_fields import SECRET_PLACEHOLDER


@pytest.mark.asyncio
async def test_settings_backup_exports_editable_values_and_only_credential_presence(db_session):
    values = {
        "currency": "EUR",
        "smtp_host": "mail.example.test",
        "forecast_global_lead_time_days": "14",
        "mqtt_enabled": "true",
        "mqtt_password": "fixture-mqtt-password",
        "smtp_password": "fixture-smtp-password",
        "prometheus_token": "",
        "virtual_printer_tailscale_auth_key": "fixture-retired-key",
        "vapid_private_key": "fixture-retired-secret",
        "dark_theme": "true",
        "debug_logging_enabled": "true",
        "user_8_email_2fa_enabled": "true",
        "_backfill_446_clear_plate_permission_done": "true",
        "ldap_enabled": "true",
        "ldap_bind_password": "fixture-ldap-password",
        "calculation_defaults": '{"legacy": 19}',
        "auth_secret_key": "fixture-signing-secret",
        "bambu_cloud_token": "fixture-cloud-token",
        "ha_url": "https://fixture-user:fixture-pass@ha.example.test",
        "spoolman_url": "http://fixture-user@spools.example.test",
        "orcaslicer_api_url": "https://:fixture-empty-user@slicer.example.test",
    }
    db_session.add_all(Settings(key=key, value=value) for key, value in values.items())
    await db_session.flush()
    config = GitHubBackupConfig(
        backup_settings=True,
        backup_kprofiles=False,
        backup_cloud_profiles=False,
        backup_archives=False,
        backup_spools=False,
    )

    files = await GitHubBackupService()._collect_backup_data(db_session, config)
    assert "fixture-" not in json.dumps(files[SETTINGS_PATH])
    exported = files[SETTINGS_PATH]["settings"]
    assert exported == {
        "currency": "EUR",
        "smtp_host": "mail.example.test",
        "forecast_global_lead_time_days": "14",
        "mqtt_enabled": "true",
        "mqtt_password": SECRET_PLACEHOLDER,
        "smtp_password": SECRET_PLACEHOLDER,
        "prometheus_token": "",
    }
    assert files["backup_metadata.json"]["contents"]["commercial_documents"] is True

    await db_session.rollback()
    plan = await plan_git_settings(db_session, exported)
    assert set(plan.blocked) == {"mqtt_password", "smtp_password", "prometheus_token"}
    assert plan.companion == ("mqtt_enabled",)
