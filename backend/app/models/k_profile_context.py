"""Portable unique storage identity for explicitly reported nozzle flow.

NULL keeps old unknown-flow rows intact, including ambiguous legacy selections.
API writes reject duplicate unknown contexts; the calibration resolver rejects
ambiguous persisted rows rather than selecting one by index.
"""

from sqlalchemy import Index, case, func
from sqlalchemy.sql.expression import Grouping


def attach_context_index(table, spool_key):
    prefix = func.upper(func.substr(func.trim(table.c.nozzle_type), 1, 2))
    flow = case((prefix.in_(("HS", "HH")), prefix), else_=None)
    return Index(
        f"uq_{table.name}_context",
        table.c[spool_key],
        table.c.printer_id,
        table.c.extruder,
        table.c.nozzle_diameter,
        Grouping(flow),
        unique=True,
    )
