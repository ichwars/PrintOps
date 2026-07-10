# PrintOps Order Management

Date: 2026-07-10
Status: Approved

## Purpose

PrintOps needs a complete commercial workflow for additive manufacturing without
turning the application into a generic accounting suite. The order domain should
connect customer demand, technical calculation, material planning, print
production, delivery, invoicing, payment status, and actual production cost.

ForgeDesk already explored the desired user journeys for customers, calculations,
quotations, invoices, and a commercial dashboard. This design keeps those useful
workflows, replaces the settings-JSON persistence with a transactional backend
domain, corrects the calculation model, and integrates the result with the
existing PrintOps project, queue, inventory, archive, energy, and permissions
systems.

The design supports two equally valid billing modes:

- PrintOps issues and archives the final commercial documents.
- An external accounting system owns final issuance while PrintOps prepares and
  synchronizes the commercial data.

The first external adapter is Lexware Office. Standards-based EN 16931, UBL, CII,
and CSV exports remain the portable foundation rather than being implemented as
Lexware-specific behavior.

## Goals

- Provide a coherent workflow from customer and calculation through order,
  production, delivery, invoice, payment, and credit note.
- Support multiple projects, print jobs, deliveries, and invoices per order.
- Make additive-manufacturing costing accurate, explainable, versioned, and
  comparable with actual PrintOps production data.
- Support configurable seller countries, tax profiles, currencies, languages,
  numbering, and document policies without a hard-coded German or 19% VAT model.
- Produce human-readable PDFs and machine-readable EN 16931 documents.
- Support internal billing, external billing, and hybrid operation per business
  profile and document.
- Integrate Lexware Office safely, idempotently, and without competing invoice
  numbers.
- Preserve the integrity and audit trail of issued documents.
- Fit the existing SQLAlchemy, FastAPI, React, settings, backup, and RBAC patterns
  in PrintOps.

## Non-Goals

- PrintOps does not file VAT returns or replace professional tax advice.
- The tax engine proposes and validates configured treatments; it does not claim
  universal legal correctness for every jurisdiction.
- The first release does not initiate bank transfers or collect card payments.
  It records payments and imports payment state from adapters.
- Generating EN 16931 documents is in scope; operating a Peppol access point is
  not. Peppol transport can be added through a future adapter.
- Automatic live tax-rate and foreign-exchange feeds are not required initially.
  Effective-dated configured values and explicit exchange-rate snapshots are.
- ForgeDesk sample customers and documents are not migrated into PrintOps.
- Business profiles are issuer configurations inside one PrintOps installation,
  not security-isolated tenants.

## Evidence and Constraints

### ForgeDesk findings

The original ForgeDesk repository contains useful screens and workflows for:

- customer records, contacts, billing and delivery addresses, payment terms, and
  tags;
- additive-manufacturing calculation from 3MF/slicer data;
- quotation and invoice lists and status actions;
- quotation-to-invoice conversion;
- a commercial overview with open amounts and reservations.

Those records are currently persisted as JSON values in generic application
settings such as `orders.customers`, `orders.offers`, and `orders.invoices`.
Document counters are incremented in the frontend, VAT is fixed at 19%, and there
is no first-class order aggregate between an accepted quotation and an invoice.
This is appropriate prototype material, not a persistence or concurrency model to
port.

ForgeDesk2 contains the newer navigation direction but only placeholder order
pages. It is a secondary information-architecture reference, not a functional
source.

### PrintOps findings

PrintOps currently has an `OrdersPage` foundation with routes for overview,
customers, calculation, offers, and invoices. It has no order backend models or
APIs yet. Existing reusable capabilities include:

- projects, project BOM items, library files, print queue items, archives, and
  print logs;
- spool inventory, filament prices, actual usage, and material forecasts;
- printer and energy data, including smart-plug measurements;
- currency, default filament price, and electricity price settings;
- group-based permissions and closed-by-default API-key permission mapping;
- ReportLab for server-side PDF rendering and lxml for XML processing;
- SQLite and PostgreSQL support, backup/restore, and existing background loops.

### External standards

- EU VAT invoices have a common set of required data, while member states retain
  additional national rules: [European Commission VAT invoicing](https://taxation-customs.ec.europa.eu/taxation/vat/vat-businesses/invoicing_en).
- Authenticity, content integrity, legibility, and a reliable audit trail must be
  preserved through the storage period: [VAT Directive Article 233](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A02006L0112-20250320).
- EN 16931 defines the semantic invoice model. The required EU syntaxes are UBL
  2.1 and UN/CEFACT CII: [EU required syntaxes](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108934/Required+syntaxes).
- EU validation artifacts are versioned and updated regularly:
  [EU validation guidance](https://ec.europa.eu/digital-building-blocks/sites/spaces/DIGITAL/pages/467108940/Validations).
- ViDA introduces digital reporting based on e-invoicing for cross-border EU B2B
  transactions from July 2030: [VAT in the Digital Age](https://taxation-customs.ec.europa.eu/taxation/vat/vat-digital-age-vida_en).
- International VAT/GST generally follows destination-based principles but
  remains jurisdiction-specific: [OECD International VAT/GST Guidelines](https://www.oecd.org/en/publications/international-vat-gst-guidelines_9789264271401-en.html).
- Additive-manufacturing cost research treats machine, material, electricity,
  labor, ancillary processes, utilization, and process failure as distinct cost
  drivers: [general AM cost model](https://www.sciencedirect.com/science/article/abs/pii/S1755581721000596) and
  [failure-aware AM cost model](https://www.sciencedirect.com/science/article/pii/S0925527321000633).

## Architecture Decision

Order management will be a modular domain inside the existing PrintOps backend,
not a separate service and not a frontend-only feature. The domain owns its
transactions and exposes APIs through the existing FastAPI application.

The module has five boundaries:

1. Commercial master data: business profiles, customers, addresses, contacts,
   terms, tax identities, and external mappings.
2. Planning: calculations, calculation revisions, cost components, variants,
   quotations, and approvals.
3. Fulfillment: orders, order lines, project/job links, reservations, production
   progress, deliveries, and actual-cost attribution.
4. Documents: document drafts, immutable issued snapshots, artifacts, numbering,
   relations, payments, and audit events.
5. Adapters: EN 16931 renderers/validators, CSV profiles, VIES verification, and
   external accounting integrations such as Lexware Office.

Adapters consume a canonical commercial-document snapshot. Domain services do
not contain Lexware field names or UBL XML construction.

## Domain Model

### Core records

| Record | Responsibility |
| --- | --- |
| `BusinessProfile` | Issuing legal entity configuration: name, addresses, country, tax IDs, bank details, currencies, locale, timezone, billing mode, and defaults. |
| `Customer` | Current customer master record, type, status, customer number, language, terms, tax status, notes, and external mappings. |
| `CustomerContact` | One or more people and communication channels belonging to a customer. |
| `CustomerAddress` | Effective billing, delivery, and other addresses without overloading one address field. |
| `Calculation` | Stable calculation identity, owner, customer/order context, lifecycle status, and current revision. |
| `CalculationRevision` | Immutable input and result snapshot for an approved or referenced calculation version. |
| `CalculationLine` | Sellable line such as printed part, service, material, shipping, discount, or text. |
| `CalculationOperation` | Costed production step such as CAD, slicing, setup, printing, drying, post-processing, QA, or packing. |
| `CommercialDocument` | Draft and issued commercial document header with type, status, currency, parties, dates, totals, and references. |
| `CommercialDocumentLine` | Quantity, unit, description, unit price, discount, tax category/rate, and source references. |
| `DocumentRelation` | Typed chain between quotation, order confirmation, delivery note, invoice, credit note, and preceding documents. |
| `DocumentArtifact` | PDF/XML/CSV artifact metadata, media type, size, checksum, validator version, and storage path. |
| `DocumentLayout` | Named editable layout assignment by business profile, document type, and locale. |
| `DocumentLayoutVersion` | Immutable published layout definition and referenced assets used by issued documents. |
| `NumberSequence` | Transactional counter and format by business profile, document type, and period. |
| `SalesOrder` | Operational aggregate with customer, dates, owner, priority, status, totals, and source quotation. |
| `SalesOrderLine` | Ordered quantity, fulfilled quantity, commercial values, calculation source, and production requirements. |
| `OrderProjectLink` | Many-to-many link between an order/order line and existing PrintOps projects. |
| `OrderJobLink` | Attribution between an order line and queue/archive/print-log production records. |
| `InventoryReservation` | Soft or hard reservation of spool/material quantities with lifecycle and shortage state. |
| `Delivery` | A partial or complete fulfillment event with address snapshot, carrier/reference, and dates. |
| `DeliveryLine` | Quantity from a specific order line included in the delivery. |
| `Payment` | Internal payment entry or externally synchronized payment allocation. |
| `ExternalSyncRecord` | Adapter, external ID/version, direction, status, last payload hash, retry state, and conflict details. |
| `BusinessEvent` | Append-only audit event for relevant commercial actions and state changes. |

Draft business data is relational. JSON is limited to immutable canonical
snapshots, adapter payload evidence, versioned layout definitions, and validation
reports; it is not the primary store for customers, orders, or mutable documents.

### Data types and invariants

- Monetary amounts use SQL `NUMERIC`/Python `Decimal`, never binary floats.
- Every amount has an ISO 4217 currency. Currency cannot change after a document
  is issued.
- Countries use ISO 3166-1 alpha-2 codes. Units map to UNECE Recommendation 20
  codes while retaining a localized display label.
- Business timestamps are stored in UTC. Legal issue, supply, due, and delivery
  dates are explicit date fields interpreted using the business-profile timezone.
- Mutable aggregates carry a version number for optimistic locking.
- Current customer data and issued-document party snapshots are separate.
- Issued documents cannot be edited or deleted through normal APIs.
- Referential deletion is restricted for records used by issued documents.

## Workflow and State Machines

### Calculation

`draft -> approved -> superseded | archived`

Editing an approved calculation creates a new revision. Referenced revisions stay
available even if a newer revision becomes current.

### Quotation

`draft -> issued -> sent -> accepted | rejected | expired | superseded`

An accepted quotation can create one order exactly once through an idempotent
command. A revised quotation supersedes rather than mutates the issued version.

### Order

`draft -> confirmed -> planned -> in_production -> partially_fulfilled -> fulfilled -> closed`

`on_hold` may be entered from confirmed through partially fulfilled states.
`cancelled` is available only while unfulfilled quantities and financial document
relations permit cancellation. Partial fulfillment and partial invoicing remain
visible rather than forcing a misleading completed state.

### Delivery

`draft -> dispatched -> delivered`

A draft may be cancelled. A dispatched or delivered record is corrected through
a reversing/correcting record and audit event rather than destructive editing.

### Invoice and credit note

`draft -> issued -> partially_paid -> paid`

An issued unpaid invoice can become `overdue` based on its due date. It can be
corrected only by a linked correction/credit document. `voided` records remain in
the number sequence and audit trail.

### External synchronization

`pending -> running -> succeeded | retryable_failure | permanent_failure | conflict`

Every transition records actor, timestamp, reason, and source. Automatic status
derivations are distinguishable from explicit user actions.

## Calculation and Pricing

### Production quantity

Each print operation defines:

- required good-part quantity;
- parts per print run/plate;
- print time and material per run;
- build-failure probability;
- per-part rejection probability;
- explicit contingency runs for scheduling.

Nominal runs are `ceil(required_good_parts / parts_per_run)`. Expected cost uses
the configured build success and part yield as separate factors. Production
scheduling remains based on integer nominal plus explicit contingency runs; a
hidden percentage surcharge does not silently create queue work.

For multi-plate 3MFs, each selected plate is a separate operation. Slicer-derived
values retain source file, plate, process profile, printer profile, material
profile, timestamp, and whether a user overrode them.

### Cost components

- Material: model, support, purge/flush, waste, and additional parts.
- Machine: acquisition value, residual value, service life, usable annual hours,
  utilization assumption, maintenance, and optional space/overhead allocation.
- Energy: printing, preheating, drying, and post-processing.
- Labor: CAD, preparation, setup, supervision, unloading, post-processing, QA,
  packing, and administration.
- Consumables and tooling.
- Packaging and shipping.
- Purchased materials and external services.
- Expected build failure and part rejection.

Labor and other operations declare whether they occur once per order, once per
run, or once per part. This prevents setup time from being multiplied by part
quantity and prevents per-part finishing from being charged only once.

### Price formation

The pricing method is selected per calculation or inherited from settings:

- Cost markup: `net_price = cost * (1 + markup_rate)`.
- Target gross margin: `net_price = cost / (1 - margin_rate)`.

Minimum order value, minimum absolute contribution, line discounts, document
discounts, and currency rounding are applied by explicit ordered rules. A discount
that would break an approved floor raises a warning and requires a permitted
override with a reason. Tax is applied after net price and never counted as margin
or revenue.

### Planned versus actual

Approved calculations snapshot all rates and assumptions. Linked queue, archive,
print-log, spool-usage, and smart-plug records supply actual time, material,
energy, failure, and reprint data. Order and line views show:

- planned and actual cost by component;
- quantity planned, completed, rejected, and delivered;
- planned and actual contribution/margin;
- variance with drill-down to the contributing runs.

Actual data never rewrites the approved quotation price.

## Inventory and Production Integration

- Order confirmation creates material requirements.
- A business-profile setting selects no automatic reservation, soft reservation,
  or hard reservation.
- Reservations may target a specific spool/material item or a fungible material
  requirement such as material, color, and quantity.
- Availability always distinguishes on-hand, reserved, allocated, consumed, and
  shortage quantities.
- Queue creation can allocate a reservation to concrete spools.
- Successful usage consumes the allocated amount from existing PrintOps usage
  data. Failed and stopped runs remain attributable to the order.
- Cancellation and quantity reduction release only unconsumed reservations.
- Project and order status remain related but independent: a project can contain
  technical work for more than one order, and an order can contain multiple
  projects.

## Business, Tax, Currency, and Locale Profiles

### Business profile

A profile contains the seller identity and policies used for a document:

- legal/trading name, addresses, country, registration and tax identifiers;
- bank and payment information;
- default and allowed currencies;
- timezone, default locale, and supported document languages;
- internal, external, or hybrid billing mode;
- numbering and document defaults;
- tax rule set and retention policy;
- default PDF layout assignments and export adapters.

An installation may configure more than one profile. Each order and document has
one profile. Profiles do not isolate users or data like tenants.

### Tax decision

The tax decision input includes seller country, customer country, B2B/B2C status,
validated tax identifiers, goods/service classification, supply or service date,
place-of-supply inputs, delivery destination, and explicit exemptions.

Effective-dated rule records produce a tax category, rate, exemption/reverse-
charge reason, required document text, and evidence requirements. Supported
categories include standard/reduced/zero rate, exempt, outside scope, reverse
charge, intra-community supply, export, and configurable jurisdiction-specific
cases.

The user sees the decision inputs and result before approval. Manual treatment is
possible only with permission, reason, and audit event. Optional VIES checks store
the submitted identifier, result, request time, and evidence reference.

### Currency

- Commercial documents support ISO currencies independently of the business
  profile's accounting currency.
- A foreign-currency document stores one explicit exchange-rate snapshot, source,
  and effective date where accounting or tax reporting needs a local-currency
  amount.
- Rounding is configured per currency and export profile, with EN 16931 rules
  enforced for EN 16931 artifacts.
- Lexware export is blocked for non-EUR documents unless a future adapter version
  explicitly supports them. Silent conversion is prohibited.

## Commercial Documents and Numbering

### Canonical document model

The common document model supports:

- quotation;
- order confirmation;
- delivery note;
- pro forma invoice;
- down-payment invoice;
- partial invoice;
- final/closing invoice;
- credit/correction note.

Document type policies determine allowed statuses, required dates, amount rules,
and valid preceding/following relations. The shared model is not used to erase
those differences.

### Draft and issue behavior

- Drafts are mutable and have no final legal number.
- A preflight validates required party, line, delivery, payment, tax, and export
  fields before issuance.
- Issuance reserves a number transactionally, renders the canonical snapshot and
  artifacts, validates them, and finalizes the immutable record.
- A failed reservation is never reused silently. It is recorded as voided with a
  reason so numbering remains explainable under concurrency and failure.
- The issued snapshot contains seller, buyer, addresses, lines, prices, taxes,
  payment data, references, locale, exchange rate, tax decision, and layout
  version.
- Every artifact stores a SHA-256 checksum. Revalidation or re-download does not
  mutate the original artifact.

## PDF Layout Settings

`Auftragsverwaltung > PDF-Layout` is a first-class settings area rather than an
unstructured HTML template field.

### Layout scope

Layouts can be assigned by business profile, document type, and locale. A default
layout exists for each supported page family. A document draft can preview another
eligible layout without changing global defaults.

### Configurable elements

- A4 and Letter page sizes, portrait/landscape where the document type permits it.
- Page margins, first-page and continuation-page behavior.
- Logo, optional PDF/image stationery background, accent and neutral colors.
- Bundled or uploaded embeddable TTF/OTF fonts with explicit fallback chains.
- Sender line, address window position, seller/buyer blocks, and contact details.
- Header and footer content, page number, document number, and legal text.
- Column visibility, labels, widths, alignment, quantity/unit/price precision, and
  tax display.
- Introductory and closing text blocks by document type and locale.
- Totals, tax breakdown, payment terms, bank details, references, and signatures
  or approval labels.
- Optional payment QR area when supported by the selected payment profile.

The editor uses structured controls and a server-rendered live preview with sample
or selected draft data. It reports overflow, missing fonts/assets, invalid page
geometry, and orphaned totals before a layout can be published.

### Versioning and rendering

- Editing creates a working draft; publishing creates an immutable
  `DocumentLayoutVersion`.
- Issued documents reference the exact published version and asset checksums.
- Later layout changes never rerender historical documents.
- ReportLab is the primary renderer because it is already an application
  dependency. A small PDF merge dependency may be added for PDF stationery.
- Uploaded fonts and backgrounds are size/type validated and stored in the
  protected data directory, never fetched from remote URLs at render time.

## Machine-Readable Exports

The canonical issued snapshot can produce:

- EN 16931 UBL 2.1 Invoice/CreditNote;
- EN 16931 UN/CEFACT Cross Industry Invoice D16B;
- configurable CSV profiles with stable column identifiers and locale-independent
  raw values;
- human-readable PDF.

EN 16931 validation artifacts and code lists are pinned and vendored with a
recorded version so runtime generation does not depend on network access. lxml
performs XSD and Schematron validation. The validation report is stored beside the
artifact.

Country CIUS/profile support builds on the canonical model. XRechnung and
ZUGFeRD/Factur-X are the first planned profiles after the EN 16931 core; Peppol
PINT compatibility remains possible without coupling the domain to a transport
network.

## Internal, External, and Hybrid Billing

### Internal mode

PrintOps owns numbering, final issuance, immutable artifacts, payment state, and
corrections. External exports are copies of an already issued PrintOps document.

### External mode

PrintOps sends an approved, unnumbered external draft. The external system owns
the final number and finalization. PrintOps stores the returned external ID,
number, status, and artifact. It never allocates an internal invoice number for
that document.

### Hybrid mode

The default owner is configured by document type and can be selected on a draft
when policy allows it. A common pattern is internal quotations and delivery notes
with externally issued invoices. Once ownership is selected and finalization
begins, it cannot be switched without cancelling the pending operation and
recording an audit event.

## Lexware Office Adapter

The adapter uses the current `https://api.lexware.io` gateway and stores its API
credential encrypted on the backend. The credential is never returned to the
frontend after save.

### Supported synchronization

- Business profile/connection validation.
- Customer/contact mapping with external UUID and version.
- Quotation, order confirmation, delivery note, invoice, down-payment invoice,
  and credit-note draft creation where supported by the API.
- Explicit finalization only after a separate permitted user action.
- External document number, status, deep link, PDF/XML artifact, and payment
  state import.
- Webhook-driven contact, document, payment, and token-revocation updates.

Lexware currently supports EUR for sales-voucher prices. Adapter preflight blocks
other currencies. Lexware-specific tax types are mapped from the canonical tax
decision only when a lossless supported mapping exists.

### Reliability and security

- Outbound operations use idempotency records and payload hashes.
- Webhooks verify the `X-Lxo-Signature` RSA-SHA512 signature before accepting the
  event.
- Accepted callbacks are persisted quickly and processed asynchronously.
- `(organization_id, event_type, resource_id, event_date)` and payload hash form
  the deduplication evidence.
- Retry uses bounded exponential backoff and distinguishes retryable transport
  errors from permanent validation errors.
- Webhook updates fetch the latest resource rather than trusting the notification
  as the complete state.
- Local and external concurrent edits create a visible conflict. Neither side is
  silently overwritten.
- `token.revoked` disables the connection, removes pending secret use, and alerts
  administrators.

Official adapter behavior is based on the
[Lexware API documentation](https://developers.lexware.io/docs/) and
[Lexware webhook guidance](https://developers.lexware.io/cookbooks/public-api/).

## User Experience

### Navigation

The order-management navigation contains:

1. `Auftragsuebersicht`
2. `Auftraege`
3. `Kalkulationen`
4. `Angebote`
5. `Kunden`
6. `Lieferungen`
7. `Rechnungen`

Payments, credit notes, and dunning state are handled in the invoice area.
Order confirmations and related documents are accessible from their order to
avoid an oversized navigation tree.

### Overview

The first screen is an operational workspace, not a marketing dashboard. It
shows a compact KPI band and actionable queues for:

- quotations awaiting action;
- confirmed work not yet planned;
- material shortages and blocked reservations;
- production progress and failed/reprint work;
- upcoming and overdue delivery dates;
- delivered work ready to invoice;
- open, partially paid, and overdue receivables;
- adapter and document-validation failures.

Amounts are never double-counted across calculation, quotation, invoice, and
payment stages.

### Lists and detail views

- Lists support search, compound filters, sorting, pagination, saved views,
  column selection, and CSV export.
- Stable column widths and concise status badges keep operational tables
  scannable.
- The order detail uses tabs for `Uebersicht`, `Positionen`, `Produktion`,
  `Material`, `Lieferungen`, `Belege`, and `Verlauf`.
- The calculation workspace keeps source/production inputs, cost breakdown, price
  result, and variants visible without nested cards.
- The document editor uses a line table, tax decision panel, preflight results,
  PDF preview, and separate Save, Approve, Issue, and Export commands.
- Empty, loading, permission-denied, validation, conflict, and retry states are
  explicit.
- Destructive or legally relevant actions require confirmation and, where
  configured, a reason.

## Settings Information Architecture

`Auftragsverwaltung` contains these sub-areas:

1. Unternehmensprofil
2. Nummernkreise und Dokumente
3. Steuern, Waehrungen und Laenderregeln
4. Kalkulationsstandards
5. Zahlungs- und Lieferbedingungen
6. PDF-Layout
7. Exportprofile
8. Lexware Office
9. Aufbewahrung und Datenschutz

Legacy cost settings remain readable and are migrated or used as initial defaults
for the first business profile. Existing settings links continue to resolve to the
canonical order-management settings area.

## Permissions

The existing `resource:action` RBAC model gains explicit permissions for:

- customers read/manage;
- calculations read/update/approve;
- orders read/update/cancel;
- order production/reservations manage;
- commercial documents read/draft/approve/issue/correct/export;
- payments read/manage;
- order audit read;
- order settings manage;
- accounting integrations manage.

Default policy:

- Administrators receive all new permissions.
- Operators can read/manage customers, calculations, orders, production, and
  reservations, but cannot issue/correct invoices or configure accounting
  integrations by default.
- Viewers receive read-only commercial access where ownership policy permits.
- API keys receive no new capability until each permission is mapped to a narrow
  explicit API-key scope. Unmapped permissions continue to fail closed.

Route, command, and frontend navigation checks all use the same permission names.
Hiding a button is not treated as authorization.

## Privacy, Retention, and Audit

- Customer fields are purpose-bound and minimized.
- Access to customer, financial, and integration data is permission-controlled.
- Legal retention and ordinary CRM retention are separate policies.
- A data-subject deletion workflow removes or anonymizes erasable master/contact
  data while retaining legally required issued-document snapshots.
- Legal hold prevents automated purge.
- Issued documents, corrections, exports, external finalization, manual tax
  overrides, payment edits, and retention actions produce audit events.
- Audit events record actor identity, request correlation ID, timestamp, action,
  object identifiers, reason, and safe before/after metadata without copying API
  secrets or unnecessary personal data.
- Document artifacts and customer exports are protected by the same authentication
  and authorization as their records.

These controls implement the GDPR principles of purpose limitation, data
minimization, storage limitation, and integrity/confidentiality described by the
[European Commission](https://commission.europa.eu/law/law-topic/data-protection/rules-business-and-organisations/principles-gdpr/overview-principles/what-data-can-we-process-and-under-which-conditions_en).

## Transactions, Background Work, and Failure Handling

### Transaction boundaries

- Accept quotation: lock quotation, verify current revision, create order and
  source relations, then commit once.
- Approve calculation/document: verify optimistic version and persist immutable
  approved revision in one transaction.
- Reserve material: validate availability and create/update all reservation rows
  atomically.
- Create delivery: validate remaining quantities and update fulfillment totals
  atomically.
- Record payment: validate currency and remaining amount, append allocation, and
  derive invoice state atomically.
- Issue internal document: reserve sequence, render/validate, then finalize the
  snapshot and artifact metadata. Failed sequence reservations are voided and
  audited, not reused.
- Start external issuance: persist the exact outbound snapshot and idempotency
  record before network work. The external result is applied in a separate
  transaction.

### Background jobs

Long-running PDF/XML rendering, bulk export, VIES checks, and external API work use
durable job rows processed by a bounded internal worker loop. Jobs survive process
restart. User-facing state distinguishes queued, running, retrying, failed,
conflicted, and completed operations.

### Error handling

- Validation errors return stable field-level problem details.
- Optimistic-lock conflicts return the current version and never overwrite it.
- Adapter errors retain sanitized provider codes and correlation IDs.
- Retries are safe because every side effect has an idempotency key or stored
  external ID.
- Partial artifact creation is cleaned up or retained in a quarantined failure
  area; it is never presented as an issued document.
- Number-sequence, validation, webhook, worker, and backup failures emit logs and
  operational metrics without exposing customer content or credentials.

## Persistence, Migration, and Backup

- New tables are created through the existing SQLite/PostgreSQL-compatible
  database migration path.
- Foreign keys, uniqueness, check constraints, and indexes enforce core
  relationships and sequence/external-ID uniqueness.
- Existing `default_filament_cost`, `currency`, and `energy_cost_per_kwh` values
  seed the first calculation profile but remain compatible with existing cost
  displays.
- Existing project, queue, archive, print-log, spool, and usage tables gain only
  narrowly scoped nullable links or association tables; their current workflows
  remain valid without an order.
- Backups include all commercial tables, published layout assets, issued
  artifacts, validation evidence, and adapter metadata.
- Integration secrets use the existing protected encryption mechanism and are not
  included in plaintext support bundles or exports.
- Restore validates artifact checksums and reports missing/quarantined files.

## Verification Strategy

### Backend unit tests

- Decimal calculations, markup versus margin, fixed/per-run/per-part allocation,
  yield/failure behavior, floors, discounts, tax grouping, and rounding.
- Every valid and invalid state transition.
- Tax-rule selection, manual override permissions, and effective dates.
- Number formatting, annual reset, concurrency, voided reservations, and no reuse.
- Immutable snapshot and checksum behavior.
- Permission and API-key fail-closed behavior.
- Lexware mapping, unsupported currency/tax cases, webhook signature validation,
  deduplication, retries, and conflict detection.

### Backend integration tests

- CRUD and filtering for customers, calculations, orders, deliveries, documents,
  payments, and settings.
- Complete quotation-to-order-to-production-to-delivery-to-invoice flow.
- Partial delivery, partial/down-payment/final invoice, payment, and credit-note
  flow.
- Simultaneous issuance requests against SQLite and PostgreSQL.
- Project, queue, archive, usage, and energy attribution.
- Backup/restore with layouts and document artifacts.
- Restart recovery for durable jobs.

### Document conformance tests

- UBL and CII examples validate against pinned XSD/Schematron artifacts.
- Tax categories, allowances/charges, references, multi-rate totals, and credit
  notes have dedicated fixtures.
- Generated PDFs are checked for page count, expected text, embedded fonts,
  artifact checksum, and overflow/page-break cases.
- PDF layout previews cover A4/Letter, long addresses, long descriptions,
  multi-page tables, continuation headers, and the longest supported locale text.

### Frontend tests

- Navigation, permissions, filters, saved views, empty/error/conflict states, and
  responsive layout.
- Calculation input and variant behavior.
- Order status and partial fulfillment actions.
- Document preflight, preview, approval, issue, correction, and export actions.
- Settings including PDF layout draft/publish/version behavior.
- End-to-end browser flows at desktop and mobile widths with screenshot checks for
  text overflow and incoherent overlap.

### External adapter tests

- Automated tests use a deterministic fake Lexware server and contract fixtures.
- A manual release checklist uses a Lexware test account; provider production APIs
  are never load-tested.
- Webhook tests verify valid/invalid signatures, duplicates, reordering, retries,
  token revocation, and payment changes.

## Delivery Shape

Implementation should be split into reviewable vertical increments that keep
`main` passing:

1. Domain foundation, business/customer data, permissions, and settings.
2. Calculation revisions, variants, slicer inputs, and planned cost.
3. Quotations, orders, projects/jobs, reservations, and actual cost.
4. Deliveries, canonical documents, numbering, PDF layout, PDF, and CSV.
5. Invoices, credit notes, payments, UBL/CII generation, and validation.
6. Lexware Office adapter, webhooks, conflicts, and external artifacts.
7. Overview, saved views, retention tools, full workflow QA, and documentation.

Each increment includes migrations, backend tests, frontend tests, permission
coverage, and browser verification. No increment may write to the upstream
repository; branch and pull-request operations target the `ichwars/PrintOps` fork.

## Acceptance Criteria

- A user can create a customer, calculate a multi-run print, issue a quotation,
  accept it into an order, link projects/jobs, reserve material, record partial
  delivery, issue multiple invoice types, record payment, and create a correction.
- Planned and actual production cost remain traceable to their source records.
- Internal issued documents are immutable, numbered concurrently without
  duplicates, checksummed, and auditable.
- A supported invoice exports as PDF, valid UBL, valid CII, and configured CSV.
- A published PDF layout renders predictable one- and multi-page documents and is
  frozen on issuance.
- External mode creates a Lexware draft without allocating a PrintOps invoice
  number and later synchronizes final number, status, files, and payment.
- Unsupported currency or tax mappings fail before external side effects.
- Permission boundaries prevent operators from issuing invoices by default and
  prevent API keys from gaining implicit new access.
- Customer erasure and retention workflows preserve required document evidence
  while removing eligible master data.
- Existing PrintOps users can continue projects, queueing, printing, inventory,
  archive, settings, and backup workflows without creating commercial records.

## Self-Review

- Scope check: the design covers the complete requested workflow while excluding
  tax filing, payment initiation, and transport-network operation.
- ForgeDesk check: useful UX and 3MF calculation concepts are retained; JSON
  persistence, browser counters, fixed VAT, fake revenue history, and direct
  quotation-to-invoice shortcuts are not.
- PrintOps fit check: existing projects, queue, inventory, logs, energy, ReportLab,
  lxml, RBAC, backups, and database support are reused through narrow links.
- Internationalization check: seller country, currency, locale, tax rule, unit,
  document profile, and adapter are explicit data rather than global constants.
- Integrity check: drafts are mutable; approved revisions and issued document,
  tax, party, exchange-rate, and layout snapshots are immutable.
- Failure check: numbering gaps, render failures, duplicate webhooks, retries,
  restarts, unsupported Lexware mappings, and concurrent edits have explicit
  states and evidence.
- UI check: all operational areas have a natural home, and PDF layout is a
  dedicated settings area without expanding the main navigation unnecessarily.
- Open-question check: no unresolved product decision blocks implementation
  planning. Detailed table columns, endpoint payloads, and exact work breakdown
  belong in the implementation plan after review.
