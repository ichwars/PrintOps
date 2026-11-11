import pytest
from sqlalchemy import select

from backend.app.models.settings import Settings
from backend.app.schemas.github_backup import RestoreCategory
from backend.app.services.github_restore import SETTINGS_PATH, GitHubRestoreService, _CategoryTally
from backend.app.services.github_restore_settings import _SettingsPlan, plan_git_settings


@pytest.mark.asyncio
async def test_git_settings_restore_validates_values_and_keeps_local_destinations(db_session):
    existing = {
        "external_url": "https://printops.example.test",
        "ha_url": "http://homeassistant.example.test",
        "mqtt_port": "1883",
        "smtp_host": "mail.example.test",
        "user_10_email_2fa_enabled": "true",
        "virtual_printer_target_printer_id": "999999",
        "virtual_printer_enabled": "true",
    }
    db_session.add_all(Settings(key=key, value=value) for key, value in existing.items())
    await db_session.commit()
    incoming = {
        "currency": "EUR",
        "default_printer_id": "None",
        "auto_archive": "YES",
        "forecast_global_lead_time_days": "-1",
        "queue_max_concurrent_uploads": "99",
        "gcode_snippets": "[]",
        "external_url": "https://elsewhere.example.test",
        "ha_url": "http://169.254.169.254",
        "mqtt_port": "1883.0",
        "smtp_host": "elsewhere.example.test",
        "smtp_auth_enabled": "false",
        "spoolman_url": "http://spools.example.test",
        "virtual_printer_target_printer_id": "1",
        "user_10_email_2fa_enabled": "false",
        "_future_runtime_marker": "true",
        "retired_flag": "true",
    }
    service = GitHubRestoreService()
    payload = {"settings": incoming}
    expected_count, detail = await service._count_items(db_session, RestoreCategory.SETTINGS, {SETTINGS_PATH: payload})
    tally = _CategoryTally()
    written: set[str] = set()
    await service._restore_settings(db_session, payload, overwrite=True, tally=tally, keys_written=written)
    await db_session.commit()

    assert detail is not None and detail.code == "settingsNotRestorableWillSkip"
    assert detail.params == {"count": 9}
    assert expected_count == tally.restored + tally.skipped + tally.failed == 5
    assert tally.skipped == 1
    assert written == {"currency", "default_printer_id", "auto_archive", "smtp_auth_enabled"}
    notes = {note["code"]: note["params"] for note in tally.notes}
    assert notes["settingsInvalidSkipped"] == {"count": 4}
    assert notes["settingsUnknownSkipped"] == {"count": 2}
    assert notes["settingsAddressKept"] == {"keys": "external_url, smtp_host, spoolman_url"}
    assert notes["settingsAuthSkipped"] == {"count": 1}
    rows = dict((await db_session.execute(select(Settings.key, Settings.value))).all())
    assert rows == {
        **existing,
        "currency": "EUR",
        "default_printer_id": "None",
        "auto_archive": "true",
        "smtp_auth_enabled": "false",
    }


@pytest.mark.asyncio
async def test_alternate_true_value_cannot_open_metrics_during_git_restore(db_session):
    payload = {"settings": {"prometheus_enabled": "yes", "currency": "EUR"}}
    tally = _CategoryTally()
    service = GitHubRestoreService()
    await service._restore_settings(db_session, payload, overwrite=True, tally=tally)
    await db_session.flush()

    assert await db_session.scalar(select(Settings.value).where(Settings.key == "prometheus_enabled")) is None
    assert await db_session.scalar(select(Settings.value).where(Settings.key == "currency")) == "EUR"
    assert {note["code"] for note in tally.notes} == {"settingsCompanionSkipped"}


@pytest.mark.asyncio
async def test_plan_leaves_unusable_key_names_for_the_failure_tally(db_session):
    plan = await plan_git_settings(db_session, {"": "x", 7: "y", "currency": "EUR"})
    assert plan == _SettingsPlan(stored={"currency": "EUR"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "credential"),
    [
        ("mqtt_broker", "mqtt_password"),
        ("smtp_host", "smtp_password"),
        ("ha_url", "ha_token"),
        ("obico_ml_url", "obico_ml_token"),
    ],
)
async def test_old_git_backups_cannot_retarget_stored_credentials(db_session, key, credential):
    current_url = "http://local.example.test"
    db_session.add_all([Settings(key=key, value=current_url), Settings(key=credential, value="fixture-local")])
    await db_session.commit()

    tally = _CategoryTally()
    await GitHubRestoreService()._restore_settings(
        db_session,
        {"settings": {key: "http://foreign.example.test", credential: "fixture-old-backup"}},
        overwrite=True,
        tally=tally,
    )
    await db_session.commit()
    stored = dict((await db_session.execute(select(Settings.key, Settings.value))).all())
    assert stored == {key: current_url, credential: "fixture-local"}
    assert tally.restored == 0
    assert {note["code"] for note in tally.notes} == {"settingsAddressKept", "settingsCredentialsSkipped"}
