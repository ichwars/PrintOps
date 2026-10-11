"""Additive commercial settings and production-quality schema migrations."""

from sqlalchemy import text


async def migrate_commercial_settings(conn, _safe_execute, is_sqlite) -> None:
    # Migration: business-profile document, tax, and payment settings.
    await _safe_execute(conn, "ALTER TABLE business_profiles ADD COLUMN tax_mode VARCHAR(16) DEFAULT 'standard'")
    await _safe_execute(conn, "ALTER TABLE business_profiles ADD COLUMN default_tax_rate NUMERIC(5, 2) DEFAULT 0")
    boolean_false = "0" if is_sqlite() else "false"
    boolean_true = "1" if is_sqlite() else "true"
    await _safe_execute(
        conn,
        f"ALTER TABLE business_profiles ADD COLUMN cash_accounting BOOLEAN DEFAULT {boolean_false}",
    )
    await _safe_execute(
        conn,
        f"ALTER TABLE business_profiles ADD COLUMN input_tax_deductible BOOLEAN DEFAULT {boolean_true}",
    )
    await _safe_execute(
        conn,
        f"ALTER TABLE business_profiles ADD COLUMN show_offer_qr BOOLEAN DEFAULT {boolean_false}",
    )
    await _safe_execute(conn, "ALTER TABLE business_profiles ADD COLUMN paypal_me_url VARCHAR(500)")
    await _safe_execute(conn, "ALTER TABLE business_profiles ADD COLUMN logo_media_type VARCHAR(32)")
    await _safe_execute(conn, "ALTER TABLE business_profiles ADD COLUMN logo_version INTEGER")
    # Migration: Complete the calculation request and commercial context.
    await _safe_execute(conn, "ALTER TABLE calculations ADD COLUMN project_id INTEGER REFERENCES projects(id)")
    await _safe_execute(conn, "ALTER TABLE calculations ADD COLUMN request_kind VARCHAR(24) DEFAULT 'single'")
    await _safe_execute(conn, "ALTER TABLE calculations ADD COLUMN quantity INTEGER DEFAULT 1")
    await _safe_execute(conn, "ALTER TABLE calculations ADD COLUMN position_description TEXT")
    await _safe_execute(conn, "ALTER TABLE calculations ADD COLUMN special_terms TEXT")
    if is_sqlite():
        await _safe_execute(conn, "ALTER TABLE calculations ADD COLUMN commercial_overrides JSON DEFAULT '{}'")
    else:
        await _safe_execute(conn, "ALTER TABLE calculations ADD COLUMN commercial_overrides JSON DEFAULT '{}'::json")
    if is_sqlite():
        profile_defaults_sql = (
            "UPDATE business_profiles SET "
            "tax_mode = COALESCE(tax_mode, 'standard'), "
            "default_tax_rate = CASE WHEN country_code = 'DE' THEN 19.00 ELSE 0.00 END, "
            "cash_accounting = COALESCE(cash_accounting, 0), "
            "input_tax_deductible = COALESCE(input_tax_deductible, 1), "
            "show_offer_qr = COALESCE(show_offer_qr, 0) "
            "WHERE default_tax_rate IS NULL OR tax_mode IS NULL "
            "OR cash_accounting IS NULL OR input_tax_deductible IS NULL OR show_offer_qr IS NULL"
        )
    else:
        profile_defaults_sql = (
            "UPDATE business_profiles SET "
            "tax_mode = COALESCE(tax_mode, 'standard'), "
            "default_tax_rate = CASE WHEN country_code = 'DE' THEN 19.00 ELSE 0.00 END, "
            "cash_accounting = COALESCE(cash_accounting, false), "
            "input_tax_deductible = COALESCE(input_tax_deductible, true), "
            "show_offer_qr = COALESCE(show_offer_qr, false) "
            "WHERE default_tax_rate IS NULL OR tax_mode IS NULL "
            "OR cash_accounting IS NULL OR input_tax_deductible IS NULL OR show_offer_qr IS NULL"
        )
    async with conn.begin_nested():
        await conn.execute(text(profile_defaults_sql))


async def migrate_production_quality(conn, _safe_execute, is_sqlite) -> None:
    """Additive migration; historical production is never made pending."""
    timestamp = "DATETIME" if is_sqlite() else "TIMESTAMP"
    for table in ("print_archives", "print_log_entries"):
        for column, declaration in (
            ("confirm_requested", "BOOLEAN DEFAULT FALSE"),
            ("user_verdict", "VARCHAR(10)"),
            ("good_quantity", "INTEGER"),
            ("reject_quantity", "INTEGER"),
            ("user_verdict_source", "VARCHAR(16)"),
            ("user_verdict_at", timestamp),
        ):
            await _safe_execute(conn, f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
    for column, declaration in (
        ("project_id", "INTEGER REFERENCES projects(id) ON DELETE SET NULL"),
        ("quantity", "INTEGER NOT NULL DEFAULT 1"),
        ("confirm_token_hash", "VARCHAR(64)"),
        ("confirm_token_expires_at", timestamp),
        ("confirm_token_used_at", timestamp),
        ("confirm_prompted_at", timestamp),
    ):
        await _safe_execute(conn, f"ALTER TABLE print_log_entries ADD COLUMN {column} {declaration}")
    await _safe_execute(conn, "ALTER TABLE print_queue ADD COLUMN confirm_outcome BOOLEAN DEFAULT FALSE")
    await _safe_execute(conn, "ALTER TABLE print_queue ADD COLUMN expected_parts INTEGER")
    await _safe_execute(
        conn, "ALTER TABLE notification_providers ADD COLUMN on_print_confirm_request BOOLEAN DEFAULT TRUE"
    )
    await _safe_execute(
        conn,
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_print_log_entries_confirm_token_hash ON print_log_entries(confirm_token_hash)",
    )
    await _safe_execute(
        conn, "CREATE INDEX IF NOT EXISTS ix_print_log_entries_project_id ON print_log_entries(project_id)"
    )
    constraint = (
        "quantity >= 1 AND ((good_quantity IS NULL AND reject_quantity IS NULL) OR "
        "(good_quantity IS NOT NULL AND reject_quantity IS NOT NULL AND "
        "good_quantity >= 0 AND reject_quantity >= 0 AND good_quantity + reject_quantity = quantity))"
    )
    if is_sqlite():
        # SQLite cannot ADD CONSTRAINT on an existing table. Equivalent triggers
        # protect upgraded installs without rebuilding unrelated archive/log FKs.
        for operation in ("INSERT", "UPDATE"):
            predicate = constraint.replace("good_quantity", "NEW.good_quantity").replace(
                "reject_quantity", "NEW.reject_quantity"
            )
            predicate = predicate.replace("= quantity", "= NEW.quantity").replace("quantity >= 1", "NEW.quantity >= 1")
            await _safe_execute(
                conn,
                f"CREATE TRIGGER IF NOT EXISTS print_log_quality_{operation.lower()} "
                f"BEFORE {operation} ON print_log_entries WHEN NOT ({predicate}) "
                "BEGIN SELECT RAISE(ABORT, 'Invalid production quality quantities'); END",
            )
    else:
        await _safe_execute(
            conn,
            "ALTER TABLE print_log_entries ADD CONSTRAINT ck_print_log_quality_quantities CHECK (" + constraint + ")",
        )


_USER_PRINT_TEMPLATE_RENAMES: tuple[tuple[str, str, str], ...] = (
    ("user_print_start", "User Print Started", "User Print Started Email"),
    ("user_print_complete", "User Print Completed", "User Print Completed Email"),
    ("user_print_failed", "User Print Failed", "User Print Failed Email"),
    ("user_print_stopped", "User Print Stopped", "User Print Stopped Email"),
)


async def migrate_rename_user_print_template_names(conn) -> None:
    """Append " Email" to the four ``user_print_*`` notification template names (#1792).

    The provider-level "Print Completed" and the per-user "User Print Completed"
    rows were visually indistinguishable in the Message Templates list because
    the seed name lacked the suffix that the EVENT_NAMES display map in
    routes/notification_templates.py already uses ("User Print Completed Email").

    Renames only rows where ``name`` is still the old default — admins who
    renamed the template themselves keep their custom name. Standard SQL
    UPDATE works on both SQLite and Postgres.
    """
    from sqlalchemy import text

    async with conn.begin_nested():
        for event_type, old_name, new_name in _USER_PRINT_TEMPLATE_RENAMES:
            await conn.execute(
                text("UPDATE notification_templates SET name = :new WHERE event_type = :et AND name = :old"),
                {"new": new_name, "et": event_type, "old": old_name},
            )
