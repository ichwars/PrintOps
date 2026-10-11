"""Bulk library queueing reports rejection and creates dispatchable targets."""

import json
import zipfile

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from backend.app.models.library import LibraryFile
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.user import User

ENDPOINT = "/api/v1/library/files/add-to-queue"


@pytest.fixture
def library_file_factory(db_session, tmp_path):
    counter = 0

    async def create(**kwargs):
        nonlocal counter
        counter += 1
        path = tmp_path / f"file-{counter}.gcode.3mf"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("Metadata/plate_1.gcode", "; printable\nG28\n")
            archive.writestr(
                "Metadata/slice_info.config",
                '<config><plate><metadata key="index" value="1"/><filament type="PLA" used_g="5"/></plate></config>',
            )
        values = {
            "filename": f"file-{counter}.gcode.3mf",
            "file_path": str(path),
            "file_type": "gcode.3mf",
            "file_size": path.stat().st_size,
            "file_metadata": {"sliced_for_model": "X1C"},
        }
        values.update(kwargs)
        file = LibraryFile(**values)
        db_session.add(file)
        await db_session.commit()
        await db_session.refresh(file)
        return file

    return create


@pytest.fixture
async def limited_user(async_client, db_session):
    response = await async_client.post(
        "/api/v1/auth/setup",
        json={"auth_enabled": True, "admin_username": "bulkadmin", "admin_password": "AdminPass1!"},
    )
    assert response.status_code == 200
    login = await async_client.post("/api/v1/auth/login", json={"username": "bulkadmin", "password": "AdminPass1!"})
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    groups = (await async_client.get("/api/v1/groups/", headers=admin_headers)).json()
    operators_id = next(group["id"] for group in groups if group["name"] == "Operators")
    response = await async_client.post(
        "/api/v1/users/",
        headers=admin_headers,
        json={"username": "bulkoperator", "password": "OperatorPass1!", "group_ids": [operators_id]},
    )
    assert response.status_code == 201
    login = await async_client.post(
        "/api/v1/auth/login", json={"username": "bulkoperator", "password": "OperatorPass1!"}
    )
    user = (await db_session.execute(select(User).where(User.username == "bulkoperator"))).scalar_one()
    return user, {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "target",
    [
        {"printer_id": 9999},
        {"target_model": "not-a-model"},
        {"target_model": ""},
        {"target_model": "   "},
        {"target_model": "H2D"},
        {"printer_id": 1, "target_model": "X1C"},
    ],
)
async def test_invalid_batch_target_rejects_before_creating_jobs(
    async_client: AsyncClient, db_session, printer_factory, library_file_factory, target
):
    await printer_factory()
    file = await library_file_factory()

    response = await async_client.post(ENDPOINT, json={"file_ids": [file.id], **target})

    assert response.status_code == 400
    assert (await db_session.execute(select(PrintQueueItem))).scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "reason", ["missing", "unsliced", "missing_disk", "invalid_filename", "directory", "unreadable", "traversal"]
)
async def test_selection_with_no_printable_jobs_returns_file_errors(
    async_client: AsyncClient, db_session, library_file_factory, reason, tmp_path, monkeypatch
):
    overrides = {
        "missing": {},
        "unsliced": {"filename": "model.stl", "file_type": "stl"},
        "missing_disk": {"file_path": str(tmp_path / "absent.gcode.3mf")},
        "invalid_filename": {"filename": "bad:name.gcode.3mf"},
        "directory": {"file_path": str(tmp_path)},
        "unreadable": {},
        "traversal": {"file_path": "../outside.gcode.3mf"},
    }
    file = await library_file_factory(**overrides[reason])
    file_id = 9999 if reason == "missing" else file.id
    if reason == "unreadable":
        import os
        from pathlib import Path

        original_access = os.access
        denied_path = Path(file.file_path)

        def access(path, mode, **kwargs):
            # Root bypasses chmod(0); model the same OS denial for every test user.
            if Path(path) == denied_path and mode == os.R_OK:
                return False
            return original_access(path, mode, **kwargs)

        monkeypatch.setattr(os, "access", access)

    response = await async_client.post(ENDPOINT, json={"file_ids": [file_id]})

    assert response.status_code == 400
    assert response.json()["detail"]["errors"][0]["file_id"] == file_id
    assert response.json()["detail"]["errors"][0]["error"]
    assert (await db_session.execute(select(PrintQueueItem))).scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("target_kind", ["printer", "model"])
async def test_cross_model_slice_is_rejected_for_explicit_target(
    async_client: AsyncClient, db_session, printer_factory, library_file_factory, target_kind
):
    printer = await printer_factory(model="H2D")
    file = await library_file_factory()
    target = {"printer_id": printer.id} if target_kind == "printer" else {"target_model": "O1D"}

    response = await async_client.post(ENDPOINT, json={"file_ids": [file.id], **target})

    assert response.status_code == 400
    assert "sliced" in response.json()["detail"]["errors"][0]["error"].lower()
    assert (await db_session.execute(select(PrintQueueItem))).scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "target,expected_model",
    [({}, "X1C"), ({"target_model": "C11"}, "P1P"), ({"target_model": "Bambu Lab X1 Carbon"}, "X1C")],
)
async def test_active_model_is_inferred_or_normalized_with_filament_requirements(
    async_client: AsyncClient, db_session, printer_factory, library_file_factory, target, expected_model
):
    await printer_factory(model=expected_model)
    file = await library_file_factory(file_metadata={"sliced_for_model": expected_model})

    response = await async_client.post(ENDPOINT, json={"file_ids": [file.id], **target})

    assert response.status_code == 200, response.text
    item = (await db_session.execute(select(PrintQueueItem))).scalar_one()
    assert item.target_model == expected_model
    assert item.printer_id is None
    assert json.loads(item.required_filament_types) == ["PLA"]
    assert response.json()["added"][0]["queue_item_id"] == item.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_explicit_printer_is_assigned(async_client, db_session, printer_factory, library_file_factory):
    printer = await printer_factory()
    file = await library_file_factory()

    response = await async_client.post(ENDPOINT, json={"file_ids": [file.id], "printer_id": printer.id})

    assert response.status_code == 200, response.text
    item = (await db_session.execute(select(PrintQueueItem))).scalar_one()
    assert item.printer_id == printer.id
    assert item.target_model is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_partial_selection_preserves_success_and_per_file_errors(
    async_client, db_session, printer_factory, library_file_factory
):
    await printer_factory()
    good = await library_file_factory()
    unsliced = await library_file_factory(filename="source.stl", file_type="stl")

    response = await async_client.post(ENDPOINT, json={"file_ids": [9999, good.id, unsliced.id]})

    assert response.status_code == 200
    assert [item["file_id"] for item in response.json()["added"]] == [good.id]
    assert [error["file_id"] for error in response.json()["errors"]] == [9999, unsliced.id]
    assert (await db_session.execute(select(PrintQueueItem.library_file_id))).scalars().all() == [good.id]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_without_active_inferred_model_legacy_unassigned_queueing_remains_available(
    async_client, db_session, printer_factory, library_file_factory
):
    await printer_factory(is_active=False)
    file = await library_file_factory()

    response = await async_client.post(ENDPOINT, json={"file_ids": [file.id]})

    assert response.status_code == 200
    item = (await db_session.execute(select(PrintQueueItem))).scalar_one()
    assert item.printer_id is None
    assert item.target_model is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_invisible_file_has_same_rejection_as_unknown_id(
    async_client, db_session, library_file_factory, limited_user
):
    _user, headers = limited_user
    invisible = await library_file_factory()

    response = await async_client.post(ENDPOINT, headers=headers, json={"file_ids": [invisible.id, 9999]})

    assert response.status_code == 400
    errors = response.json()["detail"]["errors"]
    assert errors[0]["filename"] == errors[1]["filename"] == "(not found)"
    assert errors[0]["error"] == errors[1]["error"] == "File not found"
    assert (await db_session.execute(select(PrintQueueItem))).scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_inaccessible_printer_cannot_be_used_as_bulk_target(
    async_client, db_session, printer_factory, library_file_factory, limited_user
):
    user, headers = limited_user
    allowed = await printer_factory()
    hidden = await printer_factory()
    user.allowed_printer_ids = [allowed.id]
    await db_session.commit()
    file = await library_file_factory(created_by_id=user.id)

    response = await async_client.post(ENDPOINT, headers=headers, json={"file_ids": [file.id], "printer_id": hidden.id})

    assert response.status_code == 404
    assert (await db_session.execute(select(PrintQueueItem))).scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_inaccessible_model_cannot_be_used_as_bulk_target(
    async_client, db_session, printer_factory, library_file_factory, limited_user
):
    user, headers = limited_user
    allowed = await printer_factory(model="H2D")
    await printer_factory(model="X1C")
    user.allowed_printer_ids = [allowed.id]
    await db_session.commit()
    file = await library_file_factory(created_by_id=user.id)

    response = await async_client.post(ENDPOINT, headers=headers, json={"file_ids": [file.id], "target_model": "X1C"})

    assert response.status_code == 400
    assert (await db_session.execute(select(PrintQueueItem))).scalars().all() == []
