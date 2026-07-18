# Small Parts Inventory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a complete small-parts warehouse with catalog settings, searchable articles, an immutable stock ledger, availability calculation, and a reusable calculation picker.

**Architecture:** Add a focused `small_parts` aggregate beside the existing spool inventory and reuse the shared `locations` catalog. Physical and reserved stock are derived from immutable ledger deltas; write services lock the article, validate the resulting totals, and append a journal row in one transaction. The warehouse UI receives its own route and components while the existing Filament and Ware areas remain unchanged.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic v2, SQLite/PostgreSQL-compatible DDL, Decimal, React 19, TypeScript, TanStack Query, Tailwind CSS, Vitest, Testing Library.

## Global Constraints

- Keep the warehouse navigation split exactly into Filament, Kleinteile, and Ware.
- Reuse `backend.app.models.location.Location`; do not create a second location catalog.
- Never persist a freely editable balance. Derive physical, reserved, and available quantities from ledger rows.
- Never allow physical stock, reserved stock, or available stock to become negative.
- Public stock mutations may append receipt or correction rows only; reservation rows are internal and added by the offer/reservation plan.
- Quantities use `Numeric(18, 6)` and API strings; currency uses `Numeric(18, 6)` internally and two decimals in the UI.
- Preserve existing `Permission.INVENTORY_*` gates and websocket `inventory_changed` behavior.
- Do not modify the Ware implementation beyond retaining its existing scaffold.

## File Structure

- `backend/app/models/small_part.py`: category, unit, article, and immutable ledger ORM models.
- `backend/app/schemas/small_part.py`: strict API inputs and read models with Decimal serialization.
- `backend/app/services/small_parts.py`: normalization, search, aggregate balances, guarded ledger appends, and CRUD.
- `backend/app/api/routes/small_parts.py`: `/small-parts` catalog, stock, settings, and lookup routes.
- `frontend/src/api/smallParts.ts`: typed client contracts.
- `frontend/src/pages/SmallPartsPage.tsx`: operational catalog and stock view.
- `frontend/src/components/warehouse/SmallPartEditor.tsx`: article create/edit modal.
- `frontend/src/components/warehouse/SmallPartStockDialog.tsx`: receipt/correction form and ledger history.
- `frontend/src/components/warehouse/SmallPartCombobox.tsx`: reusable keyboard-searchable article selector.
- `frontend/src/components/settings/SmallPartsSettings.tsx`: category, unit, location, and default-threshold settings.

---

### Task 1: Define the Small-Parts Schema and Migration Contract

**Files:**
- Create: `backend/app/models/small_part.py`
- Create: `backend/app/schemas/small_part.py`
- Modify: `backend/app/models/location.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/database.py`
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/integration/test_small_parts_schema.py`

**Interfaces:**
- Produces ORM classes `SmallPartCategory`, `SmallPartUnit`, `SmallPart`, and `SmallPartLedgerEntry`.
- Produces API types `SmallPartCreate`, `SmallPartUpdate`, `SmallPartRead`, `SmallPartBalanceRead`, `SmallPartLedgerCreate`, `SmallPartLedgerRead`, `SmallPartOptionRead`, `SmallPartListResponse`, `SmallPartCategoryRead`, and `SmallPartUnitRead`.
- Reuses `Location.id` through `SmallPart.location_id`.

- [ ] **Step 1: Write the failing schema contract test**

```python
EXPECTED = {
    "small_part_categories",
    "small_part_units",
    "small_parts",
    "small_part_ledger_entries",
}


async def test_small_parts_schema_contract(test_engine):
    def inspect_schema(sync_connection):
        inspector = inspect(sync_connection)
        return set(inspector.get_table_names()), {
            name
            for table in EXPECTED
            for item in inspector.get_check_constraints(table)
            if (name := item["name"])
        }

    async with test_engine.connect() as connection:
        tables, checks = await connection.run_sync(inspect_schema)

    assert tables >= EXPECTED
    assert checks >= {
        "ck_small_part_unit_precision",
        "ck_small_part_min_stock",
        "ck_small_part_unit_cost",
        "ck_small_part_ledger_nonzero",
        "ck_small_part_ledger_kind",
    }
```

- [ ] **Step 2: Run the schema test and verify the tables are missing**

Run:

```powershell
python -m pytest backend/tests/integration/test_small_parts_schema.py -q
```

Expected: FAIL because `small_part_*` tables are not registered.

- [ ] **Step 3: Implement the ORM aggregate**

```python
# backend/app/models/small_part.py
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class SmallPartCategory(Base):
    __tablename__ = "small_part_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    name_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SmallPartUnit(Base):
    __tablename__ = "small_part_units"
    __table_args__ = (CheckConstraint("decimal_places BETWEEN 0 AND 6", name="ck_small_part_unit_precision"),)
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    label: Mapped[str] = mapped_column(String(80))
    decimal_places: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SmallPart(Base):
    __tablename__ = "small_parts"
    __table_args__ = (
        CheckConstraint("minimum_stock >= 0", name="ck_small_part_min_stock"),
        CheckConstraint("unit_cost >= 0", name="ck_small_part_unit_cost"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    search_terms: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("small_part_categories.id", ondelete="SET NULL"), index=True)
    unit_code: Mapped[str] = mapped_column(ForeignKey("small_part_units.code", ondelete="RESTRICT"), index=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id", ondelete="SET NULL"), index=True)
    minimum_stock: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    supplier_reference: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    category = relationship("SmallPartCategory", lazy="selectin")
    unit = relationship("SmallPartUnit", lazy="selectin")
    location = relationship("Location", back_populates="small_parts", lazy="selectin")
    ledger_entries = relationship("SmallPartLedgerEntry", back_populates="small_part", lazy="raise")


class SmallPartLedgerEntry(Base):
    __tablename__ = "small_part_ledger_entries"
    __table_args__ = (
        CheckConstraint("physical_delta != 0 OR reserved_delta != 0", name="ck_small_part_ledger_nonzero"),
        CheckConstraint(
            "entry_kind IN ('opening','receipt','correction','reservation','release','issue')",
            name="ck_small_part_ledger_kind",
        ),
        UniqueConstraint("idempotency_key", name="uq_small_part_ledger_idempotency"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    small_part_id: Mapped[int] = mapped_column(ForeignKey("small_parts.id", ondelete="RESTRICT"), index=True)
    entry_kind: Mapped[str] = mapped_column(String(24), index=True)
    physical_delta: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    reserved_delta: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    reason: Mapped[str] = mapped_column(Text)
    reference_type: Mapped[str | None] = mapped_column(String(32))
    reference_id: Mapped[int | None] = mapped_column(Integer)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    small_part = relationship("SmallPart", back_populates="ledger_entries")
```

- [ ] **Step 4: Add strict Pydantic contracts and registration**

```python
# backend/app/schemas/small_part.py
class SmallPartLedgerCreate(SmallPartSchema):
    entry_kind: Literal["receipt", "correction"]
    quantity: Decimal
    reason: str = Field(min_length=1, max_length=2000)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_quantity(self):
        if self.entry_kind == "receipt" and self.quantity <= 0:
            raise ValueError("receipt quantity must be positive")
        if self.entry_kind == "correction" and self.quantity == 0:
            raise ValueError("correction quantity must be non-zero")
        return self


class SmallPartBalanceRead(SmallPartSchema):
    physical: Decimal
    reserved: Decimal
    available: Decimal
    is_low_stock: bool


class SmallPartOptionRead(SmallPartSchema):
    id: int
    sku: str
    name: str
    unit_code: str
    unit_cost: Decimal
    available: Decimal


class SmallPartListResponse(SmallPartSchema):
    items: list[SmallPartRead]
    total: int
    limit: int
    offset: int
```

Define category/unit create, update, and read schemas with the same length/precision constraints as the ORM. Import `small_part` in `init_db()` and `backend/tests/conftest.py`, export all four classes from `backend/app/models/__init__.py`, and add `small_parts: Mapped[list["SmallPart"]] = relationship(back_populates="location")` to `Location`.

- [ ] **Step 5: Run the schema test and commit**

Run:

```powershell
python -m pytest backend/tests/integration/test_small_parts_schema.py -q
```

Expected: PASS.

```powershell
git add backend/app/models/small_part.py backend/app/schemas/small_part.py backend/app/models/location.py backend/app/models/__init__.py backend/app/core/database.py backend/tests/conftest.py backend/tests/integration/test_small_parts_schema.py
git commit -m "feat(inventory): add small-parts stock schema"
```

---

### Task 2: Implement Guarded Balances and Immutable Ledger Writes

**Files:**
- Create: `backend/app/services/small_parts.py`
- Create: `backend/tests/unit/test_small_parts_service.py`

**Interfaces:**
- Produces `SmallPartBalance(physical: Decimal, reserved: Decimal, available: Decimal)`.
- Produces `get_balance(session, small_part_id)`, `append_ledger_entry(...)`, `search_small_parts(...)`, and CRUD helpers.
- `append_ledger_entry` accepts reservation/release/issue kinds for internal callers, but public routes constrain inputs to receipt/correction.

- [ ] **Step 1: Write failing balance, idempotency, and negative-stock tests**

```python
async def test_ledger_is_idempotent_and_never_overdraws(db_session, small_part):
    first = await append_ledger_entry(
        db_session,
        small_part_id=small_part.id,
        entry_kind="opening",
        physical_delta=Decimal("10"),
        reserved_delta=Decimal("0"),
        reason="Opening stock",
        idempotency_key="opening-M3-001",
    )
    again = await append_ledger_entry(
        db_session,
        small_part_id=small_part.id,
        entry_kind="opening",
        physical_delta=Decimal("10"),
        reserved_delta=Decimal("0"),
        reason="Opening stock",
        idempotency_key="opening-M3-001",
    )
    assert again.id == first.id
    assert await get_balance(db_session, small_part.id) == SmallPartBalance(
        physical=Decimal("10"), reserved=Decimal("0"), available=Decimal("10")
    )
    with pytest.raises(InsufficientSmallPartStock):
        await append_ledger_entry(
            db_session,
            small_part_id=small_part.id,
            entry_kind="reservation",
            physical_delta=Decimal("0"),
            reserved_delta=Decimal("11"),
            reason="Order reservation",
            idempotency_key="reserve-order-11",
        )
```

- [ ] **Step 2: Run the service test and verify imports fail**

Run `python -m pytest backend/tests/unit/test_small_parts_service.py -q`.

Expected: FAIL because `backend.app.services.small_parts` does not exist.

- [ ] **Step 3: Implement Decimal aggregation and guarded append**

```python
@dataclass(frozen=True)
class SmallPartBalance:
    physical: Decimal
    reserved: Decimal
    available: Decimal


async def get_balance(session: AsyncSession, small_part_id: int) -> SmallPartBalance:
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(SmallPartLedgerEntry.physical_delta), 0),
                func.coalesce(func.sum(SmallPartLedgerEntry.reserved_delta), 0),
            ).where(SmallPartLedgerEntry.small_part_id == small_part_id)
        )
    ).one()
    physical, reserved = Decimal(row[0]), Decimal(row[1])
    return SmallPartBalance(physical, reserved, physical - reserved)


async def append_ledger_entry(session: AsyncSession, *, small_part_id: int, entry_kind: str,
                              physical_delta: Decimal, reserved_delta: Decimal, reason: str,
                              idempotency_key: str, reference_type: str | None = None,
                              reference_id: int | None = None, actor_id: int | None = None) -> SmallPartLedgerEntry:
    existing = await session.scalar(
        select(SmallPartLedgerEntry).where(SmallPartLedgerEntry.idempotency_key == idempotency_key)
    )
    if existing:
        return existing
    part = await session.scalar(select(SmallPart).where(SmallPart.id == small_part_id).with_for_update())
    if not part:
        raise SmallPartNotFound(small_part_id)
    current = await get_balance(session, small_part_id)
    next_physical = current.physical + Decimal(physical_delta)
    next_reserved = current.reserved + Decimal(reserved_delta)
    if next_physical < 0 or next_reserved < 0 or next_reserved > next_physical:
        raise InsufficientSmallPartStock(small_part_id, next_physical - next_reserved)
    entry = SmallPartLedgerEntry(
        small_part_id=small_part_id, entry_kind=entry_kind,
        physical_delta=physical_delta, reserved_delta=reserved_delta,
        reason=reason.strip(), reference_type=reference_type, reference_id=reference_id,
        actor_id=actor_id, idempotency_key=idempotency_key,
    )
    session.add(entry)
    await session.flush()
    return entry
```

- [ ] **Step 4: Implement normalized CRUD and search**

Use `func.lower()` over `sku`, `name`, `description`, and `search_terms`; eager-load category, unit, and location; order active records first then by `name`. Reject changing `unit_code` when any ledger row exists unless the caller supplies a separately designed stock conversion; this plan deliberately exposes no conversion endpoint.

- [ ] **Step 5: Run focused tests and commit**

Run `python -m pytest backend/tests/unit/test_small_parts_service.py -q` and expect PASS.

```powershell
git add backend/app/services/small_parts.py backend/tests/unit/test_small_parts_service.py
git commit -m "feat(inventory): add guarded small-parts ledger"
```

---

### Task 3: Expose Catalog, Settings, Search, and Stock APIs

**Files:**
- Create: `backend/app/api/routes/small_parts.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_small_parts_api.py`

**Interfaces:**
- Produces `GET/POST/PATCH /api/v1/small-parts` and `GET /api/v1/small-parts/{id}`.
- Produces `GET /api/v1/small-parts/search?q=&limit=` returning active article options with balances.
- Produces `GET/POST /api/v1/small-parts/{id}/ledger`.
- Produces category and unit CRUD under `/api/v1/small-parts/settings/*` and reuses `/api/v1/inventory/locations`.

- [ ] **Step 1: Write failing API lifecycle tests**

```python
async def test_small_part_api_tracks_receipt_and_correction(async_client):
    unit = await async_client.post("/api/v1/small-parts/settings/units", json={
        "code": "C62", "label": "Stück", "decimal_places": 0
    })
    assert unit.status_code == 201
    created = await async_client.post("/api/v1/small-parts", json={
        "sku": "M3-INSERT", "name": "M3 Gewindeeinsatz", "unit_code": "C62",
        "category_id": None, "location_id": None, "minimum_stock": "20",
        "unit_cost": "0.08", "is_active": True,
    })
    part_id = created.json()["id"]
    receipt = await async_client.post(f"/api/v1/small-parts/{part_id}/ledger", json={
        "entry_kind": "receipt", "quantity": "100", "reason": "Purchase",
        "idempotency_key": "receipt-M3-20260718",
    })
    assert receipt.status_code == 201
    detail = (await async_client.get(f"/api/v1/small-parts/{part_id}")).json()
    assert detail["balance"] == {"physical": "100.000000", "reserved": "0.000000", "available": "100.000000", "is_low_stock": False}
```

Also assert search finds SKU/name/category terms, inactive items are excluded by default, duplicate idempotency does not double stock, and an overdrawn correction returns HTTP 409 with `code=insufficient_stock`.

- [ ] **Step 2: Run API tests and verify routes return 404**

Run `python -m pytest backend/tests/integration/test_small_parts_api.py -q`.

Expected: FAIL because the router is absent.

- [ ] **Step 3: Implement the router and stable error body**

```python
router = APIRouter(prefix="/small-parts", tags=["small-parts"])


@router.get("/search", response_model=list[SmallPartOptionRead])
async def search_small_part_options(q: str = "", limit: int = Query(30, ge=1, le=100),
                                    db: AsyncSession = Depends(get_db),
                                    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ)):
    return await small_parts.search_small_parts(db, query=q, active_only=True, limit=limit)


@router.post("/{small_part_id}/ledger", response_model=SmallPartLedgerRead, status_code=201)
async def add_small_part_stock(small_part_id: int, data: SmallPartLedgerCreate,
                               db: AsyncSession = Depends(get_db),
                               user: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE)):
    try:
        entry = await small_parts.append_ledger_entry(
            db, small_part_id=small_part_id, entry_kind=data.entry_kind,
            physical_delta=data.quantity, reserved_delta=Decimal("0"), reason=data.reason,
            idempotency_key=data.idempotency_key, actor_id=user.id if user else None,
        )
    except InsufficientSmallPartStock as exc:
        raise HTTPException(409, detail={"code": "insufficient_stock", "message": str(exc)})
    await ws_manager.broadcast({"type": "inventory_changed", "resource": "small_part", "id": small_part_id})
    return entry
```

Use `INVENTORY_READ` for reads, `INVENTORY_CREATE` for create/settings create, `INVENTORY_UPDATE` for edit/ledger, and `INVENTORY_DELETE` for category/unit deletion. Return 409 when a category/unit is still referenced; deactivate articles instead of deleting any article with ledger history.

- [ ] **Step 4: Register the router, run tests, and commit**

Add `small_parts` to the route import tuple and `app.include_router(small_parts.router, prefix=app_settings.api_prefix)` beside inventory.

Run `python -m pytest backend/tests/integration/test_small_parts_api.py -q` and expect PASS.

```powershell
git add backend/app/api/routes/small_parts.py backend/app/main.py backend/tests/integration/test_small_parts_api.py
git commit -m "feat(api): expose small-parts inventory"
```

---

### Task 4: Build the Typed Client and Reusable Search Control

**Files:**
- Create: `frontend/src/api/smallParts.ts`
- Create: `frontend/src/components/warehouse/SmallPartCombobox.tsx`
- Create: `frontend/src/__tests__/components/SmallPartCombobox.test.tsx`

**Interfaces:**
- Produces `smallPartsApi.list`, `search`, `create`, `update`, `ledger`, `categories`, and `units`.
- Produces `SmallPartCombobox({ value, onChange, disabled, locale })` with debounced keyboard search.

- [ ] **Step 1: Write a failing keyboard-search test**

```tsx
it('searches by keyboard and selects the highlighted article', async () => {
  server.use(http.get('/api/v1/small-parts/search', ({ request }) => {
    expect(new URL(request.url).searchParams.get('q')).toBe('m3');
    return HttpResponse.json([{ id: 7, sku: 'M3-INSERT', name: 'M3 Gewindeeinsatz', unit_code: 'C62', available: '42.000000' }]);
  }));
  const onChange = vi.fn();
  const user = userEvent.setup();
  render(<SmallPartCombobox value={null} onChange={onChange} locale="de-DE" />);
  await user.type(screen.getByRole('combobox'), 'm3');
  await user.keyboard('{ArrowDown}{Enter}');
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }));
});
```

- [ ] **Step 2: Run the test and verify the component is missing**

Run `npm.cmd run test -- --run src/__tests__/components/SmallPartCombobox.test.tsx` from `frontend`.

- [ ] **Step 3: Implement typed API contracts**

```ts
export interface SmallPartOption {
  id: number;
  sku: string;
  name: string;
  unit_code: string;
  unit_cost: string;
  available: string;
}

export interface SmallPartListParams { q?: string; active?: boolean; low_stock?: boolean; limit?: number; offset?: number }
export interface SmallPartPage { items: SmallPart[]; total: number; limit: number; offset: number }

export const smallPartsApi = {
  search: (q: string) => request<SmallPartOption[]>(`/small-parts/search?${new URLSearchParams({ q, limit: '30' })}`),
  list: (params: SmallPartListParams = {}) => request<SmallPartPage>(`/small-parts?${listParams(params)}`),
  create: (input: SmallPartCreate) => request<SmallPart>('/small-parts', { method: 'POST', body: JSON.stringify(input) }),
  update: (id: number, input: SmallPartUpdate) => request<SmallPart>(`/small-parts/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),
  addLedger: (id: number, input: SmallPartLedgerCreate) => request<SmallPartLedgerEntry>(`/small-parts/${id}/ledger`, { method: 'POST', body: JSON.stringify(input) }),
};
```

- [ ] **Step 4: Implement an accessible combobox**

Use `role="combobox"`, `aria-expanded`, `aria-controls`, a `role="listbox"`, `role="option"`, `aria-activedescendant`, 250 ms debounce, ArrowUp/ArrowDown, Enter, Escape, click-outside, and visible SKU/name/available quantity. Do not permit free-text values.

- [ ] **Step 5: Run the focused test and commit**

Run the focused Vitest command and expect PASS.

```powershell
git add frontend/src/api/smallParts.ts frontend/src/components/warehouse/SmallPartCombobox.tsx frontend/src/__tests__/components/SmallPartCombobox.test.tsx
git commit -m "feat(ui): add searchable small-part selector"
```

---

### Task 5: Replace the Kleinteile Warehouse Scaffold

**Files:**
- Create: `frontend/src/pages/SmallPartsPage.tsx`
- Create: `frontend/src/components/warehouse/SmallPartEditor.tsx`
- Create: `frontend/src/components/warehouse/SmallPartStockDialog.tsx`
- Modify: `frontend/src/pages/WarehousePage.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/__tests__/pages/SmallPartsPage.test.tsx`

**Interfaces:**
- `/warehouse/parts` renders `SmallPartsPage`.
- `SmallPartEditor` writes catalog metadata only.
- `SmallPartStockDialog` appends receipt/correction rows and renders journal history.

- [ ] **Step 1: Write failing warehouse interaction tests**

Cover empty state, search, low-stock filter, create, edit, receipt, correction with required reason, inactive badge, balance columns, ledger ordering, and a 409 error that preserves the entered form.

```tsx
expect(await screen.findByRole('heading', { name: 'Kleinteile' })).toBeInTheDocument();
await user.type(screen.getByRole('searchbox', { name: 'Kleinteile durchsuchen' }), 'M3');
expect(await screen.findByText('M3 Gewindeeinsatz')).toBeInTheDocument();
expect(screen.getByText('42 Stück verfügbar')).toBeInTheDocument();
```

- [ ] **Step 2: Run the page test and verify the scaffold fails expectations**

Run `npm.cmd run test -- --run src/__tests__/pages/SmallPartsPage.test.tsx` from `frontend`.

- [ ] **Step 3: Implement the operational page**

Use TanStack Query keys `['small-parts', filters]`, `['small-part', id, 'ledger']`, and invalidate both plus `['warehouse']` after mutations. The desktop table columns are Artikel, Kategorie, Lagerort, Physisch, Reserviert, Verfügbar, Meldebestand, Preis, Aktionen; the mobile view uses cards with the same information. Low stock is `available <= minimum_stock`.

- [ ] **Step 4: Wire the route without changing other warehouse areas**

```tsx
<Route path="warehouse/parts" element={<SmallPartsPage />} />
<Route path="warehouse/filament" element={<InventoryPage />} />
<Route path="warehouse/stock" element={<WarehousePage />} />
```

Update the overview card for Kleinteile to show active article count and low-stock count from the small-parts API; keep Ware as its existing planned scaffold.

- [ ] **Step 5: Run tests and commit**

Run focused tests plus `npm.cmd run check:i18n`; expect PASS.

```powershell
git add frontend/src/pages/SmallPartsPage.tsx frontend/src/components/warehouse/SmallPartEditor.tsx frontend/src/components/warehouse/SmallPartStockDialog.tsx frontend/src/pages/WarehousePage.tsx frontend/src/App.tsx frontend/src/__tests__/pages/SmallPartsPage.test.tsx frontend/src/i18n/locales/de.ts frontend/src/i18n/locales/en.ts
git commit -m "feat(warehouse): implement small-parts inventory"
```

---

### Task 6: Add Kleinteile Catalog Settings

**Files:**
- Create: `frontend/src/components/settings/SmallPartsSettings.tsx`
- Modify: `frontend/src/lib/settingsNavigation.ts`
- Modify: `frontend/src/lib/settingsSearch.ts`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `backend/app/schemas/settings.py`
- Create: `frontend/src/__tests__/components/SmallPartsSettings.test.tsx`

**Interfaces:**
- Adds `small-parts` to `WarehouseMaterialSubTab`.
- Stores `small_parts_default_minimum_stock` and `small_parts_low_stock_warning` in `AppSettings`.
- Category/unit/location catalogs use their existing typed APIs, not JSON blobs.

- [ ] **Step 1: Write failing settings tests**

Assert the Warehouse settings tab exposes Kleinteile, category/unit/location CRUD, default minimum stock, warning toggle, and blocks unit deletion when referenced.

- [ ] **Step 2: Run the focused settings test and verify the subtab is absent**

Run `npm.cmd run test -- --run src/__tests__/components/SmallPartsSettings.test.tsx`.

- [ ] **Step 3: Extend settings contracts**

```python
small_parts_default_minimum_stock: Decimal = Field(default=Decimal("0"), ge=0)
small_parts_low_stock_warning: bool = Field(default=True)
```

Add both keys to the settings route allowlist and frontend `AppSettings`. Serialize Decimal as a string to avoid binary float drift.

- [ ] **Step 4: Implement the settings component and navigation entry**

`SmallPartsSettings` renders three catalog cards and one defaults card. Unit editing disables `code` and `decimal_places` once referenced. Location CRUD calls the existing inventory location routes so spool and small-part locations remain shared.

- [ ] **Step 5: Run settings tests, i18n parity, and commit**

```powershell
git add backend/app/schemas/settings.py backend/app/api/routes/settings.py frontend/src/api/client.ts frontend/src/components/settings/SmallPartsSettings.tsx frontend/src/lib/settingsNavigation.ts frontend/src/lib/settingsSearch.ts frontend/src/pages/SettingsPage.tsx frontend/src/__tests__/components/SmallPartsSettings.test.tsx frontend/src/i18n/locales/de.ts frontend/src/i18n/locales/en.ts
git commit -m "feat(settings): manage small-parts catalogs"
```

---

### Task 7: Verify and Document the Small-Parts Deliverable

**Files:**
- Modify: `docs/order-management.md`
- Modify: `docs/superpowers/plans/2026-07-18-small-parts-inventory.md`

**Interfaces:**
- Produces a stable small-parts API and reusable `SmallPartCombobox` for the calculation plan.

- [ ] **Step 1: Document article, balance, journal, and permission semantics**

Include the invariant `available = physical - reserved`, immutable ledger rules, no-negative-stock behavior, and shared location catalog.

- [ ] **Step 2: Run backend verification**

```powershell
python -m pytest backend/tests/integration/test_small_parts_schema.py backend/tests/unit/test_small_parts_service.py backend/tests/integration/test_small_parts_api.py -q
python -m ruff check backend/app/models/small_part.py backend/app/schemas/small_part.py backend/app/services/small_parts.py backend/app/api/routes/small_parts.py
python -m ruff format --check backend/app/models/small_part.py backend/app/schemas/small_part.py backend/app/services/small_parts.py backend/app/api/routes/small_parts.py
```

Expected: all selected tests pass and Ruff reports no errors.

- [ ] **Step 3: Run frontend verification**

```powershell
Set-Location frontend
npm.cmd run test -- --run src/__tests__/components/SmallPartCombobox.test.tsx src/__tests__/pages/SmallPartsPage.test.tsx src/__tests__/components/SmallPartsSettings.test.tsx
npm.cmd run check:i18n
npm.cmd run build
```

Expected: all tests, parity check, and build pass.

- [ ] **Step 4: Browser smoke test**

Verify `/warehouse/filament` is unchanged, `/warehouse/parts` supports keyboard search and stock journal actions, `/warehouse/stock` remains the Ware scaffold, and the settings catalog changes immediately appear in article forms.

- [ ] **Step 5: Commit verification documentation**

```powershell
git add docs/order-management.md docs/superpowers/plans/2026-07-18-small-parts-inventory.md
git commit -m "docs: document small-parts inventory"
```
