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
