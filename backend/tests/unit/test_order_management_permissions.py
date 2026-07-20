"""Contract tests for order-management permissions and default roles."""

from collections import Counter

from backend.app.core.permissions import DEFAULT_GROUPS, PERMISSION_CATEGORIES, Permission

ORDER_PERMISSIONS = {
    "CUSTOMERS_READ": "customers:read",
    "CUSTOMERS_MANAGE": "customers:manage",
    "CALCULATIONS_READ": "calculations:read",
    "CALCULATIONS_UPDATE": "calculations:update",
    "CALCULATIONS_APPROVE": "calculations:approve",
    "ORDERS_READ": "orders:read",
    "ORDERS_UPDATE": "orders:update",
    "ORDERS_CANCEL": "orders:cancel",
    "ORDERS_MANAGE_PRODUCTION": "orders:manage_production",
    "COMMERCIAL_DOCUMENTS_READ": "commercial_documents:read",
    "COMMERCIAL_DOCUMENTS_DRAFT": "commercial_documents:draft",
    "COMMERCIAL_DOCUMENTS_APPROVE": "commercial_documents:approve",
    "COMMERCIAL_DOCUMENTS_ISSUE": "commercial_documents:issue",
    "COMMERCIAL_DOCUMENTS_CORRECT": "commercial_documents:correct",
    "COMMERCIAL_DOCUMENTS_EXPORT": "commercial_documents:export",
    "COMMERCIAL_DOCUMENTS_TAX_OVERRIDE": "commercial_documents:tax_override",
    "DOCUMENT_TEMPLATES_READ": "document_templates:read",
    "DOCUMENT_TEMPLATES_MANAGE": "document_templates:manage",
    "PAYMENTS_READ": "payments:read",
    "PAYMENTS_MANAGE": "payments:manage",
    "ORDER_AUDIT_READ": "order_audit:read",
    "ORDER_SETTINGS_READ": "order_settings:read",
    "ORDER_SETTINGS_MANAGE": "order_settings:manage",
    "ACCOUNTING_INTEGRATIONS_MANAGE": "accounting_integrations:manage",
}

OPERATOR_DEFAULTS = {
    "customers:read",
    "customers:manage",
    "calculations:read",
    "calculations:update",
    "calculations:approve",
    "orders:read",
    "orders:update",
    "orders:manage_production",
    "commercial_documents:read",
    "commercial_documents:draft",
    "commercial_documents:approve",
    "payments:read",
    "order_audit:read",
}

VIEWER_DEFAULTS = {
    "customers:read",
    "calculations:read",
    "orders:read",
    "commercial_documents:read",
    "payments:read",
    "order_audit:read",
}


def test_order_permission_enum_contract():
    enum_values = {permission.value for permission in Permission}

    assert set(ORDER_PERMISSIONS.values()).issubset(enum_values)
    for member_name, value in ORDER_PERMISSIONS.items():
        assert getattr(Permission, member_name).value == value


def test_order_management_category_contains_each_order_permission_once():
    order_category = PERMISSION_CATEGORIES["Order Management"]
    categorized_counts = Counter(
        permission.value for permissions in PERMISSION_CATEGORIES.values() for permission in permissions
    )

    assert {permission.value for permission in order_category} == set(ORDER_PERMISSIONS.values())
    assert len(order_category) == len(ORDER_PERMISSIONS)
    assert all(categorized_counts[value] == 1 for value in ORDER_PERMISSIONS.values())


def test_operator_order_defaults_are_least_privilege():
    order_values = set(ORDER_PERMISSIONS.values())
    operator_permissions = set(DEFAULT_GROUPS["Operators"]["permissions"])

    assert operator_permissions & order_values == OPERATOR_DEFAULTS
    assert "orders:cancel" not in operator_permissions
    assert "commercial_documents:issue" not in operator_permissions
    assert "commercial_documents:correct" not in operator_permissions
    assert "commercial_documents:export" not in operator_permissions
    assert "commercial_documents:tax_override" not in operator_permissions
    assert "document_templates:read" not in operator_permissions
    assert "document_templates:manage" not in operator_permissions
    assert "payments:manage" not in operator_permissions
    assert "order_settings:read" not in operator_permissions
    assert "order_settings:manage" not in operator_permissions
    assert "accounting_integrations:manage" not in operator_permissions


def test_viewer_order_defaults_are_read_only():
    order_values = set(ORDER_PERMISSIONS.values())
    viewer_permissions = set(DEFAULT_GROUPS["Viewers"]["permissions"])

    assert viewer_permissions & order_values == VIEWER_DEFAULTS
    assert not any(
        action in permission
        for permission in viewer_permissions & order_values
        for action in (":manage", ":update", ":draft", ":approve", ":issue", ":cancel", ":export")
    )


def test_order_settings_defaults_are_administrator_only():
    for permission in ("order_settings:read", "order_settings:manage"):
        assert permission in DEFAULT_GROUPS["Administrators"]["permissions"]
        assert permission not in DEFAULT_GROUPS["Operators"]["permissions"]
        assert permission not in DEFAULT_GROUPS["Viewers"]["permissions"]


def test_document_template_and_tax_override_permissions_are_administrator_only():
    administrator_permissions = set(DEFAULT_GROUPS["Administrators"]["permissions"])
    operator_permissions = set(DEFAULT_GROUPS["Operators"]["permissions"])
    viewer_permissions = set(DEFAULT_GROUPS["Viewers"]["permissions"])

    protected_permissions = {
        "document_templates:read",
        "document_templates:manage",
        "commercial_documents:tax_override",
    }

    assert protected_permissions <= administrator_permissions
    assert protected_permissions.isdisjoint(operator_permissions)
    assert protected_permissions.isdisjoint(viewer_permissions)


def test_document_template_and_tax_override_permissions_are_administrator_only():
    administrator_permissions = set(DEFAULT_GROUPS["Administrators"]["permissions"])
    operator_permissions = set(DEFAULT_GROUPS["Operators"]["permissions"])
    viewer_permissions = set(DEFAULT_GROUPS["Viewers"]["permissions"])

    protected_permissions = {
        "document_templates:read",
        "document_templates:manage",
        "commercial_documents:tax_override",
    }

    assert protected_permissions <= administrator_permissions
    assert protected_permissions.isdisjoint(operator_permissions)
    assert protected_permissions.isdisjoint(viewer_permissions)
