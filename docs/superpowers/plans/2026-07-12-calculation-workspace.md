# Calculation Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a quotation-ready calculation workspace for concrete customer requests with transparent 3D-print production costs, variants, immutable approved revisions, and reusable templates.

**Architecture:** Add a relational calculation aggregate beside the existing business-profile and customer aggregates. Keep editable drafts normalized, persist approved revisions as immutable relational snapshots plus canonical result data, and centralize all `Decimal` formulas in a pure calculation engine used by the service layer. The React feature is split into a routed page, list, workspace sections, and a typed API module; Settings remains the owner of fallback defaults and the live example calculation.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Pydantic, SQLite/PostgreSQL compatibility, Python `Decimal`, React, TypeScript, Tailwind CSS, Vitest, Testing Library, pytest, Ruff, ESLint.

**Parity completion update (2026-07-12):** Tasks 1-6 and the minimal parts of Tasks 7-10 exist on `main`, but are not feature-complete. Execute Tasks 12-15 below to close the approved ForgeDesk-parity gap without reintroducing browser-local owners or activating later quotation, project, or production commands.

## Global Constraints

- Follow `docs/superpowers/specs/2026-07-12-calculation-workspace-design.md` and the parent `docs/superpowers/specs/2026-07-10-order-management-design.md`.
- Store money and rates as SQL `NUMERIC` and Python `Decimal`; never use binary floats for commercial arithmetic.
- Drafts are mutable; approved revisions are immutable and remain addressable after supersession.
- Store a complete cost-source and settings snapshot in every approved revision.
- Printer and inventory values override profile/material defaults; global calculation settings are fallback values only.
- Scrap changes explicit production runs and may not exist only as a hidden monetary surcharge.
- A customer is optional for calculation approval but required with a billing address for quotation handoff readiness.
- Do not implement quotation issuance, PDFs, reservations, actual costs, scheduling, or queue automation in this increment.
- Support SQLite and PostgreSQL without database-specific business behavior.
- Follow existing permission names: `calculations:read`, `calculations:update`, and `calculations:approve`.
- Preserve the current PrintOps UI language: full-width operational tables, compact controls, explicit states, and no nested-card maze.
- Every task starts with focused failing tests, ends with focused passing tests, and creates one intentional commit.

---

## File Structure

### Backend files to create

- `backend/app/models/calculation.py`: calculation aggregate, variants, lines, operations, labor entries, revisions, and templates.
- `backend/app/schemas/calculation.py`: enums plus create/update/list/detail/approval/template API contracts.
- `backend/app/services/calculation_engine.py`: pure `Decimal` quantity, cost, price, and rounding functions.
- `backend/app/services/calculation.py`: validation, source resolution, optimistic updates, revision snapshots, and template orchestration.
- `backend/app/api/routes/calculations.py`: permission-gated REST endpoints.
- `backend/tests/unit/test_calculation_engine.py`: formula and precision coverage.
- `backend/tests/integration/test_calculation_schema.py`: migration/model constraints and cross-database-safe invariants.
- `backend/tests/integration/test_calculations_api.py`: list, CRUD, variants, conflicts, approval, snapshots, templates, and permissions.

### Backend files to modify

- `backend/app/models/__init__.py`: export calculation models for metadata registration.
- `backend/app/core/database.py`: register models and add idempotent SQLite/PostgreSQL schema migration helpers.
- `backend/app/main.py`: import and register the calculations router.
- `backend/app/api/routes/__init__.py`: expose the calculations route module if required by the current import convention.

### Frontend files to create

- `frontend/src/api/calculations.ts`: calculation types and typed API calls.
- `frontend/src/lib/calculationMath.ts`: display-only preview math mirroring backend formulas with decimal strings.
- `frontend/src/pages/CalculationsPage.tsx`: route owner, data loading, filters, and explicit list states.
- `frontend/src/components/orders/CalculationList.tsx`: full-width operational table.
- `frontend/src/components/orders/CalculationWorkspace.tsx`: editor shell, save/approve/template commands, validation summary.
- `frontend/src/components/orders/calculation/RequestSection.tsx`: business profile, customer, dates, notes, and files metadata.
- `frontend/src/components/orders/calculation/LinesSection.tsx`: sellable-line editor.
- `frontend/src/components/orders/calculation/ProductionSection.tsx`: print and labor operations with provenance markers.
- `frontend/src/components/orders/calculation/CostPriceSection.tsx`: cost breakdown and price controls.
- `frontend/src/components/orders/calculation/VariantsSection.tsx`: comparison and preferred-variant selection.
- `frontend/src/__tests__/api/calculations.test.ts`: request/response contract tests.
- `frontend/src/__tests__/lib/calculationMath.test.ts`: frontend preview parity cases.
- `frontend/src/__tests__/pages/CalculationsPage.test.tsx`: list states, filtering, routing, and permissions.
- `frontend/src/__tests__/components/orders/CalculationWorkspace.test.tsx`: editing, provenance, live totals, warnings, approval, and conflict behavior.

### Frontend files to modify

- `frontend/src/App.tsx`: route `/orders/calculation` to `CalculationsPage`.
- `frontend/src/pages/OrdersPage.tsx`: remove the calculation placeholder branch if still present.
- `frontend/src/pages/SettingsPage.tsx`: replace the minimal cost card with the six approved calculation-default sections and live example.
- `frontend/src/api/client.ts`: re-export calculation contracts or keep the shared API transport consumed by `calculations.ts`.
- `frontend/src/i18n/locales/*.ts`: add parity-safe calculation, validation, source, revision, template, and settings copy.
- `frontend/src/__tests__/pages/SettingsPage.test.tsx`: calculation settings and example coverage.
- `frontend/src/__tests__/App.ordersCustomersRoute.test.tsx`: extend routing coverage to calculations or rename to an order-route suite.

## Stable Interfaces

Use these names consistently throughout all tasks:

```python
class CalculationStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"

class PriceMethod(str, Enum):
    MARKUP = "markup"
    TARGET_MARGIN = "target_margin"

class AllocationBasis(str, Enum):
    REQUEST = "request"
    RUN = "run"
    UNIT = "unit"

def calculate_variant(inputs: VariantCostInputs) -> VariantCostResult: ...
async def create_calculation(db, actor, payload) -> Calculation: ...
async def update_calculation(db, calculation_id, expected_version, payload) -> Calculation: ...
async def approve_calculation(db, calculation_id, expected_version, warning_reasons) -> CalculationRevision: ...
async def create_template(db, calculation_id, revision_id, name) -> CalculationTemplate: ...
```

Frontend API surface:

```typescript
export const calculationsApi = {
  list(params: CalculationListParams): Promise<CalculationPage>,
  get(id: number): Promise<CalculationDetail>,
  create(input: CalculationCreate): Promise<CalculationDetail>,
  update(id: number, input: CalculationUpdate): Promise<CalculationDetail>,
  approve(id: number, input: CalculationApprove): Promise<CalculationRevision>,
  archive(id: number, expectedVersion: number): Promise<CalculationDetail>,
  createTemplate(id: number, input: CalculationTemplateCreate): Promise<CalculationTemplate>,
};
```

---

### Task 1: Relational Calculation Aggregate

**Files:**
- Create: `backend/app/models/calculation.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/database.py`
- Test: `backend/tests/integration/test_calculation_schema.py`

**Interfaces:**
- Consumes: existing `BusinessProfile`, `Customer`, `User`, UTC timestamp, and model-registration conventions.
- Produces: `Calculation`, `CalculationVariant`, `CalculationLine`, `CalculationOperation`, `CalculationLabor`, `CalculationRevision`, `CalculationTemplate`.

- [ ] **Step 1: Write failing schema tests**

Test that a calculation can omit `customer_id`, must reference a business profile, has `version=1`, permits one preferred variant, rejects duplicate revision numbers, and rejects mutation-oriented cascades that would delete referenced revisions.

```python
async def test_calculation_supports_request_without_customer(db_session, business_profile):
    calculation = Calculation(business_profile_id=business_profile.id, title="Four brackets")
    db_session.add(calculation)
    await db_session.flush()
    assert calculation.customer_id is None
    assert calculation.version == 1
    assert calculation.status == CalculationStatus.DRAFT.value
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `pytest backend/tests/integration/test_calculation_schema.py -q`  
Expected: FAIL because `backend.app.models.calculation` does not exist.

- [ ] **Step 3: Implement the normalized models and constraints**

Use integer primary keys, UTC timestamps, explicit `sort_order`, `NUMERIC` columns, and foreign keys. Store approved snapshot payloads as canonical JSON only for immutable evidence; mutable draft lines and operations remain relational. Add unique constraints for `(calculation_id, revision_number)`, `(calculation_id, name)` variants, and one preferred variant using service validation plus a supported partial unique index where safe.

- [ ] **Step 4: Register models and idempotent schema creation**

Import the models before `Base.metadata.create_all()` and follow existing `_safe_execute` migration patterns for installed databases. The migration must be rerunnable and preserve all current data.

- [ ] **Step 5: Run schema and foundation regression tests**

Run: `pytest backend/tests/integration/test_calculation_schema.py backend/tests/integration/test_order_foundation_schema.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/models/calculation.py backend/app/models/__init__.py backend/app/core/database.py backend/tests/integration/test_calculation_schema.py
git commit -m "Add calculation aggregate schema"
```

### Task 2: Decimal Calculation Engine

**Files:**
- Create: `backend/app/services/calculation_engine.py`
- Create: `backend/tests/unit/test_calculation_engine.py`

**Interfaces:**
- Consumes: decimal-string inputs and enums defined in `backend/app/schemas/calculation.py` in Task 3; initially define engine-local frozen dataclasses and re-export compatible schema values later.
- Produces: `required_runs`, `suggested_scrap_runs`, `calculate_variant`, `apply_price_method`, and `round_money`.

- [ ] **Step 1: Write table-driven failing tests for quantity and cost**

Cover ceiling division, explicit scrap runs, material components, printer-specific hourly cost, dryer energy, labor allocation by request/run/unit, shipping separation, and zero quantities.

```python
@pytest.mark.parametrize(("good_parts", "per_run", "expected"), [(10, 4, 3), (8, 4, 2)])
def test_required_runs_uses_ceiling(good_parts, per_run, expected):
    assert required_runs(good_parts, per_run) == expected
```

- [ ] **Step 2: Write failing price-method and precision tests**

Assert that 35% markup differs from 35% target margin, minimum profit wins when higher, shipping stays separate, and `Decimal("0.1")` arithmetic is exact.

- [ ] **Step 3: Run tests and verify failure**

Run: `pytest backend/tests/unit/test_calculation_engine.py -q`  
Expected: FAIL because the engine functions do not exist.

- [ ] **Step 4: Implement pure frozen input/result dataclasses and formulas**

The engine must not access the database, current time, settings, or locale. Reject invalid denominators and negative physical inputs with typed `CalculationInputError` codes.

- [ ] **Step 5: Run engine tests**

Run: `pytest backend/tests/unit/test_calculation_engine.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/services/calculation_engine.py backend/tests/unit/test_calculation_engine.py
git commit -m "Add decimal calculation engine"
```

### Task 3: Calculation API Contracts

**Files:**
- Create: `backend/app/schemas/calculation.py`
- Test: `backend/tests/unit/test_calculation_engine.py`

**Interfaces:**
- Consumes: model enums and engine decimal-string requirements.
- Produces: `CalculationCreate`, `CalculationUpdate`, `CalculationDetail`, `CalculationSummary`, `CalculationPage`, `CalculationApprove`, `CalculationRevisionRead`, and template contracts.

- [ ] **Step 1: Write failing schema-validation tests**

Test non-empty titles, positive quantities, valid ISO currency, decimal serialization as strings, target margin below 1, source provenance fields, and required `expected_version` on mutations.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest backend/tests/unit/test_calculation_engine.py -q -k schema`  
Expected: FAIL because the Pydantic contracts do not exist.

- [ ] **Step 3: Implement enums and nested contracts**

Define discriminated line types, operation types, source kinds (`spool`, `material_profile`, `printer`, `settings`, `manual`, `slicer`), warning severity, decimal-string serializers, and pagination metadata. Avoid exposing internal ORM snapshot JSON directly.

- [ ] **Step 4: Run schema and engine tests**

Run: `pytest backend/tests/unit/test_calculation_engine.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/schemas/calculation.py backend/tests/unit/test_calculation_engine.py
git commit -m "Define calculation API contracts"
```

### Task 4: Draft CRUD and Source Resolution Service

**Files:**
- Create: `backend/app/services/calculation.py`
- Create: `backend/tests/integration/test_calculations_api.py`
- Modify: `backend/app/services/order_errors.py`

**Interfaces:**
- Consumes: calculation models, schemas, engine, business profiles, customers, printers, spools/material profiles, and settings.
- Produces: CRUD service signatures from Stable Interfaces plus `list_calculations` and `get_calculation`.

- [ ] **Step 1: Write failing service/API-independent integration tests**

Cover creating without customer, resolving spool before material-profile before settings cost, resolving printer before settings machine cost, preserving manual override provenance, and rejecting stale `expected_version`.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest backend/tests/integration/test_calculations_api.py -q -k "create or source or conflict"`  
Expected: FAIL because the calculation service does not exist.

- [ ] **Step 3: Implement transactional create, get, list, and update**

Load the full aggregate with bounded eager loading, replace nested draft collections transactionally, increment `version` exactly once per successful update, and raise the existing order-domain not-found/conflict error types.

- [ ] **Step 4: Implement deterministic source resolution**

Return both normalized numeric inputs and provenance records. Never substitute a fallback silently: add an informational validation item whenever a fallback is selected.

- [ ] **Step 5: Run focused integration tests**

Run: `pytest backend/tests/integration/test_calculations_api.py -q -k "create or source or conflict"`  
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/services/calculation.py backend/app/services/order_errors.py backend/tests/integration/test_calculations_api.py
git commit -m "Add calculation draft service"
```

### Task 5: Approval, Immutable Revisions, and Templates

**Files:**
- Modify: `backend/app/services/calculation.py`
- Modify: `backend/tests/integration/test_calculations_api.py`

**Interfaces:**
- Consumes: draft CRUD, source resolver, engine results, current actor, and validation codes.
- Produces: `approve_calculation`, `create_template`, and `instantiate_template`.

- [ ] **Step 1: Write failing approval tests**

Cover blockers, accepted warnings with mandatory reasons, approval without customer, immutable canonical snapshot, stale approval conflict, sequential revision numbers, supersession, and settings changes not altering old revisions.

- [ ] **Step 2: Write failing template tests**

Assert templates retain structure and rules but exclude customer, addresses, concrete files, slicer values, dates, results, and approval state.

- [ ] **Step 3: Run focused tests and verify failure**

Run: `pytest backend/tests/integration/test_calculations_api.py -q -k "approve or revision or template"`  
Expected: FAIL because approval and template operations are not implemented.

- [ ] **Step 4: Implement validation and atomic approval**

Lock or version-check the calculation, resolve sources, calculate every variant, require exactly one preferred variant, build a canonical snapshot with sorted keys and decimal strings, insert the next immutable revision, and update aggregate status in one transaction.

- [ ] **Step 5: Implement safe template projection and instantiation**

Use an explicit allow-list projection rather than deleting forbidden fields after serialization. Instantiation records `source_template_id` and `source_template_version`.

- [ ] **Step 6: Run focused tests**

Run: `pytest backend/tests/integration/test_calculations_api.py -q -k "approve or revision or template"`  
Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add backend/app/services/calculation.py backend/tests/integration/test_calculations_api.py
git commit -m "Add calculation revisions and templates"
```

### Task 6: Permission-Gated REST API

**Files:**
- Create: `backend/app/api/routes/calculations.py`
- Modify: `backend/app/api/routes/__init__.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/integration/test_calculations_api.py`

**Interfaces:**
- Consumes: calculation service and schemas.
- Produces: `/calculations`, `/calculations/{id}`, `/calculations/{id}/approve`, `/calculations/{id}/archive`, `/calculations/{id}/templates`, and `/calculation-templates/{id}/instantiate`.

- [ ] **Step 1: Write failing endpoint and permission tests**

Verify readers can list/get only, updaters can create/edit/template, approvers can approve/archive, unauthenticated calls fail, and a user lacking every calculation permission is denied.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest backend/tests/integration/test_calculations_api.py -q -k "permission or endpoint"`  
Expected: FAIL with 404 because the router is not registered.

- [ ] **Step 3: Implement thin routes and register the router**

Routes translate domain errors to the same HTTP shapes used by customers/business profiles, return 409 for optimistic conflicts, and never recompute formulas in route handlers.

- [ ] **Step 4: Run calculation and permission regression tests**

Run: `pytest backend/tests/integration/test_calculations_api.py backend/tests/unit/test_order_management_permissions.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/api/routes/calculations.py backend/app/api/routes/__init__.py backend/app/main.py backend/tests/integration/test_calculations_api.py
git commit -m "Expose calculation API"
```

### Task 7: Calculation Settings and Live Example

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/i18n/locales/*.ts`
- Modify: `frontend/src/__tests__/pages/SettingsPage.test.tsx`
- Create: `frontend/src/lib/calculationMath.ts`
- Create: `frontend/src/__tests__/lib/calculationMath.test.ts`

**Interfaces:**
- Consumes: existing settings persistence and business-profile authority boundaries.
- Produces: decimal-string calculation defaults and `calculatePreview(input): CalculationPreview`.

- [ ] **Step 1: Write failing preview-math parity tests**

Use the same golden cases as backend engine tests for markup versus margin, minimum price/profit, and separate shipping. The TypeScript module is display-only; backend approval remains authoritative.

- [ ] **Step 2: Write failing SettingsPage tests**

Assert six sections, stable input heights, explanatory copy, live example components, target-margin warning, and persistence of decimal strings.

- [ ] **Step 3: Run focused frontend tests and verify failure**

Run from `frontend`: `npm.cmd run test -- --run src/__tests__/lib/calculationMath.test.ts src/__tests__/pages/SettingsPage.test.tsx`  
Expected: FAIL because the expanded settings and math module do not exist.

- [ ] **Step 4: Implement preview math and settings sections**

Split local render helpers inside `SettingsPage.tsx` only if they remain small; otherwise create focused setting-section components. Reuse existing settings API keys with a versioned `orders.calculation_defaults` object and safe defaults for existing installations.

- [ ] **Step 5: Add parity-safe translations**

German and English receive native text. Other locales receive English fallback values with identical key structure so `check:i18n` remains green.

- [ ] **Step 6: Run tests and i18n parity**

Run from `frontend`: `npm.cmd run test -- --run src/__tests__/lib/calculationMath.test.ts src/__tests__/pages/SettingsPage.test.tsx`  
Run: `npm.cmd run check:i18n`  
Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add frontend/src/pages/SettingsPage.tsx frontend/src/lib/calculationMath.ts frontend/src/__tests__/lib/calculationMath.test.ts frontend/src/__tests__/pages/SettingsPage.test.tsx frontend/src/i18n/locales
git commit -m "Expand calculation settings"
```

### Task 8: Typed Frontend API and Calculation List

**Files:**
- Create: `frontend/src/api/calculations.ts`
- Create: `frontend/src/pages/CalculationsPage.tsx`
- Create: `frontend/src/components/orders/CalculationList.tsx`
- Create: `frontend/src/__tests__/api/calculations.test.ts`
- Create: `frontend/src/__tests__/pages/CalculationsPage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/OrdersPage.tsx`
- Modify: `frontend/src/__tests__/App.ordersCustomersRoute.test.tsx`

**Interfaces:**
- Consumes: REST contracts from Task 6 and existing API transport/auth behavior.
- Produces: `calculationsApi`, routed list page, filter state, and create/open actions.

- [ ] **Step 1: Write failing API contract tests with MSW**

Assert decimal strings remain strings, filters become query parameters, optimistic versions are included, and 409 responses map to a typed conflict error.

- [ ] **Step 2: Write failing route and list-state tests**

Cover `/orders/calculation`, full-width table columns, loading, empty, permission denied, server retry, archived filtering, and search.

- [ ] **Step 3: Run focused tests and verify failure**

Run from `frontend`: `npm.cmd run test -- --run src/__tests__/api/calculations.test.ts src/__tests__/pages/CalculationsPage.test.tsx src/__tests__/App.ordersCustomersRoute.test.tsx`  
Expected: FAIL because the module and page do not exist.

- [ ] **Step 4: Implement typed API, page, table, and route**

Use semantic table markup, icon actions with tooltips, an accessible status label, and query-state-driven filters. Do not put editor state in the list component.

- [ ] **Step 5: Run focused tests**

Run the command from Step 3.  
Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/api/calculations.ts frontend/src/pages/CalculationsPage.tsx frontend/src/components/orders/CalculationList.tsx frontend/src/__tests__/api/calculations.test.ts frontend/src/__tests__/pages/CalculationsPage.test.tsx frontend/src/App.tsx frontend/src/pages/OrdersPage.tsx frontend/src/__tests__/App.ordersCustomersRoute.test.tsx
git commit -m "Add calculation list"
```

### Task 9: Calculation Workspace Editing and Live Results

**Files:**
- Create: `frontend/src/components/orders/CalculationWorkspace.tsx`
- Create: `frontend/src/components/orders/calculation/RequestSection.tsx`
- Create: `frontend/src/components/orders/calculation/LinesSection.tsx`
- Create: `frontend/src/components/orders/calculation/ProductionSection.tsx`
- Create: `frontend/src/components/orders/calculation/CostPriceSection.tsx`
- Create: `frontend/src/__tests__/components/orders/CalculationWorkspace.test.tsx`
- Modify: `frontend/src/pages/CalculationsPage.tsx`
- Modify: `frontend/src/i18n/locales/*.ts`

**Interfaces:**
- Consumes: `CalculationDetail`, business-profile/customer APIs, `calculatePreview`, and `calculationsApi.update`.
- Produces: accessible five-area workspace for request, lines, production, cost/price, and validation.

- [ ] **Step 1: Write failing editor tests**

Cover customer-optional request creation, adding a printed line, adding a plate operation, source badges, manual override markers, labor allocation basis, immediate total updates, blocker summary, save, and stale-version conflict.

- [ ] **Step 2: Run the focused test and verify failure**

Run from `frontend`: `npm.cmd run test -- --run src/__tests__/components/orders/CalculationWorkspace.test.tsx`  
Expected: FAIL because the workspace does not exist.

- [ ] **Step 3: Implement workspace state and request/line sections**

Keep a single normalized draft state in `CalculationWorkspace`; child sections emit typed changes and do not call the API directly.

- [ ] **Step 4: Implement production and cost/price sections**

Show provenance for every sourced value, use explicit override actions, distinguish per-request/run/unit labor, and display shipping separately from production cost.

- [ ] **Step 5: Implement save and conflict recovery**

On 409, retain unsaved local changes, display the conflict, and offer `Reload server version`; never auto-overwrite.

- [ ] **Step 6: Run focused tests and i18n parity**

Run the command from Step 2 and `npm.cmd run check:i18n`.  
Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add frontend/src/components/orders/CalculationWorkspace.tsx frontend/src/components/orders/calculation frontend/src/__tests__/components/orders/CalculationWorkspace.test.tsx frontend/src/pages/CalculationsPage.tsx frontend/src/i18n/locales
git commit -m "Add calculation workspace"
```

### Task 10: Variants, Approval, Revisions, and Templates UI

**Files:**
- Create: `frontend/src/components/orders/calculation/VariantsSection.tsx`
- Modify: `frontend/src/components/orders/CalculationWorkspace.tsx`
- Modify: `frontend/src/__tests__/components/orders/CalculationWorkspace.test.tsx`
- Modify: `frontend/src/i18n/locales/*.ts`

**Interfaces:**
- Consumes: workspace draft state and approve/template API contracts.
- Produces: variant comparison, preferred selection, approval dialog, immutable revision viewer, and save-as-template flow.

- [ ] **Step 1: Write failing variant tests**

Assert creating/cloning/renaming variants, exactly one preferred variant, comparison of lead time/cost/price/margin, and no cross-variant mutation.

- [ ] **Step 2: Write failing approval and template tests**

Cover blocker prevention, warning-reason requirement, permission-gated approval, approved read-only state, `Revise` creating a draft, template field exclusions, and quotation-ready status without creating a quotation.

- [ ] **Step 3: Run focused tests and verify failure**

Run from `frontend`: `npm.cmd run test -- --run src/__tests__/components/orders/CalculationWorkspace.test.tsx`  
Expected: FAIL on the new behaviors.

- [ ] **Step 4: Implement variants and comparison**

Clone only variant-owned data. Keep request context shared. The preferred selector must be a radio-style single choice with an accessible label.

- [ ] **Step 5: Implement approval, revision view, and template commands**

Require explicit confirmation, display immutable snapshot data after approval, and label the future document action `Ready for quotation` without calling a non-existent quotation endpoint.

- [ ] **Step 6: Run focused tests and i18n parity**

Run Step 3 and `npm.cmd run check:i18n`.  
Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add frontend/src/components/orders/calculation/VariantsSection.tsx frontend/src/components/orders/CalculationWorkspace.tsx frontend/src/__tests__/components/orders/CalculationWorkspace.test.tsx frontend/src/i18n/locales
git commit -m "Add calculation approval workflow"
```

### Task 11: Documentation and Full Verification

**Files:**
- Modify: `docs/order-management.md`
- Modify: `docs/superpowers/plans/2026-07-12-calculation-workspace.md` only to mark completed checkboxes during execution.

**Interfaces:**
- Consumes: completed backend and frontend feature.
- Produces: operator documentation and release-quality verification evidence.

- [ ] **Step 1: Update user documentation**

Document creating a customer request, importing or entering production data, interpreting provenance and warnings, comparing variants, approving a revision, revising approved work, and saving a template. State clearly that quotation generation is the next increment.

- [ ] **Step 2: Run backend calculation suites**

Run: `pytest backend/tests/unit/test_calculation_engine.py backend/tests/integration/test_calculation_schema.py backend/tests/integration/test_calculations_api.py -q`  
Expected: PASS.

- [ ] **Step 3: Run backend regression and lint**

Run: `pytest backend/tests/unit backend/tests/integration -q`  
Run: `ruff check backend/app backend/tests`  
Expected: PASS with no new warnings.

- [ ] **Step 4: Run frontend focused and full suites**

Run from `frontend`: `npm.cmd run test -- --run src/__tests__/api/calculations.test.ts src/__tests__/lib/calculationMath.test.ts src/__tests__/pages/CalculationsPage.test.tsx src/__tests__/components/orders/CalculationWorkspace.test.tsx src/__tests__/pages/SettingsPage.test.tsx`  
Run: `npm.cmd run test -- --run`  
Expected: PASS.

- [ ] **Step 5: Run frontend static verification**

Run from `frontend`: `npm.cmd run lint`  
Run: `npm.cmd run check:i18n`  
Run: `npm.cmd run build`  
Expected: PASS.

- [ ] **Step 6: Perform browser verification**

Verify at desktop and narrow widths: list states, create without customer, source/fallback markers, live totals, explicit scrap runs, variant isolation, warning reason, approval immutability, revision creation, template instantiation, and settings example. Capture defects as focused failing tests before fixes.

- [ ] **Step 7: Review the final diff for scope and migration safety**

Run: `git diff --check` and `git status --short`. Confirm no quotation, PDF, reservation, actual-cost, scheduling, or queue implementation slipped into this increment.

- [ ] **Step 8: Commit documentation and verification adjustments**

```powershell
git add docs/order-management.md docs/superpowers/plans/2026-07-12-calculation-workspace.md
git commit -m "Document calculation workflow"
```

### Task 12: Canonical Defaults and Preview API

**Files:** `backend/app/schemas/calculation.py`, `backend/app/services/calculation_engine.py`, `backend/app/services/calculation.py`, `backend/app/api/routes/calculations.py`, `backend/tests/unit/test_calculation_engine.py`, `backend/tests/integration/test_calculations_api.py`

**Produces:** Versioned defaults plus one backend preview result containing runs, material, machine, energy, labor, consumables, packaging, risk, production cost, shipping, contribution, margin, net, tax, gross, and unit price.

- [ ] Add failing engine tests for every component, markup, target margin, explicit price, discount, tax, minimums, contribution, and rounding.
- [ ] Add failing API tests for defaults round-trip and backend preview parity with approval.
- [ ] Extend the `Decimal` engine and permission-gated defaults/preview endpoints.
- [ ] Run `pytest backend/tests/unit/test_calculation_engine.py backend/tests/integration/test_calculations_api.py -q`; require PASS.

### Task 13: Full Calculation Settings

**Files:** Create `frontend/src/components/orders/calculation/CalculationSettings.tsx`; modify `frontend/src/pages/SettingsPage.tsx` and `frontend/src/api/calculations.ts`; test `frontend/src/__tests__/components/CalculationSettings.test.tsx` and `frontend/src/__tests__/pages/SettingsPage.test.tsx`.

**Consumes:** Task 12 defaults and preview endpoints. **Produces:** Six full-width settings sections and a backend-computed live example.

- [ ] Write failing tests for all sections, save/reload, validation, and live totals.
- [ ] Remove the settings-only JavaScript formula from `SettingsPage`.
- [ ] Implement cost basis, labor, risk/scrap, price, ancillary, and editable example sections.
- [ ] Run the two focused frontend test files; require PASS.

### Task 14: ForgeDesk-Parity Workspace

**Files:** Modify `frontend/src/components/orders/CalculationWorkspace.tsx` and `frontend/src/api/calculations.ts`; create focused request, lines, production, cost-price, and variants components under `frontend/src/components/orders/calculation/`; test `frontend/src/__tests__/components/CalculationWorkspace.test.tsx`.

**Consumes:** Backend preview, business profiles, customers, printers, files, spools/materials, and slicing profiles. **Produces:** One normalized persisted draft with provenance and stable later-handoff references.

- [ ] Test real selectors, 3MF/file metadata, operations/labor, line CRUD, variants, totals, save, approval, and conflict recovery.
- [ ] Replace numeric customer IDs and hard-coded choices with PrintOps sources.
- [ ] Render every approved cost/price component without duplicating formulas.
- [ ] Keep quotation/project/print-job actions inactive and explicitly deferred.
- [ ] Run focused workspace tests; require PASS.

### Task 15: Parity Verification and Delivery

- [ ] Verify every ForgeDesk parity-table row against API, rendered UI, or an explicitly deferred handoff.
- [ ] Run backend calculation suites, focused frontend suites, lint, typecheck, coverage, production build, and browser smoke tests for calculation and settings.
- [ ] Update `docs/order-management.md`; commit, push, and merge only after all required checks pass.

### Task 16: Calculation Settings Overview Layout

**Files:**
- Modify: `frontend/src/components/orders/calculation/CalculationSettings.tsx`

**Interfaces:**
- Consumes: the existing six settings groups and live backend preview.
- Produces: a responsive two-column overview without changing persisted settings or calculation behavior.

- [ ] Add an icon component to each group definition and render a consistent icon/title row.
- [ ] Arrange cost basis, labor, and ancillary costs in the left column; risk, pricing, and example calculation in the right column.
- [ ] Keep global currency/material/electricity defaults full-width and collapse the overview to one column below the desktop breakpoint.
- [ ] Run `npm.cmd run build --prefix frontend` and require PASS.
- [ ] Commit and push the focused layout change.

### Task 17: Calculable Device Master Data

**Files:**
- Modify: `backend/app/models/printer.py`
- Create: `backend/app/models/equipment.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/core/database.py`
- Create: `backend/app/schemas/equipment.py`
- Create: `backend/app/services/equipment.py`
- Test: `backend/tests/unit/test_equipment_costs.py`

**Interfaces:**
- Produces: commercial fields for printers plus `Equipment` records of type `dryer`; `calculate_residual_value(...)` and `calculate_hourly_rate(...)` are the only owners of derived device costs.

- [ ] Add failing unit cases for new, halfway-depreciated, expired, and invalid device values.
- [ ] Add optional acquisition date/value, service years, annual hours, maintenance percentage, and nominal watts to printers; create the dryer equipment model with the same commercial fields.
- [ ] Add idempotent SQLite/PostgreSQL startup migration coverage following existing database migration patterns.
- [ ] Implement Decimal-based straight-line residual value and hourly-rate helpers and expose derived read-only schema fields.
- [ ] Run equipment unit and migration tests; require PASS.

### Task 18: Device API and Unified Device Management

**Files:**
- Create: `backend/app/api/routes/equipment.py`
- Modify: `backend/app/api/routes/__init__.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas/printer.py`
- Modify: `backend/app/api/routes/printers.py`
- Create: `backend/tests/integration/test_equipment_api.py`
- Modify: `backend/tests/integration/test_printers_api.py`
- Create: `frontend/src/components/settings/DeviceManagement.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Produces: CRUD `/equipment` for dryers and extended printer responses; unified settings UI renders both sources without copying printer records.

- [ ] Test dryer CRUD, validation, inactive filtering, derived values, and extended printer commercial fields.
- [ ] Implement permission-gated dryer CRUD and printer commercial-field updates.
- [ ] Replace the device settings surface with printer and dryer sections, add/edit forms, derived-value display, and active-state controls.
- [ ] Run focused backend tests and the frontend production build; require PASS.

### Task 19: Device Selection and Central Price Rounding

**Files:**
- Modify: `backend/app/services/calculation_engine.py`
- Modify: `backend/app/schemas/calculation.py`
- Modify: `backend/tests/unit/test_calculation_engine.py`
- Modify: `frontend/src/components/orders/calculation/CalculationSettings.tsx`
- Modify: `frontend/src/components/orders/CalculationWorkspace.tsx`
- Modify: `frontend/src/api/calculations.ts`

**Interfaces:**
- Consumes: active printer and dryer master data.
- Produces: default device selectors, per-operation overrides, drying duration, and backend-owned price rounding shared by preview and approval.

- [ ] Add failing rounding tests for none, 0.05, 0.10, 0.50, 1.00, x.90, and x.99.
- [ ] Add rounding mode to preview/approval inputs and apply it after commercial price derivation using Decimal arithmetic.
- [ ] Replace free-text currency with the existing supported ISO currency selector.
- [ ] Replace device-entry defaults with active default-printer/default-dryer selectors and read-only residual/hourly-rate summaries.
- [ ] Add per-operation printer/dryer selection and drying hours to the workspace, persisting resolved provenance.
- [ ] Run calculation unit/API tests and frontend build; require PASS.

### Task 20: Device and Calculation Verification

**Files:**
- Modify: `docs/order-management.md`
- Modify: `docs/superpowers/plans/2026-07-12-calculation-workspace.md`

- [ ] Run backend equipment, printer, calculation, permission, migration, lint, and security checks.
- [ ] Run frontend lint, typecheck, focused tests, i18n parity, and production build.
- [ ] Browser-smoke device creation, default selection, order override, residual/hourly display, and every rounding mode.
- [ ] Update operator documentation and check off only verified plan items.
- [ ] Commit, push, and merge only after required GitHub checks pass.

---

## Plan Self-Review

- **Spec coverage:** Tasks 1-11 cover the original aggregate and minimal workspace. Tasks 12-15 close the approved ForgeDesk-parity gaps in canonical preview math, complete settings, sourced inputs, full workspace behavior, and delivery verification.
- **Deferred-scope check:** Quotation issuance, PDF output, numbering, reminders, reservations, actual cost, scheduling, and queue automation remain consumers for later increments.
- **Type consistency:** Backend and frontend both use decimal strings at the API boundary, `expected_version` on mutations, one preferred variant, and the status/price/allocation enums declared in Stable Interfaces.
- **Placeholder scan:** The plan contains no TBD/TODO steps; every task names files, interfaces, focused tests, commands, expected outcomes, implementation boundaries, and a commit.
