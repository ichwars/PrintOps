# Order Management Foundation Evidence

## Baseline

- Branch before implementation: `codex/order-management` at `136d281e`.
- Worktree was clean.
- Full backend suite command:
  `.\.venv\Scripts\python.exe -m pytest backend\tests -q`.
- The run reached 15 percent before the five-minute limit and had multiple
  pre-existing failures.
- First isolated failure after 145 passes:
  `backend/tests/integration/test_archives_api.py::TestUploadSourceThreeMF::test_fallback_archive_source_upload_lands_under_base_dir`.
- Observed mismatch is Windows path separators (`archive\\no_source...`)
  versus a POSIX-only expected string (`archive/no_source...`). It is unrelated
  to order-management schema, authorization, APIs, or frontend behavior and is
  outside this increment.

## Evidence Policy

Each task records its focused pytest, Ruff, Vitest, lint, build, and browser
results here. Broader regression failures must be compared against this
baseline and classified before completion claims.

## Task 1: Relational Model Foundation

- TDD red state: the initial schema test reported all twelve required tables
  missing.
- Initial green state: table registration test passed and Ruff was clean.
- Specification review: compliant with all Task 1 fields, constraints,
  relationships, imports, and scope boundaries.
- Quality review initially found unsafe SQLite lifecycle handling for profile
  sequences and tag links, case-sensitive tag uniqueness, and shallow tests.
- Repair: explicit ORM ownership for profile sequences and tag links, portable
  unique `lower(name)` tag index, and behavior-level regression tests.
- Final focused command:
  `.\.venv\Scripts\python.exe -m pytest backend\tests\integration\test_order_foundation_schema.py -v`.
- Result: six passed.
- Ruff result: all checks passed for model files and the schema test.
- Final quality review: ready, with all four findings closed.
- PostgreSQL evidence: all twelve tables and the functional tag index compiled;
  no live PostgreSQL server was available for `create_all` execution.

## Task 2: Permission Contract And Backfill

- TDD red state: five permission-contract failures and one order-backfill
  integration failure.
- Added 21 exact order-management enum/category/frontend permission values.
- Fresh Operators and Viewers receive only the approved least-privilege sets;
  issuer settings and commercial issuance remain administrator-only.
- Existing system groups receive an additive, idempotent upgrade that preserves
  customized permissions and ignores non-system groups.
- Initial specification review found the existing API-key classification
  invariant incomplete and one Ruff import-order error.
- Repair: all 21 permissions are explicitly present in the API-key denylist,
  remain absent from the allowlist, and imports were normalized.
- Final expanded command covered permission units, groups API/backfill, and
  API-key authorization invariants; result: 91 passed.
- Ruff result: all checks passed for permissions, database, auth, and tests.
- Specification re-review: compliant. Code-quality review: ready with no
  findings.
- Residual risk: legacy `NULL` permission lists are not directly exercised;
  current model defaults and non-null typing prevent them in normal writes.

## Task 3: Transactional Number Sequences

- TDD red state: sequence service import was absent.
- Added strict `{PREFIX}`, `{YYYY}`, `{YY}`, and one-to-ten-digit counter
  validation and formatting.
- Added caller-transaction-owned optimistic reservation with ten CAS attempts,
  yearly reset behavior, and shared domain exceptions.
- Specification review found early years were not zero-padded to four digits;
  repair added exact `0001`–`9999` formatting and regression coverage.
- Quality review found yearly periods could rewind and final CAS exhaustion
  could leave stale ORM state.
- Repair: yearly periods are monotonic, backdating is rejected before mutation,
  malformed stored periods fail explicitly, and every failed CAS expires the
  tracked entity including the final attempt.
- Final focused result: 29 passed. Ruff and diff-check were clean.
- Specification review: compliant. Quality re-review: ready with no remaining
  findings.
- Residual risk: true simultaneous PostgreSQL/file-backed SQLite writers remain
  deliberately deferred to the document-numbering increment.

## Task 4: Issuing Business Profile API

- TDD red state: 21 profile API tests collected and the first POST returned
  405 before router registration.
- Added normalized nested Pydantic contracts, aggregate service, safe options
  projection, permissioned CRUD routes, stable problem details, and initial
  customer sequence creation.
- Specification review found missing `from_attributes` on the safe option type
  plus validation and authorization evidence gaps; repair expanded the suite.
- Quality review found non-atomic profile versions, race-prone defaults,
  profile-delete cascade risk, broad integrity classification, weak ISO
  validation, and unstable child ordering.
- Repairs added atomic version CAS, versioned default clearing, a portable
  one-default partial index, `RESTRICT` customer-account FK plus row lock,
  constraint-aware error mapping, `pycountry` ISO validation, normalized tax
  identifiers, optional-blank normalization, and deterministic relationships.
- Final review found and closed direct Asyncpg constraint metadata handling and
  a race between dedicated default switching and PUT; set-default now uses its
  own active/version CAS and rollback-safe transition.
- Final focused result: 65 passed. Ruff and diff-check were clean.
- Specification review: compliant. Quality re-review: ready with no remaining
  findings.
- Residual risk: no live PostgreSQL test server was available; SQLite foreign
  keys remain globally disabled, so a true concurrent customer-account insert
  during profile deletion remains a bounded platform risk despite the settled
  reference check. PostgreSQL is protected by row locking and `RESTRICT`.

## Task 5: Customer Master Data API

- TDD red state: customer POST returned 405 before router registration.
- Added nested customer contracts, multiple per-profile accounts, transactional
  number allocation, normalized tags, aggregate CRUD, distinct search/filter/
  pagination, explicit serializers, permissions, and stable problem details.
- Specification review found two missing field bounds; repair added locale and
  notes limits plus API-level 422 evidence.
- Quality review found blocked automatic numbering after manual values, reused
  SQLite child IDs, Decimal scale drift, nonportable Unicode case behavior, and
  stale profile validation/error classification.
- Repairs added deterministic profile/sequence locks, occupied-number skipping,
  in-place account replacement, exact two-decimal validation, shared NFKC+
  casefold keys, Unicode-literal search, tag savepoint reuse, and FK-aware
  resource errors.
- Follow-up review found PostgreSQL B-tree width risk and overbroad integrity
  classification. Broad normalized search indexes were removed, unique tag
  keys are capped at 512 UTF-8 bytes, and only verified FK/unique violations
  map to domain 409 responses.
- Final focused result: 98 passed. Ruff and diff-check were clean.
- Specification review: compliant. Quality re-review: ready with no remaining
  findings.
- Residual risk: no live PostgreSQL or true Asyncpg concurrency environment was
  available; PostgreSQL DDL, lock ordering, and direct metadata probes pass.

## Task 6: Frontend Contracts, Navigation, And Settings Routing

- TDD started with focused Layout, settings-navigation, and SettingsPage tests
  before the production wiring existed.
- Added exact request/response contracts and API methods for issuing profiles
  and customers, including optional server-defaulted request fields, required
  response fields, string decimal discounts, safe profile options, and stable
  query parameter serialization that preserves `offset=0`.
- Added the dedicated `/orders/customers` route, removed the customer
  placeholder from OrdersPage, applied the approved any-of parent and exact
  child permission gates, and added an App-level route regression test.
- Added canonical business-profile/calculation settings subtabs with shared URL
  resolution, explicit legacy calculation behavior, Building2 navigation, and
  locale-key parity across all eleven locales.
- Added compact real-data foundations for business profiles and customers with
  distinct loading, error, no-profile, empty, and list states; no synthetic
  business data or Task 7/8 editor behavior was introduced.
- Specification review initially found overly strict request optionality and
  missing route-level coverage. Both were repaired and the re-review passed.
- Quality review found disabled-query spinner leakage, a value-global i18n
  exception, and duplicate settings subtab resolution. Repairs introduced an
  ordered customer-page state machine, exact key-and-locale i18n exceptions
  with checker self-tests, one shared resolver, and rendered direct-URL tests.
- Final focused result: seven Vitest files and 154 tests passed. All eleven
  locale files report 5,635 leaves in parity. ESLint, `git diff --check`, and
  `tsc -b && vite build` passed.
- Final specification review: compliant. Final code-quality review: approved
  with no findings.
- Residual risk: the existing Vite bundle-size advisory remains; generated
  `static` assets were removed from the task diff after verification.

## Task 7: Business Profile Settings

- TDD expanded the compact Task 6 profile list into create, edit, default,
  activate/deactivate, and delete workflows with read/manage permission states.
- Added a scrollable fixed-footer editor for identity, registered and other
  addresses, tax identifiers, bank accounts, locale, currency, timezone,
  billing mode, and active state, including repeatable aggregates and Boolean
  controls.
- Added optimistic version submission, field-adjacent FastAPI 422 mapping,
  modal-local 409 conflicts that retain input, and persistent row-action errors
  tied to the exact operation and profile.
- Specification review exposed unusable bank rows, a hard-coded profile country,
  incomplete validation fallback, hidden row-action conflicts, and missing
  Boolean controls. Repairs added complete bank identifiers, independent
  profile/address countries, exhaustive mapped-or-global validation display,
  and accessible default/primary checkboxes.
- Quality review exposed cross-kind tax-primary clearing, removable final
  registered addresses, editable drafts during submission, unrelated-success
  error clearing, missing Escape handling, broad cache invalidation, and unsafe
  retention of validation `input`/`ctx`. All were repaired with focused tests.
- ApiError now accepts validation metadata only for HTTP 422, retains only
  `loc`, `msg`, and `type`, and uses a fixed safe fallback for empty messages;
  secret-value regression coverage confirms raw input/context is discarded.
- Final focused result: three Vitest files and 131 tests passed. All eleven
  locale files report 5,689 leaves in parity. ESLint, `git diff --check`, and
  `tsc -b && vite build` passed.
- Final specification review: compliant. Final code-quality review: approved
  with no findings.
- Residual risk: the existing Vite bundle-size advisory remains; generated
  `static` assets were removed after verification.

## Task 8: Customer Management Workspace

- TDD expanded the compact customer foundation into the complete list,
  filtering, pagination, details, create, edit, conflict-reload, and delete
  workflows with read/manage permission states.
- Added complete nested customer editing for profile accounts, contacts,
  addresses, tax identifiers, preferences, notes, and tags, including stable
  client keys, field-adjacent validation, fixed modal footers, and explicit
  retryable API failures.
- Client validation now mirrors backend ISO country/currency sets and Python
  3.13 Unicode 15.1 NFKC-casefold behavior. The generated source is
  byte-for-byte checked, and tag normalization matches Python display
  selection, whitespace stripping, normalized-key ordering, and the 512-byte
  normalized-key bound.
- Review repairs closed stale editor versions, explicit/background reload
  races, query-cache regression, empty later pages after delete, unbounded
  history refetching, unstable keys, silent modal failures, duplicate modal
  owners, and incomplete loading/focus semantics.
- Shared modal focus handling now provides named modal dialogs, initial focus,
  Tab containment, focus restoration, and pending-safe Escape behavior for the
  customer workspace and confirmation dialogs.
- Final focused result: six Vitest files and 97 tests passed. All eleven locale
  files report 5,781 leaves in parity. ESLint, TypeScript, Ruff, generated
  source verification, `git diff --check`, and `tsc -b && vite build` passed.
  The Unicode verifier matched 249 countries, 178 currencies, and all
  1,114,112 code points with zero mismatches.
- Final specification review: compliant. Final code-quality re-review:
  approved with no findings.
- Residual risk: the existing Vite bundle-size advisory remains; generated
  `static` assets were removed after verification.

## Task 9: End-to-End Verification And Operator Documentation

- Backend foundation verification passed all 155 selected permission, sequence,
  schema, business-profile, customer, and group tests. Ruff reported no findings
  across `backend/app` and `backend/tests`.
- Frontend verification passed five focused files and 199 tests after the local
  browser was closed; the two tests that had timed out under concurrent browser,
  backend, and Vitest load passed individually and in the repeated full run.
  All eleven locale files remained at 5,781 leaves, full ESLint passed, and the
  production build completed with only the existing bundle-size advisory.
- Chromium verification at 1440x900 and 390x844 covered empty and populated
  profile/customer views, long German customer data, create/edit forms,
  validation, repeatable contacts/addresses/tax/bank rows, read-only Viewer
  controls, and a retryable customer-list 503 response.
- Browser inspection found native `fieldset` overflow painting and hit-testing
  over the editor footer when repeatable rows were tall. Dedicated scroll
  viewports now contain the disabled fieldsets in both customer and business
  profile editors. The corrected desktop and mobile flows kept headers and
  footers stable and the save action clickable; two structural regression tests
  protect the layout owner.
- Live API verification confirmed exactly one default profile, stale aggregate
  updates returning 409, customer-number uniqueness per profile, Viewer writes
  returning 403, Operator customer creation with no issue/integration rights,
  API-key profile/customer writes returning 403, and restart persistence. After
  restart, the second profile retained its rows and allocated `CUST-00002`.
- Added `docs/order-management.md` with initial profile setup, exact default
  workflow, billing-mode scope, profile accounts, numbering, roles/groups, and
  links to later calculation, PDF-layout, standards-export, and Lexware Office
  increments without claiming those workflows are already implemented.
- Final Task 9 review: approved after correcting default-profile and per-account
  numbering language. `git diff --check` was clean.
