# Order Management Foundation Checkpoint

## TodoCheckpointDraft

- Active: Task 6, frontend contracts, navigation, and settings routing.
- Pending: Tasks 7 through 9 from the implementation plan.
- Completed: Task 5, customer schemas, service, and API.
- Completed: Task 4, business-profile schemas, service, and API.
- Completed: Task 3, concurrency-safe number sequences.
- Completed: Task 2, order-management permissions and safe role backfill.
- Completed: Task 1, relational profile, sequence, and customer models.
- Completed: approved design and executable plan.
- Next: dispatch the Task 6 TDD implementer, then run specification and
  code-quality reviews.

## Slice Card

- Goal: add typed frontend contracts, permission-aware navigation, dedicated
  customer routing, and canonical order-settings subtabs.
- Parent plan: `docs/superpowers/plans/2026-07-10-order-management-foundation.md`, Task 6.
- Files: API client types/methods, app routes, navigation, settings routing,
  locale parity, and focused frontend tests.
- Boundary: contracts and routing only; no profile/customer editors yet.
- Verification: focused Vitest, i18n, lint, and production build.
- Stop: focused tests and both review gates pass, or a plan conflict is found.

## ResumeStateHint

Resume on `codex/order-management`, confirm a clean or checkpoint-consistent
worktree, read Task 6 and the latest review evidence, then continue at the next
open review or implementation step. `origin` is the only allowed push remote.

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
- Decision: continue.
