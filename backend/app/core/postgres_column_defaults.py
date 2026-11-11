"""Align previously migrated PostgreSQL column defaults and nullability."""

from decimal import Decimal, InvalidOperation

from sqlalchemy import Boolean, Numeric, inspect
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql.schema import MetaData

_COLUMNS = {
    "api_keys": (
        "can_access_cloud",
        "can_manage_archives",
        "can_manage_inventory",
        "can_manage_library",
        "can_manage_maintenance",
        "can_manage_projects",
        "can_send_notifications",
        "can_update_energy_cost",
    ),
    "github_backup_config": ("allow_insecure_http", "provider"),
    "library_files": ("variant_position",),
    "notification_providers": (
        "attach_photo",
        "on_ai_failure_detection",
        "on_app_message",
        "on_ha_sensor_alert",
        "on_print_confirm_request",
        "on_stock_break_alert",
        "on_stock_reorder_alert",
    ),
    "oidc_providers": (
        "auto_link_existing_accounts",
        "email_claim",
        "is_autologin",
        "is_env_managed",
        "require_email_verified",
    ),
    "print_queue": (
        "bed_levelling",
        "cleanup_library_after_dispatch",
        "confirm_outcome",
        "dispatch_attempts",
        "filament_short",
        "flow_cali",
        "gate_acknowledged",
        "nozzle_offset_cali",
        "preheat_override",
        "skip_filament_check",
    ),
    "smart_plugs": (
        "auto_off_after_drying",
        "controls_printer_power",
        "off_delay_after_drying_minutes",
        "rest_energy_total_multiplier",
    ),
    "spool": ("weight_used_baseline",),
    "virtual_printers": ("gcode_injection", "queue_force_color_match", "tailscale_disabled"),
}
# Preserve the behavior of an existing NULL in fields that control actions.
_BACKFILL_FALSE = {
    ("notification_providers", "attach_photo"),
    ("print_queue", "bed_levelling"),
    ("print_queue", "nozzle_offset_cali"),
    ("smart_plugs", "controls_printer_power"),
}


def _literal_default(value: str | None, column_type) -> str | Decimal | None:
    if value is None:
        return None
    # PostgreSQL adds casts to literals and may render a float without ".0".
    literal = value.split("::", 1)[0].strip("'")
    if isinstance(column_type, Boolean):
        lower = literal.lower()
        return {"0": "false", "1": "true", "f": "false", "t": "true"}.get(lower, lower)
    if isinstance(column_type, Numeric):
        try:
            return Decimal(literal)
        except InvalidOperation:
            return literal
    return literal


def _matches(column, default: str, installed: dict | None) -> bool:
    if installed is None or installed["nullable"] != column.nullable:
        return False
    return _literal_default(installed["default"], column.type) == _literal_default(default, column.type)


async def _align_table(conn: AsyncConnection, table: str, desired, compiler) -> None:
    quote = conn.dialect.identifier_preparer.quote_identifier
    table_sql = quote(table)
    await conn.exec_driver_sql(f"LOCK TABLE {table_sql} IN ACCESS EXCLUSIVE MODE")
    existing = await conn.run_sync(lambda sync: inspect(sync).get_columns(table))
    installed = {item["name"]: item for item in existing}
    for column, default in desired:
        current = installed.get(column.name)
        if _matches(column, default, current):
            continue
        name = quote(column.name)
        if current is None:
            type_sql = compiler.dialect.type_compiler_instance.process(column.type)
            await conn.exec_driver_sql(f"ALTER TABLE {table_sql} ADD COLUMN {name} {type_sql}")
            current = {"nullable": True, "default": None}
        await conn.exec_driver_sql(f"ALTER TABLE {table_sql} ALTER COLUMN {name} SET DEFAULT {default}")
        if current["nullable"] and not column.nullable:
            fill = "false" if (table, column.name) in _BACKFILL_FALSE else default
            assignments = f"{name} = {fill}"
            if (table, column.name) == ("oidc_providers", "email_claim"):
                # An absent email claim could not link an account. Retain that
                # behavior when giving the provider its new default claim.
                assignments += ", auto_link_existing_accounts = false"
            sql = f"UPDATE {table_sql} SET {assignments} WHERE {name} IS NULL"  # noqa: S608
            await conn.exec_driver_sql(sql)
            await conn.exec_driver_sql(f"ALTER TABLE {table_sql} ALTER COLUMN {name} SET NOT NULL")
        elif not current["nullable"] and column.nullable:
            await conn.exec_driver_sql(f"ALTER TABLE {table_sql} ALTER COLUMN {name} DROP NOT NULL")


async def migrate_postgres_column_defaults(conn: AsyncConnection, metadata: MetaData) -> None:
    if conn.dialect.name != "postgresql":
        return
    compiler = conn.dialect.ddl_compiler(conn.dialect, None)
    reflected = await conn.run_sync(lambda sync: inspect(sync).get_multi_columns(filter_names=list(_COLUMNS)))
    for table, names in _COLUMNS.items():
        installed = {item["name"]: item for item in reflected[(None, table)]}
        desired = []
        for name in names:
            column = metadata.tables[table].c[name]
            default = compiler.get_column_default_string(column)
            if default is None:
                raise RuntimeError(f"Missing model default for {table}.{name}")
            desired.append((column, default))
        if any(not _matches(column, default, installed.get(column.name)) for column, default in desired):
            await _align_table(conn, table, desired, compiler)
