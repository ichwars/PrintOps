# Material, Suppliers, and Procurement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable supplier and procurement-source system for material and filament, redesign the material workflow from the ForgeDesk reference, and replace visible “Kleinteile/Small parts” terminology with “Material/Materials”.

**Architecture:** Add `Supplier` and `ProcurementOffer` aggregates behind inventory permissions. Offers target either an existing material (`SmallPart`) or a lazily resolved `FilamentSkuSettings` row, so internal and Spoolman inventory share one procurement identity. Keep all existing `small_parts` technical contracts and routes; extend them additively and compose the UI from the shared PrintOps controls.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2 async, SQLite/PostgreSQL startup migrations, React 19, TypeScript 5.9, TanStack Query 5, Tailwind 4, Vitest/Testing Library/MSW.

## Global Constraints

- Visible copy uses **Material/Materials** instead of **Kleinteil/Kleinteile/Small part/Small parts**; technical `small_parts` names and `/warehouse/parts` remain unchanged.
- A manufacturer or Spoolman vendor is not a supplier and must never be auto-imported as one.
- A resource may have many active procurement offers but at most one active preferred offer.
- Supplier and offer writes use existing `inventory:create`, `inventory:update`, and `inventory:delete`; reads use `inventory:read`.
- Use shared `Modal`, `TextField`, `TextArea`, `NumberField`, `Select`, `Checkbox`, `Button`, and `ScrollArea`; do not add native controls or local `gray-*`/`green-*` form overrides.
- Desktop controls remain 38 px high; touch controls remain at least 44 px through the shared component defaults.
- Preserve existing unrelated working-tree files and the already-started material-page style changes.
- Add no new runtime dependency.
- Run backend and Git commands from the repository root. Run every `npm.cmd` command from `frontend` unless a step contains its own `cd frontend`.

## File Map

- `backend/app/models/procurement.py`: supplier and offer persistence plus target/preferred constraints.
- `backend/app/schemas/procurement.py`: public supplier/offer contracts and resource descriptors.
- `backend/app/services/procurement.py`: normalized names, guarded deletion, target resolution, preferred-offer replacement.
- `backend/app/api/routes/procurement.py`: `/suppliers` and `/procurement-offers` HTTP API.
- `frontend/src/api/procurement.ts`: TypeScript contracts and request wrappers.
- `frontend/src/pages/SuppliersPage.tsx`: supplier list/search/activation surface.
- `frontend/src/components/warehouse/SupplierEditor.tsx`: supplier master-data dialog.
- `frontend/src/components/warehouse/ProcurementOffersEditor.tsx`: reusable preferred/alternative offer editor.
- `frontend/src/components/warehouse/SmallPartEditor.tsx`: ForgeDesk-derived material dialog.
- `frontend/src/components/ForecastPanel.tsx`: filament-SKU procurement integration.

---

### Task 1: Supplier and Procurement Persistence

**Files:**
- Create: `backend/app/models/procurement.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/database.py:170-225`
- Modify: `backend/tests/conftest.py:100-175`
- Create: `backend/tests/integration/test_procurement_schema.py`

**Interfaces:**
- Produces: `Supplier`, `ProcurementOffer`; `ProcurementOffer.resource_key: str` is `material:<small_part_id>` or `filament:<filament_sku_settings_id>`.
- Consumes: `SmallPart.id`, `FilamentSkuSettings.id`, and `Base`.

- [ ] **Step 1: Write the failing schema contract**

```python
from sqlalchemy import inspect


async def test_procurement_schema_contract(test_engine):
    def inspect_schema(sync_connection):
        inspector = inspect(sync_connection)
        return (
            set(inspector.get_table_names()),
            {item["name"] for item in inspector.get_check_constraints("procurement_offers")},
            {item["name"] for item in inspector.get_indexes("procurement_offers")},
        )

    async with test_engine.connect() as connection:
        tables, checks, indexes = await connection.run_sync(inspect_schema)

    assert {"suppliers", "procurement_offers"} <= tables
    assert {"ck_procurement_offer_target", "ck_procurement_offer_values"} <= checks
    assert "uq_procurement_offer_preferred_resource" in indexes
```

- [ ] **Step 2: Run the contract and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_procurement_schema.py -q`

Expected: FAIL because the tables do not exist.

- [ ] **Step 3: Implement the two models and preferred partial index**

```python
# backend/app/models/procurement.py
class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(80))
    website: Mapped[str | None] = mapped_column(String(2048))
    address_line1: Mapped[str | None] = mapped_column(String(255))
    address_line2: Mapped[str | None] = mapped_column(String(255))
    postal_code: Mapped[str | None] = mapped_column(String(32))
    city: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(2))
    customer_number: Mapped[str | None] = mapped_column(String(120))
    payment_terms: Mapped[str | None] = mapped_column(String(500))
    default_lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    internal_notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProcurementOffer(Base):
    __tablename__ = "procurement_offers"
    __table_args__ = (
        CheckConstraint(
            "(small_part_id IS NOT NULL AND filament_sku_settings_id IS NULL) OR "
            "(small_part_id IS NULL AND filament_sku_settings_id IS NOT NULL)",
            name="ck_procurement_offer_target",
        ),
        CheckConstraint(
            "package_quantity > 0 AND minimum_order_quantity > 0 AND lead_time_days >= 0 "
            "AND net_price >= 0 AND gross_price >= 0",
            name="ck_procurement_offer_values",
        ),
        Index(
            "uq_procurement_offer_preferred_resource",
            "resource_key",
            unique=True,
            sqlite_where=text("is_preferred = 1 AND is_active = 1"),
            postgresql_where=text("is_preferred = true AND is_active = true"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True)
    small_part_id: Mapped[int | None] = mapped_column(ForeignKey("small_parts.id", ondelete="CASCADE"), index=True)
    filament_sku_settings_id: Mapped[int | None] = mapped_column(ForeignKey("filament_sku_settings.id", ondelete="CASCADE"), index=True)
    resource_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    supplier_sku: Mapped[str | None] = mapped_column(String(255))
    purchase_url: Mapped[str | None] = mapped_column(String(2048))
    package_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("1"))
    package_unit_code: Mapped[str] = mapped_column(String(16), nullable=False, default="C62")
    minimum_order_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("1"))
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    net_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    gross_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    is_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

Export both models, import the module in `init_db()` and the test metadata fixture. `create_all` creates both additive tables on existing installations; no hand-written table DDL is needed.

- [ ] **Step 4: Run schema and formatting gates**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_procurement_schema.py -q`

Expected: PASS.

Run: `.\.venv\Scripts\python.exe -m ruff check backend/app/models/procurement.py backend/tests/integration/test_procurement_schema.py`

Expected: exit 0.

- [ ] **Step 5: Commit the persistence slice**

```bash
git add backend/app/models/procurement.py backend/app/models/__init__.py backend/app/core/database.py backend/tests/conftest.py backend/tests/integration/test_procurement_schema.py
git commit -m "feat(procurement): add supplier and offer models"
```

---

### Task 2: Supplier Contracts, Service, and API

**Files:**
- Create: `backend/app/schemas/procurement.py`
- Create: `backend/app/services/procurement.py`
- Create: `backend/app/api/routes/procurement.py`
- Modify: `backend/app/main.py:55-75,6735-6745`
- Create: `backend/tests/integration/test_suppliers_api.py`

**Interfaces:**
- Produces: `SupplierCreate`, `SupplierUpdate`, `SupplierRead`, `list_suppliers()`, `create_supplier()`, `update_supplier()`, `delete_supplier()`.
- Consumes: Task 1 `Supplier` and existing inventory permissions.

- [ ] **Step 1: Write failing supplier lifecycle tests**

```python
@pytest.mark.asyncio
async def test_supplier_lifecycle_and_normalized_conflict(async_client):
    payload = {
        "name": "Filament World",
        "contact_name": "Ada Einkauf",
        "email": "orders@example.test",
        "country_code": "DE",
        "default_lead_time_days": 4,
        "is_active": True,
    }
    created = await async_client.post("/api/v1/suppliers", json=payload)
    duplicate = await async_client.post("/api/v1/suppliers", json={**payload, "name": " filament world "})
    listed = await async_client.get("/api/v1/suppliers", params={"q": "Ada"})
    updated = await async_client.patch(
        f"/api/v1/suppliers/{created.json()['id']}", json={"payment_terms": "14 Tage netto"}
    )

    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert [item["id"] for item in listed.json()["items"]] == [created.json()["id"]]
    assert updated.json()["payment_terms"] == "14 Tage netto"
```

- [ ] **Step 2: Run the API test and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_suppliers_api.py -q`

Expected: FAIL with 404 for `/api/v1/suppliers`.

- [ ] **Step 3: Implement typed contracts, normalized CRUD, and route mounting**

```python
class ProcurementSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, str_strip_whitespace=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_decimals(self, value):
        return str(value) if isinstance(value, Decimal) else value


class SupplierBase(ProcurementSchema):
    name: str = Field(min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    website: str | None = Field(default=None, max_length=2048)
    address_line1: str | None = Field(default=None, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    postal_code: str | None = Field(default=None, max_length=32)
    city: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    customer_number: str | None = Field(default=None, max_length=120)
    payment_terms: str | None = Field(default=None, max_length=500)
    default_lead_time_days: int = Field(default=0, ge=0, le=3650)
    internal_notes: str | None = None
    is_active: bool = True


def supplier_name_key(name: str) -> str:
    return " ".join(name.split()).casefold()
```

Expose `GET/POST /suppliers`, `GET/PATCH/DELETE /suppliers/{supplier_id}`. Search `name`, `contact_name`, `email`, and `customer_number`; normalize `country_code` to uppercase. Return 409 for duplicate normalized names and for deleting a supplier referenced by any active or inactive offer; allow deletion only when the total offer count is zero. Add authenticated route tests proving reads require `inventory:read` and create/update/delete each require their matching inventory permission.

- [ ] **Step 4: Run supplier tests and backend lint**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_suppliers_api.py -q`

Expected: PASS.

Run: `.\.venv\Scripts\python.exe -m ruff check backend/app/schemas/procurement.py backend/app/services/procurement.py backend/app/api/routes/procurement.py`

Expected: exit 0.

- [ ] **Step 5: Commit supplier API**

```bash
git add backend/app/schemas/procurement.py backend/app/services/procurement.py backend/app/api/routes/procurement.py backend/app/main.py backend/tests/integration/test_suppliers_api.py
git commit -m "feat(procurement): add supplier management API"
```

---

### Task 3: Shared Material and Filament Procurement Offers API

**Files:**
- Modify: `backend/app/schemas/procurement.py`
- Modify: `backend/app/services/procurement.py`
- Modify: `backend/app/api/routes/procurement.py`
- Create: `backend/tests/integration/test_procurement_offers_api.py`

**Interfaces:**
- Produces: `MaterialResource(small_part_id)`, `FilamentResource(material, subtype, brand, color_name)`, `ProcurementOfferWrite`, `ProcurementOfferRead` with nested `SupplierRead`, `replace_offers()`.
- Consumes: Task 1 models and Task 2 supplier lookup.

- [ ] **Step 1: Write failing replacement and preferred-invariant tests**

```python
@pytest.mark.asyncio
async def test_replaces_material_offers_with_one_preferred(async_client, material_id, supplier_ids):
    response = await async_client.put(
        "/api/v1/procurement-offers/resource",
        json={
            "resource": {"kind": "material", "small_part_id": material_id},
            "offers": [
                {"supplier_id": supplier_ids[0], "net_price": "4.20", "gross_price": "4.99", "is_preferred": True},
                {"supplier_id": supplier_ids[1], "net_price": "4.10", "gross_price": "4.88", "is_preferred": False},
            ],
        },
    )
    assert response.status_code == 200
    assert sum(item["is_preferred"] for item in response.json()) == 1
    assert all(item["resource_key"] == f"material:{material_id}" for item in response.json())


@pytest.mark.asyncio
async def test_filament_descriptor_reuses_sku_identity(async_client, supplier_ids):
    descriptor = {"kind": "filament", "material": "PLA", "subtype": "Matte", "brand": "Poly", "color_name": "Black"}
    first = await async_client.put("/api/v1/procurement-offers/resource", json={"resource": descriptor, "offers": [{"supplier_id": supplier_ids[0], "is_preferred": True}]})
    second = await async_client.get("/api/v1/procurement-offers", params={"kind": "filament", "material": "PLA", "subtype": "Matte", "brand": "Poly", "color_name": "Black"})
    assert first.status_code == second.status_code == 200
    assert second.json()[0]["id"] == first.json()[0]["id"]


@pytest.mark.asyncio
async def test_replacement_soft_deactivates_omitted_offer(async_client, material_id, supplier_ids):
    created = await replace_material_offers(async_client, material_id, supplier_ids)
    await async_client.put(
        "/api/v1/procurement-offers/resource",
        json={"resource": {"kind": "material", "small_part_id": material_id}, "offers": []},
    )
    inactive = await async_client.get(
        "/api/v1/procurement-offers",
        params={"kind": "material", "small_part_id": material_id, "active": False},
    )
    assert {item["id"] for item in inactive.json()} == {item["id"] for item in created}
    assert all(item["is_active"] is False and item["is_preferred"] is False for item in inactive.json())
```

- [ ] **Step 2: Run and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_procurement_offers_api.py -q`

Expected: FAIL because offer endpoints and schemas are absent.

- [ ] **Step 3: Implement resource resolution and transactional replacement**

```python
class MaterialResource(ProcurementSchema):
    kind: Literal["material"]
    small_part_id: int = Field(gt=0)


class FilamentResource(ProcurementSchema):
    kind: Literal["filament"]
    material: str = Field(min_length=1, max_length=50)
    subtype: str | None = Field(default=None, max_length=50)
    brand: str | None = Field(default=None, max_length=100)
    color_name: str | None = Field(default=None, max_length=100)


class ProcurementOfferWrite(ProcurementSchema):
    id: int | None = Field(default=None, gt=0)
    supplier_id: int = Field(gt=0)
    supplier_sku: str | None = Field(default=None, max_length=255)
    purchase_url: str | None = Field(default=None, max_length=2048)
    package_quantity: Decimal = Field(default=Decimal("1"), gt=0)
    package_unit_code: str = Field(default="C62", min_length=1, max_length=16)
    minimum_order_quantity: Decimal = Field(default=Decimal("1"), gt=0)
    lead_time_days: int | None = Field(default=None, ge=0, le=3650)
    net_price: Decimal = Field(default=Decimal("0"), ge=0)
    gross_price: Decimal = Field(default=Decimal("0"), ge=0)
    is_preferred: bool = False
    is_active: bool = True
```

`resolve_resource(db, resource, create_filament)` validates a material or resolves `FilamentSkuSettings` using its existing four-column identity. GET uses `create_filament=False` and returns an empty list when no settings row exists; PUT uses `create_filament=True` and upserts the row. `replace_offers()` rejects more than one active preferred draft with 422, rejects IDs from another resource, applies the supplier default lead time when a draft omits it, demotes the current preferred row before flushing, updates submitted IDs, inserts new drafts, and soft-deactivates omitted rows by setting `is_active=False` and `is_preferred=False`. It commits only after all validation and writes succeed and returns active offers ordered preferred-first then supplier name. `DELETE` performs the same soft deactivation; historical offers are never hard-deleted.

Expose:

```text
GET    /procurement-offers?kind=material&small_part_id=7&active=true
GET    /procurement-offers?kind=filament&material=PLA&subtype=Matte&brand=Poly&color_name=Black
PUT    /procurement-offers/resource
DELETE /procurement-offers/{offer_id}
```

Add authenticated route tests proving reads require `inventory:read`, replacement requires `inventory:update`, and deletion requires `inventory:delete`.

- [ ] **Step 4: Verify offer API and legacy inventory forecasting**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_procurement_offers_api.py backend/tests/integration/test_small_parts_schema.py -q`

Expected: PASS.

Run: `.\.venv\Scripts\python.exe -m ruff check backend/app/schemas/procurement.py backend/app/services/procurement.py backend/app/api/routes/procurement.py`

Expected: exit 0.

- [ ] **Step 5: Commit shared offer API**

```bash
git add backend/app/schemas/procurement.py backend/app/services/procurement.py backend/app/api/routes/procurement.py backend/tests/integration/test_procurement_offers_api.py
git commit -m "feat(procurement): share offers across material and filament"
```

---

### Task 4: Material Metadata, Opening Stock, and Preferred Offer Read Model

**Files:**
- Modify: `backend/app/models/small_part.py`
- Modify: `backend/app/schemas/small_part.py`
- Modify: `backend/app/services/procurement.py`
- Modify: `backend/app/api/routes/small_parts.py`
- Modify: `backend/app/core/database.py:run_migrations`
- Modify: `backend/tests/integration/test_small_parts_api.py`
- Create: `backend/tests/integration/test_material_procurement_migration.py`

**Interfaces:**
- Produces: `SmallPartCreate.opening_quantity`, `SmallPartRead.preferred_offer`, `SmallPart.default_consumption_reason`, `SmallPart.internal_notes`.
- Consumes: Task 3 `ProcurementOfferRead` and `preferred_offers_for_materials()`.

- [ ] **Step 1: Write failing atomic-opening and migration tests**

```python
@pytest.mark.asyncio
async def test_material_create_books_opening_stock_atomically(async_client):
    await async_client.post("/api/v1/small-parts/settings/units", json={"code": "C62", "label": "Stück"})
    created = await async_client.post(
        "/api/v1/small-parts",
        json={
            "sku": "MAT-1",
            "name": "Magnet",
            "unit_code": "C62",
            "opening_quantity": "25",
            "default_consumption_reason": "Produktion",
            "internal_notes": "Nur trocken lagern",
        },
    )
    ledger = await async_client.get(f"/api/v1/small-parts/{created.json()['id']}/ledger")
    assert created.status_code == 201
    assert created.json()["balance"]["physical"] == "25.000000"
    assert ledger.json()[0]["entry_kind"] == "opening"
    assert ledger.json()[0]["reason"] == "Anfangsbestand"


@pytest.mark.asyncio
async def test_material_procurement_columns_migrate_idempotently(existing_database_connection):
    await run_migrations(existing_database_connection)
    await run_migrations(existing_database_connection)
    columns = await column_names(existing_database_connection, "small_parts")
    assert {"default_consumption_reason", "internal_notes"} <= columns
```

- [ ] **Step 2: Run and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_small_parts_api.py::test_material_create_books_opening_stock_atomically backend/tests/integration/test_material_procurement_migration.py -q`

Expected: FAIL because the new fields are forbidden/missing.

- [ ] **Step 3: Add fields, migration, atomic create, and preferred-offer batching**

```python
# model fields
default_consumption_reason: Mapped[str] = mapped_column(String(120), nullable=False, default="Produktion")
internal_notes: Mapped[str | None] = mapped_column(Text)

# migration
await _safe_execute(
    conn,
    "ALTER TABLE small_parts ADD COLUMN default_consumption_reason VARCHAR(120) NOT NULL DEFAULT 'Produktion'",
)
await _safe_execute(conn, "ALTER TABLE small_parts ADD COLUMN internal_notes TEXT")

# create route
payload = data.model_dump(exclude={"opening_quantity"})
part = SmallPart(**payload)
db.add(part)
await db.flush()
if data.opening_quantity > 0:
    await service.append_ledger_entry(
        db,
        small_part_id=part.id,
        entry_kind="opening",
        physical_delta=Decimal(data.opening_quantity),
        reserved_delta=Decimal("0"),
        reason="Anfangsbestand",
        idempotency_key=f"material-opening:{part.id}",
    )
await db.commit()
```

Keep the add/flush/ledger/commit sequence inside one `try`; rollback the session on every exception so neither the material nor opening entry survives a failed create. Add `opening_quantity` only to `SmallPartCreate`, never `SmallPartUpdate`. Add optional `preferred_offer` to `SmallPartRead`. `preferred_offers_for_materials(db, ids)` performs one query and `_read_part()` receives a preloaded offer to avoid one offer query per list row. Synchronize `unit_cost` from the active preferred offer’s `net_price` inside Task 3 replacement; if no preferred source remains, preserve the existing legacy `unit_cost`.

- [ ] **Step 4: Run material backend regression gates**

Run: `.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_small_parts_api.py backend/tests/integration/test_material_procurement_migration.py backend/tests/unit/test_small_parts_service.py -q`

Expected: PASS.

Run: `.\.venv\Scripts\python.exe -m ruff check backend/app/models/small_part.py backend/app/schemas/small_part.py backend/app/api/routes/small_parts.py backend/app/services/procurement.py`

Expected: exit 0.

- [ ] **Step 5: Commit material backend extension**

```bash
git add backend/app/models/small_part.py backend/app/schemas/small_part.py backend/app/services/procurement.py backend/app/api/routes/small_parts.py backend/app/core/database.py backend/tests/integration/test_small_parts_api.py backend/tests/integration/test_material_procurement_migration.py
git commit -m "feat(material): add opening stock and procurement metadata"
```

---

### Task 5: Frontend Procurement Client and Supplier Management Page

**Files:**
- Create: `frontend/src/api/procurement.ts`
- Create: `frontend/src/pages/SuppliersPage.tsx`
- Create: `frontend/src/components/warehouse/SupplierEditor.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/i18n/locales/{de,en,es,fr,it,ja,ko,pt-BR,tr,zh-CN,zh-TW}.ts`
- Create: `frontend/src/__tests__/pages/SuppliersPage.test.tsx`
- Create: `frontend/src/__tests__/components/SupplierEditor.test.tsx`

**Interfaces:**
- Produces: `suppliersApi`, `Supplier`, `SupplierInput`, route `/warehouse/suppliers`.
- Consumes: Task 2 API.

- [ ] **Step 1: Write failing supplier-page and editor tests**

```tsx
it('searches suppliers and opens the supplier editor', async () => {
  server.use(http.get('/api/v1/suppliers', () => HttpResponse.json({ items: [supplier], total: 1, limit: 100, offset: 0 })));
  const user = userEvent.setup();
  renderPage();
  expect(await screen.findByRole('heading', { name: 'Lieferanten' })).toBeInTheDocument();
  expect(screen.getByText('Filament World')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Lieferant anlegen' }));
  expect(screen.getByRole('dialog', { name: 'Lieferant anlegen' })).toBeInTheDocument();
});

it('submits complete supplier master data', async () => {
  await user.type(screen.getByLabelText('Firma'), 'Filament World');
  await user.type(screen.getByLabelText('E-Mail'), 'orders@example.test');
  await user.type(screen.getByLabelText('Standard-Lieferzeit'), '4');
  await user.click(screen.getByRole('button', { name: 'Lieferant speichern' }));
  await waitFor(() => expect(suppliersApi.create).toHaveBeenCalledWith(expect.objectContaining({ name: 'Filament World', default_lead_time_days: 4 })));
});
```

- [ ] **Step 2: Run and verify RED**

Run: `npm.cmd run test -- SuppliersPage.test.tsx SupplierEditor.test.tsx --run`

Expected: FAIL because files/routes do not exist.

- [ ] **Step 3: Implement client, page, responsive editor, route, and navigation**

```ts
export interface SupplierInput {
  name: string;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  address_line1: string | null;
  address_line2: string | null;
  postal_code: string | null;
  city: string | null;
  country_code: string | null;
  customer_number: string | null;
  payment_terms: string | null;
  default_lead_time_days: number;
  internal_notes: string | null;
  is_active: boolean;
}

function queryString(params: Record<string, string | number | boolean | undefined>): string {
  const result = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) result.set(key, String(value));
  });
  return result.toString();
}

export const suppliersApi = {
  list: (params: { q?: string; active?: boolean } = {}) => request<SupplierPage>(`/suppliers?${queryString(params)}`),
  create: (input: SupplierInput) => request<Supplier>('/suppliers', { method: 'POST', body: JSON.stringify(input) }),
  update: (id: number, input: Partial<SupplierInput>) => request<Supplier>(`/suppliers/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),
  remove: (id: number) => request<void>(`/suppliers/${id}`, { method: 'DELETE' }),
};
```

Use `Truck` for the `Lager > Lieferanten` navigation item. `SupplierEditor` sections are `Stammdaten`, `Kontakt & Adresse`, `Beschaffung`, `Notiz intern`; use shared controls and `Modal className="max-w-3xl"`.
Use the existing permission hook: list/search require `inventory:read`; show create only for `inventory:create`, edit only for `inventory:update`, and delete only for `inventory:delete`. If a delete returns the referenced-supplier 409, keep the editor open and present the server’s domain message with `role="alert"`.

- [ ] **Step 4: Run component tests and i18n parity**

Run: `npm.cmd run test -- SuppliersPage.test.tsx SupplierEditor.test.tsx --run`

Expected: PASS.

Run: `npm.cmd run check:i18n`

Expected: exit 0 for all 11 locales.

- [ ] **Step 5: Commit supplier frontend**

```bash
git add frontend/src/api/procurement.ts frontend/src/pages/SuppliersPage.tsx frontend/src/components/warehouse/SupplierEditor.tsx frontend/src/App.tsx frontend/src/components/Layout.tsx frontend/src/i18n/locales frontend/src/__tests__/pages/SuppliersPage.test.tsx frontend/src/__tests__/components/SupplierEditor.test.tsx
git commit -m "feat(procurement): add supplier management UI"
```

---

### Task 6: Reusable Preferred and Alternative Offer Editor

**Files:**
- Modify: `frontend/src/api/procurement.ts`
- Create: `frontend/src/components/warehouse/ProcurementOffersEditor.tsx`
- Create: `frontend/src/__tests__/components/ProcurementOffersEditor.test.tsx`

**Interfaces:**
- Produces: `ProcurementResource`, `ProcurementOfferDraft`, `ProcurementOffersEditor` with `readOnly?: boolean`.
- Consumes: Task 5 `Supplier[]` and Task 3 replacement endpoint.

- [ ] **Step 1: Write failing editor behavior tests**

```tsx
it('keeps one preferred offer and supports an alternative', async () => {
  const onChange = vi.fn();
  render(<ProcurementOffersEditor suppliers={[supplierA, supplierB]} offers={[]} onChange={onChange} />);
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Bezugsquelle hinzufügen' }));
  expect(screen.getByRole('heading', { name: 'Bevorzugte Bezugsquelle' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Alternative Bezugsquelle hinzufügen' }));
  expect(screen.getByRole('heading', { name: 'Alternative Bezugsquelle' })).toBeInTheDocument();
});

it('promotes an alternative and demotes the old preferred offer', async () => {
  const user = userEvent.setup();
  render(<Harness initial={[preferred, alternative]} />);
  await user.click(screen.getByRole('button', { name: 'Als bevorzugt festlegen' }));
  expect(readOffers()).toEqual([
    expect.objectContaining({ supplier_id: preferred.supplier_id, is_preferred: false }),
    expect.objectContaining({ supplier_id: alternative.supplier_id, is_preferred: true }),
  ]);
});
```

- [ ] **Step 2: Run and verify RED**

Run: `npm.cmd run test -- ProcurementOffersEditor.test.tsx --run`

Expected: FAIL because the editor does not exist.

- [ ] **Step 3: Implement controlled offer drafts and replacement client**

```ts
export type ProcurementResource =
  | { kind: 'material'; small_part_id: number }
  | { kind: 'filament'; material: string; subtype: string | null; brand: string | null; color_name: string | null };

export interface ProcurementOfferDraft {
  id?: number;
  supplier_id: number | null;
  supplier_sku: string;
  purchase_url: string;
  package_quantity: string;
  package_unit_code: string;
  minimum_order_quantity: string;
  lead_time_days: number | null;
  net_price: string;
  gross_price: string;
  is_preferred: boolean;
  is_active: boolean;
}

export const procurementOffersApi = {
  list: (resource: ProcurementResource) => request<ProcurementOffer[]>(`/procurement-offers?${resourceQuery(resource)}`),
  replace: (resource: ProcurementResource, offers: ProcurementOfferDraft[]) => request<ProcurementOffer[]>('/procurement-offers/resource', { method: 'PUT', body: JSON.stringify({ resource, offers }) }),
};
```

The component renders a bordered section per offer, uses supplier defaults for a newly selected supplier, exposes “Als bevorzugt festlegen”, and allows more than two offers under “Weitere Bezugsquellen”. It never performs network writes itself.
It keeps the nested supplier snapshot from `ProcurementOfferRead`, marks an inactive supplier visibly as “Lieferant deaktiviert”, and still displays that existing offer. With `readOnly`, render the same values without add/remove/promote actions and disable all shared form controls.

- [ ] **Step 4: Run editor tests and lint**

Run: `npm.cmd run test -- ProcurementOffersEditor.test.tsx --run`

Expected: PASS.

Run: `npm.cmd run lint`

Expected: exit 0.

- [ ] **Step 5: Commit shared editor**

```bash
git add frontend/src/api/procurement.ts frontend/src/components/warehouse/ProcurementOffersEditor.tsx frontend/src/__tests__/components/ProcurementOffersEditor.test.tsx
git commit -m "feat(procurement): add reusable offer editor"
```

---

### Task 7: ForgeDesk-Derived Material Dialog and Material Overview

**Files:**
- Modify: `frontend/src/api/smallParts.ts`
- Modify: `frontend/src/components/warehouse/SmallPartEditor.tsx`
- Modify: `frontend/src/components/warehouse/SmallPartStockDialog.tsx`
- Modify: `frontend/src/pages/SmallPartsPage.tsx`
- Modify: `frontend/src/__tests__/components/SmallPartEditor.test.tsx`
- Modify: `frontend/src/__tests__/pages/SmallPartsPage.test.tsx`

**Interfaces:**
- Produces: complete material create/edit flow and offer persistence.
- Consumes: Task 4 material API, Task 5 suppliers client, Task 6 controlled offer editor.

- [ ] **Step 1: Write failing dialog structure and submit tests**

```tsx
it('renders the ForgeDesk-derived material sections', async () => {
  renderEditor(null);
  expect(screen.getByRole('dialog', { name: 'Material hinzufügen' })).toBeInTheDocument();
  for (const heading of ['Artikel', 'Bestand', 'Beschaffung', 'Verbrauchsgrund', 'Notiz intern']) {
    expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument();
  }
  expect(screen.getByLabelText('Anfangsmenge')).toBeInTheDocument();
  expect(screen.getByLabelText('Beschreibung')).toBeInTheDocument();
});

it('creates material, books opening stock, then persists offers', async () => {
  vi.mocked(smallPartsApi.create).mockResolvedValue({ ...part, id: 42 });
  await fillRequiredMaterialFields(user);
  await user.type(screen.getByLabelText('Anfangsmenge'), '25');
  await user.click(screen.getByRole('button', { name: 'Material speichern' }));
  await waitFor(() => expect(smallPartsApi.create).toHaveBeenCalledWith(expect.objectContaining({ opening_quantity: '25', default_consumption_reason: 'Produktion' })));
  expect(procurementOffersApi.replace).toHaveBeenCalledWith({ kind: 'material', small_part_id: 42 }, expect.any(Array));
});
```

- [ ] **Step 2: Run and verify RED**

Run: `npm.cmd run test -- SmallPartEditor.test.tsx SmallPartsPage.test.tsx --run`

Expected: FAIL on old title, missing sections, and missing fields.

- [ ] **Step 3: Rebuild the dialog with shared controls and procurement flow**

Import `type ReactNode` from React, add this local section primitive, and use it for all five sections:

```tsx
function FormSection({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section className="space-y-4" aria-labelledby={id}>
      <div className="flex items-center gap-3">
        <h3 id={id} className="shrink-0 text-sm font-semibold text-white">{title}</h3>
        <div className="h-px flex-1 bg-bambu-dark-tertiary" />
      </div>
      {children}
    </section>
  );
}
```

Inside `Modal open onClose={onClose} title={part ? 'Material bearbeiten' : 'Material hinzufügen'} className="max-w-3xl"`, render one `form.space-y-6`. Use stable IDs `material-section-article`, `material-section-stock`, `material-section-procurement`, `material-section-consumption`, and `material-section-notes`. Each field group uses `grid gap-4 sm:grid-cols-2`; full-width description, search terms, offers, and notes use `sm:col-span-2`. Render `Button variant="secondary"` for cancel and the primary `Button` with `loading={pending}` in `sticky bottom-0 flex justify-end gap-3 border-t border-bambu-dark-tertiary bg-bambu-dark-secondary pt-4`. Do not add another `ScrollArea`; shared `Modal` already owns the single scrolling content region.

Do not show opening quantity while editing. On create, await `smallPartsApi.create`, then replace offers with the returned ID; on update, update the material and replace offers for the existing ID. Keep the dialog open with a visible error if offer persistence fails. `SmallPartStockDialog` initializes its reason from `part.default_consumption_reason`. When `part.supplier_reference` is non-empty, show “Bisherige Lieferantenreferenz” as a read-only legacy value until the user maps it into an offer; never discard it during material updates.

On `SmallPartsPage`, use visible `Material`, `Material hinzufügen`, `Material durchsuchen`, loading/error/empty material copy, and show `preferred_offer.supplier.name`, net price, and lead time on cards.

- [ ] **Step 4: Run material UI tests**

Run: `npm.cmd run test -- SmallPartEditor.test.tsx SmallPartsPage.test.tsx --run`

Expected: PASS.

Run: `npm.cmd run lint`

Expected: exit 0.

- [ ] **Step 5: Commit material redesign**

```bash
git add frontend/src/api/smallParts.ts frontend/src/components/warehouse/SmallPartEditor.tsx frontend/src/components/warehouse/SmallPartStockDialog.tsx frontend/src/pages/SmallPartsPage.tsx frontend/src/__tests__/components/SmallPartEditor.test.tsx frontend/src/__tests__/pages/SmallPartsPage.test.tsx
git commit -m "feat(material): adopt ForgeDesk procurement workflow"
```

---

### Task 8: Filament SKU Procurement Integration

**Files:**
- Modify: `frontend/src/components/ForecastPanel.tsx`
- Create: `frontend/src/__tests__/components/ForecastPanelProcurement.test.tsx`
- Modify: `frontend/src/i18n/locales/{de,en,es,fr,it,ja,ko,pt-BR,tr,zh-CN,zh-TW}.ts`

**Interfaces:**
- Produces: procurement editor in each expanded filament SKU row.
- Consumes: Task 6 `ProcurementOffersEditor` and `procurementOffersApi`; existing four-field filament SKU identity.

- [ ] **Step 1: Write failing filament procurement test**

```tsx
it('loads and saves procurement offers for a filament SKU', async () => {
  server.use(
    http.get('/api/v1/procurement-offers', () => HttpResponse.json([preferredOffer])),
    http.put('/api/v1/procurement-offers/resource', async ({ request }) => HttpResponse.json((await request.json() as { offers: unknown[] }).offers)),
  );
  const user = userEvent.setup();
  renderForecastWithSpool({ material: 'PLA', subtype: 'Matte', brand: 'Poly', color_name: 'Black' });
  await user.click(await screen.findByRole('button', { name: 'PLA Matte Poly Black erweitern' }));
  expect(await screen.findByRole('heading', { name: 'Beschaffung' })).toBeInTheDocument();
  expect(screen.getByText('Filament World')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Bezugsquellen speichern' }));
  await waitFor(() => expect(screen.getByText('Bezugsquellen gespeichert')).toBeInTheDocument());
});
```

- [ ] **Step 2: Run and verify RED**

Run: `npm.cmd run test -- ForecastPanelProcurement.test.tsx --run`

Expected: FAIL because no procurement section exists.

- [ ] **Step 3: Add procurement to expanded SKU rows**

```tsx
const resource: ProcurementResource = {
  kind: 'filament',
  material: f.group.material,
  subtype: f.group.subtype,
  brand: f.group.brand,
  color_name: f.group.colorName,
};

{expanded ? (
  <FilamentProcurementSection resource={resource} readOnly={!canWrite} />
) : null}
```

Extract `FilamentProcurementSection` at module scope to avoid inline component recreation. It always queries `['procurement-offers', resource]`; it queries `['suppliers', 'active']` and enables save only when `readOnly` is false. It keeps drafts locally, writes through the replacement endpoint, invalidates the offer query, and shows success/error toasts. Read-only inventory users see offers but no mutation controls. Add `aria-label={expanded ? `${label} reduzieren` : `${label} erweitern`}` to the expand button.

- [ ] **Step 4: Run filament procurement and forecasting regressions**

Run: `npm.cmd run test -- ForecastPanelProcurement.test.tsx ForecastPanel --run`

Expected: PASS.

Run: `npm.cmd run check:i18n`

Expected: exit 0.

- [ ] **Step 5: Commit filament integration**

```bash
git add frontend/src/components/ForecastPanel.tsx frontend/src/__tests__/components/ForecastPanelProcurement.test.tsx frontend/src/i18n/locales
git commit -m "feat(filament): connect supplier procurement offers"
```

---

### Task 9: System-Wide Visible Material Terminology

**Files:**
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/pages/WarehousePage.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/components/settings/SmallPartsSettings.tsx`
- Modify: `frontend/src/components/warehouse/SmallPartCombobox.tsx`
- Modify: `frontend/src/components/orders/calculation/{AvailabilityPanel,CostBreakdown,MaterialsEditor,SmallPartsEditor}.tsx`
- Modify: `frontend/src/pages/OrderDetailPage.tsx`
- Modify: `frontend/src/i18n/locales/{de,en,es,fr,it,ja,ko,pt-BR,tr,zh-CN,zh-TW}.ts`
- Modify: `backend/app/api/routes/small_parts.py`
- Modify: affected tests under `frontend/src/__tests__`
- Create: `frontend/src/__tests__/lib/materialTerminology.test.ts`

**Interfaces:**
- Produces: no visible “Kleinteil/Small part” copy in the application.
- Consumes: all prior UI changes; technical identifiers remain untouched.

- [ ] **Step 1: Add a failing terminology regression scan**

```ts
import { readdirSync, readFileSync } from 'node:fs';
import { extname, join } from 'node:path';

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (entry.name === '__tests__' || entry.name === 'api') return [];
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return ['.ts', '.tsx'].includes(extname(entry.name)) ? [path] : [];
  });
}

it('does not expose legacy small-part terminology in frontend source', () => {
  const files = sourceFiles(join(process.cwd(), 'src'));
  const offenders = files.filter((file) => /Kleinteil(?:e|en|s)?|Small parts?|small parts?/.test(readFileSync(file, 'utf8')));
  expect(offenders).toEqual([]);
});
```

- [ ] **Step 2: Run and verify RED**

Run: `npm.cmd run test -- materialTerminology.test.ts --run`

Expected: FAIL listing the current visible-copy files.

- [ ] **Step 3: Replace visible copy without renaming technical symbols**

Use these canonical terms:

```text
German singular/plural: Material / Materialien
English singular/plural: Material / Materials
Navigation: Material
Settings: Materialkataloge / Material catalogs
Calculation section: Material & Zusatzmaterial / Materials & additional material
Search: Material suchen / Search materials
Backend visible 404: Material fehlt
```

Keep `SmallPartsPage`, `SmallPartEditor`, `smallPartsApi`, `small_part_id`, resource kind `small_part`, routes, query keys, and database tables unchanged. Update tests to assert the new accessible names and visible strings. Update all 11 `printops.nav.parts` locale values to their language’s normal word for material; preserve locale key parity.

- [ ] **Step 4: Run terminology, settings, calculation, and i18n tests**

Run: `npm.cmd run test -- materialTerminology.test.ts SmallPartsSettings.test.tsx CalculationWorkspace.test.tsx SmallPartCombobox.test.tsx --run`

Expected: PASS.

Run: `npm.cmd run check:i18n`

Expected: exit 0.

- [ ] **Step 5: Commit visible terminology**

```bash
git add frontend/src backend/app/api/routes/small_parts.py
git commit -m "refactor(ui): rename visible small parts to material"
```

---

### Task 10: Full Verification, Generated Frontend, and Browser QA

**Files:**
- Modify generated: `static/index.html`
- Replace generated: `static/assets/*` as produced by Vite
- Modify: `docs/order-management.md`
- Create or update: `design-qa.md`

**Interfaces:**
- Consumes: Tasks 1–9.
- Produces: deployable static assets and recorded reference-driven visual QA.

- [ ] **Step 1: Run focused backend feature suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_procurement_schema.py backend/tests/integration/test_suppliers_api.py backend/tests/integration/test_procurement_offers_api.py backend/tests/integration/test_small_parts_api.py backend/tests/integration/test_material_procurement_migration.py backend/tests/unit/test_small_parts_service.py -q
```

Expected: all selected tests PASS with zero failures.

- [ ] **Step 2: Run backend quality gates**

Run:

```powershell
.\.venv\Scripts\python.exe -m ruff check backend/app/models/procurement.py backend/app/schemas/procurement.py backend/app/services/procurement.py backend/app/api/routes/procurement.py backend/app/models/small_part.py backend/app/schemas/small_part.py backend/app/api/routes/small_parts.py
.\.venv\Scripts\python.exe -m ruff format --check backend/app/models/procurement.py backend/app/schemas/procurement.py backend/app/services/procurement.py backend/app/api/routes/procurement.py backend/app/models/small_part.py backend/app/schemas/small_part.py backend/app/api/routes/small_parts.py
```

Expected: both commands exit 0.

- [ ] **Step 3: Run frontend tests, lint, parity, and production build**

Run:

```powershell
cd frontend
npm.cmd run test -- SuppliersPage.test.tsx SupplierEditor.test.tsx ProcurementOffersEditor.test.tsx SmallPartEditor.test.tsx SmallPartsPage.test.tsx ForecastPanelProcurement.test.tsx materialTerminology.test.ts --run
npm.cmd run lint
npm.cmd run check:i18n
npm.cmd run build
```

Expected: all tests PASS; lint, parity, TypeScript, and Vite build exit 0.

- [ ] **Step 4: Perform reference-driven browser QA**

Use the in-app Browser on the existing server and test this exact flow:

```text
/warehouse/suppliers -> create supplier -> supplier appears
/warehouse/parts -> Material hinzufügen -> complete all sections -> save -> opening balance and preferred supplier appear
/warehouse/filament -> forecast -> expand SKU -> add alternative supplier -> save -> reload -> both offers remain
```

Check desktop near 1405×904 and a 390×844 mobile viewport. Verify page identity, meaningful DOM, no framework overlay, relevant console errors/warnings, keyboard focus, modal scrolling, sticky footer, and interaction state. Compare the material dialog against both ForgeDesk reference screenshots. Record `design-qa.md` with `final result: passed`; fix P0/P1/P2 mismatches before continuing.

- [ ] **Step 5: Update documentation and inspect the complete diff**

Document supplier and procurement behavior in `docs/order-management.md`. Run:

```powershell
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors; only intended source, tests, docs, and regenerated assets are changed. Confirm pre-existing untracked user files remain untouched.

- [ ] **Step 6: Commit release-ready implementation**

```bash
git add static/index.html static/assets docs/order-management.md design-qa.md
git commit -m "build: publish procurement frontend and documentation"
```
