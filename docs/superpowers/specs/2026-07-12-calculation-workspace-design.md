# Calculation Workspace Design

**Date:** 2026-07-12  
**Status:** Approved  
**Scope:** Delivery increment 2 from the order-management design: calculation revisions, variants, slicer inputs, and planned cost.

**Revision note:** The approved scope now explicitly requires functional parity
with the useful calculation capabilities already explored in ForgeDesk. Parity
means equivalent user outcomes on PrintOps' relational backend, not copying
ForgeDesk's browser-persisted implementation.

## Objective

PrintOps shall turn a concrete customer request into a transparent, auditable production calculation that can later become a quotation without re-entering positions. A calculation may start without a fully registered customer, but creating a quotation requires a customer with a suitable billing address.

The design combines ForgeDesk's continuous request-to-quotation workflow with PrintOps-specific additive-manufacturing inputs, cost attribution, variants, and immutable revisions. The existing calculation settings remain the source of defaults; they are expanded rather than replaced.

## Scope Boundaries

This increment includes:

- calculation list and workspace;
- requests, sellable lines, and production operations;
- slicer-derived and manually entered production inputs;
- planned material, machine, energy, labor, ancillary, and risk cost;
- price derivation, variants, approval, and immutable revisions;
- reusable calculation templates;
- a stable handoff contract for a later quotation increment.

It does not issue quotations, invoices, or other commercial documents, reserve stock, schedule production, attribute actual cost, render PDFs, or automate the print queue. Those consumers may reference approved calculation revisions later.

## ForgeDesk Parity Requirements

This increment must not stop at the currently implemented minimal editor. It
adopts every ForgeDesk calculation capability that belongs to calculation or
calculation defaults and maps it to an authoritative PrintOps owner.

| ForgeDesk outcome | Required PrintOps implementation |
| --- | --- |
| Start from a concrete customer request | Persisted request context with business profile, optional customer/contact, reference, dates, description, notes, tags, and source-file metadata |
| Drop or select a 3MF file | PrintOps file/project selection plus upload, plate discovery, local 3MF metadata analysis, optional configured slicer execution, and an explicit manual fallback after an import error |
| Select printer, process, plate, filament, and material | References to PrintOps printer profiles, slicing profiles, inventory/spools, materials, colors, nozzle data, and stored provenance instead of hard-coded option lists |
| Apply slicing results to the calculation | One operation per selected plate with parts, runs, time, consumption, purge/support/waste, profile data, source timestamp, and visible overrides |
| Add warehouse materials | Additional-material lines backed by PrintOps inventory records and cost snapshots; this increment reads availability but does not reserve stock |
| Calculate machine, electricity, labor, material, ancillary, risk, packaging, and shipping amounts | Backend `Decimal` calculation engine with separately visible components, documented allocation bases, and no double counting |
| Compare markup, target-margin, and explicit-price strategies | Per-variant price method, rate or override, effective margin, contribution, minimum-price/profit warnings, discounts, tax, rounding, net/gross totals, and unit price |
| Compare alternatives | Persisted variants for printer, material, profile, quantity, processing, lead time, and price assumptions with one preferred variant |
| Save and reopen calculations | Relational drafts with optimistic concurrency, list/search/filter states, and no browser-local calculation owner |
| Save a reusable calculation | Versioned templates derived from calculation structure while excluding concrete customer, file, result, and approval data |
| Create an offer, project, or print job | Stable references and handoff readiness only in this increment; activation remains owned by the later quotation, project, and production increments |

ForgeDesk concepts that are not valid PrintOps owners must not be carried over:
local-storage drafts, hard-coded customers/printers/materials, duplicated
calculation formulas in React, or direct mutation of offers/projects from the
calculation page.

## Workflow

The commercial path is:

`customer request -> calculation -> approved revision -> quotation -> accepted work -> production -> invoice`

A calculation has the lifecycle:

`draft -> approved -> superseded | archived`

- Drafts are mutable and use optimistic concurrency control.
- Approving a draft persists an immutable revision snapshot.
- Editing an approved calculation creates a new draft revision.
- Referenced revisions remain available even after a newer revision is approved.
- A calculation can be created without a customer; quotation creation requires one.
- `Save as template` creates a reusable starting structure, not a second calculation model.

## Calculation List

`Orders > Calculation` uses the full available content width and follows the compact operational-table language used elsewhere in PrintOps. Its primary columns are:

- calculation number;
- customer or `No customer assigned`;
- title;
- preferred variant;
- current revision;
- lifecycle status;
- production cost;
- selling price;
- effective margin;
- last update;
- actions.

The list provides explicit loading, empty, permission-denied, error, retry, archived, and superseded states. Filtering covers status, business profile, customer, owner, and update date. Search covers number, title, customer, and tags.

## Calculation Workspace

The editor keeps five areas directly reachable without nested cards obscuring the working context.

### Request

- business profile;
- optional customer and contact;
- internal title and request reference;
- requested date;
- notes, tags, and attached source files.

### Lines

Sellable line types include printed part, service, additional material, packaging, shipping, discount, and text. Lines contain localized descriptions, quantity, unit, derived or overridden price, tax category placeholder, and ordering.

### Production

Production operations include CAD/repair, slicing, setup, printing, drying, post-processing, quality assurance, and packing. A print operation can reference a source file and plate and contains quantity, parts per run, printer/profile, material/color, nozzle, print time, and material consumption.

Slicer-derived values retain source file, plate, slicer/process profile, printer profile, material profile, import timestamp, and override state. Manual entry remains supported and is visibly distinguishable from sourced values.

### Cost and Price

The workspace continuously shows material, machine, energy, labor, ancillary, and risk components alongside total production cost, contribution, effective margin, net price, tax, gross price, and unit price. Defaults and manual overrides are visually distinct.

### Variants

Variants share the request context but own their lines, operations, cost inputs, and results. They can represent alternative materials, colors, printers, profiles, layer heights, quantities, post-processing, lead times, or price strategies. The comparison shows at least lead time, production cost, selling price, and margin. Exactly one variant may be preferred for quotation handoff.

## Production Quantity

For each print operation:

```text
required good parts = requested customer quantity
base runs = ceil(required good parts / good parts per run)
total runs = base runs + explicitly planned scrap runs
```

A configured scrap rate may recommend additional runs, but it may not silently add only a monetary surcharge. The resulting production quantity and queue work must remain explainable.

For multi-plate 3MF files, each selected plate is a separate print operation.

## Cost Model

All monetary arithmetic uses SQL `NUMERIC` and Python `Decimal`; binary floating-point values are prohibited. Intermediate values retain sufficient precision and rounding occurs only at defined commercial boundaries.

### Material

```text
material cost =
  (model + support + purge/flush + waste + additional consumption)
  * price per mass unit
```

Cost-source precedence is:

1. selected spool or inventory lot;
2. material profile;
3. global calculation fallback.

The chosen source, price, unit, tax basis, and snapshot are stored with the revision. If input-tax deduction is disabled, material purchase prices are treated according to the business profile's gross-cost policy.

### Machine

```text
depreciation per hour =
  (acquisition value - residual value)
  / (service years * usable annual hours)

machine hourly cost =
  depreciation
  + maintenance and wear
  + optional space and overhead allocation
```

Printer-specific values take precedence over calculation-setting fallbacks. The snapshot records acquisition value, residual value, service life, usable annual hours, utilization assumption, maintenance, and overhead inputs.

### Energy

```text
energy cost =
  print duration * average printer power * electricity price
  + drying duration * dryer power * electricity price
```

Power is normalized to kilowatts before multiplication. Drying is represented as a production operation, not as an unexplained surcharge.

### Labor

Labor operations include request review/preparation, CAD or repair, slicing, setup, post-processing, quality assurance, and packing. Each operation stores duration, hourly rate, and allocation basis:

- per request;
- per run;
- per unit.

### Production Cost

```text
production cost =
  material
  + machine
  + energy
  + labor
  + consumables
  + packaging
  + other explicit costs
```

Shipping remains separately visible and is not disguised as production cost.

## Price Model

PrintOps supports two explicitly named derivation methods:

```text
Markup:
selling price = production cost * (1 + markup)

Target margin:
selling price = production cost / (1 - target margin)
```

Markup and margin are not interchangeable. The revision stores the selected method and rate. The system then applies minimum price, minimum profit, line discount, rounding policy, and tax decision in a documented order.

A user with update permission may override the selling price. The editor warns when the override violates minimum profit or target margin and records the reason when the warning is accepted.

## Calculation Settings

`Settings > Order management > Calculation` retains the current cost-tracking settings and expands to these sections:

1. Cost basis;
2. Labor times;
3. Risk and scrap;
4. Price derivation;
5. Ancillary costs;
6. Example calculation.

Relevant ForgeDesk concepts adopted as defaults are acquisition value, service life, annual print hours, maintenance and wear, labor rate, electricity rate, setup/post-processing/QA time, material markup, target margin, default discount, scrap rate, minimum price, minimum profit, rounding, consumables, packaging, and shipping.

The six sections expose at least these editable defaults:

- **Cost basis:** acquisition and residual value, service years, usable annual
  hours, utilization, maintenance/wear, average printer power, electricity
  price, default filament price by material, dryer power, space cost, and
  overhead allocation;
- **Labor times:** hourly rate plus request preparation, CAD/repair, slicing,
  setup, post-processing, quality assurance, and packing defaults with their
  allocation bases;
- **Risk and scrap:** material waste, purge/support treatment, recommended
  scrap runs/rate, risk surcharge, and the approval thresholds that convert a
  warning into a blocker;
- **Price derivation:** default method (`markup`, `target_margin`, or explicit
  price), rate, minimum price, minimum profit, default discount, tax display,
  and warning thresholds;
- **Ancillary costs:** consumables, packaging, shipping, and named additional
  cost defaults with per-request, per-run, or per-unit allocation;
- **Example calculation:** editable representative quantity, duration,
  material, and machine inputs with a complete live result and validation
  messages.

Settings inputs use the same units, formulas, validation codes, rounding, and
labels as the workspace. A second settings-only formula implementation is not
permitted.

The live example calculation displays machine, labor, energy, material, production cost, contribution, and recommended selling price so invalid defaults are visible immediately.

Calculation settings are fallback sources. Business-profile currency, language, timezone, and tax settings remain authoritative for their scope. Printer and inventory records override generic cost fallbacks. Every new revision stores a settings snapshot so later changes do not rewrite history.

## Revision Snapshot

An approved revision freezes:

- all request, line, operation, variant, and result data;
- business profile, currency, locale, timezone, and tax decision;
- relevant customer and address references or snapshots;
- calculation-setting inputs;
- printer and material cost sources;
- slicer provenance and manual override markers;
- price method, discounts, minimums, and rounding;
- approver, approval timestamp, warnings, and accepted reasons;
- exchange-rate data if multi-currency support is introduced later.

Approval verifies the current optimistic version and persists the immutable revision atomically.

## Quotation Handoff Contract

Only an approved revision may be used to create a quotation. The handoff includes:

- selected preferred variant;
- sellable lines, descriptions, quantities, and units;
- unit and total prices;
- discounts and tax decision;
- enabled technical print information.

It excludes internal hourly rates, purchase prices, production costs, margins, and risk assessments. A quotation retains the exact calculation-revision reference. Later calculation changes do not mutate an existing quotation; a new revision can create a new quotation version in the later document increment.

## Templates

Templates may retain line and operation structure, default material/profile choices, time and cost rules, and optional variants. They exclude customer data, addresses, concrete source files, slicer results, requested dates, calculated prices, and approval state.

Instantiating a template creates a normal calculation draft and records the source template and version.

## Validation

Approval requires:

- an active business profile;
- at least one sellable line;
- valid quantities and units;
- material and duration for every print operation;
- resolvable cost sources;
- explicit currency and tax decision;
- non-negative selling prices;
- no unresolved conflicts between sourced and manual values.

Quotation handoff additionally requires a customer with a suitable billing address.

Validation severity is explicit:

- information: a fallback source was used;
- warning: target margin is missed or a sourced value was overridden;
- blocker: a required source, quantity, or tax decision is invalid or missing.

Warnings may be accepted with a recorded reason by an authorized user. Blockers prevent approval and quotation handoff.

## Permissions and Audit

Existing permissions are used:

- `calculations:read`: view calculations and revisions;
- `calculations:update`: create and edit drafts, variants, and templates;
- `calculations:approve`: approve, accept warnings, and supersede revisions.

The later quotation command also requires the commercial-document draft permission. An optional profile-level rule may require approval above a configured value or discount threshold.

Audit events cover creation, edit conflict, sourced-value override, price override, warning acceptance, approval, supersession, archival, template creation, and quotation handoff.

## Failure and Concurrency Behavior

- Draft updates use optimistic version checks and never silently overwrite concurrent edits.
- A stale approval request fails without creating a partial revision.
- Missing or deleted source records remain explainable through revision snapshots.
- Failed slicer imports retain an error state and permit corrected manual entry.
- Every operational surface has explicit loading, empty, validation, permission, conflict, server-error, and retry states.

## Verification Expectations

The implementation plan must cover:

- formula, precision, and rounding tests;
- quantity and explicit-scrap tests;
- cost-source precedence and snapshot tests;
- revision immutability and concurrent-update tests;
- validation, warning-reason, and permission tests;
- API integration tests for calculations, variants, templates, and approval;
- frontend tests for the list, editor, live totals, provenance, and comparison;
- browser verification from customer request through an approved quotation-ready revision.

## Deferred Work

Later increments will implement quotation/document generation, customer-facing acceptance links, numbering, PDF layout, reminders, automatic order creation, reservations, production scheduling, actual-cost comparison, and queue automation. Those capabilities must consume approved revisions rather than duplicating or mutating calculation logic.

## Calculation Settings Overview Layout

The calculation settings surface uses a responsive two-column overview so operators can quickly see configured defaults and missing decisions. The compact global values for currency, filament price, and electricity price span the full width above the cards.

The left column contains cost inputs in this order: cost basis, labor times, and ancillary costs. The right column contains commercial decisions in this order: risk and scrap, price derivation, and the live example calculation. On narrow screens the cards collapse to one column while retaining this reading order.

Every card title has a meaningful Lucide icon: `Coins` for cost basis, `Clock` for labor, `Package` for ancillary costs, `TriangleAlert` for risk, `BadgeEuro` for pricing, and `Calculator` for the example. Icons use the existing orange/green accent treatment and do not replace visible text labels. Card spacing, title rows, descriptions, input heights, and borders remain consistent with the existing PrintOps settings design.

## Central Device Master Data

PrintOps has one authoritative device-management surface under Settings. The existing printer-management UI is renamed to device management and presents printers and dryers together without duplicating printer records. Existing printer connection, control, archive, and maintenance behavior remains backed by the printer model. Dryers use a separate general-equipment model because they do not have printer connectivity or print-job behavior.

The first supported calculable device types are `printer` and `dryer`. General-equipment records contain a name, active state, acquisition date, acquisition value, service life in years, expected annual operating hours, maintenance/wear percentage, and nominal power in watts. Printer records receive the same optional commercial fields without changing their operational fields. A later increment may add other equipment types through the same general-equipment model.

Current residual value is read-only and calculated by straight-line depreciation from acquisition value and acquisition date to zero at the end of service life. The calculated machine hourly rate is also read-only and uses depreciable value, expected operating hours, and maintenance/wear. Both derived values are returned by the backend so every UI uses the same result.

Calculation settings no longer create equipment. They select an active default printer and an optional active default dryer from device management. An order calculation resolves those defaults and may override them per production step. A dryer selection additionally records the required drying duration for that calculation. Approval snapshots retain device identifiers, names, and the resolved commercial values so historical revisions remain explainable after master data changes.

Currency is selected from supported ISO currencies rather than entered as free text. Price derivation gains a backend-owned rounding rule matching the available ForgeDesk behavior; preview and approval apply the same rule. Device deletion is blocked when operational dependencies require it, while inactive devices remain visible in historical revisions but are excluded from new default selectors.
