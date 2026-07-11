# Order Management Foundation Reflection

## Outcome

The approved foundation increment is implemented and independently approved.
It provides business profiles, customer master data, per-profile number
sequences, permissions, APIs, settings, navigation, and the customer workspace.
Later calculation, quote, order, document, export, PDF-layout, and Lexware
Office increments remain explicit non-goals of this branch.

## Key Judgments

- SQLite profile lifecycle and customer writes share the customer-sequence row
  as their serialization owner. The lock is acquired before the first read.
- A global SQLite foreign-key PRAGMA was rejected because it changed unrelated
  legacy migration and fixture behavior.
- Persisted case-insensitive keys use one pinned Unicode 15.1 contract across
  backend, frontend, generators, Python 3.10-3.13, and legacy visible values.
- API integrity failures are converted to domain conflicts only when their
  database metadata proves the classification; unknown failures remain visible
  to operators instead of being masked as duplicates.
- Frontend active-profile selection is derived from current server options, so
  removed or deactivated profiles cannot remain an editing owner.

## Evidence

- 117 focused backend tests passed, including WAL lock-order regressions.
- 85 focused frontend tests passed, including payload, focus, profile-refetch,
  localization, and normalized-length regressions.
- Ruff, ESLint, locale parity, generated-source verification, TypeScript, the
  production build, and `git diff --check` passed.
- All 1,114,112 Unicode code points matched between backend and frontend with
  zero mismatches; 249 countries and 178 currencies matched.
- Independent backend and frontend re-reviews reported no remaining Critical
  or Important findings.

## Residual Risk

The local Docker client had no running engine, so the Python 3.13 image itself
was not built. The compatibility decision is instead covered by provider unit
tests, dependency-marker evaluation, static Docker-version inspection, and the
shared generator/backend owner. The existing frontend bundle-size advisory is
unchanged.

## Next Boundary

Continue with the approved later order-management increments. PDF layouts stay
attached to the canonical document increment, where document type, business
profile, language, EN 16931 exports, UBL/CII, CSV, and Lexware Office ownership
can be implemented without inventing temporary document contracts here.
