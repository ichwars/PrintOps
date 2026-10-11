"""Quality is per production run; machine completion alone is not acceptance."""

import pytest
from sqlalchemy import func, select

from backend.app.models.archive import PrintArchive
from backend.app.models.print_batch import PrintBatch, PrintBatchPlate
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.print_queue import PrintQueueItem


@pytest.fixture
async def quality_run(db_session, printer_factory):
    printer = await printer_factory()
    archive = PrintArchive(
        filename="parts.3mf",
        file_path="parts.3mf",
        file_size=1,
        printer_id=printer.id,
        status="completed",
        quantity=4,
    )
    archive.confirm_requested = True
    db_session.add(archive)
    await db_session.flush()
    batch = PrintBatch(name="Customer production", archive_id=archive.id, quantity=1)
    db_session.add(batch)
    await db_session.flush()
    db_session.add(PrintBatchPlate(batch_id=batch.id, quantity_target=1))
    item = PrintQueueItem(archive_id=archive.id, printer_id=printer.id, batch_id=batch.id, status="completed")
    item.confirm_outcome = True
    db_session.add(item)
    await db_session.flush()
    run = PrintLogEntry(archive_id=archive.id, queue_item_id=item.id, printer_id=printer.id, status="completed")
    run.quantity = 4
    run.confirm_requested = True
    db_session.add(run)
    await db_session.commit()
    return archive, batch, item, run


async def test_unconfirmed_run_reserves_target_but_does_not_fulfill_batch(async_client, quality_run, db_session):
    from backend.app.services.print_batch import refresh_batch_status

    _, batch, _, _ = quality_run
    await refresh_batch_status(db_session, batch)
    await db_session.commit()
    response = await async_client.get(f"/api/v1/queue/batches/{batch.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "active", "machine completion must await the operator's acceptance"
    assert data["remaining_count"] == 0, "do not dispatch a duplicate while inspection is pending"
    assert data["unconfirmed_count"] == 1
    assert data["accepted_count"] == 0


async def test_partial_acceptance_records_parts_and_restores_run_target(async_client, quality_run, db_session):
    archive, batch, item, run = quality_run
    response = await async_client.post(
        f"/api/v1/archives/{archive.id}/outcome",
        json={"run_id": run.id, "good_quantity": 3, "reject_quantity": 1, "failure_reason": "warping"},
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(run)
    await db_session.refresh(item)
    assert (run.good_quantity, run.reject_quantity, run.user_verdict) == (3, 1, "mixed")
    assert item.status == "completed", "quality must retain the machine's actual outcome"
    progress = (await async_client.get(f"/api/v1/queue/batches/{batch.id}")).json()
    assert progress["remaining_count"] == 1, "a partial run cannot satisfy an entire run target"
    assert (progress["good_quantity"], progress["reject_quantity"]) == (3, 1)
    assert progress["status"] == "active"
    assert (await db_session.scalars(select(PrintQueueItem).where(PrintQueueItem.batch_id == batch.id))).all() == [item]


@pytest.mark.parametrize("good,reject", [(5, 0), (3, 0), (-1, 5), (2.5, 1.5)])
async def test_counts_must_be_nonnegative_integers_and_cover_intended_parts(
    async_client, quality_run, db_session, good, reject
):
    archive, _, _, run = quality_run
    response = await async_client.post(
        f"/api/v1/archives/{archive.id}/outcome",
        json={"run_id": run.id, "good_quantity": good, "reject_quantity": reject},
    )
    assert response.status_code in (409, 422), response.text
    await db_session.refresh(run)
    assert getattr(run, "good_quantity", None) is None


async def test_good_acceptance_closes_batch_and_correction_reopens_it(async_client, quality_run):
    archive, batch, _, run = quality_run
    path = f"/api/v1/archives/{archive.id}/outcome"
    assert (
        await async_client.post(path, json={"run_id": run.id, "good_quantity": 4, "reject_quantity": 0})
    ).status_code == 200
    assert (await async_client.get(f"/api/v1/queue/batches/{batch.id}")).json()["status"] == "completed"
    assert (
        await async_client.post(path, json={"run_id": run.id, "good_quantity": 0, "reject_quantity": 4})
    ).status_code == 200
    assert (await async_client.get(f"/api/v1/queue/batches/{batch.id}")).json()["status"] == "active"


async def test_legacy_completed_run_still_fulfills_historical_batch(async_client, quality_run, db_session):
    from backend.app.services.print_batch import refresh_batch_status

    archive, batch, item, run = quality_run
    archive.confirm_requested = False
    item.confirm_outcome = False
    run.confirm_requested = False
    await db_session.flush()
    await refresh_batch_status(db_session, batch)
    await db_session.commit()
    data = (await async_client.get(f"/api/v1/queue/batches/{batch.id}")).json()
    assert data["status"] == "completed"


async def test_persisted_parts_cannot_exceed_the_run_quantity(quality_run, db_session):
    from sqlalchemy.exc import IntegrityError

    _, _, _, run = quality_run
    run.good_quantity, run.reject_quantity = 4, 1
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.fixture
async def outcome_link(quality_run, db_session):
    from backend.app.services.print_confirmation import issue_confirmation_token

    archive, _, _, _ = quality_run
    token = await issue_confirmation_token(db_session, archive)
    await db_session.commit()
    return f"/api/v1/archives/outcome-link/{token}"


async def test_link_get_cannot_accept_parts_or_spend_the_capability(
    async_client, outcome_link, quality_run, db_session
):
    _, _, _, run = quality_run
    response = await async_client.get(outcome_link + "/good", headers={"User-Agent": "TelegramBot"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "<script" not in response.text
    await db_session.refresh(run)
    assert run.good_quantity is None
    assert run.confirm_token_used_at is None


async def test_link_first_answer_wins_and_is_not_a_session_credential(
    async_client, outcome_link, quality_run, db_session
):
    archive, _, _, run = quality_run
    await async_client.post(
        "/api/v1/auth/setup",
        json={"auth_enabled": True, "admin_username": "quality-admin", "admin_password": "QualityPass1!"},
    )
    response = await async_client.post(outcome_link + "/reject")
    assert response.status_code == 200, response.text
    repeated = await async_client.post(outcome_link + "/good")
    assert repeated.status_code == 200
    assert "Already answered" in repeated.text
    await db_session.refresh(run)
    assert (run.good_quantity, run.reject_quantity) == (0, 4)
    token = outcome_link.rsplit("/", 1)[-1]
    for path in (f"/api/v1/archives/{archive.id}", f"/api/v1/archives/{archive.id}/outcome", "/api/v1/orders"):
        method = async_client.post if path.endswith("/outcome") else async_client.get
        assert (await method(path, headers={"Authorization": f"Bearer {token}"})).status_code == 401


async def test_old_run_and_its_link_cannot_change_a_reprint(async_client, outcome_link, quality_run, db_session):
    archive, _, _, run = quality_run
    archive.status = "printing"
    await db_session.commit()
    assert (await async_client.post(outcome_link + "/good")).status_code == 404
    response = await async_client.post(
        f"/api/v1/archives/{archive.id}/outcome", json={"run_id": run.id, "good_quantity": 4, "reject_quantity": 0}
    )
    assert response.status_code == 409
    archive.status = "completed"
    new_run = PrintLogEntry(archive_id=archive.id, status="completed", quantity=4, confirm_requested=True)
    db_session.add(new_run)
    await db_session.commit()
    assert (await async_client.post(outcome_link + "/good")).status_code == 404
    assert (
        await async_client.post(
            f"/api/v1/archives/{archive.id}/outcome", json={"run_id": run.id, "good_quantity": 4, "reject_quantity": 0}
        )
    ).status_code == 409
    await db_session.refresh(run)
    assert run.good_quantity is None


async def test_expired_deleted_and_unknown_links_cannot_record(async_client, outcome_link, quality_run, db_session):
    from datetime import datetime, timedelta, timezone

    archive, _, _, run = quality_run
    run.confirm_token_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    await db_session.commit()
    assert (await async_client.post(outcome_link + "/good")).status_code == 404
    run.confirm_token_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    archive.deleted_at = datetime.now()
    await db_session.commit()
    assert (await async_client.post(outcome_link + "/good")).status_code == 404
    assert (await async_client.post("/api/v1/archives/outcome-link/" + "a" * 43 + "/good")).status_code == 404
    await db_session.refresh(run)
    assert run.good_quantity is None


async def test_link_page_escapes_operator_controlled_text(async_client, outcome_link, quality_run, db_session):
    _, _, _, run = quality_run
    run.print_name = "<script>alert('x')</script>"
    await db_session.commit()
    page = await async_client.get(outcome_link + "/good")
    assert "&lt;script&gt;" in page.text
    assert "<script>alert" not in page.text
    assert "document.getElementById" not in page.text, "message text links never auto-submit"


async def test_run_snapshot_protects_project_and_quantity_from_later_archive_edits(quality_run, db_session):
    from backend.app.models.project import Project
    from backend.app.services.print_log import write_log_entry

    archive, _, item, _ = quality_run
    project = Project(name="Customer production")
    db_session.add(project)
    await db_session.flush()
    item.project_id = project.id
    archive.quantity = 12
    run = await write_log_entry(db_session, status="completed", archive_id=archive.id, queue_item_id=item.id)
    await db_session.commit()
    archive.quantity, archive.project_id = 99, None
    await db_session.commit()
    await db_session.refresh(run)
    assert (run.project_id, run.quantity, run.confirm_requested) == (project.id, 12, True)


@pytest.mark.parametrize("historical", [False, True])
async def test_confirmation_obeys_group_ownership_and_printer_scope(async_client, quality_run, db_session, historical):
    from backend.app.core.auth import create_access_token, get_password_hash
    from backend.app.models.group import Group
    from backend.app.models.settings import Settings
    from backend.app.models.user import User

    archive, _, _, run = quality_run
    owner_group = Group(name="Quality operators", permissions=["archives:update_own"])
    owner = User(username="quality-owner", password_hash=get_password_hash("QualityPass1!"), groups=[owner_group])
    other = User(username="quality-other", password_hash=get_password_hash("QualityPass1!"), groups=[owner_group])
    db_session.add_all([owner, other, Settings(key="auth_enabled", value="true")])
    await db_session.flush()
    archive.created_by_id = owner.id
    await db_session.commit()
    path = (
        f"/api/v1/archives/{archive.id}/runs/{run.id}/outcome"
        if historical
        else f"/api/v1/archives/{archive.id}/outcome"
    )
    body = {"run_id": run.id, "good_quantity": 4, "reject_quantity": 0}

    def headers(user):
        return {"Authorization": "Bearer " + create_access_token(data={"sub": user.username})}

    assert (await async_client.post(path, json=body, headers=headers(other))).status_code == 404
    owner.allowed_printer_ids = [archive.printer_id + 100]
    await db_session.commit()
    assert (await async_client.post(path, json=body, headers=headers(owner))).status_code == 404
    owner.allowed_printer_ids = [archive.printer_id]
    await db_session.commit()
    assert (await async_client.post(path, json=body, headers=headers(owner))).status_code == 200
    owner_group.permissions = []
    await db_session.commit()
    assert (await async_client.post(path, json=body, headers=headers(owner))).status_code == 403


@pytest.mark.parametrize("historical", [False, True])
async def test_api_key_archive_and_printer_scopes_apply_to_outcome(async_client, quality_run, db_session, historical):
    from backend.app.core.auth import generate_api_key
    from backend.app.models.api_key import APIKey
    from backend.app.models.settings import Settings

    archive, _, _, run = quality_run
    key, digest, prefix = generate_api_key()
    api_key = APIKey(
        name="quality-reader",
        key_hash=digest,
        key_prefix=prefix,
        can_manage_archives=False,
        printer_ids=[archive.printer_id],
    )
    db_session.add_all([api_key, Settings(key="auth_enabled", value="true")])
    await db_session.commit()
    path = (
        f"/api/v1/archives/{archive.id}/runs/{run.id}/outcome"
        if historical
        else f"/api/v1/archives/{archive.id}/outcome"
    )
    body = {"run_id": run.id, "good_quantity": 4, "reject_quantity": 0}
    headers = {"X-API-Key": key}
    assert (await async_client.post(path, json=body, headers=headers)).status_code == 403
    api_key.can_manage_archives, api_key.printer_ids = True, []
    await db_session.commit()
    assert (await async_client.post(path, json=body, headers=headers)).status_code == 404
    api_key.printer_ids = [archive.printer_id]
    await db_session.commit()
    assert (await async_client.post(path, json=body, headers=headers)).status_code == 200


async def test_order_production_counts_only_confirmed_parts_and_preserves_stock(async_client, quality_run, db_session):
    from backend.app.models.small_part import SmallPartLedgerEntry
    from backend.tests.integration.test_order_reservation_lifecycle import _accepted_order

    order, _, spool = await _accepted_order(async_client, db_session)
    archive, _, item, run = quality_run
    archive.project_id = item.project_id = run.project_id = order["project_id"]
    await db_session.commit()
    before = (await async_client.get(f"/api/v1/orders/{order['id']}")).json()
    ledger_count = await db_session.scalar(select(func.count(SmallPartLedgerEntry.id)))
    weight = spool.weight_used
    production_path = f"/api/v1/orders/{order['id']}/production"
    assert (await async_client.get(production_path)).json() == {
        "good_quantity": 0,
        "reject_quantity": 0,
        "unconfirmed_runs": 1,
    }
    assert (
        await async_client.post(
            f"/api/v1/archives/{archive.id}/outcome", json={"run_id": run.id, "good_quantity": 3, "reject_quantity": 1}
        )
    ).status_code == 200
    assert (await async_client.get(production_path)).json() == {
        "good_quantity": 3,
        "reject_quantity": 1,
        "unconfirmed_runs": 0,
    }
    assert (await async_client.get(f"/api/v1/orders/{order['id']}")).json() == before
    assert await db_session.scalar(select(func.count(SmallPartLedgerEntry.id))) == ledger_count
    await db_session.refresh(spool)
    assert spool.weight_used == weight


async def test_quality_stats_are_parts_and_keep_machine_results(async_client, quality_run):
    archive, _, _, run = quality_run
    await async_client.post(
        f"/api/v1/archives/{archive.id}/outcome", json={"run_id": run.id, "good_quantity": 3, "reject_quantity": 1}
    )
    stats = (await async_client.get("/api/v1/archives/stats")).json()
    assert (stats["successful_prints"], stats["failed_prints"]) == (1, 0)
    assert (stats["confirmed_good_quantity"], stats["confirmed_reject_quantity"], stats["yield_percent"]) == (
        3,
        1,
        75.0,
    )
    assert stats["unconfirmed_prints"] == 0


async def test_provider_confirmation_toggle_round_trips(async_client):
    created = await async_client.post(
        "/api/v1/notifications/",
        json={
            "name": "Quality alerts",
            "provider_type": "ntfy",
            "config": {"server": "https://ntfy.sh", "topic": "quality"},
            "on_print_confirm_request": False,
        },
    )
    assert created.status_code == 200, created.text
    provider_id = created.json()["id"]
    assert created.json()["on_print_confirm_request"] is False
    providers = (await async_client.get("/api/v1/notifications/")).json()
    assert next(item for item in providers if item["id"] == provider_id)["on_print_confirm_request"] is False


async def test_historical_run_can_be_inspected_without_changing_the_current_run(async_client, quality_run, db_session):
    archive, batch, _, run = quality_run
    archive.status = "printing"
    await db_session.commit()
    path = f"/api/v1/archives/{archive.id}/runs/{run.id}/outcome"
    response = await async_client.post(path, json={"run_id": run.id, "good_quantity": 4, "reject_quantity": 0})
    assert response.status_code == 200, response.text
    await db_session.refresh(run)
    await db_session.refresh(archive)
    assert (run.good_quantity, run.reject_quantity) == (4, 0)
    assert archive.status == "printing"
    assert archive.good_quantity is None
    assert (await async_client.get(f"/api/v1/queue/batches/{batch.id}")).json()["status"] == "completed"
    unrelated = PrintLogEntry(status="completed", quantity=4)
    db_session.add(unrelated)
    await db_session.commit()
    response = await async_client.post(
        f"/api/v1/archives/{archive.id}/runs/{unrelated.id}/outcome",
        json={"run_id": unrelated.id, "good_quantity": 4, "reject_quantity": 0},
    )
    assert response.status_code == 404


async def test_new_production_run_requires_inspection_but_ordinary_runs_are_opt_in(quality_run, db_session):
    from backend.app.services.print_confirmation import initialize_queue_outcome

    archive, batch, item, previous = quality_run
    ordinary = PrintQueueItem(archive_id=archive.id, printer_id=archive.printer_id, confirm_outcome=False)
    db_session.add(ordinary)
    await db_session.flush()
    await initialize_queue_outcome(db_session, ordinary, archive)
    assert ordinary.confirm_outcome is False
    assert ordinary.expected_parts == 4
    item.confirm_outcome = False
    item.expected_parts = 2
    await initialize_queue_outcome(db_session, item, archive)
    await db_session.commit()
    assert item.confirm_outcome is True, (
        "a production target requires inspection even if the optional toggle is omitted"
    )
    assert archive.quantity == item.expected_parts == 2
    assert previous.quantity == 4, "new run preparation must preserve historical intended parts"


async def test_marked_notification_button_is_one_tap_but_preview_get_is_read_only(
    async_client, outcome_link, quality_run, db_session
):
    _, _, _, run = quality_run
    response = await async_client.get(outcome_link + "/good?tap=1", headers={"User-Agent": "Mozilla/5.0"})
    assert "document.getElementById('confirmation').submit()" in response.text
    nonce = response.text.split("<script nonce='")[1].split("'")[0]
    assert "nonce-" + nonce in response.headers["content-security-policy"]
    preview = await async_client.get(
        outcome_link + "/good?tap=1", headers={"User-Agent": "Mozilla/5.0", "Sec-Purpose": "prefetch"}
    )
    assert "<script" not in preview.text
    await db_session.refresh(run)
    assert run.good_quantity is None
    assert run.confirm_token_used_at is None


async def test_print_log_metadata_edit_keeps_confirmed_run_fields_in_response(async_client, quality_run):
    archive, _, _, run = quality_run
    await async_client.post(
        f"/api/v1/archives/{archive.id}/outcome", json={"run_id": run.id, "good_quantity": 3, "reject_quantity": 1}
    )
    response = await async_client.patch(f"/api/v1/print-log/{run.id}", json={"failure_reason": "warping"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["quantity"], data["good_quantity"], data["reject_quantity"]) == (4, 3, 1)
    assert data["user_verdict"] == "mixed"
    assert not any("token" in key for key in data)


async def test_completion_prompt_keeps_capability_out_of_socket_and_app_link(quality_run, db_session, monkeypatch):
    from unittest.mock import AsyncMock

    from backend.app.core.websocket import ws_manager
    from backend.app.models.settings import Settings
    from backend.app.services.notification_service import notification_service
    from backend.app.services.print_confirmation import dispatch_outcome_confirmation, token_digest

    archive, _, _, run = quality_run
    db_session.add(Settings(key="external_url", value="https://printops.example"))
    await db_session.commit()
    notify, socket = AsyncMock(), AsyncMock()
    monkeypatch.setattr(notification_service, "on_print_confirm_request", notify)
    monkeypatch.setattr(ws_manager, "broadcast_to_user", socket)
    assert await dispatch_outcome_confirmation(db_session, archive.id, archive.printer_id, "Printer") is True
    kwargs = notify.call_args.kwargs
    token = kwargs["outcome_urls"]["good"].rsplit("/", 2)[1]
    assert kwargs["confirm_url"] == f"https://printops.example/archives?confirm={archive.id}&confirm_run={run.id}"
    assert token not in str(socket.call_args)
    assert token not in kwargs["confirm_url"]
    await db_session.refresh(run)
    assert run.confirm_token_hash == token_digest(token)
    assert await dispatch_outcome_confirmation(db_session, archive.id, archive.printer_id, "Printer") is False
    assert notify.call_count == 1, "duplicate completion must not invalidate sent actions"


async def test_confirmation_event_reaches_http_actions_and_records_success(db_session, quality_run, monkeypatch):
    from unittest.mock import AsyncMock

    import httpx

    from backend.app.models.notification import NotificationLog, NotificationProvider
    from backend.app.services.notification_service import NotificationService

    archive, _, _, _ = quality_run
    provider = NotificationProvider(
        name="Quality",
        provider_type="ntfy",
        config='{"server":"https://ntfy.sh","topic":"quality"}',
        on_print_confirm_request=True,
    )
    db_session.add(provider)
    await db_session.commit()
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "notification"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        service = NotificationService()
        monkeypatch.setattr(service, "_get_client", AsyncMock(return_value=client))
        await service.on_print_confirm_request(
            archive.printer_id,
            "Printer",
            db_session,
            print_name="Production",
            confirm_url="https://printops.example/archives?confirm=1&confirm_run=7",
            outcome_urls={
                verdict: f"https://printops.example/api/v1/archives/outcome-link/capability/{verdict}"
                for verdict in ("good", "reject")
            },
        )
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert "outcome-link/capability/good" in requests[0].headers["Actions"]
    assert "method=POST" in requests[0].headers["Actions"]
    assert b"capability" not in requests[0].content
    log = await db_session.scalar(select(NotificationLog).where(NotificationLog.provider_id == provider.id))
    assert log.success is True
    assert log.event_type == "print_confirm_request"
    assert "capability" not in log.message


@pytest.mark.parametrize("blocked_work,next_copy,start_before_hint", [
    ("photo", True, False), ("provider", True, False), ("photo", False, False), ("photo", True, True),
])
async def test_completed_run_hint_survives_next_copy_during_finish_work(
    async_client, quality_run, db_session, test_engine, monkeypatch, blocked_work, next_copy, start_before_hint
):
    """Catch a prompt deferred behind camera/provider work or rebound to the next run."""
    import asyncio
    import json
    from datetime import datetime, timedelta
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from backend.app import main
    from backend.app.core.auth import create_access_token, get_password_hash
    from backend.app.core.websocket import ws_manager
    from backend.app.models.commerce import CustomerOrder
    from backend.app.models.group import Group
    from backend.app.models.notification import NotificationProvider
    from backend.app.models.printer import Printer
    from backend.app.models.settings import Settings
    from backend.app.models.small_part import SmallPartLedgerEntry
    from backend.app.models.stock_reservation import StockReservationCommand
    from backend.app.models.user import User
    from backend.app.services import active_print_provenance, usage_tracker
    from backend.app.services.bambu_ftp import DeleteResult
    from backend.app.services.notification_service import notification_service
    from backend.app.services.print_confirmation import issue_confirmation_token
    from backend.tests.integration.test_order_reservation_lifecycle import _accepted_order

    order_data, _, spool = await _accepted_order(async_client, db_session)
    order = await db_session.get(CustomerOrder, order_data["id"])
    archive, batch, item, fixture_run = quality_run
    await db_session.delete(fixture_run)
    owner = User(username="prompt-owner", password_hash=get_password_hash("QualityPass1!"), groups=[
        Group(name="Prompt operators", permissions=["archives:update_own", "archives:read_own"])
    ])
    db_session.add(owner)
    await db_session.flush()
    archive.status = item.status = "printing"
    archive.started_at = datetime.now() - timedelta(minutes=5)
    archive.created_by_id = owner.id
    archive.project_id = item.project_id = order.project_id
    batch.quantity = 2
    plate = await db_session.scalar(select(PrintBatchPlate).where(PrintBatchPlate.batch_id == batch.id))
    plate.quantity_target = 2
    next_item = PrintQueueItem(archive_id=archive.id, printer_id=archive.printer_id,
                              batch_id=batch.id, project_id=order.project_id, status="pending",
                              confirm_outcome=True, expected_parts=4, position=2)
    db_session.add_all([next_item, Settings(key="auth_enabled", value="true"),
                       Settings(key="external_url", value="https://printops.example"),
                       NotificationProvider(name="Completion and quality", provider_type="ntfy",
                           config='{"server":"https://ntfy.sh","topic":"quality"}',
                           on_print_complete=True, on_print_confirm_request=True, on_queue_completed=False)])
    await db_session.commit()
    printer = await db_session.get(Printer, archive.printer_id)
    printer.external_camera_enabled = False
    printer.plate_detection_enabled = False
    await db_session.commit()

    raced_token = []

    class StartNextCopyAfterLogCommit(AsyncSession):
        async def commit(self):
            finished = next((row for row in self.identity_map.values() if isinstance(row, PrintLogEntry)), None)
            await super().commit()
            if finished is not None and start_before_hint and not raced_token:
                mirror = await self.get(PrintArchive, archive.id)
                raced_token.append(await issue_confirmation_token(self, mirror))
                await super().commit()
                queued = await self.get(PrintQueueItem, next_item.id)
                queued.status = "printing"
                await super().commit()
                main._expected_prints[(printer.id, archive.filename)] = archive.id
                await main.on_print_start(printer.id, {"filename": archive.filename,
                                                      "raw_data": {"subtask_id": "copy-two"}})

    sessions = async_sessionmaker(test_engine, class_=StartNextCopyAfterLogCommit, expire_on_commit=False)
    monkeypatch.setattr(main, "async_session", sessions)
    monkeypatch.setattr(active_print_provenance, "async_session", sessions)
    monkeypatch.setattr(usage_tracker, "_active_sessions", {})
    monkeypatch.setattr(main, "_last_progress_milestone", {})
    monkeypatch.setattr(main, "_first_layer_notified", {})
    monkeypatch.setattr(main, "_bed_cool_waiters", {})
    monkeypatch.setattr(main, "_active_prints", {(printer.id, archive.filename): archive.id})
    monkeypatch.setattr(main, "_expected_prints", {})
    monkeypatch.setattr(main, "_stage22_finish_in_flight", {})
    monkeypatch.setattr(main, "_stage22_finish_frames", {})
    monkeypatch.setattr(main.printer_manager, "get_printer", lambda _id: printer)
    monkeypatch.setattr(main.printer_manager, "get_status", lambda _id: None)
    monkeypatch.setattr(main.printer_manager, "get_client", lambda _id: None)
    monkeypatch.setattr(main.printer_manager, "get_current_print_user", lambda _id: None)
    monkeypatch.setattr(main.printer_manager, "set_awaiting_plate_clear", lambda *_args: None)
    for method in ("on_print_complete", "on_print_start", "on_archive_updated", "on_queue_job_completed"):
        monkeypatch.setattr(main.mqtt_relay, method, AsyncMock())
    monkeypatch.setattr("backend.app.services.bambu_ftp.delete_file_async", AsyncMock(return_value=DeleteResult.NOT_FOUND))
    monkeypatch.setattr(main, "_capture_timelapse_baseline_at_start", AsyncMock())
    monkeypatch.setattr(main, "ensure_default_types", AsyncMock())
    monkeypatch.setattr(main, "_get_printer_maintenance_internal", AsyncMock(return_value=SimpleNamespace(maintenance_items=[])))
    monkeypatch.setattr("backend.app.api.routes.camera.get_buffered_frame", lambda _id: None)
    monkeypatch.setattr("backend.app.api.routes.camera.is_stream_active", lambda _id: False)

    sockets = [SimpleNamespace(state=SimpleNamespace(printops_principal_user_id=uid), send_text=AsyncMock())
               for uid in (owner.id, owner.id + 100, None)]
    monkeypatch.setattr(ws_manager, "active_connections", sockets)
    blocked, release = asyncio.Event(), asyncio.Event()

    async def photo(**_kwargs):
        if blocked_work == "photo":
            blocked.set()
            await release.wait()
        return None

    monkeypatch.setattr("backend.app.services.camera.capture_finish_photo", photo)
    monkeypatch.setattr("backend.app.services.camera.capture_camera_frame_bytes", AsyncMock(return_value=None))
    provider_requests = []

    async def transport(request):
        provider_requests.append(request)
        if blocked_work == "provider" and "Actions" not in request.headers:
            blocked.set()
            await release.wait()
        return httpx.Response(200, json={"id": "notification"})

    tasks = []
    original_spawn = main.spawn_background_task

    def spawn(coro, *, name):
        task = original_spawn(coro, name=name)
        tasks.append(task)
        return task

    monkeypatch.setattr(main, "spawn_background_task", spawn)
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as provider_client:
        monkeypatch.setattr(notification_service, "_get_client", AsyncMock(return_value=provider_client))
        try:
            await main.on_print_complete(printer.id, {"status": "completed", "filename": archive.filename,
                                                     "progress": 100, "timelapse_was_active": False})
            await asyncio.wait_for(blocked.wait(), timeout=3)
            await db_session.refresh(archive)
            completed_run = await db_session.scalar(select(PrintLogEntry).where(PrintLogEntry.archive_id == archive.id))
            assert completed_run is not None and completed_run.status == "completed"
            assert completed_run.queue_item_id == item.id
            early_hints = [json.loads(call.args[0]) for call in sockets[0].send_text.call_args_list
                           if json.loads(call.args[0]).get("type") == "print_confirm_request"]
            assert len(early_hints) == 1, "hint must be sent while optional finish work is still blocked"
            assert early_hints[0]["data"]["run_id"] == completed_run.id
            if not next_copy:
                release.set()
                await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
                actions = [request.headers["Actions"] for request in provider_requests if "Actions" in request.headers]
                assert len(actions) == 1, "still-current run must reach actual provider actions"
                token = actions[0].split("outcome-link/")[1].split("/")[0]
                assert (await async_client.post(f"/api/v1/archives/outcome-link/{token}/good")).status_code == 200
                await db_session.refresh(completed_run)
                assert (completed_run.good_quantity, completed_run.reject_quantity) == (4, 0)
                hints = [json.loads(call.args[0]) for call in sockets[0].send_text.call_args_list
                         if json.loads(call.args[0]).get("type") == "print_confirm_request"]
                assert len(hints) == 1, "provider dispatch must not repeat the early UI hint"
                return
            # This old capability must remain unusable after the archive is reused.
            if start_before_hint:
                old_token = raced_token[0]
            else:
                old_token = (await issue_confirmation_token(db_session, archive)
                             if blocked_work == "photo" else None)
                await db_session.commit()
                next_item.status = "printing"
                await db_session.commit()
                main._expected_prints[(printer.id, archive.filename)] = archive.id
                await main.on_print_start(printer.id, {"filename": archive.filename,
                                                      "raw_data": {"subtask_id": "copy-two"}})
            if blocked_work == "photo":
                assert old_token
            await db_session.refresh(archive)
            active_started_at = archive.started_at
            assert archive.status == "printing"
            release.set()
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
            hints = [json.loads(call.args[0]) for call in sockets[0].send_text.call_args_list
                     if json.loads(call.args[0]).get("type") == "print_confirm_request"]
            assert len(hints) == 1, "completed run's hint must precede optional camera/provider awaits"
            assert hints[0]["printer_id"] == printer.id
            assert hints[0]["data"]["run_id"] == completed_run.id
            if old_token:
                assert old_token not in str(hints)
            for other in sockets[1:]:
                assert not any(json.loads(call.args[0]).get("type") == "print_confirm_request"
                               for call in other.send_text.call_args_list)
            assert not any("Actions" in request.headers for request in provider_requests), "no stale external capability"
            if old_token:
                assert (await async_client.post(f"/api/v1/archives/outcome-link/{old_token}/good")).status_code == 404

            order_before = (order.status, dict(order.accepted_snapshot))
            await db_session.refresh(spool)
            weight_before = spool.weight_used
            ledger_before = await db_session.scalar(select(func.count(SmallPartLedgerEntry.id)))
            commands_before = await db_session.scalar(select(func.count(StockReservationCommand.id)))
            headers = {"Authorization": "Bearer " + create_access_token({"sub": owner.username})}
            response = await async_client.post(f"/api/v1/archives/{archive.id}/runs/{completed_run.id}/outcome",
                json={"run_id": completed_run.id, "good_quantity": 3, "reject_quantity": 1}, headers=headers)
            assert response.status_code == 200, response.text
            for row in (archive, completed_run, next_item, batch, plate, spool, order):
                await db_session.refresh(row)
            assert (completed_run.good_quantity, completed_run.reject_quantity) == (3, 1)
            assert (archive.status, archive.started_at, archive.good_quantity, archive.reject_quantity) == (
                "printing", active_started_at, None, None)
            assert next_item.status == "printing"
            assert (batch.quantity, plate.quantity_target) == (2, 2)
            assert (order.status, order.accepted_snapshot) == order_before
            assert spool.weight_used == weight_before
            assert await db_session.scalar(select(func.count(SmallPartLedgerEntry.id))) == ledger_before
            assert await db_session.scalar(select(func.count(StockReservationCommand.id))) == commands_before
        finally:
            release.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def test_delayed_prompt_cannot_issue_actions_for_a_later_completed_run(quality_run, db_session):
    """An old callback must not silently prompt whichever copy is newest now."""
    from datetime import datetime, timedelta

    from backend.app.services.print_confirmation import dispatch_outcome_confirmation

    archive, _, _, previous = quality_run
    next_start = datetime.now() + timedelta(minutes=1)
    archive.started_at = next_start
    later = PrintLogEntry(archive_id=archive.id, printer_id=archive.printer_id,
                         status="completed", started_at=next_start, quantity=4, confirm_requested=True)
    db_session.add(later)
    await db_session.commit()
    assert await dispatch_outcome_confirmation(
        db_session, archive.id, archive.printer_id, "Printer", run_id=previous.id, notify_user=False,
    ) is False
    await db_session.refresh(later)
    assert later.confirm_token_hash is None, "old callbacks must not mint a capability for a later copy"


@pytest.mark.parametrize("blocked", [False, "printer", "current-printer", "ownerless", "inactive", "deleted", "answered", "wrong-printer"])
async def test_historical_quality_hint_keeps_owner_and_printer_guards(
    quality_run, db_session, printer_factory, monkeypatch, blocked
):
    import json
    from datetime import datetime
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from backend.app.core.websocket import ws_manager
    from backend.app.models.settings import Settings
    from backend.app.models.user import User
    from backend.app.services.print_confirmation import send_outcome_confirmation_hint

    archive, _, _, run = quality_run
    owner = User(username="hint-owner", allowed_printer_ids=[archive.printer_id + 100] if blocked == "printer" else [archive.printer_id],
                 is_active=blocked != "inactive")
    db_session.add_all([owner, Settings(key="auth_enabled", value="true")])
    await db_session.flush()
    archive.created_by_id = None if blocked == "ownerless" else owner.id
    archive.status = "printing"
    if blocked == "current-printer":
        archive.printer_id = (await printer_factory()).id
    if blocked == "deleted":
        archive.deleted_at = datetime.now()
    if blocked == "answered":
        run.good_quantity, run.reject_quantity, run.user_verdict = 4, 0, "good"
    await db_session.commit()
    socket = SimpleNamespace(state=SimpleNamespace(printops_principal_user_id=owner.id), send_text=AsyncMock())
    monkeypatch.setattr(ws_manager, "active_connections", [socket])
    assert await send_outcome_confirmation_hint(
        db_session, archive.id, run.id, run.printer_id + (1 if blocked == "wrong-printer" else 0),
    ) is (not blocked)
    hints = [json.loads(call.args[0]) for call in socket.send_text.call_args_list]
    assert len(hints) == (0 if blocked else 1)
    if hints:
        assert hints[0]["data"]["run_id"] == run.id
        assert run.confirm_token_hash is None, "a historical hint must never issue a public capability"
