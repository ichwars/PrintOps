"""Add optional VP network configuration without changing existing rows."""


async def migrate_vp_network_config(conn, safe_execute, *, sqlite: bool) -> None:
    """Support SQLite and PostgreSQL through the idempotent DDL executor."""
    # Tailscale remains opt-in; PostgreSQL requires a boolean literal.
    default = "1" if sqlite else "true"
    await safe_execute(conn, f"ALTER TABLE virtual_printers ADD COLUMN tailscale_disabled BOOLEAN DEFAULT {default}")
    await safe_execute(conn, "ALTER TABLE virtual_printers ADD COLUMN advertised_ip VARCHAR(15)")
