"""Restore objects from a proven source without clearing skip telemetry."""

import asyncio
import logging

from backend.app.services.printer_manager import resolve_plate_id
from backend.app.services.running_print_archive import find_running_archive, local_archive_file

logger = logging.getLogger(__name__)


class PrintChangedDuringReload(Exception):
    pass


def print_identity(state):
    try:
        plate = resolve_plate_id(state)
    except (AttributeError, TypeError):
        plate = None
    return tuple(getattr(state, field, None) for field in ("subtask_id", "subtask_name", "gcode_file")) + (plate,)


async def load_archive_objects(archive, client, base_dir, *, expected_identity, is_current):
    from backend.app.services.archive import extract_printable_objects_from_3mf

    state = client.state
    if print_identity(state) != expected_identity or not is_current():
        raise PrintChangedDuringReload("Print changed while reloading objects")
    path = local_archive_file(archive, base_dir)
    if path is None:
        return False
    identity = expected_identity

    def parse():
        return extract_printable_objects_from_3mf(path.read_bytes(), plate_number=identity[-1], include_positions=True)

    result = await asyncio.to_thread(parse)
    if client.state is not state or print_identity(state) != identity or not is_current():
        raise PrintChangedDuringReload("Print changed while reloading objects")
    if not isinstance(result, tuple) or len(result) != 2:
        return False
    objects, bounds = result
    if not objects:
        return False
    state.printable_objects = objects
    state.printable_objects_bbox_all = bounds
    return True


async def restore_running_objects(printer_id, *, manager, bindings, session_factory, base_dir):
    client = manager.get_client(printer_id)
    if client is None or client.state.printable_objects:
        return
    expected = print_identity(client.state)
    try:
        async with session_factory() as db:
            archive = await find_running_archive(
                db,
                printer_id,
                client.state,
                bindings=bindings,
                printing_only=True,
                by_name=False,
            )
        if archive is not None:
            await load_archive_objects(
                archive,
                client,
                base_dir,
                expected_identity=expected,
                is_current=lambda: manager.get_client(printer_id) is client,
            )
    except PrintChangedDuringReload:
        logger.debug("Printer %s changed prints during object recovery", printer_id)
    except Exception as error:
        logger.debug("Could not restore objects for printer %s: %s", printer_id, error)
