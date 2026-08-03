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
                "private": [
                    {"setting_id": f"fil-{self.label}", "name": f"Filament {self.label}", "updated_time": 123}
                ],
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
