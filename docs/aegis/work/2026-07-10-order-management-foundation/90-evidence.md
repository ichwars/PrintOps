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
