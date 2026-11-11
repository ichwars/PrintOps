"""Archive suggestions, aggregates, and bulk actions cannot cross printer scopes."""

import pytest

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.models.api_key import APIKey
from backend.app.models.group import Group
from backend.app.models.user import User
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def scoped_archives(async_client, db_session, printer_factory):
    admin = {"Authorization": f"Bearer {await _setup_admin(async_client)}"}
    visible, hidden = await printer_factory(), await printer_factory()
    member = User(
        username="scoped_archive_bulk",
        allowed_printer_ids=[visible.id],
        groups=[Group(name="Scoped archive actions", permissions=["archives:read_own", "archives:update_all"])],
    )
    secret, key_hash, prefix = generate_api_key()
    key = APIKey(
        name="Scoped archive actions",
        key_hash=key_hash,
        key_prefix=prefix,
        can_manage_archives=True,
        printer_ids=[visible.id],
    )
    db_session.add_all([member, key])
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': member.username})}"}
    return visible, hidden, member, headers, {"X-API-Key": secret}, admin


async def test_duplicates_similar_tags_and_warning_share_the_read_scope(async_client, archive_factory, scoped_archives):
    visible, hidden, member, headers, key, admin = scoped_archives
    mine = await archive_factory(visible.id, created_by_id=member.id, content_hash="same", tags="Mine")
    peer = await archive_factory(visible.id, content_hash="same", tags="Peer")
    outside = await archive_factory(
        hidden.id, created_by_id=member.id, content_hash="same", tags="Outside", extra_data={"no_3mf_available": True}
    )
    base = "/api/v1/archives"
    for credentials, peers, tags in (
        (headers, set(), {"Mine"}),
        (key, {peer.id}, {"Mine", "Peer"}),
        (admin, {peer.id, outside.id}, {"Mine", "Peer", "Outside"}),
    ):
        response = await async_client.get(base + "/", headers=credentials)
        assert response.status_code == 200
        listing = {row["id"]: row for row in response.json()}
        assert set(listing) == {mine.id, *peers}
        assert listing[mine.id]["duplicate_count"] == len(peers)
        details = await async_client.get(f"{base}/{mine.id}", headers=credentials)
        assert {row["id"] for row in details.json()["duplicates"]} == peers
        duplicates = await async_client.get(f"{base}/{mine.id}/duplicates", headers=credentials)
        assert {row["id"] for row in duplicates.json()["duplicates"]} == peers
        similar = await async_client.get(f"{base}/{mine.id}/similar", headers=credentials)
        assert {row["archive"]["id"] for row in similar.json()} == peers
        response = await async_client.get(f"{base}/tags", headers=credentials)
        assert {row["name"] for row in response.json()} == tags
        response = await async_client.get(f"{base}/no-3mf-warning", headers=credentials)
        assert response.json()["has_fallback"] is (credentials == admin)


async def test_bulk_writes_and_upload_matching_ignore_hidden_archives(
    async_client, db_session, archive_factory, scoped_archives
):
    visible, hidden, member, headers, key, _ = scoped_archives
    mine = await archive_factory(visible.id, created_by_id=member.id, tags="shared", cost=2.5, filament_used_grams=170)
    outside = await archive_factory(hidden.id, print_name="Unique other", tags="shared", cost=8.0)

    base = "/api/v1/archives"
    for operation in ("rescan-all", "backfill-hashes"):
        response = await async_client.post(f"{base}/{operation}", headers=key)
        assert response.status_code == 200
        assert [row["id"] for row in response.json()["errors"]] == [mine.id]

    response = await async_client.put(f"{base}/tags/shared", headers=headers, json={"new_name": "renamed"})
    assert response.json()["affected"] == 1
    response = await async_client.delete(f"{base}/tags/shared", headers=key)
    assert response.json()["affected"] == 0
    response = await async_client.post(f"{base}/recalculate-costs", headers=key)
    assert response.json()["updated"] == 1
    await db_session.refresh(mine)
    await db_session.refresh(outside)
    assert (mine.tags, mine.cost) == ("renamed", 4.25)
    assert (outside.tags, outside.cost) == ("shared", 8.0)
    response = await async_client.post(
        f"{base}/upload-source",
        headers=key,
        params={"print_name": "Unique other"},
        files={"file": ("project.3mf", b"fixture", "application/octet-stream")},
    )
    assert response.status_code == 404
    await db_session.refresh(outside)
    assert outside.source_3mf_path is None
