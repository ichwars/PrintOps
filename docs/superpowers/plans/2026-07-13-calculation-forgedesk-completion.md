# Calculation ForgeDesk Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the PrintOps calculation workspace with the remaining ForgeDesk costing, material, project, explanation, and prepared follow-up functionality.

**Architecture:** Extend the existing calculation aggregate rather than creating a second calculator. Persist request metadata and commercial overrides on `Calculation`, additive materials on `CalculationLine`, and retain device/file provenance on operations; the existing Decimal engine remains the single preview and approval owner. Split the large workspace into focused request, materials, breakdown, and decision components.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, SQLite/PostgreSQL-compatible migrations, Decimal, React 19, TypeScript, Tailwind, Vitest, Testing Library.

## Global Constraints

- Preserve variants, immutable revisions, warning reasons, templates, and managed devices.
- Prefer existing projects, inventory, printers, dryers, customers, and slicer integration.
- Keep offer and print-order follow-up controls visible but disabled and side-effect free.
- Do not build a second slicer integration.
- Preview and approval must use the same Decimal calculation engine.
- Do not lower lint, test, security, or coverage gates.

---

### Task 1: Persist request metadata and commercial overrides

**Files:**
- Modify: `backend/app/models/calculation.py`
- Modify: `backend/app/schemas/calculation.py`
- Modify: `backend/app/core/database.py`
- Modify: `backend/app/services/calculation.py`
- Test: `backend/tests/integration/test_calculations_api.py`

**Interfaces:**
- Produces: `Calculation.request_kind`, `project_id`, `quantity`, `position_description`, `special_terms`, and `commercial_overrides` in create/update/detail/snapshot contracts.
- Consumes: existing optimistic versioning and `_snapshot()`.

- [ ] Add a failing API test that creates, reads, updates, approves, and snapshots all new fields; assert negative quantity and negative override amounts return 422.
- [ ] Run `python -m pytest backend/tests/integration/test_calculations_api.py -q` and confirm the new test fails on missing fields.
- [ ] Add nullable project reference, request fields, JSON overrides, and idempotent SQLite/PostgreSQL schema upgrade statements following the existing `database.py` migration pattern.
- [ ] Extend Pydantic validation with `quantity >= 1`, known request kinds, non-negative override values, and percentage values in `[0, 1)`.
- [ ] Map the fields through create, update, template instantiation, revision cloning, and approval snapshots.
- [ ] Re-run the API test and commit `feat(calculations): persist request and pricing context`.

### Task 2: Add additive materials and engine breakdown

**Files:**
- Modify: `backend/app/schemas/calculation.py`
- Modify: `backend/app/services/calculation_engine.py`
- Modify: `backend/app/services/calculation.py`
- Test: `backend/tests/unit/test_calculation_engine.py`
- Test: `backend/tests/integration/test_calculations_api.py`

**Interfaces:**
- Produces: `CalculationCostBreakdownItem(code, label, basis, amount)` and `breakdown` on preview responses.
- Consumes: line kinds `material`, `packaging`, `shipping`, and existing `VariantCostInputs`.

- [ ] Add failing engine tests for material markup, percentage scrap, additive material lines, and per-unit price across quantity greater than one.
- [ ] Run the focused engine tests and verify numeric assertions fail.
- [ ] Extend `VariantCostInputs` with additive material cost and material markup while preserving Decimal quantization.
- [ ] Return stable breakdown entries for machine, labor, material, energy, drying, additive materials, consumables, scrap/risk, packaging, and shipping.
- [ ] Feed preferred-variant lines and persisted overrides into both preview-batch and approval.
- [ ] Run engine and API tests and commit `feat(calculations): explain complete production costs`.

### Task 3: Complete calculation settings

**Files:**
- Modify: `frontend/src/components/orders/calculation/CalculationSettings.tsx`
- Modify: `frontend/src/api/calculations.ts`
- Test: `frontend/src/__tests__/pages/SettingsPage.test.tsx`

**Interfaces:**
- Produces settings keys `materialMarkupPercent`, `scrapPercent`, and existing defaults through `calculation_defaults`.
- Consumes managed printer/dryer defaults and central rounding.

- [ ] Add failing settings tests asserting material markup, scrap percentage, and reset-safe defaults are rendered and serialized.
- [ ] Run the SettingsPage test and confirm the new controls are absent.
- [ ] Add the missing fields to the logical `Preisbildung` and `Material & Ausschuss` cards with appropriate icons and explanatory text.
- [ ] Ensure example preview uses the same new inputs and displays additive costs.
- [ ] Run SettingsPage tests, i18n parity, and commit `feat(settings): complete calculation defaults`.

### Task 4: Split and complete the workspace input flow

**Files:**
- Create: `frontend/src/components/orders/calculation/RequestEditor.tsx`
- Create: `frontend/src/components/orders/calculation/MaterialsEditor.tsx`
- Create: `frontend/src/components/orders/calculation/CommercialOverridesEditor.tsx`
- Modify: `frontend/src/components/orders/CalculationWorkspace.tsx`
- Modify: `frontend/src/api/calculations.ts`
- Test: `frontend/src/__tests__/components/CalculationWorkspace.test.tsx`

**Interfaces:**
- `RequestEditor` edits profile, customer, project, request kind, quantity, title, description, terms, notes, and currency.
- `MaterialsEditor` edits warehouse-backed or manual material lines.
- `CommercialOverridesEditor` edits per-calculation overrides and exposes `onReset()`.

- [ ] Add failing workspace tests for project selection, print kind, quantity, warehouse/manual material, additive line, overrides, and confirmed reset.
- [ ] Run the focused test and confirm the new labels and callbacks are missing.
- [ ] Extract the request editor and populate projects through the existing project API.
- [ ] Implement warehouse-backed selection using existing spool/inventory endpoints and snapshot material label, unit, and cost on the line.
- [ ] Implement additive material rows and override controls without duplicating device records.
- [ ] Add reset confirmation that reconstructs the draft from current central defaults while retaining profile/customer/project/title.
- [ ] Run workspace tests and commit `feat(calculations): complete costing input workflow`.

### Task 5: Add transparent result and prepared follow-up panels

**Files:**
- Create: `frontend/src/components/orders/calculation/CostBreakdown.tsx`
- Create: `frontend/src/components/orders/calculation/PriceDecision.tsx`
- Create: `frontend/src/components/orders/calculation/FollowUpActions.tsx`
- Modify: `frontend/src/components/orders/CalculationWorkspace.tsx`
- Test: `frontend/src/__tests__/components/CalculationWorkspace.test.tsx`

**Interfaces:**
- `CostBreakdown` consumes `CalculationPreview.breakdown` and formats basis plus amount.
- `PriceDecision` consumes production cost, contribution, effective margin, unit, net, tax, and gross prices.
- `FollowUpActions` renders two disabled checkboxes and explanatory copy without handlers.

- [ ] Add failing tests for every breakdown code, price-decision KPI, and disabled follow-up controls.
- [ ] Run the focused test and verify the panels are missing.
- [ ] Build the three focused components and replace the current flat result tiles.
- [ ] Keep accessible headings, control labels, responsive two-column layout, and explicit empty/loading states.
- [ ] Run component tests and commit `feat(calculations): show price decision and cost proof`.

### Task 6: Finish verification and handoff

**Files:**
- Modify: `docs/order-management.md`
- Modify: `docs/superpowers/plans/2026-07-13-calculation-forgedesk-completion.md`

**Interfaces:**
- Produces a verified PR branch with all plan checkboxes completed.

- [ ] Update the order-management documentation with the completed request, material, override, breakdown, and prepared follow-up behavior.
- [ ] Run `python -m ruff format --check backend/` and `python -m ruff check backend/`; expect success.
- [ ] Run calculation, equipment, printer, project, and customer backend suites; expect all selected tests to pass.
- [ ] Run `npm run lint`, `npm run test:coverage`, `npm run check:i18n`, and `npm run build`; expect all gates to pass without lowering thresholds.
- [ ] Reload PrintOps locally and browser-smoke-test settings, new calculation, material/override inputs, reset, preview, save, and prepared follow-up controls.
- [ ] Commit documentation, push the branch, and confirm PR checks are green.
