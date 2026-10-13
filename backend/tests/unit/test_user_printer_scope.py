from types import SimpleNamespace


def test_user_can_access_printer_allows_unscoped_users_and_unbound_resources():
    from backend.app.core.auth import user_can_access_printer

    assert user_can_access_printer(SimpleNamespace(allowed_printer_ids=None), 7) is True
    assert user_can_access_printer(SimpleNamespace(allowed_printer_ids=[3]), None) is True


def test_user_can_access_printer_restricts_scoped_users():
    from backend.app.core.auth import user_can_access_printer

    user = SimpleNamespace(allowed_printer_ids=[3, 5])

    assert user_can_access_printer(user, 3) is True
    assert user_can_access_printer(user, 7) is False


def test_empty_user_printer_scope_denies_printers():
    from backend.app.core.auth import allowed_printer_ids_for_user, user_can_access_printer

    user = SimpleNamespace(allowed_printer_ids=[])
    assert allowed_printer_ids_for_user(user) == set()
    assert user_can_access_printer(user, 7) is False


async def test_scope_write_preparation_refuses_pending_mutations(db_session, printer_factory):
    import pytest

    from backend.app.core.user_printer_scope import prepare_printer_scope_write

    printer = await printer_factory()
    printer.name = "Pending change must survive"
    with pytest.raises(RuntimeError, match="precede mutations"):
        await prepare_printer_scope_write(db_session)
    assert printer in db_session.dirty
    assert printer.name == "Pending change must survive"


async def test_scope_write_preparation_leaves_postgres_row_lock_order_unchanged():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from backend.app.core.user_printer_scope import prepare_printer_scope_write

    db = MagicMock()
    db.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    db.rollback = AsyncMock()
    db.execute = AsyncMock()
    await prepare_printer_scope_write(db)
    db.rollback.assert_not_awaited()
    db.execute.assert_not_awaited()


async def test_scope_migration_history_survives_git_settings_collect_and_restore(db_session):
    from sqlalchemy import select

    from backend.app.core.user_printer_scope import USER_PRINTER_SCOPE_MIGRATION_KEY
    from backend.app.models.settings import Settings
    from backend.app.services.github_backup import github_backup_service
    from backend.app.services.github_restore import SETTINGS_PATH, GitHubRestoreService, _CategoryTally

    db_session.add(Settings(key=USER_PRINTER_SCOPE_MIGRATION_KEY, value="true"))
    await db_session.commit()
    files = {}
    await github_backup_service._collect_settings(db_session, files)
    assert files[SETTINGS_PATH]["settings"][USER_PRINTER_SCOPE_MIGRATION_KEY] == "true"
    # Category restore upserts supplied app settings, preserving local history
    # even for older backups which omitted this private migration marker.
    await GitHubRestoreService()._restore_settings(
        db_session, {"settings": {"currency": "EUR"}}, overwrite=True, tally=_CategoryTally()
    )
    await db_session.commit()
    marker = await db_session.scalar(select(Settings).where(Settings.key == USER_PRINTER_SCOPE_MIGRATION_KEY))
    assert marker.value == "true"
