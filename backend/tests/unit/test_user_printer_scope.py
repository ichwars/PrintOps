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
