"""Git backup cloud-profile collection."""

import pytest

from backend.app.api.routes.cloud import CLOUD_TOKEN_KEY
from backend.app.core.auth import get_password_hash
from backend.app.models.settings import Settings
from backend.app.models.user import User
from backend.app.services.github_backup import GitHubBackupService


class FakeCloud:
    def __init__(self, label: str):
        self.label = label
        self.is_authenticated = True
        self.closed = False

    async def get_slicer_settings(self):
        return {
            "filament": {
                "private": [{"setting_id": f"fil-{self.label}", "name": f"Filament {self.label}", "updated_time": 123}],
                "public": [{"setting_id": "public-filament"}],
            },
            "printer": {"private": []},
            "print": {
                "private": [{"setting_id": f"proc-{self.label}", "name": f"Process {self.label}"}],
            },
        }

    async def get_setting_detail(self, setting_id: str):
        return {
            "name": f"Detail {setting_id}",
            "base_id": f"base-{setting_id}",
            "filament_id": "GFA00",
            "setting": {"id": setting_id},
        }

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_collects_bambu_cloud_profiles_from_global_and_user_accounts(db_session, monkeypatch):
    monkeypatch.setattr("backend.app.services.github_backup._BAMBU_DETAIL_THROTTLE_SECONDS", 0)
    db_session.add(Settings(key=CLOUD_TOKEN_KEY, value="tok-global"))
    user = User(
        username="cloud-user",
        password_hash=get_password_hash("AdminPass1!"),
        role="user",
        is_active=True,
        cloud_token="tok-user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    async def fake_build_authenticated_cloud(db, user=None):
        return FakeCloud("global" if user is None else f"user-{user.id}")

    monkeypatch.setattr("backend.app.api.routes.cloud.build_authenticated_cloud", fake_build_authenticated_cloud)

    files = {}
    summary = await GitHubBackupService()._collect_cloud_profiles(db_session, files)

    user_key = f"user-{user.id}"
    assert summary == {
        "bambu": {
            "global": {"filament": 1, "process": 1},
            user_key: {"filament": 1, "process": 1},
        }
    }
    assert files["cloud_profiles/bambu/global/filament.json"]["profiles"][0]["setting_id"] == "fil-global"
    assert files[f"cloud_profiles/bambu/{user_key}/process.json"]["profiles"][0]["base_id"] == f"base-proc-{user_key}"


@pytest.mark.asyncio
async def test_backup_data_marks_legacy_cloud_profile_paths_for_delete(db_session, monkeypatch):
    monkeypatch.setattr("backend.app.services.github_backup._BAMBU_DETAIL_THROTTLE_SECONDS", 0)
    db_session.add(Settings(key=CLOUD_TOKEN_KEY, value="tok-global"))
    await db_session.commit()

    async def fake_build_authenticated_cloud(db, user=None):
        return FakeCloud("global")

    monkeypatch.setattr("backend.app.api.routes.cloud.build_authenticated_cloud", fake_build_authenticated_cloud)

    config = type(
        "Config",
        (),
        {
            "backup_kprofiles": False,
            "backup_cloud_profiles": True,
            "backup_settings": False,
            "backup_spools": False,
            "backup_archives": False,
        },
    )()

    files = await GitHubBackupService()._collect_backup_data(db_session, config)

    assert files["cloud_profiles/filament.json"] is None
    assert files["cloud_profiles/printer.json"] is None
    assert files["cloud_profiles/process.json"] is None


@pytest.mark.asyncio
async def test_bambu_detail_fetch_retries_rate_limit_then_succeeds(monkeypatch):
    monkeypatch.setattr("backend.app.services.github_backup._BAMBU_DETAIL_THROTTLE_SECONDS", 0)

    class FlakyCloud:
        def __init__(self):
            self.calls = 0

        async def get_setting_detail(self, setting_id: str):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("HTTP 429 rate limit")
            return {"setting": {"id": setting_id}}

    cloud = FlakyCloud()

    detail = await GitHubBackupService()._fetch_bambu_setting_detail_with_retry(cloud, "preset-1", "global")

    assert detail == {"setting": {"id": "preset-1"}}
    assert cloud.calls == 2


@pytest.mark.asyncio
async def test_bambu_profile_backup_fails_instead_of_writing_partial_files(db_session, monkeypatch):
    monkeypatch.setattr("backend.app.services.github_backup._BAMBU_DETAIL_THROTTLE_SECONDS", 0)
    db_session.add(Settings(key=CLOUD_TOKEN_KEY, value="tok-global"))
    await db_session.commit()

    class FailingCloud(FakeCloud):
        async def get_setting_detail(self, setting_id: str):
            raise RuntimeError("HTTP 429 rate limit")

    async def fake_build_authenticated_cloud(db, user=None):
        return FailingCloud("global")

    monkeypatch.setattr("backend.app.api.routes.cloud.build_authenticated_cloud", fake_build_authenticated_cloud)

    files = {}
    with pytest.raises(RuntimeError, match="failed preset detail fetches"):
        await GitHubBackupService()._collect_cloud_profiles(db_session, files)

    assert "cloud_profiles/bambu/global/filament.json" not in files
