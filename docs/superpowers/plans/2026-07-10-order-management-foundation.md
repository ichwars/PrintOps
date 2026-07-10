# Order Management Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the first usable order-management increment: configurable issuing business profiles, concurrency-safe customer numbering, relational customer master data, complete access control, APIs, settings UI, and customer UI.

**Architecture:** Add a focused modular domain inside the existing FastAPI/SQLAlchemy application. Relational tables own mutable business data; service functions own aggregate replacement, default-profile invariants, numbering, and optimistic locking. React pages use the existing API client and TanStack Query, while Settings keeps its current canonical-tab/sub-tab architecture.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 async, SQLite/PostgreSQL, React 19, TypeScript 5.9, TanStack Query 5, React Router 7, Tailwind CSS 4, Vitest, Testing Library, pytest, Ruff.

## Global Constraints

- Source design: `docs/superpowers/specs/2026-07-10-order-management-design.md`.
- All repository writes, commits, pushes, and pull requests target `ichwars/PrintOps`; never push to `maziggy/bambuddy`.
- Keep `origin` as the write remote and `upstream` fetch-only with disabled push URL.
- Support both SQLite and PostgreSQL.
- Store money as SQL `NUMERIC` and Python `Decimal`, never binary floats.
- Store country codes as uppercase ISO 3166-1 alpha-2 and currencies as uppercase ISO 4217 alpha-3.
- Store business timestamps in UTC and legal dates separately in later increments.
- API keys receive no order-management capability in this increment; new permissions remain unmapped and fail closed.
- Operators may manage customers, calculations, orders, and production, but may not issue invoices or configure integrations by default.
- Issuer profiles are configurations within one installation, not security tenants.
- Customer mutable data is relational; JSON may not be used as the primary customer/profile store.
- Follow existing `backend/app/core/database.py` model-registration and system-group backfill patterns.
- Follow existing frontend design language: compact operational tables, Lucide icon buttons with tooltips, no nested cards, stable dimensions, and explicit loading/empty/error/permission states.
- Every task starts with a failing focused test, ends with passing focused tests, and produces one intentional commit.

## Scope Boundary

This plan implements delivery increment 1 from the design. It deliberately does not add calculations, quotations, orders, reservations, documents, PDF rendering, EN 16931, payments, or Lexware network calls. It defines the stable profile, customer, permission, numbering, and frontend contracts those later implementation plans consume.

## File Structure

### Backend files to create

- `backend/app/models/business_profile.py`: issuer profile, addresses, tax identifiers, and bank accounts.
- `backend/app/models/number_sequence.py`: per-profile sequence configuration and optimistic counter.
- `backend/app/models/customer.py`: customer identity, profile account, contacts, addresses, tax IDs, and tags.
- `backend/app/schemas/business_profile.py`: nested create/update/response contracts.
- `backend/app/schemas/customer.py`: customer detail and paginated list contracts.
- `backend/app/services/order_errors.py`: shared domain exceptions mapped by routes.
- `backend/app/services/number_sequence.py`: format validation and atomic reservation.
- `backend/app/services/business_profile.py`: profile aggregate CRUD and default-profile invariant.
- `backend/app/services/customer.py`: customer aggregate CRUD, filtering, and number allocation.
- `backend/app/api/routes/business_profiles.py`: issuer-profile HTTP API.
- `backend/app/api/routes/customers.py`: customer HTTP API.
- `backend/tests/unit/test_order_management_permissions.py`: permission/default-group contract.
- `backend/tests/unit/services/test_number_sequence.py`: formatting/reset/reservation behavior.
- `backend/tests/integration/test_business_profiles_api.py`: nested profile CRUD and locking.
- `backend/tests/integration/test_customers_api.py`: customer CRUD, search, uniqueness, and locking.

### Backend files to modify

- `backend/app/models/__init__.py`: export the new models.
- `backend/app/core/database.py`: register models and add additive system-group permission backfill.
- `backend/app/core/permissions.py`: define and categorize the complete order-management permission set.
- `backend/app/main.py`: import and mount the two routers.
- `backend/tests/conftest.py`: register the new models for in-memory test metadata.
- `backend/tests/integration/test_groups_api.py`: assert the new category is returned.

### Frontend files to create

- `frontend/src/components/orders/CustomerEditorModal.tsx`: complete create/edit form.
- `frontend/src/components/orders/CustomerDetailsModal.tsx`: read-only customer/account/contact/address detail.
- `frontend/src/components/settings/BusinessProfileSettings.tsx`: profile list, default selection, and editor.
- `frontend/src/components/settings/BusinessProfileEditorModal.tsx`: nested profile form.
- `frontend/src/pages/OrdersCustomersPage.tsx`: searchable, filterable customer workspace.
- `frontend/src/__tests__/components/BusinessProfileSettings.test.tsx`: settings behavior.
- `frontend/src/__tests__/pages/OrdersCustomersPage.test.tsx`: customer workflow.

### Frontend files to modify

- `frontend/src/api/client.ts`: permission union, API types, and methods.
- `frontend/src/App.tsx`: route `/orders/customers` to the dedicated page.
- `frontend/src/pages/OrdersPage.tsx`: remove the now-dedicated customer placeholder branch.
- `frontend/src/components/Layout.tsx`: permission-gate the orders parent and children.
- `frontend/src/lib/settingsNavigation.ts`: add the `business-profile` order-management sub-tab.
- `frontend/src/pages/SettingsPage.tsx`: render profile settings and retain calculation defaults.
- `frontend/src/i18n/locales/*.ts`: add parity-safe order/profile/customer keys in every locale; German and English receive native copy, other locales receive English fallback copy.
- `frontend/src/__tests__/components/Layout.test.tsx`: verify order navigation permissions.
- `frontend/src/__tests__/lib/settingsNavigation.test.ts`: verify the new sub-tab.
- `frontend/src/__tests__/pages/SettingsPage.test.tsx`: verify profile settings routing/search.

## Stable Interfaces Produced by This Plan

```text
backend.app.services.number_sequence.validate_number_pattern(pattern: str) -> str
backend.app.services.number_sequence.format_number(*, pattern: str, prefix: str, value: int, effective_date: date) -> str
backend.app.services.number_sequence.reserve_number(db: AsyncSession, *, business_profile_id: int, key: str, effective_date: date) -> str

backend.app.services.business_profile.list_business_profiles(db: AsyncSession, *, include_inactive: bool = False) -> list[BusinessProfile]
backend.app.services.business_profile.create_business_profile(db: AsyncSession, data: BusinessProfileCreate) -> BusinessProfile
backend.app.services.business_profile.replace_business_profile(db: AsyncSession, profile_id: int, data: BusinessProfileUpdate) -> BusinessProfile
backend.app.services.business_profile.set_default_business_profile(db: AsyncSession, profile_id: int) -> BusinessProfile
backend.app.services.business_profile.delete_business_profile(db: AsyncSession, profile_id: int) -> None

backend.app.services.customer.list_customers(db: AsyncSession, *, business_profile_id: int, search: str | None, status: str | None, kind: str | None, limit: int, offset: int) -> tuple[list[CustomerListItem], int]
backend.app.services.customer.get_customer(db: AsyncSession, customer_id: int) -> Customer
backend.app.services.customer.create_customer(db: AsyncSession, data: CustomerCreate) -> Customer
backend.app.services.customer.replace_customer(db: AsyncSession, customer_id: int, data: CustomerUpdate) -> Customer
backend.app.services.customer.delete_customer(db: AsyncSession, customer_id: int) -> None
```

Do not rename these interfaces without updating this plan and every consumer in the same commit.

---

### Task 1: Add Relational Profile, Sequence, and Customer Models

**Files:**
- Create: `backend/app/models/business_profile.py`
- Create: `backend/app/models/number_sequence.py`
- Create: `backend/app/models/customer.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/database.py:160-215`
- Modify: `backend/tests/conftest.py:100-155`
- Test: `backend/tests/integration/test_order_foundation_schema.py`

**Interfaces:**
- Consumes: existing `backend.app.core.database.Base` and SQLAlchemy 2 typed mappings.
- Produces: model classes named in the domain design and imported before `Base.metadata.create_all()`.

- [ ] **Step 1: Write the failing schema-registration test**

Create `backend/tests/integration/test_order_foundation_schema.py`:

```python
import pytest
from sqlalchemy import inspect


@pytest.mark.asyncio
async def test_order_foundation_tables_are_registered(test_engine):
    async with test_engine.begin() as connection:
        table_names = await connection.run_sync(lambda sync_connection: set(inspect(sync_connection).get_table_names()))

    assert {
        "business_profiles",
        "business_profile_addresses",
        "business_profile_tax_identifiers",
        "business_profile_bank_accounts",
        "number_sequences",
        "customers",
        "customer_accounts",
        "customer_contacts",
        "customer_addresses",
        "customer_tax_identifiers",
        "customer_tags",
        "customer_tag_links",
    } <= table_names
```

- [ ] **Step 2: Run the test and verify the missing-table failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_order_foundation_schema.py -v
```

Expected: FAIL because the asserted tables are absent.

- [ ] **Step 3: Implement the issuer and numbering models**

In `backend/app/models/business_profile.py`, define these classes and constraints:

```python
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class BusinessProfile(Base):
    __tablename__ = "business_profiles"
    __table_args__ = (
        CheckConstraint("length(country_code) = 2", name="ck_business_profiles_country_code"),
        CheckConstraint("length(default_currency) = 3", name="ck_business_profiles_currency"),
        CheckConstraint("billing_mode IN ('internal', 'external', 'hybrid')", name="ck_business_profiles_billing_mode"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    legal_name: Mapped[str] = mapped_column(String(255))
    trading_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2))
    default_currency: Mapped[str] = mapped_column(String(3))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    default_locale: Mapped[str] = mapped_column(String(16), default="en")
    billing_mode: Mapped[str] = mapped_column(String(16), default="hybrid")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    addresses: Mapped[list["BusinessProfileAddress"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    tax_identifiers: Mapped[list["BusinessProfileTaxIdentifier"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    bank_accounts: Mapped[list["BusinessProfileBankAccount"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class BusinessProfileAddress(Base):
    __tablename__ = "business_profile_addresses"
    __table_args__ = (
        CheckConstraint("kind IN ('registered', 'billing', 'shipping', 'other')", name="ck_business_profile_address_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(ForeignKey("business_profiles.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    additional: Mapped[str | None] = mapped_column(String(255), nullable=True)
    street: Mapped[str] = mapped_column(String(255))
    street_2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    postal_code: Mapped[str] = mapped_column(String(32))
    city: Mapped[str] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class BusinessProfileTaxIdentifier(Base):
    __tablename__ = "business_profile_tax_identifiers"
    __table_args__ = (
        UniqueConstraint("business_profile_id", "kind", "value", name="uq_business_profile_tax_identifier"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(ForeignKey("business_profiles.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(64))
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)


class BusinessProfileBankAccount(Base):
    __tablename__ = "business_profile_bank_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(ForeignKey("business_profiles.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(100))
    account_holder: Mapped[str] = mapped_column(String(255))
    bank_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    iban: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bic: Mapped[str | None] = mapped_column(String(32), nullable=True)
    account_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    routing_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
```

In `backend/app/models/number_sequence.py`, define:

```python
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class NumberSequence(Base):
    __tablename__ = "number_sequences"
    __table_args__ = (
        UniqueConstraint("business_profile_id", "key", name="uq_number_sequence_profile_key"),
        CheckConstraint("next_value > 0", name="ck_number_sequence_next_value"),
        CheckConstraint("reset_policy IN ('none', 'yearly')", name="ck_number_sequence_reset_policy"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(ForeignKey("business_profiles.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(32))
    prefix: Mapped[str] = mapped_column(String(20), default="")
    pattern: Mapped[str] = mapped_column(String(100), default="{PREFIX}-{#####}")
    next_value: Mapped[int] = mapped_column(Integer, default=1)
    reset_policy: Mapped[str] = mapped_column(String(16), default="none")
    current_period: Mapped[str | None] = mapped_column(String(8), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 4: Implement the customer aggregate model**

In `backend/app/models/customer.py`, define `Customer`, `CustomerAccount`, `CustomerContact`, `CustomerAddress`, `CustomerTaxIdentifier`, `CustomerTag`, and the `customer_tag_links` association table with these invariants:

```python
customer_tag_links = Table(
    "customer_tag_links",
    Base.metadata,
    Column("customer_id", ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("customer_tags.id", ondelete="CASCADE"), primary_key=True),
)
```

```python
class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("kind IN ('company', 'person')", name="ck_customers_kind"),
        CheckConstraint("status IN ('active', 'inactive', 'blocked')", name="ck_customers_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))
    display_name: Mapped[str] = mapped_column(String(255), index=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    preferred_locale: Mapped[str] = mapped_column(String(16), default="en")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    accounts: Mapped[list["CustomerAccount"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    contacts: Mapped[list["CustomerContact"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    addresses: Mapped[list["CustomerAddress"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    tax_identifiers: Mapped[list["CustomerTaxIdentifier"]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    tags: Mapped[list["CustomerTag"]] = relationship(secondary=customer_tag_links, lazy="selectin")
```

Add the following exact constraints to child tables:

```python
UniqueConstraint("business_profile_id", "number", name="uq_customer_account_profile_number")
UniqueConstraint("customer_id", "business_profile_id", name="uq_customer_account_customer_profile")
UniqueConstraint("customer_id", "kind", "value", name="uq_customer_tax_identifier")
UniqueConstraint("name", name="uq_customer_tag_name")
```

Use `NUMERIC(5, 2)` for `CustomerAccount.discount_percent`, three-character `preferred_currency`, integer `payment_term_days`, text `delivery_terms`, and booleans `is_active`, `is_primary`, `include_on_documents`, and `is_default` as appropriate.

- [ ] **Step 5: Register every model in runtime and test metadata imports**

Add imports/exports in:

```python
# backend/app/models/__init__.py
from backend.app.models.business_profile import (
    BusinessProfile,
    BusinessProfileAddress,
    BusinessProfileBankAccount,
    BusinessProfileTaxIdentifier,
)
from backend.app.models.customer import (
    Customer,
    CustomerAccount,
    CustomerAddress,
    CustomerContact,
    CustomerTag,
    CustomerTaxIdentifier,
)
from backend.app.models.number_sequence import NumberSequence
```

Add `business_profile`, `customer`, and `number_sequence` to the model import tuples in `init_db()` and `backend/tests/conftest.py`.

- [ ] **Step 6: Run schema test and model lint**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_order_foundation_schema.py -v
.\.venv\Scripts\python.exe -m ruff check backend/app/models backend/tests/integration/test_order_foundation_schema.py
```

Expected: PASS and no Ruff findings.

- [ ] **Step 7: Commit the relational model foundation**

```powershell
git add backend/app/models backend/app/core/database.py backend/tests/conftest.py backend/tests/integration/test_order_foundation_schema.py
git commit -m "feat: add order management master data models"
```

---

### Task 2: Define Permissions and Safe Default-Group Backfill

**Files:**
- Modify: `backend/app/core/permissions.py:10-190`
- Modify: `backend/app/core/database.py:3406-3685`
- Modify: `frontend/src/api/client.ts:3130-3185`
- Create: `backend/tests/unit/test_order_management_permissions.py`
- Modify: `backend/tests/integration/test_groups_api.py`

**Interfaces:**
- Consumes: existing `Permission`, `PERMISSION_CATEGORIES`, `DEFAULT_GROUPS`, and additive `seed_default_groups()` behavior.
- Produces: the complete permission string contract used by all later order-management plans.

- [ ] **Step 1: Write the failing permission contract tests**

Create `backend/tests/unit/test_order_management_permissions.py`:

```python
from backend.app.core.permissions import DEFAULT_GROUPS, PERMISSION_CATEGORIES, Permission


ORDER_PERMISSIONS = {
    "customers:read",
    "customers:manage",
    "calculations:read",
    "calculations:update",
    "calculations:approve",
    "orders:read",
    "orders:update",
    "orders:cancel",
    "orders:manage_production",
    "commercial_documents:read",
    "commercial_documents:draft",
    "commercial_documents:approve",
    "commercial_documents:issue",
    "commercial_documents:correct",
    "commercial_documents:export",
    "payments:read",
    "payments:manage",
    "order_audit:read",
    "order_settings:read",
    "order_settings:manage",
    "accounting_integrations:manage",
}


def test_order_permissions_are_categorized_once():
    categorized = [permission.value for values in PERMISSION_CATEGORIES.values() for permission in values]
    assert ORDER_PERMISSIONS <= set(categorized)
    for permission in ORDER_PERMISSIONS:
        assert categorized.count(permission) == 1


def test_default_order_permissions_are_least_privilege():
    operators = set(DEFAULT_GROUPS["Operators"]["permissions"])
    viewers = set(DEFAULT_GROUPS["Viewers"]["permissions"])

    assert {"customers:manage", "calculations:update", "orders:manage_production"} <= operators
    assert "commercial_documents:issue" not in operators
    assert "accounting_integrations:manage" not in operators
    assert "order_settings:read" not in operators
    assert {"customers:read", "calculations:read", "orders:read", "commercial_documents:read"} <= viewers
    assert "customers:manage" not in viewers


def test_order_permissions_exist_in_enum():
    assert ORDER_PERMISSIONS <= {permission.value for permission in Permission}
```

- [ ] **Step 2: Run the permission tests and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_order_management_permissions.py -v
```

Expected: FAIL because the permission enum members do not exist.

- [ ] **Step 3: Add the exact permission enum and category entries**

Add these enum members to `Permission`:

```python
CUSTOMERS_READ = "customers:read"
CUSTOMERS_MANAGE = "customers:manage"
CALCULATIONS_READ = "calculations:read"
CALCULATIONS_UPDATE = "calculations:update"
CALCULATIONS_APPROVE = "calculations:approve"
ORDERS_READ = "orders:read"
ORDERS_UPDATE = "orders:update"
ORDERS_CANCEL = "orders:cancel"
ORDERS_MANAGE_PRODUCTION = "orders:manage_production"
COMMERCIAL_DOCUMENTS_READ = "commercial_documents:read"
COMMERCIAL_DOCUMENTS_DRAFT = "commercial_documents:draft"
COMMERCIAL_DOCUMENTS_APPROVE = "commercial_documents:approve"
COMMERCIAL_DOCUMENTS_ISSUE = "commercial_documents:issue"
COMMERCIAL_DOCUMENTS_CORRECT = "commercial_documents:correct"
COMMERCIAL_DOCUMENTS_EXPORT = "commercial_documents:export"
PAYMENTS_READ = "payments:read"
PAYMENTS_MANAGE = "payments:manage"
ORDER_AUDIT_READ = "order_audit:read"
ORDER_SETTINGS_READ = "order_settings:read"
ORDER_SETTINGS_MANAGE = "order_settings:manage"
ACCOUNTING_INTEGRATIONS_MANAGE = "accounting_integrations:manage"
```

Add one `Order Management` category containing those members exactly once. `order_settings:read` and `order_settings:manage` are intentionally administrator-only in the default groups because full issuer profiles include bank and tax identifiers.

- [ ] **Step 4: Apply the default-role policy and upgrade backfill**

Add these permissions to fresh-install `DEFAULT_GROUPS`:

```python
OPERATOR_ORDER_PERMISSIONS = [
    Permission.CUSTOMERS_READ.value,
    Permission.CUSTOMERS_MANAGE.value,
    Permission.CALCULATIONS_READ.value,
    Permission.CALCULATIONS_UPDATE.value,
    Permission.CALCULATIONS_APPROVE.value,
    Permission.ORDERS_READ.value,
    Permission.ORDERS_UPDATE.value,
    Permission.ORDERS_MANAGE_PRODUCTION.value,
    Permission.COMMERCIAL_DOCUMENTS_READ.value,
    Permission.COMMERCIAL_DOCUMENTS_DRAFT.value,
    Permission.COMMERCIAL_DOCUMENTS_APPROVE.value,
    Permission.PAYMENTS_READ.value,
    Permission.ORDER_AUDIT_READ.value,
]

VIEWER_ORDER_PERMISSIONS = [
    Permission.CUSTOMERS_READ.value,
    Permission.CALCULATIONS_READ.value,
    Permission.ORDERS_READ.value,
    Permission.COMMERCIAL_DOCUMENTS_READ.value,
    Permission.PAYMENTS_READ.value,
    Permission.ORDER_AUDIT_READ.value,
]
```

Inline those lists into Operators and Viewers instead of adding new module-level constants. In `seed_default_groups()`, add an additive backfill block after the administrator `ALL_PERMISSIONS` sync:

```python
order_backfill = {
    "Operators": [
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
    ],
    "Viewers": [
        "customers:read",
        "calculations:read",
        "orders:read",
        "commercial_documents:read",
        "payments:read",
        "order_audit:read",
    ],
}
```

For each named system group, append missing values without removing customized permissions and commit once.

- [ ] **Step 5: Update the frontend permission union**

Add every string from `ORDER_PERMISSIONS` to `Permission` in `frontend/src/api/client.ts`. Do not add any of them to `_APIKEY_SCOPE_BY_PERMISSION`; the backend's unmapped-permission behavior must remain fail-closed.

- [ ] **Step 6: Add API category assertion and run all permission tests**

Extend `backend/tests/integration/test_groups_api.py` to assert that `/api/v1/groups/permissions` contains an `Order Management` category with `customers:read` and `commercial_documents:issue`.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_permissions.py backend/tests/unit/test_order_management_permissions.py backend/tests/integration/test_groups_api.py -v
.\.venv\Scripts\python.exe -m ruff check backend/app/core/permissions.py backend/app/core/database.py backend/tests/unit/test_order_management_permissions.py
```

Expected: PASS and no Ruff findings.

- [ ] **Step 7: Commit the permission contract**

```powershell
git add backend/app/core/permissions.py backend/app/core/database.py backend/tests frontend/src/api/client.ts
git commit -m "feat: add order management permissions"
```

---

### Task 3: Implement Concurrency-Safe Number Sequences

**Files:**
- Create: `backend/app/services/order_errors.py`
- Create: `backend/app/services/number_sequence.py`
- Create: `backend/tests/unit/services/test_number_sequence.py`

**Interfaces:**
- Consumes: `NumberSequence` from Task 1 and caller-owned `AsyncSession` transactions.
- Produces: `validate_number_pattern()`, `format_number()`, and `reserve_number()` with no internal commit.

- [ ] **Step 1: Write formatting, yearly-reset, and atomic-reservation tests**

Create tests covering these exact cases:

```python
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.number_sequence import NumberSequence
from backend.app.services.number_sequence import format_number, reserve_number, validate_number_pattern


def test_format_number_replaces_supported_tokens():
    assert format_number(
        pattern="{PREFIX}-{YYYY}-{#####}",
        prefix="CUST",
        value=42,
        effective_date=date(2026, 7, 10),
    ) == "CUST-2026-00042"


@pytest.mark.parametrize("pattern", ["{PREFIX}", "{PREFIX}-{UNKNOWN}-{####}", "{PREFIX}-{###########}"])
def test_number_pattern_requires_one_supported_counter(pattern):
    with pytest.raises(ValueError):
        validate_number_pattern(pattern)


@pytest.mark.asyncio
async def test_yearly_sequence_resets_on_new_year(db_session):
    profile = BusinessProfile(
        name="Primary",
        legal_name="Primary Ltd",
        country_code="IE",
        default_currency="EUR",
        timezone="Europe/Dublin",
        default_locale="en-IE",
        billing_mode="hybrid",
    )
    db_session.add(profile)
    await db_session.flush()
    db_session.add(NumberSequence(
        business_profile_id=profile.id,
        key="customer",
        prefix="C",
        pattern="{PREFIX}-{YYYY}-{####}",
        next_value=88,
        reset_policy="yearly",
        current_period="2025",
    ))
    await db_session.commit()

    number = await reserve_number(
        db_session,
        business_profile_id=profile.id,
        key="customer",
        effective_date=date(2026, 1, 2),
    )

    assert number == "C-2026-0001"


@pytest.mark.asyncio
async def test_parallel_reservations_are_unique(test_engine):
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    async with sessions() as setup:
        profile = BusinessProfile(
            name="Concurrent",
            legal_name="Concurrent Inc",
            country_code="US",
            default_currency="USD",
            timezone="America/New_York",
            default_locale="en-US",
            billing_mode="internal",
        )
        setup.add(profile)
        await setup.flush()
        profile_id = profile.id
        setup.add(NumberSequence(
            business_profile_id=profile_id,
            key="customer",
            prefix="CUS",
            pattern="{PREFIX}-{#####}",
        ))
        await setup.commit()

    async def reserve_one() -> str:
        async with sessions() as session:
            value = await reserve_number(
                session,
                business_profile_id=profile_id,
                key="customer",
                effective_date=date(2026, 7, 10),
            )
            await session.commit()
            return value

    values = [await reserve_one() for _ in range(10)]
    assert len(values) == len(set(values)) == 10
```

The final concurrency test is deliberately sequential on the in-memory fixture because it uses one SQLite connection. Add a second PostgreSQL/SQLite-file integration test in the later document-numbering plan for true simultaneous writers.

- [ ] **Step 2: Run the focused tests and verify import failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_number_sequence.py -v
```

Expected: FAIL because `backend.app.services.number_sequence` does not exist.

- [ ] **Step 3: Implement shared domain exceptions**

Create `backend/app/services/order_errors.py`:

```python
class OrderDomainError(Exception):
    """Base class for expected order-domain conflicts."""


class ResourceNotFoundError(OrderDomainError):
    pass


class VersionConflictError(OrderDomainError):
    pass


class ResourceInUseError(OrderDomainError):
    pass


class DuplicateBusinessKeyError(OrderDomainError):
    pass
```

- [ ] **Step 4: Implement strict formatting and optimistic atomic update**

`validate_number_pattern()` must accept only `{PREFIX}`, `{YYYY}`, `{YY}`, and one numeric token containing 1-10 `#` characters. `format_number()` validates first, substitutes date/prefix, and pads the numeric token.

`reserve_number()` must:

1. select the unique `(business_profile_id, key)` row;
2. raise `ResourceNotFoundError` if absent;
3. derive `current_period` as the four-digit year for yearly sequences;
4. use `UPDATE number_sequences SET next_value=?, current_period=?, version=version+1 WHERE id=? AND version=? RETURNING id`;
5. retry the optimistic update up to 10 times without committing;
6. raise `VersionConflictError` after retry exhaustion;
7. return the number built from the value that was reserved, not the incremented value.

Use this exact SQLAlchemy update shape:

```python
statement = (
    update(NumberSequence)
    .where(NumberSequence.id == sequence.id, NumberSequence.version == sequence.version)
    .values(
        next_value=reserved_value + 1,
        current_period=period,
        version=NumberSequence.version + 1,
    )
    .returning(NumberSequence.id)
)
```

Expire the selected row after a failed optimistic update before retrying.

- [ ] **Step 5: Run sequence tests and lint**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/unit/services/test_number_sequence.py -v
.\.venv\Scripts\python.exe -m ruff check backend/app/services/order_errors.py backend/app/services/number_sequence.py backend/tests/unit/services/test_number_sequence.py
```

Expected: PASS and no Ruff findings.

- [ ] **Step 6: Commit numbering service**

```powershell
git add backend/app/services/order_errors.py backend/app/services/number_sequence.py backend/tests/unit/services/test_number_sequence.py
git commit -m "feat: add transactional business number sequences"
```

---

### Task 4: Add Business Profile Schemas, Service, and API

**Files:**
- Create: `backend/app/schemas/business_profile.py`
- Create: `backend/app/services/business_profile.py`
- Create: `backend/app/api/routes/business_profiles.py`
- Modify: `backend/app/main.py:20-75,6716-6770`
- Test: `backend/tests/integration/test_business_profiles_api.py`

**Interfaces:**
- Consumes: profile/child models, `NumberSequence`, domain exceptions, `ORDER_SETTINGS_READ`, `ORDER_SETTINGS_MANAGE`, and safe order-domain read permissions.
- Produces: `/api/v1/business-profiles` CRUD with nested replace semantics and optimistic version checks plus a non-sensitive options endpoint.

- [ ] **Step 1: Write failing profile API tests**

Create integration tests for:

```python
PROFILE = {
    "name": "EU Operations",
    "legal_name": "Example Manufacturing GmbH",
    "trading_name": "Example Print",
    "country_code": "de",
    "default_currency": "eur",
    "timezone": "Europe/Berlin",
    "default_locale": "de-DE",
    "billing_mode": "hybrid",
    "is_active": True,
    "is_default": True,
    "addresses": [{
        "kind": "registered",
        "label": "Head office",
        "additional": None,
        "street": "Musterstrasse 1",
        "street_2": None,
        "postal_code": "10115",
        "city": "Berlin",
        "region": "Berlin",
        "country_code": "de",
        "is_default": True,
    }],
    "tax_identifiers": [{
        "kind": "vat",
        "value": "DE123456789",
        "country_code": "de",
        "is_primary": True,
        "valid_from": None,
        "valid_until": None,
    }],
    "bank_accounts": [{
        "label": "EUR account",
        "account_holder": "Example Manufacturing GmbH",
        "bank_name": "Example Bank",
        "country_code": "de",
        "currency": "eur",
        "iban": "DE02120300000000202051",
        "bic": "BYLADEM1001",
        "account_number": None,
        "routing_number": None,
        "is_default": True,
    }],
}
```

Required assertions:

- POST returns 201, uppercases country/currency codes, and creates a `customer` sequence.
- The first profile becomes default even if `is_default` is false.
- Setting a second profile as default clears the first in one transaction.
- PUT with the current version replaces child collections and increments version.
- PUT with a stale version returns 409 with `detail.code == "version_conflict"`.
- DELETE of the default profile returns 409.
- Invalid timezone, country, currency, duplicate primary tax IDs, or two default addresses of one kind returns 422.
- GET `/options` returns only ID, name, country, currency, active/default state, timezone, locale, and billing mode; it never exposes addresses, tax IDs, or bank accounts.

- [ ] **Step 2: Run profile tests and verify route failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_business_profiles_api.py -v
```

Expected: FAIL with 404 because the router is not mounted.

- [ ] **Step 3: Implement normalized nested Pydantic contracts**

In `backend/app/schemas/business_profile.py`:

- define `AddressInput`, `TaxIdentifierInput`, and `BankAccountInput`;
- define `BusinessProfileCreate` with all fields from `PROFILE`;
- define `BusinessProfileUpdate(BusinessProfileCreate)` adding `version: int = Field(ge=1)`;
- define response variants adding child IDs, profile ID/version/timestamps;
- define `BusinessProfileOption` with only `id`, `name`, `country_code`, `default_currency`, `timezone`, `default_locale`, `billing_mode`, `is_default`, and `is_active`;
- uppercase country/currency codes in `field_validator` methods;
- validate timezone with `ZoneInfo(value)`;
- require at least one registered address;
- require at most one default address per kind, one primary tax identifier per kind, and one default bank account per currency;
- require at least one of `iban` or `account_number` for every bank account.

Use `model_config = {"from_attributes": True}` on response models.

- [ ] **Step 4: Implement profile aggregate service**

The service must use `selectinload` for all children, replace child collections only after version validation, flush without committing, and expose this helper for both routes and later domains:

```python
async def get_default_business_profile(db: AsyncSession) -> BusinessProfile:
    result = await db.execute(
        select(BusinessProfile)
        .where(BusinessProfile.is_default.is_(True), BusinessProfile.is_active.is_(True))
        .options(
            selectinload(BusinessProfile.addresses),
            selectinload(BusinessProfile.tax_identifiers),
            selectinload(BusinessProfile.bank_accounts),
        )
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise ResourceNotFoundError("No default business profile configured")
    return profile
```

On create, normalize the first profile to default and add this default sequence before flush:

```python
NumberSequence(
    business_profile_id=profile.id,
    key="customer",
    prefix="CUST",
    pattern="{PREFIX}-{#####}",
    next_value=1,
    reset_policy="none",
)
```

Catch database uniqueness errors, roll back the route transaction, and convert them to `DuplicateBusinessKeyError` with a stable message.

- [ ] **Step 5: Implement routes and stable problem details**

Mount `APIRouter(prefix="/business-profiles", tags=["business-profiles"])` with:

- `GET /` requiring `Permission.ORDER_SETTINGS_READ`;
- `GET /options` requiring any of `CUSTOMERS_READ`, `CALCULATIONS_READ`, `ORDERS_READ`, or `COMMERCIAL_DOCUMENTS_READ` and returning `list[BusinessProfileOption]`;
- `POST /` returning 201 and requiring `Permission.ORDER_SETTINGS_MANAGE`;
- `GET /{profile_id}` requiring `Permission.ORDER_SETTINGS_READ`;
- `PUT /{profile_id}` requiring `Permission.ORDER_SETTINGS_MANAGE`;
- `POST /{profile_id}/default` requiring `Permission.ORDER_SETTINGS_MANAGE`;
- `DELETE /{profile_id}` returning 204 and requiring `Permission.ORDER_SETTINGS_MANAGE`.

Declare the static `/options` route before `/{profile_id}` so FastAPI never attempts to parse `options` as an integer profile ID.

Map domain errors to:

```python
HTTPException(status_code=404, detail={"code": "not_found", "message": str(error)})
HTTPException(status_code=409, detail={"code": "version_conflict", "message": str(error)})
HTTPException(status_code=409, detail={"code": "resource_in_use", "message": str(error)})
HTTPException(status_code=409, detail={"code": "duplicate_business_key", "message": str(error)})
```

Add the router import and `app.include_router(business_profiles.router, prefix=app_settings.api_prefix)` in `backend/app/main.py`.

- [ ] **Step 6: Run focused API tests, permissions, and lint**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_business_profiles_api.py backend/tests/unit/test_order_management_permissions.py -v
.\.venv\Scripts\python.exe -m ruff check backend/app/schemas/business_profile.py backend/app/services/business_profile.py backend/app/api/routes/business_profiles.py backend/app/main.py
```

Expected: PASS and no Ruff findings.

- [ ] **Step 7: Commit profile backend**

```powershell
git add backend/app/schemas/business_profile.py backend/app/services/business_profile.py backend/app/api/routes/business_profiles.py backend/app/main.py backend/tests/integration/test_business_profiles_api.py
git commit -m "feat: add issuing business profile API"
```

---

### Task 5: Add Customer Schemas, Service, and API

**Files:**
- Create: `backend/app/schemas/customer.py`
- Create: `backend/app/services/customer.py`
- Create: `backend/app/api/routes/customers.py`
- Modify: `backend/app/main.py:20-75,6716-6775`
- Test: `backend/tests/integration/test_customers_api.py`

**Interfaces:**
- Consumes: customer aggregate models, profile existence, `reserve_number()`, optimistic version, and customer permissions.
- Produces: paginated customer list and complete aggregate CRUD APIs used by the customer page and later quotations/orders.

- [ ] **Step 1: Write failing customer API tests**

Use the profile API fixture to create a business profile, then use this payload:

```python
CUSTOMER = {
    "kind": "company",
    "display_name": "Atelier Nord GmbH",
    "company_name": "Atelier Nord GmbH",
    "first_name": None,
    "last_name": None,
    "status": "active",
    "preferred_locale": "de-DE",
    "notes": "Receives production samples before series runs.",
    "accounts": [{
        "business_profile_id": 1,
        "number": None,
        "preferred_currency": "eur",
        "payment_term_days": 14,
        "delivery_terms": "DHL shipment",
        "discount_percent": "2.00",
        "is_active": True,
    }],
    "contacts": [{
        "salutation": "Herr",
        "first_name": "Jonas",
        "last_name": "Berger",
        "role": "Purchasing",
        "email": "einkauf@example.test",
        "phone": "+49 371 440081",
        "is_primary": True,
        "include_on_documents": True,
    }],
    "addresses": [{
        "kind": "billing",
        "label": "Main office",
        "additional": "Building 2",
        "street": "Zwickauer Strasse 18",
        "street_2": None,
        "postal_code": "09111",
        "city": "Chemnitz",
        "region": "Saxony",
        "country_code": "de",
        "is_default": True,
    }],
    "tax_identifiers": [{
        "kind": "vat",
        "value": "DE999999999",
        "country_code": "de",
        "validation_status": "unchecked",
    }],
    "tags": ["B2B", "Series"],
}
```

Required test cases:

- POST returns 201 and auto-generates `CUST-00001`.
- A supplied unique number is preserved.
- Duplicate number within one profile returns 409; the same number in a second profile is allowed through a second account.
- GET list filters by case-insensitive name/number/email, status, and kind; total is independent of pagination.
- GET detail returns nested accounts, contacts, addresses, tax IDs, and normalized sorted unique tags.
- PUT replaces child data, increments version, and preserves `created_at`.
- stale PUT returns 409.
- DELETE removes an unreferenced customer and returns 204.
- company requires `company_name`; person requires first and last name.
- every submitted business profile appears at most once and receives exactly one customer account.
- no more than one primary contact and one default address per kind is accepted.

- [ ] **Step 2: Run customer tests and verify route failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_customers_api.py -v
```

Expected: FAIL with 404 because the customer router is not mounted.

- [ ] **Step 3: Implement customer schemas**

Define:

```python
class CustomerAccountInput(BaseModel):
    business_profile_id: int = Field(gt=0)
    number: str | None = Field(default=None, min_length=1, max_length=50)
    preferred_currency: str = Field(min_length=3, max_length=3)
    payment_term_days: int = Field(default=14, ge=0, le=365)
    delivery_terms: str | None = Field(default=None, max_length=1000)
    discount_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    is_active: bool = True


class CustomerCreate(BaseModel):
    kind: Literal["company", "person"]
    display_name: str = Field(min_length=1, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    status: Literal["active", "inactive", "blocked"] = "active"
    preferred_locale: str = Field(default="en", min_length=2, max_length=16)
    notes: str | None = Field(default=None, max_length=10000)
    accounts: list[CustomerAccountInput] = Field(min_length=1)
    contacts: list[CustomerContactInput] = Field(default_factory=list)
    addresses: list[CustomerAddressInput] = Field(default_factory=list)
    tax_identifiers: list[CustomerTaxIdentifierInput] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list, max_length=50)


class CustomerUpdate(CustomerCreate):
    version: int = Field(ge=1)
```

Add validators for kind/name rules, uppercase codes, normalized tag trimming/case-insensitive deduplication, unique `business_profile_id` values across accounts, one primary contact, and one default address per kind. Define `CustomerListItem`, `CustomerDetailResponse`, and `CustomerListResponse(items, total, limit, offset)`.

- [ ] **Step 4: Implement aggregate serialization and service behavior**

The service must:

- load all relationships with `selectinload`;
- verify profile existence and active state for every submitted account;
- allocate each omitted customer number from that account's profile inside the same transaction;
- normalize tag names and reuse existing `CustomerTag` rows case-insensitively;
- use a joined `CustomerAccount` filter for profile-specific list number/terms;
- search `Customer.display_name`, `CustomerAccount.number`, and `CustomerContact.email` without duplicate rows;
- return deterministic ordering by `display_name`, then ID;
- reject stale versions before replacing children;
- increment parent version for every aggregate replacement;
- flush, but let the route dependency own commit;
- map uniqueness errors to `DuplicateBusinessKeyError`;
- hard-delete only while no later commercial references exist. This increment has no commercial references, but keep the check in one helper named `_assert_customer_deletable()` so later plans extend it.

Use `Decimal` values end-to-end and never convert `discount_percent` to float.

- [ ] **Step 5: Implement routes**

Mount `APIRouter(prefix="/customers", tags=["customers"])` with:

- `GET /` requiring `customers:read`, accepting `business_profile_id`, `search`, `status`, `kind`, `limit=50 (1..200)`, and `offset>=0`;
- `POST /` returning 201 and requiring `customers:manage`;
- `GET /{customer_id}` requiring `customers:read`;
- `PUT /{customer_id}` requiring `customers:manage`;
- `DELETE /{customer_id}` returning 204 and requiring `customers:manage`.

Use the same problem-detail codes from Task 4. Register the router in `backend/app/main.py`.

- [ ] **Step 6: Run customer/profile integration tests and lint**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_business_profiles_api.py backend/tests/integration/test_customers_api.py -v
.\.venv\Scripts\python.exe -m ruff check backend/app/schemas/customer.py backend/app/services/customer.py backend/app/api/routes/customers.py backend/app/main.py
```

Expected: PASS and no Ruff findings.

- [ ] **Step 7: Commit customer backend**

```powershell
git add backend/app/schemas/customer.py backend/app/services/customer.py backend/app/api/routes/customers.py backend/app/main.py backend/tests/integration/test_customers_api.py
git commit -m "feat: add customer master data API"
```

---

### Task 6: Add Frontend API Contracts, Navigation Gates, and Settings Routing

**Files:**
- Modify: `frontend/src/api/client.ts:3104-3185,5741-5790`
- Modify: `frontend/src/App.tsx:1-25,215-228`
- Modify: `frontend/src/pages/OrdersPage.tsx`
- Modify: `frontend/src/components/Layout.tsx:45-80,375-415`
- Modify: `frontend/src/lib/settingsNavigation.ts:30-40`
- Modify: `frontend/src/pages/SettingsPage.tsx:60-80,403-418,610-670,720-900,3575-3790,4135-4165`
- Modify: `frontend/src/i18n/locales/*.ts`
- Modify: `frontend/src/__tests__/components/Layout.test.tsx`
- Modify: `frontend/src/__tests__/lib/settingsNavigation.test.ts`
- Modify: `frontend/src/__tests__/pages/SettingsPage.test.tsx`

**Interfaces:**
- Consumes: APIs from Tasks 4-5 and permission strings from Task 2.
- Produces: typed frontend API methods, dedicated customer route, permission-gated navigation, and canonical `business-profile` settings sub-tab.

- [ ] **Step 1: Write failing client/navigation/settings tests**

Add tests that assert:

```typescript
expect(resolveOrderManagementSubTab('business-profile')).toBe('business-profile');
```

Add Layout cases:

- a user with `customers:read` sees the Orders parent and Customers child;
- a user with only `calculations:read` sees the Orders parent and Calculation child but not Customers;
- a user with no order read permission sees neither parent nor children;
- Settings remains governed by `settings:read`.

Add a SettingsPage MSW handler for `GET /api/v1/business-profiles/` and assert `/settings?tab=orders-calculation&sub=business-profile` activates a `Business profile` button and profile content.

- [ ] **Step 2: Run focused frontend tests and verify failure**

Run from `frontend`:

```powershell
npm.cmd run test -- --run src/__tests__/components/Layout.test.tsx src/__tests__/lib/settingsNavigation.test.ts src/__tests__/pages/SettingsPage.test.tsx
```

Expected: FAIL because the sub-tab, route component, API methods, and permission gates are missing.

- [ ] **Step 3: Add exact TypeScript API contracts**

Add string unions:

```typescript
export type BillingMode = 'internal' | 'external' | 'hybrid';
export type CustomerKind = 'company' | 'person';
export type CustomerStatus = 'active' | 'inactive' | 'blocked';
```

Add interfaces mirroring every backend field, preserving `Decimal` JSON values as strings for `discount_percent`. Add:

```typescript
getBusinessProfiles(includeInactive = false): Promise<BusinessProfile[]>;
getBusinessProfileOptions(): Promise<BusinessProfileOption[]>;
createBusinessProfile(data: BusinessProfileCreate): Promise<BusinessProfile>;
updateBusinessProfile(id: number, data: BusinessProfileUpdate): Promise<BusinessProfile>;
setDefaultBusinessProfile(id: number): Promise<BusinessProfile>;
deleteBusinessProfile(id: number): Promise<void>;
getCustomers(params: CustomerListParams): Promise<CustomerListResponse>;
getCustomer(id: number): Promise<CustomerDetail>;
createCustomer(data: CustomerCreate): Promise<CustomerDetail>;
updateCustomer(id: number, data: CustomerUpdate): Promise<CustomerDetail>;
deleteCustomer(id: number): Promise<void>;
```

Implement them on the existing `api` object with `/business-profiles`, `/business-profiles/options`, and `/customers` paths and `URLSearchParams` for customer filters. `BusinessProfileOption` must contain no address, tax, or bank fields.

- [ ] **Step 4: Route customers to a dedicated page and remove duplicate placeholder behavior**

Import `OrdersCustomersPage` in `App.tsx` and change only `/orders/customers` to render it. Remove `customers` from `OrderSectionId`, `COPY.page`, `getSection()`, and icon mapping in `OrdersPage.tsx`; all other placeholder routes remain until their increments.

- [ ] **Step 5: Add navigation permission gates**

Add to `navPermissions`:

```typescript
orders: ['orders:read', 'customers:read', 'calculations:read', 'commercial_documents:read'],
'orders-offers': 'commercial_documents:read',
'orders-calculation': 'calculations:read',
'orders-customers': 'customers:read',
'orders-invoice': 'commercial_documents:read',
```

Because array entries mean any permission is sufficient in current Layout logic, the parent remains visible whenever one child domain is available.

- [ ] **Step 6: Add the canonical profile settings sub-tab**

Change:

```typescript
export type OrderManagementSubTab = 'business-profile' | 'calculation';
```

Make `business-profile` the default for a direct canonical order-settings visit, while legacy cost links/search results continue selecting `calculation`. Add metadata using the Lucide `Building2` icon, then render `<BusinessProfileSettings />` for the new sub-tab. Register search keywords `business company seller issuer tax bank country currency` with anchor `card-business-profile`.

- [ ] **Step 7: Add parity-safe translations**

Add the same key structure to every locale under `settings.tabs`, `settings.orderManagementSubTabDescriptions`, and new top-level `orders` sections. English keys include `businessProfile`, `customers`, `customerEditor`, and common status/form labels. German receives native text. Copy the English values into other locales in this increment so `npm run check:i18n` passes without pretending they are translated.

- [ ] **Step 8: Run focused tests, i18n parity, and TypeScript build**

Run:

```powershell
npm.cmd run test -- --run src/__tests__/components/Layout.test.tsx src/__tests__/lib/settingsNavigation.test.ts src/__tests__/pages/SettingsPage.test.tsx
npm.cmd run check:i18n
npm.cmd run build
```

Expected: tests pass, i18n parity passes, and TypeScript/Vite build succeeds.

- [ ] **Step 9: Commit frontend contracts and routing**

```powershell
git add frontend/src/api/client.ts frontend/src/App.tsx frontend/src/pages/OrdersPage.tsx frontend/src/components/Layout.tsx frontend/src/lib/settingsNavigation.ts frontend/src/pages/SettingsPage.tsx frontend/src/i18n frontend/src/__tests__
git commit -m "feat: wire order master data navigation"
```

---

### Task 7: Build Business Profile Settings

**Files:**
- Create: `frontend/src/components/settings/BusinessProfileSettings.tsx`
- Create: `frontend/src/components/settings/BusinessProfileEditorModal.tsx`
- Create: `frontend/src/__tests__/components/BusinessProfileSettings.test.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`

**Interfaces:**
- Consumes: full profile API/types, `order_settings:read`, and `order_settings:manage` permissions.
- Produces: working issuer-profile list, create/edit/default/deactivate/delete actions, and explicit setup/error states.

- [ ] **Step 1: Write failing component workflow tests**

Use MSW and the shared test render helper. Cover:

- loading then empty setup state;
- opening create modal and submitting a valid registered address;
- editing nested identity/localization/billing mode data with current version;
- adding/removing tax IDs and bank accounts;
- setting a non-default profile as default;
- showing a permission-denied state without `order_settings:read`;
- hiding mutation buttons without `order_settings:manage` while retaining read-only data for a user that has `order_settings:read`;
- displaying 409 conflict text and retaining unsaved form input;
- showing inactive profiles only when the toggle is enabled;
- prohibiting delete of the default profile in the UI.

Assert accessible names such as `Add business profile`, `Edit EU Operations`, and `Set EU Operations as default`.

- [ ] **Step 2: Run component tests and verify module failure**

Run from `frontend`:

```powershell
npm.cmd run test -- --run src/__tests__/components/BusinessProfileSettings.test.tsx
```

Expected: FAIL because the components do not exist.

- [ ] **Step 3: Implement the compact profile workspace**

`BusinessProfileSettings` must:

- check `order_settings:read` before starting the full-profile query;
- use query key `['business-profiles', includeInactive]`;
- render one unframed settings section with a compact table, not cards inside the Settings page;
- use Building2, Check, Pencil, Power, Star, Plus, and Trash2 Lucide icons with tooltips;
- show profile name/legal name, country, currency, timezone, billing mode, active/default status, and row actions;
- disable mutations while another mutation is pending;
- invalidate both profile list variants after mutation;
- keep server error details visible until dismissed or a retry succeeds.

`BusinessProfileEditorModal` must:

- use fixed Identity, Address, Tax and bank, and Locale sections inside one scrollable dialog;
- use selects for billing mode/country/currency/locale/timezone option sets and checkboxes for boolean values;
- support repeatable addresses, tax IDs, and bank accounts with icon add/remove controls;
- keep a stable footer with Cancel and Save buttons;
- map server 422 field errors next to their fields and 409 conflicts to a top-level conflict banner;
- submit `BusinessProfileCreate` or `BusinessProfileUpdate` with the unchanged version on edit.

Use the existing `Button`, form input classes, modal overlay conventions, `useAuth()`, `useMutation()`, and `useQueryClient()`.

- [ ] **Step 4: Wire SettingsPage only after the component passes in isolation**

Import and render:

```tsx
{activeTab === 'orders-calculation' && orderManagementSubTab === 'business-profile' && (
  <BusinessProfileSettings />
)}
```

Do not condition profile rendering on `localSettings`; it has its own query and must show an independent error/setup state.

- [ ] **Step 5: Run component, SettingsPage, lint, and build checks**

Run:

```powershell
npm.cmd run test -- --run src/__tests__/components/BusinessProfileSettings.test.tsx src/__tests__/pages/SettingsPage.test.tsx
npm.cmd run lint -- src/components/settings/BusinessProfileSettings.tsx src/components/settings/BusinessProfileEditorModal.tsx src/pages/SettingsPage.tsx
npm.cmd run build
```

Expected: PASS, no lint findings, and build succeeds.

- [ ] **Step 6: Commit profile settings UI**

```powershell
git add frontend/src/components/settings frontend/src/pages/SettingsPage.tsx frontend/src/__tests__/components/BusinessProfileSettings.test.tsx
git commit -m "feat: add business profile settings"
```

---

### Task 8: Build the Customer Management Workspace

**Files:**
- Create: `frontend/src/pages/OrdersCustomersPage.tsx`
- Create: `frontend/src/components/orders/CustomerEditorModal.tsx`
- Create: `frontend/src/components/orders/CustomerDetailsModal.tsx`
- Create: `frontend/src/__tests__/pages/OrdersCustomersPage.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: customer API, non-sensitive business-profile options API, `customers:read`, and `customers:manage`.
- Produces: complete list/create/read/update/deactivate/delete master-data workflow for later calculation and order selectors.

- [ ] **Step 1: Write failing page workflow tests**

Cover these exact user behaviors with MSW:

- profile selector loads from `/business-profiles/options` and defaults to the default active business profile;
- no-profile state links to `/settings?tab=orders-calculation&sub=business-profile`;
- debounced search sends `search`, active status filter sends `status`, and kind segmented control sends `kind`;
- table displays number, name, primary contact, default billing city/country, status, tags, and actions;
- pagination uses backend `total`, `limit`, and `offset` without client-side total guessing;
- user with read-only permission can open details but cannot create/edit/delete;
- create form submits nested account/contact/address/tax/tag data;
- edit form submits current version and updates query cache;
- 409 retains editor input and offers Reload current data;
- delete requires `ConfirmModal`, then invalidates list and closes details;
- loading skeleton, empty filtered result, API error with Retry, and permission-denied states are distinct.

- [ ] **Step 2: Run page tests and verify module failure**

Run from `frontend`:

```powershell
npm.cmd run test -- --run src/__tests__/pages/OrdersCustomersPage.test.tsx
```

Expected: FAIL because the page and order components do not exist.

- [ ] **Step 3: Implement the customer page**

`OrdersCustomersPage` must:

- use query key `['customers', profileId, search, status, kind, limit, offset]`;
- wait 300 ms before applying search text to the query;
- reset offset to zero when profile/search/status/kind changes;
- render a compact header with Users icon, title, profile selector, and Plus icon/text command;
- use a search input, status menu, and company/person/all segmented control;
- keep the table inside a bordered overflow container with stable columns;
- use Eye, Pencil, and Trash2 icon buttons with tooltips and `aria-label` including customer name;
- render pagination controls with disabled previous/next states;
- never calculate revenue or receivables from fabricated values;
- use the API-provided total and primary flattened list fields.

- [ ] **Step 4: Implement editor and details modals**

`CustomerEditorModal` must provide:

- company/person segmented control;
- repeatable profile account rows with profile, optional customer number, currency, payment days, delivery terms, discount, and active state; initialize a new customer with the currently selected profile;
- identity fields appropriate to the selected kind;
- repeatable contacts with one primary and include-on-documents checkbox;
- repeatable billing/delivery/other addresses with one default per kind;
- repeatable tax identifiers;
- normalized tag entry;
- status, locale, and notes;
- field-level validation before mutation and mapped 422 server feedback;
- stable Cancel/Save footer and Escape close when no mutation is pending.

`CustomerDetailsModal` must show all profile accounts with the currently selected profile first, all contacts, addresses, tax identifiers, tags, status, timestamps, and an Edit command only when permitted. Do not display fake history or derived revenue.

- [ ] **Step 5: Run customer page, route, layout, lint, and build checks**

Run:

```powershell
npm.cmd run test -- --run src/__tests__/pages/OrdersCustomersPage.test.tsx src/__tests__/components/Layout.test.tsx
npm.cmd run lint -- src/pages/OrdersCustomersPage.tsx src/components/orders/CustomerEditorModal.tsx src/components/orders/CustomerDetailsModal.tsx
npm.cmd run build
```

Expected: PASS, no lint findings, and build succeeds.

- [ ] **Step 6: Commit customer workspace**

```powershell
git add frontend/src/pages/OrdersCustomersPage.tsx frontend/src/components/orders frontend/src/__tests__/pages/OrdersCustomersPage.test.tsx frontend/src/App.tsx
git commit -m "feat: add customer management workspace"
```

---

### Task 9: Verify the Vertical Increment End to End

**Files:**
- Modify if required by discovered regression only: files changed in Tasks 1-8.
- Update: `docs/superpowers/specs/2026-07-10-order-management-design.md` status from `Draft for review` to `Approved`.
- Create: `docs/order-management.md` with operator-facing setup instructions for business profiles and customers.

**Interfaces:**
- Consumes: the complete foundation increment.
- Produces: release-ready, documented, verified software and a clean branch for a fork-only pull request.

- [ ] **Step 1: Run backend focused and full foundation suites**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_permissions.py backend/tests/unit/test_order_management_permissions.py backend/tests/unit/services/test_number_sequence.py backend/tests/integration/test_order_foundation_schema.py backend/tests/integration/test_business_profiles_api.py backend/tests/integration/test_customers_api.py backend/tests/integration/test_groups_api.py -v
.\.venv\Scripts\python.exe -m ruff check backend/app backend/tests
```

Expected: all selected tests pass and Ruff reports no findings.

- [ ] **Step 2: Run frontend focused and complete checks**

Run from `frontend`:

```powershell
npm.cmd run test -- --run src/__tests__/components/BusinessProfileSettings.test.tsx src/__tests__/pages/OrdersCustomersPage.test.tsx src/__tests__/components/Layout.test.tsx src/__tests__/lib/settingsNavigation.test.ts src/__tests__/pages/SettingsPage.test.tsx
npm.cmd run check:i18n
npm.cmd run lint
npm.cmd run build
```

Expected: all tests pass, locale parity passes, lint is clean, and production build succeeds.

- [ ] **Step 3: Run browser verification at desktop and mobile widths**

Start the existing development stack on an unused local port. Verify with Playwright or the repository's browser tooling:

- `/settings?tab=orders-calculation&sub=business-profile` at 1440x900 and 390x844;
- `/orders/customers` at 1440x900 and 390x844;
- empty, populated, editor, validation error, read-only permission, and API failure states;
- longest German labels, repeatable address/contact rows, and modal scrolling;
- no text overlap, no clipped action buttons, stable table columns, and no nested cards.

Capture screenshots into the existing ignored/test-output location, not tracked product assets.

- [ ] **Step 4: Verify database and authorization invariants manually**

Use API calls against the local stack to confirm:

- two profiles cannot both remain default;
- stale versions return 409;
- duplicate customer numbers are blocked per profile;
- a viewer cannot mutate profiles/customers;
- an operator can manage customers but cannot access future issue/integration permissions;
- an API key receives 403 for new profile/customer mutation routes unless a future explicit scope is added;
- application restart preserves all profile/customer rows and next customer number.

- [ ] **Step 5: Add operator documentation and verify the approved design**

`docs/order-management.md` must document:

1. required initial business-profile fields;
2. default-profile behavior;
3. internal/external/hybrid meaning without claiming billing is implemented in this increment;
4. customer accounts per business profile;
5. customer number generation and manual override;
6. role defaults and how administrators customize groups;
7. the next increment is calculation, linked from the approved design delivery shape.

Verify that the design status remains `Status: Approved`; do not alter approved scope while documenting this increment.

- [ ] **Step 6: Review the complete diff and commit verification/docs**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors and only intentional documentation or regression-fix changes remain.

Commit:

```powershell
git add docs frontend backend
git commit -m "docs: document order management foundation"
```

- [ ] **Step 7: Prepare fork-only integration**

Verify remotes before any network write:

```powershell
git remote -v
git config --get remote.pushDefault
git config --get branch.codex/order-management.pushRemote
```

Expected:

- `origin` points to `ichwars/PrintOps` for fetch and push;
- `upstream` fetches `maziggy/bambuddy` and has disabled/no usable push URL;
- push default is `origin`.

Push only the current branch to the fork, open an internal pull request from `ichwars/PrintOps:codex/order-management` to `ichwars/PrintOps:main`, wait for required checks, and merge only after all checks pass. Never create a pull request whose base repository is `maziggy/bambuddy`.

## Plan Self-Review

- Spec coverage: delivery increment 1 covers relational profiles, customer master data, numbering, permissions, APIs, settings, and customer UX. Calculation and later commercial workflows remain explicitly outside this plan and are separate vertical increments from the approved design.
- File-boundary check: models contain persistence only; schemas normalize HTTP data; services own transactions/invariants; routes map HTTP/permissions; frontend pages and focused dialogs stay out of `SettingsPage.tsx` and `OrdersPage.tsx`.
- Type check: `business_profile_id`, `version`, nested child field names, permission strings, status/kind literals, and API method names are consistent across backend and frontend tasks.
- Concurrency check: customer numbering uses optimistic atomic update; aggregate PUTs require version; true simultaneous cross-database document numbering is deferred to the document-numbering plan where legal sequence reservations and void evidence are added.
- Security check: mutation routes have explicit permissions, frontend gating mirrors them, API keys remain fail-closed, and issuer/customer data never uses generic settings JSON.
- Placeholder check: implementation behavior, commands, expected results, routes, fields, and tests are specified. Later domains are excluded by scope rather than left as unfinished code in this increment.
