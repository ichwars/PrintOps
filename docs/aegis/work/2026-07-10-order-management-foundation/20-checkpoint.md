# Order Management Foundation Checkpoint

## TodoCheckpointDraft

- Active: Task 9, end-to-end verification and operator documentation.
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
- Next: run the complete foundation verification, browser and authorization
  checks, add operator documentation, and prepare fork-only integration.

## Slice Card

- Goal: verify and document the complete order-management foundation increment.
- Parent plan: `docs/superpowers/plans/2026-07-10-order-management-foundation.md`, Task 9.
- Files: approved design status, operator documentation, and regression fixes
  only when verification proves they are required.
- Boundary: business profiles and customer master data only; calculation and
  commercial documents remain later increments.
- Verification: backend and frontend suites, browser states, authorization and
  persistence invariants, diff review, and fork-only integration checks.
- Stop: all verification and review gates pass, or an unresolved regression is
  found.

## ResumeStateHint

Resume on `codex/order-management`, confirm a clean or checkpoint-consistent
worktree, read Task 9 and the latest review evidence, then continue at the next
open verification or documentation step. `origin` is the only allowed push
remote.

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
- Decision: continue.
