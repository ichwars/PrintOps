# Offers, Orders, and Stock Reservations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the commercial workflow from an approved calculation revision through offer draft/sent/accepted states to one atomically created order, project, and complete filament/small-part reservation set.

**Architecture:** Add commercial offer/order aggregates that reference immutable calculation revisions and a generic reservation aggregate with typed allocations for internal spools, Spoolman spool IDs, and small parts. A single acceptance service re-derives requirements from the approved snapshot, rechecks availability, allocates exact sources, reserves numbers, creates the project/order, appends stock events, and commits once. Read-only availability preview and the calculation summary use the same allocation service in dry-run mode.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic v2, Decimal, SQLite/PostgreSQL transactions, existing NumberSequence/Project/Spool/Spoolman services, React 19, TypeScript, TanStack Query, Tailwind CSS, Vitest, Testing Library.

## Global Constraints

- A calculation and an offer draft/sent state never reserve inventory.
- Only an offer in `sent` state may transition to `accepted`.
- Acceptance is all-or-nothing: no partial project, order, reservation, ledger entry, or status update may survive failure.
- Repeating an acceptance with the same idempotency key returns the original result and creates no duplicates.
- A different key after acceptance returns the existing acceptance as a conflict; it does not create another order.
- Negative stock and partial reservations are forbidden.
- Internal spool availability is `label_weight - weight_used - active allocations`.
- Small-part availability is `physical ledger total - reserved ledger total`.
- Spoolman availability is re-fetched immediately before acceptance and reduced by active PrintOps overlay reservations. PrintOps serializes its own allocations; if external Spoolman state changes later, reconciliation raises a visible deficit instead of silently altering reservations.
- Filament requirements may allocate across multiple compatible spools; small-part requirements allocate only the referenced article.
- Rejection before acceptance creates no release events because no reservation exists.
- Cancellation releases only unconsumed allocations. Filament consumption is reconciled after print; small-part issue requires explicit project confirmation.
- Preserve existing `ORDERS_*`, `COMMERCIAL_DOCUMENTS_*`, `PROJECTS_*`, and `INVENTORY_*` permission boundaries.
- This plan consumes the structured calculation revision from `2026-07-18-calculation-project-files-slicer.md` and the small-parts ledger from `2026-07-18-small-parts-inventory.md`.

## File Structure

- `backend/app/models/commerce.py`: Offer, CustomerOrder, and idempotent OfferAcceptance.
- `backend/app/models/stock_reservation.py`: reservation requirements and allocations.
- `backend/app/schemas/commerce.py`: offer/order lifecycle contracts.
- `backend/app/schemas/stock_reservation.py`: requirement, allocation, availability, issue, and reconciliation contracts.
- `backend/app/services/stock_availability.py`: unified internal-spool, Spoolman, and small-part availability/allocation.
- `backend/app/services/stock_reservations.py`: append/release/consume reservation state and ledger effects.
- `backend/app/services/offers.py`: draft, send, reject, and atomic accept use case.
- `backend/app/api/routes/offers.py`: offer lifecycle and acceptance endpoints.
- `backend/app/api/routes/orders.py`: order detail, cancellation, reservation, and issue endpoints.
- `frontend/src/api/offers.ts`: typed commercial API.
- `frontend/src/pages/OffersPage.tsx`: offer list/detail/lifecycle UI.
- `frontend/src/pages/OrderDetailPage.tsx`: project/order reservation operations.
- `frontend/src/components/orders/calculation/AvailabilityPanel.tsx`: calculation dry-run stock status.

---

### Task 1: Define Offer, Order, Acceptance, and Reservation Schemas

**Files:**
- Create: `backend/app/models/commerce.py`
- Create: `backend/app/models/stock_reservation.py`
- Create: `backend/app/schemas/commerce.py`
- Create: `backend/app/schemas/stock_reservation.py`
- Modify: `backend/app/models/project.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/database.py`
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/integration/test_commerce_reservation_schema.py`

**Interfaces:**
- Produces `Offer`, `CustomerOrder`, `OfferAcceptance`, `StockReservation`, `StockReservationAllocation`, and `StockResourceLock`.
- `Offer.calculation_revision_id` freezes the commercial source.
- `CustomerOrder.project_id` is unique and `OfferAcceptance.offer_id` is unique.

- [ ] **Step 1: Write the failing schema contract test**

```python
EXPECTED = {"offers", "customer_orders", "offer_acceptances", "stock_reservations", "stock_reservation_allocations", "stock_resource_locks"}


def test_reservation_target_constraint_compiles():
    names = {constraint.name for constraint in StockReservationAllocation.__table__.constraints}
    assert "ck_stock_allocation_exact_target" in names
    assert "ck_stock_allocation_quantities" in names


async def test_acceptance_keys_are_unique(db_session, offer):
    db_session.add_all([
        OfferAcceptance(offer_id=offer.id, idempotency_key="accept-1", order_id=1, project_id=1),
        OfferAcceptance(offer_id=offer.id, idempotency_key="accept-2", order_id=2, project_id=2),
    ])
    with pytest.raises(IntegrityError):
        await db_session.commit()
```

- [ ] **Step 2: Run the schema test and verify models are absent**

Run `python -m pytest backend/tests/integration/test_commerce_reservation_schema.py -q`.

- [ ] **Step 3: Implement commercial models**

```python
class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (UniqueConstraint("business_profile_id", "number", name="uq_offer_profile_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(ForeignKey("business_profiles.id", ondelete="RESTRICT"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), index=True)
    calculation_revision_id: Mapped[int] = mapped_column(ForeignKey("calculation_revisions.id", ondelete="RESTRICT"), index=True)
    number: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    preferred_variant_sort_order: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CustomerOrder(Base):
    __tablename__ = "customer_orders"
    __table_args__ = (UniqueConstraint("business_profile_id", "number", name="uq_order_profile_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(ForeignKey("business_profiles.id", ondelete="RESTRICT"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), index=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id", ondelete="RESTRICT"), unique=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), unique=True)
    number: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    accepted_snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OfferAcceptance(Base):
    __tablename__ = "offer_acceptances"
    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offers.id", ondelete="RESTRICT"), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("customer_orders.id", ondelete="RESTRICT"), unique=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Implement reservation models**

```python
class StockReservation(Base):
    __tablename__ = "stock_reservations"
    __table_args__ = (UniqueConstraint("order_id", "source_key", name="uq_stock_reservation_source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("customer_orders.id", ondelete="RESTRICT"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), index=True)
    source_key: Mapped[str] = mapped_column(String(255))
    resource_kind: Mapped[str] = mapped_column(String(24))
    material_code: Mapped[str | None] = mapped_column(String(120))
    requested_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    unit_code: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StockReservationAllocation(Base):
    __tablename__ = "stock_reservation_allocations"
    __table_args__ = (
        CheckConstraint(
            "(spool_id IS NOT NULL AND external_spool_id IS NULL AND small_part_id IS NULL) OR "
            "(spool_id IS NULL AND external_spool_id IS NOT NULL AND small_part_id IS NULL) OR "
            "(spool_id IS NULL AND external_spool_id IS NULL AND small_part_id IS NOT NULL)",
            name="ck_stock_allocation_exact_target",
        ),
        CheckConstraint("allocated_quantity > 0 AND consumed_quantity >= 0 AND consumed_quantity <= allocated_quantity", name="ck_stock_allocation_quantities"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("stock_reservations.id", ondelete="CASCADE"), index=True)
    inventory_backend: Mapped[str] = mapped_column(String(16))
    spool_id: Mapped[int | None] = mapped_column(ForeignKey("spool.id", ondelete="RESTRICT"), index=True)
    external_spool_id: Mapped[str | None] = mapped_column(String(120), index=True)
    small_part_id: Mapped[int | None] = mapped_column(ForeignKey("small_parts.id", ondelete="RESTRICT"), index=True)
    allocated_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    consumed_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))


class StockResourceLock(Base):
    __tablename__ = "stock_resource_locks"
    resource_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    touched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 5: Add strict schemas, registration, and commit**

Schemas expose Decimal strings, allowed status literals, `expected_version`, and nested allocation reads. Add `order` relationship to `Project` without changing existing project APIs.

Run the focused schema test and expect PASS.

```powershell
git add backend/app/models/commerce.py backend/app/models/stock_reservation.py backend/app/schemas/commerce.py backend/app/schemas/stock_reservation.py backend/app/models/project.py backend/app/models/__init__.py backend/app/core/database.py backend/tests/conftest.py backend/tests/integration/test_commerce_reservation_schema.py
git commit -m "feat(orders): add offers and reservation schema"
```

---

### Task 2: Build Unified Availability and Deterministic Allocation

**Files:**
- Create: `backend/app/services/stock_availability.py`
- Create: `backend/tests/unit/test_stock_availability.py`

**Interfaces:**
- Produces `StockRequirement`, `StockCandidate`, `AvailabilityLine`, and `AllocationPlan` dataclasses.
- Produces `requirements_from_revision(snapshot, variant_sort_order)`.
- Produces `check_availability(session, requirements, *, lock: bool) -> AvailabilityReport`.
- Produces `allocate_all(report) -> list[AllocationPlan]`; raises `InsufficientStock` with every short line.

- [ ] **Step 1: Write failing allocation tests**

Cover one filament requirement split across two internal spools, compatible material matching, archived/empty exclusion, existing active allocation subtraction, one Spoolman candidate with local overlay subtraction, small-part availability, deterministic oldest/lowest-remainder allocation, and a report containing all shortages rather than failing on the first.

```python
plan = allocate_filament(
    Decimal("750"),
    [candidate(1, "500"), candidate(2, "400")],
)
assert [(item.resource_id, item.quantity) for item in plan] == [
    ("1", Decimal("500")),
    ("2", Decimal("250")),
]
```

- [ ] **Step 2: Run tests and verify service is absent**

Run `python -m pytest backend/tests/unit/test_stock_availability.py -q`.

- [ ] **Step 3: Derive requirements from immutable revision data**

```python
@dataclass(frozen=True)
class StockRequirement:
    source_key: str
    resource_kind: Literal["filament", "small_part"]
    quantity: Decimal
    unit_code: str
    material_key: str | None = None
    color_key: str | None = None
    allow_color_substitution: bool = False
    small_part_id: int | None = None


@dataclass(frozen=True)
class StockCandidate:
    backend: Literal["internal", "spoolman", "small_part"]
    resource_id: str
    available: Decimal
    material_key: str | None
    color_key: str | None


@dataclass(frozen=True)
class AllocationPlan:
    source_key: str
    candidate: StockCandidate
    quantity: Decimal


@dataclass(frozen=True)
class AvailabilityLine:
    requirement: StockRequirement
    status: Literal["available", "short", "unmapped"]
    physical: Decimal
    reserved: Decimal
    available: Decimal
    shortage: Decimal
    allocations: tuple[AllocationPlan, ...]


@dataclass(frozen=True)
class AvailabilityReport:
    lines: tuple[AvailabilityLine, ...]
    checked_at: datetime
```

For every selected plate compute `(ceil(good_parts / parts_per_print) + scrap_prints) * grams_per_print`; preserve `material_key`, `color_key`, and `allow_color_substitution` from the approved mapping and group only compatible requirements. Preserve a source key per plate/material. For every small-part row use its snapshot quantity and ID. Reject snapshots missing required IDs, provenance, or positive quantities.

- [ ] **Step 4: Implement internal and external filament candidates**

Internal candidates use `select(Spool).with_for_update()` when `lock=True`, then subtract active allocation totals. Match normalized material and required color; permit a color mismatch only when the approved requirement explicitly sets `allow_color_substitution=true`. Spoolman candidates come from `get_spoolman_client()` and are re-fetched for locked acceptance. Before allocation, insert-or-load `StockResourceLock(resource_key=f"spoolman:{id}")` and select that row with `FOR UPDATE`, so two PrintOps requests cannot allocate the same external remainder concurrently. Do not write Spoolman physical usage during reservation.

- [ ] **Step 5: Implement small-part candidates and reports**

Use `small_parts.get_balance()` and `SmallPart.unit_code`. Return `status` as `available`, `short`, or `unmapped`, plus required, physical, reserved, available, shortage, selected allocations, and checked timestamp.

- [ ] **Step 6: Run tests and commit**

```powershell
git add backend/app/services/stock_availability.py backend/tests/unit/test_stock_availability.py
git commit -m "feat(inventory): plan atomic stock allocations"
```

---

### Task 3: Expose Read-Only Availability to Calculations

**Files:**
- Modify: `backend/app/schemas/calculation.py`
- Modify: `backend/app/api/routes/calculations.py`
- Create: `backend/tests/integration/test_calculation_availability_api.py`

**Interfaces:**
- `GET /calculations/{id}/availability?variant_id=` checks a persisted draft.
- `POST /calculations/availability-preview` accepts one unsaved `CalculationVariantInput` plus current effective defaults.
- Both return the same `AvailabilityReportRead` and never write reservations or ledger rows.

- [ ] **Step 1: Write failing no-side-effect API tests**

Assert available and short filament/small-part lines, last-checked timestamp, mapped allocations as advisory data, no `StockReservation` rows, no small-part reservation ledger rows, and repeated preview with changed stock returns changed availability.

- [ ] **Step 2: Run tests and verify endpoints are absent**

Run `python -m pytest backend/tests/integration/test_calculation_availability_api.py -q`.

- [ ] **Step 3: Implement dry-run endpoints**

Define `AvailabilityReportRead(lines: list[AvailabilityLineRead], reservation_state: Literal["not_reserved"], checked_at: datetime)` in `backend/app/schemas/stock_reservation.py`. Load or validate the variant, derive requirements with the same function used by acceptance, call `check_availability(..., lock=False)`, and return `reservation_state="not_reserved"`. Gate with `CALCULATIONS_READ`; preview accepts no project/order IDs.

- [ ] **Step 4: Run tests and commit**

```powershell
git add backend/app/schemas/calculation.py backend/app/api/routes/calculations.py backend/tests/integration/test_calculation_availability_api.py
git commit -m "feat(calculations): preview stock availability"
```

---

### Task 4: Implement Offer Draft, Send, and Reject Lifecycles

**Files:**
- Create: `backend/app/services/offers.py`
- Create: `backend/app/api/routes/offers.py`
- Modify: `backend/app/services/business_profile.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_offers_api.py`

**Interfaces:**
- `POST /offers` creates a draft from `calculation_revision_id`.
- `GET /offers` and `GET /offers/{id}` read offers.
- `POST /offers/{id}/send`, `/reject`, and `/accept` are versioned transitions.
- Uses `reserve_number(..., key="offer")`; acceptance later uses key `order`.

- [ ] **Step 1: Write failing lifecycle tests**

Assert only approved revisions can create offers, preferred variant is snapshotted, draft can be sent, sent can be rejected, invalid transitions return 409, optimistic version conflicts return 409, and no stock rows appear for create/send/reject.

- [ ] **Step 2: Run tests and verify routes are absent**

Run `python -m pytest backend/tests/integration/test_offers_api.py -q`.

- [ ] **Step 3: Seed number sequences and create immutable offer snapshots**

When creating a business profile, add sequences `offer` with prefix `ANG` and `order` with prefix `AUF`, pattern `{PREFIX}-{YYYY}-{#####}`, yearly reset. Existing profiles receive idempotent backfill rows. Offer snapshot includes customer/profile identity, currency, selected variant, derived positions, price totals, effective values, plate requirements, and small-part requirements.

- [ ] **Step 4: Implement guarded transitions**

```python
ALLOWED_TRANSITIONS = {
    "draft": {"sent"},
    "sent": {"accepted", "rejected"},
    "accepted": set(),
    "rejected": set(),
}


def transition(offer: Offer, target: str, expected_version: int, now: datetime) -> None:
    if offer.version != expected_version:
        raise VersionConflictError("Offer version changed")
    if target not in ALLOWED_TRANSITIONS[offer.status]:
        raise InvalidOfferTransition(offer.status, target)
    offer.status = target
    offer.version += 1
    setattr(offer, f"{target}_at", now)
```

- [ ] **Step 5: Register routes, run tests, and commit**

Use `COMMERCIAL_DOCUMENTS_DRAFT` for create, `COMMERCIAL_DOCUMENTS_READ` for reads, `COMMERCIAL_DOCUMENTS_ISSUE` for send, and `COMMERCIAL_DOCUMENTS_CORRECT` for reject.

```powershell
git add backend/app/services/offers.py backend/app/api/routes/offers.py backend/app/services/business_profile.py backend/app/core/database.py backend/app/main.py backend/tests/integration/test_offers_api.py
git commit -m "feat(offers): add commercial lifecycle"
```

---

### Task 5: Implement Atomic and Idempotent Offer Acceptance

**Files:**
- Create: `backend/app/services/stock_reservations.py`
- Modify: `backend/app/services/offers.py`
- Modify: `backend/app/api/routes/offers.py`
- Create: `backend/tests/integration/test_offer_acceptance.py`

**Interfaces:**
- Produces `accept_offer(session, offer_id, expected_version, idempotency_key, actor_id) -> AcceptanceResult`.
- Produces one `Project`, one `CustomerOrder`, one `OfferAcceptance`, reservation requirements, allocations, and small-part ledger reservation rows.

- [ ] **Step 1: Write failing happy-path and rollback tests**

The happy path uses two plates, one material split across two spools, a second material, and two small parts. Assert exact allocations, project targets, order/offer links, reservation journal deltas, accepted status, and one committed acceptance. The shortage path asserts zero new rows in every involved table and offer remains `sent` with a structured shortage response.

- [ ] **Step 2: Write failing idempotency and concurrency tests**

Run two sessions against the same scarce stock and two sent offers. Exactly one accepts; the other returns `reservation_blocked`. Repeating the winner's idempotency key returns its original IDs and table counts remain unchanged.

- [ ] **Step 3: Run acceptance tests and verify failures**

Run `python -m pytest backend/tests/integration/test_offer_acceptance.py -q`.

- [ ] **Step 4: Implement one-transaction acceptance**

```python
@dataclass(frozen=True)
class AcceptanceResult:
    offer: Offer
    order: CustomerOrder
    project: Project
    reservations: tuple[StockReservation, ...]


async def accept_offer(session: AsyncSession, *, offer_id: int, expected_version: int,
                       idempotency_key: str, actor_id: int | None) -> AcceptanceResult:
    replay = await session.scalar(select(OfferAcceptance).where(OfferAcceptance.idempotency_key == idempotency_key))
    if replay:
        return await load_acceptance_result(session, replay)
    offer = await session.scalar(select(Offer).where(Offer.id == offer_id).with_for_update())
    validate_offer_for_acceptance(offer, expected_version)
    requirements = requirements_from_revision(offer.snapshot, offer.preferred_variant_sort_order)
    report = await check_availability(session, requirements, lock=True)
    plans = allocate_all(report)
    project = Project(name=offer.snapshot["title"], status="active", target_count=plate_runs(requirements),
                      target_parts_count=good_parts(requirements))
    session.add(project)
    await session.flush()
    order = CustomerOrder(
        business_profile_id=offer.business_profile_id, customer_id=offer.customer_id, offer_id=offer.id,
        project_id=project.id,
        number=await reserve_number(session, business_profile_id=offer.business_profile_id, key="order", effective_date=date.today()),
        accepted_snapshot=offer.snapshot,
    )
    session.add(order)
    await session.flush()
    reservations = await persist_reservation_plans(session, order, project, plans, actor_id=actor_id)
    acceptance = OfferAcceptance(offer_id=offer.id, idempotency_key=idempotency_key, order_id=order.id, project_id=project.id)
    session.add(acceptance)
    transition(offer, "accepted", expected_version, datetime.now(timezone.utc))
    await session.flush()
    return AcceptanceResult(offer, order, project, reservations)
```

The route must not call `commit()` inside helpers; `get_db` owns the single commit. Convert `InsufficientStock` to HTTP 409 with all shortage lines and `code="reservation_blocked"`.

- [ ] **Step 5: Persist reservation effects**

For small parts append `entry_kind="reservation"`, `reserved_delta=quantity`, physical delta zero, and idempotency `reservation:<allocation_id>`. Internal/Spoolman filament remains an allocation overlay; do not increment `weight_used` at reservation time.

- [ ] **Step 6: Run tests and commit**

```powershell
git add backend/app/services/stock_reservations.py backend/app/services/offers.py backend/app/api/routes/offers.py backend/tests/integration/test_offer_acceptance.py
git commit -m "feat(orders): accept offers with atomic reservations"
```

---

### Task 6: Release, Issue, and Reconcile Reserved Stock

**Files:**
- Create: `backend/app/api/routes/orders.py`
- Modify: `backend/app/services/stock_reservations.py`
- Modify: `backend/app/services/usage_tracker.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/integration/test_order_reservation_lifecycle.py`

**Interfaces:**
- `GET /orders/{id}` includes project and reservations.
- `POST /orders/{id}/cancel` releases all unconsumed allocations atomically.
- `POST /orders/{id}/small-parts/{allocation_id}/issue` confirms quantity issue.
- `POST /orders/{id}/filament/{allocation_id}/reconcile` applies actual grams when automatic print linkage is unavailable.
- `usage_tracker` reconciles linked project/order allocations after successful print.

- [ ] **Step 1: Write failing release/issue/reconcile tests**

Assert cancel releases remaining small-part reserved deltas and marks allocations/reservations released; confirmed small-part issue writes one journal row with both `physical_delta=-q` and `reserved_delta=-q`; filament reconciliation increases `Spool.weight_used` once, records actual consumption, and releases unused allocation grams. Repeating any command with its idempotency key changes nothing.

- [ ] **Step 2: Run lifecycle tests and verify routes are absent**

Run `python -m pytest backend/tests/integration/test_order_reservation_lifecycle.py -q`.

- [ ] **Step 3: Implement state transitions**

`issue_small_part` locks allocation and part, limits issue to `allocated-consumed`, appends an `issue` ledger row, and updates consumed quantity. `release_order` appends a `release` reserved delta only for outstanding small-part quantity and marks filament overlay allocations released without touching physical weight. All changes occur in one transaction.

- [ ] **Step 4: Connect successful prints to filament reconciliation**

Use `Project -> CustomerOrder -> active filament allocations` and the existing usage tracker result. Distribute actual grams proportionally over the reserved allocations for the printed plate/source key; use existing `SpoolUsageHistory` for internal physical usage and update only reservation consumed/released values around it. If automatic mapping is ambiguous, leave reservation active and expose `needs_reconciliation=true`.

- [ ] **Step 5: Implement routes and permissions**

Use `ORDERS_READ` for reads, `ORDERS_CANCEL` for cancel, and `ORDERS_MANAGE_PRODUCTION` plus `INVENTORY_UPDATE` for issue/reconcile.

- [ ] **Step 6: Run tests and commit**

```powershell
git add backend/app/api/routes/orders.py backend/app/services/stock_reservations.py backend/app/services/usage_tracker.py backend/app/main.py backend/tests/integration/test_order_reservation_lifecycle.py
git commit -m "feat(orders): reconcile and release reservations"
```

---

### Task 7: Build Offer/Order UI and Live Calculation Availability

**Files:**
- Create: `frontend/src/api/offers.ts`
- Create: `frontend/src/pages/OffersPage.tsx`
- Create: `frontend/src/pages/OrderDetailPage.tsx`
- Create: `frontend/src/components/orders/OfferDetail.tsx`
- Create: `frontend/src/components/orders/ReservationList.tsx`
- Create: `frontend/src/components/orders/calculation/AvailabilityPanel.tsx`
- Modify: `frontend/src/components/orders/calculation/CalculationSummary.tsx`
- Modify: `frontend/src/components/orders/calculation/FollowUpActions.tsx`
- Modify: `frontend/src/components/orders/CalculationWorkspace.tsx`
- Modify: `frontend/src/pages/OrdersPage.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/__tests__/pages/OffersPage.test.tsx`
- Create: `frontend/src/__tests__/components/CalculationAvailability.test.tsx`

**Interfaces:**
- `/orders/offers` renders `OffersPage`; `/orders/offers/:id` renders detail; `/orders/:id` renders order/reservations.
- Calculation summary polls dry-run availability after a 300 ms debounce.
- Follow-up action creates an offer draft only from an approved revision.

- [ ] **Step 1: Write failing calculation availability tests**

Assert lines for filament and small parts, physical/reserved/available/required values, `Prüfung ohne Reservierung`, stale timestamp, short/unmapped blockers, and refresh after requirement changes. Status must use icon and text, not color only.

- [ ] **Step 2: Write failing offer lifecycle tests**

Cover draft creation from a revision, send, reject, accept confirmation, idempotency header/body key reuse, shortage dialog with all missing resources, accepted order/project links, and disabled duplicate acceptance.

- [ ] **Step 3: Implement typed clients**

```ts
export const offersApi = {
  list: (status?: OfferStatus) => request<Offer[]>(`/offers${status ? `?status=${status}` : ''}`),
  create: (calculationRevisionId: number) => request<Offer>('/offers', { method: 'POST', body: JSON.stringify({ calculation_revision_id: calculationRevisionId }) }),
  send: (id: number, expectedVersion: number) => request<Offer>(`/offers/${id}/send`, { method: 'POST', body: JSON.stringify({ expected_version: expectedVersion }) }),
  reject: (id: number, expectedVersion: number) => request<Offer>(`/offers/${id}/reject`, { method: 'POST', body: JSON.stringify({ expected_version: expectedVersion }) }),
  accept: (id: number, expectedVersion: number, idempotencyKey: string) => request<AcceptanceResult>(`/offers/${id}/accept`, { method: 'POST', body: JSON.stringify({ expected_version: expectedVersion, idempotency_key: idempotencyKey }) }),
};
```

- [ ] **Step 4: Implement availability panel and follow-up activation**

Use persisted calculation GET availability when saved and preview POST for unsaved edits. `FollowUpActions` is no longer disabled after approval; its offer action shows the exact revision being used. Do not expose direct “Druckauftrag erstellen” before offer acceptance.

- [ ] **Step 5: Replace the offers scaffold and add order detail**

Offers table columns are number, customer, revision, net value, status, updated date, and actions. Offer detail renders immutable positions and availability; acceptance requires confirmation. Order detail renders project link, reservation groups/allocations, remaining quantity, small-part issue, manual filament reconciliation, and cancel/release.

- [ ] **Step 6: Run tests, i18n parity, and commit**

```powershell
git add frontend/src/api/offers.ts frontend/src/pages/OffersPage.tsx frontend/src/pages/OrderDetailPage.tsx frontend/src/components/orders/OfferDetail.tsx frontend/src/components/orders/ReservationList.tsx frontend/src/components/orders/calculation/AvailabilityPanel.tsx frontend/src/components/orders/calculation/CalculationSummary.tsx frontend/src/components/orders/calculation/FollowUpActions.tsx frontend/src/components/orders/CalculationWorkspace.tsx frontend/src/pages/OrdersPage.tsx frontend/src/App.tsx frontend/src/__tests__/pages/OffersPage.test.tsx frontend/src/__tests__/components/CalculationAvailability.test.tsx frontend/src/i18n/locales/de.ts frontend/src/i18n/locales/en.ts
git commit -m "feat(ui): complete offers and reservation workflow"
```

---

### Task 8: Run Integrated Acceptance, Migration, and End-to-End Verification

**Files:**
- Create: `backend/tests/integration/test_calculation_offer_order_e2e.py`
- Modify: `backend/app/core/database.py`
- Modify: `docs/order-management.md`
- Modify: `docs/superpowers/plans/2026-07-18-offers-orders-reservations.md`

**Interfaces:**
- Produces one tested path from multi-plate 3MF calculation to completed reservation lifecycle.
- Backfills offer/order number sequences for existing business profiles idempotently.

- [ ] **Step 1: Add the full failing backend workflow test**

Create a calculation with a four-plate project file, select two plates, clone a second variant, change material/quantity, add small parts, approve, create/send/accept an offer, verify exactly one order/project/reservation set, issue small parts, reconcile filament, and release remaining reservations on completion/cancel.

- [ ] **Step 2: Add migration and backup coverage**

Backfill `offer` and `order` sequences once per business profile and verify database backup/restore includes all new commerce, reservation, calculation-project, slice, small-part, and ledger tables without nulling required defaults.

- [ ] **Step 3: Run focused backend gates**

```powershell
python -m pytest backend/tests/integration/test_commerce_reservation_schema.py backend/tests/unit/test_stock_availability.py backend/tests/integration/test_calculation_availability_api.py backend/tests/integration/test_offers_api.py backend/tests/integration/test_offer_acceptance.py backend/tests/integration/test_order_reservation_lifecycle.py backend/tests/integration/test_calculation_offer_order_e2e.py -q
python -m ruff check backend/app/models/commerce.py backend/app/models/stock_reservation.py backend/app/services/stock_availability.py backend/app/services/stock_reservations.py backend/app/services/offers.py backend/app/api/routes/offers.py backend/app/api/routes/orders.py
python -m ruff format --check backend/app/models/commerce.py backend/app/models/stock_reservation.py backend/app/services/stock_availability.py backend/app/services/stock_reservations.py backend/app/services/offers.py backend/app/api/routes/offers.py backend/app/api/routes/orders.py
```

Expected: all selected tests pass and Ruff reports no errors.

- [ ] **Step 4: Run focused frontend gates**

```powershell
Set-Location frontend
npm.cmd run test -- --run src/__tests__/pages/OffersPage.test.tsx src/__tests__/components/CalculationAvailability.test.tsx src/__tests__/components/CalculationWorkspace.test.tsx src/__tests__/pages/SmallPartsPage.test.tsx
npm.cmd run check:i18n
npm.cmd run build
```

Expected: all tests, parity, and build pass.

- [ ] **Step 5: Run concurrency repeatedly**

Run the two-offers/one-stock acceptance test at least 20 times against SQLite and once against the project's PostgreSQL test configuration. Every run must produce exactly one accepted offer and no negative/partial stock state.

- [ ] **Step 6: Browser smoke test the complete workflow**

Verify calculation availability has no reservation side effect; send offer; accept it; follow order/project links; confirm exact spool and small-part allocations; attempt a conflicting acceptance; issue a small part; reconcile filament; cancel/release; reload every page and verify state persists.

- [ ] **Step 7: Update docs and commit verification**

Document statuses, permissions, idempotency, allocation order, Spoolman overlay behavior, release/issue/reconciliation, and the later Ware auto-intake exclusion.

```powershell
git add backend/app/core/database.py backend/tests/integration/test_calculation_offer_order_e2e.py docs/order-management.md docs/superpowers/plans/2026-07-18-offers-orders-reservations.md
git commit -m "test(orders): verify calculation to reservation workflow"
```
