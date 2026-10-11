"""Recheck plate acknowledgment after the final awaited dispatch commit."""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import delete, select, update

from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.settings import Settings
from backend.tests.unit.test_preheat_external_print_race import external_print  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation,journal_failure", [(None, False), ("cancelled", False), ("deleted", False), (None, True)]
)
async def test_unobserved_complete_external_print_blocks_final_publish(
    external_print, monkeypatch, mutation, journal_failure
):
    context = external_print
    context.owner.poll_seconds = 60
    if journal_failure:
        original_unlink = Path.unlink

        def unlink(path, *args, **kwargs):
            if path == context.owner.path(context.printer_id):
                raise OSError("ownership record unavailable")
            return original_unlink(path, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", unlink)
    async with context.factory() as db:
        db.add(Settings(key="require_plate_clear", value="true"))
        await db.commit()
    completed = False
    lease = None
    async with context.factory() as db:
        original = db.commit

        async def commit():
            nonlocal completed, lease
            await original()
            async with context.factory() as verification:
                status = await verification.scalar(
                    select(PrintQueueItem.status).where(PrintQueueItem.id == context.item_id)
                )
            if status == "printing" and not completed:
                completed = True
                lease = context.owner.leases[context.printer_id]
                # Both firmware observations arrive during the final commit:
                # the ownership monitor has no chance to observe ACTIVE.
                context.client.state.state = "RUNNING"
                context.client.state.subtask_id = "external-between-polls"
                context.client.state.state = "FINISH"
                context.awaiting["value"] = True
                if mutation:
                    async with context.factory() as other:
                        statement = (
                            delete(PrintQueueItem)
                            if mutation == "deleted"
                            else update(PrintQueueItem).values(status="cancelled")
                        )
                        await other.execute(statement.where(PrintQueueItem.id == context.item_id))
                        await other.commit()

        monkeypatch.setattr(db, "commit", commit)
        item = await db.get(PrintQueueItem, context.item_id)
        await context.scheduler._dispatch_with_claim(db, item)

    assert completed and lease is not None and not lease.interrupted
    assert context.awaiting["value"]
    assert [payload["print"]["command"] for payload in context.published] == ["gcode_line"]
    assert context.published[0]["print"]["param"] == "M140 S60"
    assert context.client.state.temperatures["bed_target"] == 60
    assert context.owner.blocks_power_off(context.printer_id) == journal_failure
    async with context.factory() as db:
        item = await db.get(PrintQueueItem, context.item_id)
        if mutation == "deleted":
            assert item is None
        else:
            assert item.status == ("cancelled" if mutation else "pending")
            assert item.started_at is None if mutation is None else item.started_at is not None
            assert item.dispatching_at is None


@pytest.mark.asyncio
async def test_disabled_plate_gate_preserves_automatic_dispatch(external_print, monkeypatch):
    context = external_print
    context.owner.poll_seconds = 60
    async with context.factory() as db:
        db.add(Settings(key="require_plate_clear", value="false"))
        await db.commit()

    async def upload(*args):
        context.client.state.state = "FINISH"
        context.awaiting["value"] = True
        return "queue.3mf", "/queue.3mf", 1, None

    monkeypatch.setattr(context.scheduler, "_upload_print_file", upload)
    async with context.factory() as db:
        item = await db.get(PrintQueueItem, context.item_id)
        await context.scheduler._dispatch_with_claim(db, item)
    assert [payload["print"]["command"] for payload in context.published] == ["gcode_line", "project_file"]
    assert not context.awaiting["value"]


@pytest.mark.asyncio
async def test_enabled_plate_gate_keeps_published_own_start_handoff(external_print):
    context = external_print
    async with context.factory() as db:
        db.add(Settings(key="require_plate_clear", value="true"))
        await db.commit()
        item = await db.get(PrintQueueItem, context.item_id)
        await context.scheduler._dispatch_with_claim(db, item)
    lease = context.owner.leases[context.printer_id]
    assert lease.published
    context.client.state.state = "PREPARE"
    await asyncio.wait_for(lease.monitor, 2)
    assert [payload["print"]["command"] for payload in context.published] == ["gcode_line", "project_file"]
    assert context.client.state.temperatures["bed_target"] == 60
    assert not context.owner.blocks_power_off(context.printer_id)
    async with context.factory() as db:
        item = await db.get(PrintQueueItem, context.item_id)
        assert item.status == "printing"
        assert item.dispatching_at is None
