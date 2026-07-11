# Order Management Foundation Checkpoint

## TodoCheckpointDraft

- Active: independent re-review of the completed final correction wave.
- Completed: consolidated backend, frontend, i18n, Unicode, and documentation
  corrections from both whole-branch reviews.
- Completed: Task 9, end-to-end verification and operator documentation.
- Completed: Task 8, full customer-management workspace.
- Completed: Task 7, full business-profile settings workspace.
- Completed: Task 6, frontend contracts, navigation, settings routing, and
  compact API-backed profile/customer foundations.
- Completed: Task 5, customer schemas, service, and API.
- Completed: Task 4, business-profile schemas, service, and API.
- Completed: Task 3, concurrency-safe number sequences.
- Completed: Task 2, order-management permissions and safe role backfill.
- Completed: Task 1, relational profile, sequence, and customer models.
- Completed: approved design and executable plan.
- Completed: independent backend and frontend correction re-reviews approved
  with no remaining Critical or Important findings.
- Next: commit the correction wave, verify the committed branch-wide diff,
  then verify fork remotes and integrate through an internal fork pull request
  only.

## Slice Card

- Goal: make the order-management foundation eligible for fork integration by
  resolving the consolidated final-review findings.
- Parent plan: `docs/superpowers/plans/2026-07-10-order-management-foundation.md`, Task 9.
- Files: backend data-integrity/normalization code and tests; profile/customer
  frontend code and tests; i18n/generated validation; work records.
- Boundary: the upstream repository remains fetch-only with a disabled push URL.
- Verification: focused regression suites, generated-source/Unicode parity,
  frontend static checks/build, branch-wide diff-check, and independent
  whole-branch re-review.
- Stop: all findings are independently approved and the branch is clean, or a
  correctness regression/scope conflict is found.

## ResumeStateHint

Resume on `codex/order-management`, read `final-review-fix-brief.md`, confirm the
worktree matches this correction wave, and continue at implementation or
re-review. `origin` remains the only allowed push remote; no remote write is
allowed before the re-review is approved.

## DriftCheckDraft

- Scope: aligned with the approved foundation increment.
- Compatibility: existing model initialization remains green; Task 1 adds only
  the approved relational owners and wiring.
- New owners: only the model modules explicitly named by the plan.
- Evidence: Task 1 passed specification review, code-quality review, six
  focused behavior tests, Ruff, and PostgreSQL DDL compilation.
- Evidence: Task 2 passed specification review, code-quality review, 91
  permission/group/auth tests, and Ruff.
- Evidence: Task 3 passed specification review, code-quality review, 29
  sequence behavior tests, and Ruff.
- Evidence: Task 4 passed specification review, code-quality review, 65
  schema/profile/permission tests, and Ruff.
- Evidence: Task 5 passed specification review, code-quality review, 98
  foundation/profile/customer tests, and Ruff.
- Evidence: Task 6 passed specification review and code-quality re-review,
  154 focused frontend tests, all 11 locale parity checks, ESLint, diff-check,
  and the production build.
- Evidence: Task 7 passed specification review and code-quality re-review,
  131 focused frontend tests, all 11 locale parity checks, ESLint, diff-check,
  and the production build.
- Evidence: Task 8 passed specification review and repeated code-quality
  re-review, 97 focused frontend tests, all 11 locale parity checks, ESLint,
  TypeScript, Ruff, byte-for-byte generated-source validation, full Unicode
  parity across 1,114,112 code points, diff-check, and the production build.
- Evidence: Task 9 passed 155 backend tests, 199 frontend tests, Ruff, all 11
  locale parity checks, full ESLint, and the production build. Chromium checks
  covered 1440x900 and 390x844 empty, populated, editor, validation, read-only,
  API-failure, and repeatable-row states. Live API checks confirmed default,
  optimistic-lock, numbering, role, API-key, and restart invariants. The
  browser-discovered fieldset/footer regression was repaired, regression-tested,
  and independently approved with the operator documentation.
- Final-review finding: SQLite profile deletion can race customer creation and
  leave orphan accounts without production foreign-key enforcement.
- Final-review finding: normalized manual customer-number uniqueness and
  post-normalization length validation are incomplete.
- Final-review finding: normalization parity is runtime-dependent on Python 3.11.
- Final-review finding: profile deactivation can strand referenced customers.
- Final-review finding: the profile editor is not yet internationally complete,
  omits supported nested fields and modal focus ownership, retains stale option
  caches, and exposes raw English validation/status text in German.
- Final-review finding: branch-wide diff-check detects a blank line at EOF in
  `10-intent.md`.
- Correction evidence: 117 backend tests and 85 frontend tests passed. Ruff,
  ESLint, all 11 locale files at 5,829 leaves, generated-source verification,
  the production build, and worktree `git diff --check` passed. The pinned
  Unicode 15.1 owner matched frontend/backend normalization for all 1,114,112
  code points with zero mismatches.
- Correction evidence: SQLite profile deletion/customer creation and manual
  normalized-number races pass without globally enabling foreign keys. Profile
  deactivation rejects referenced accounts; both tax-kind schemas reject
  post-normalization overflow.
- Correction evidence: uniqueness checks normalize stored visible customer
  numbers again, so legacy interpreter-derived `number_key` values cannot hide
  Unicode 15.1 collisions. Business-profile tax kinds/values use the same pinned
  owner as customers.
- Correction evidence: the profile UI exposes full ISO country/currency values,
  configurable locale/timezone, complete nested address/tax fields, focus
  ownership, truthful localized errors/statuses, stable address invariants, and
  exact profile-options invalidation. Tax-kind and bank-currency changes retain
  one primary/default owner, and Escape has one modal-local owner.
- Final re-review evidence: SQLite write-lock ordering is covered under WAL,
  unknown profile integrity failures are re-raised, the automatic collision
  scan is linear, and Python 3.13 uses its Unicode 15.1 stdlib while 3.10-3.12
  use the pinned backport. Frontend toggle payloads omit response IDs, pending
  focus remains trapped, stale profile selection is cleared, `not_found` is
  localized, and normalized tax-kind overflow is rejected client-side.
- Residual verification gap: the production build passed, but a Docker image
  build could not run because the local Docker engine was unavailable. Provider
  tests and marker evaluation cover the Python 3.13 dependency decision.
- Decision: correction implementation verified and independently approved;
  fork-only integration is the remaining step.
