# Order Management Foundation Checkpoint

## TodoCheckpointDraft

- Active: Task 8, full customer-management workspace.
- Pending: Task 9 from the implementation plan.
- Completed: Task 7, full business-profile settings workspace.
- Completed: Task 6, frontend contracts, navigation, settings routing, and
  compact API-backed profile/customer foundations.
- Completed: Task 5, customer schemas, service, and API.
- Completed: Task 4, business-profile schemas, service, and API.
- Completed: Task 3, concurrency-safe number sequences.
- Completed: Task 2, order-management permissions and safe role backfill.
- Completed: Task 1, relational profile, sequence, and customer models.
- Completed: approved design and executable plan.
- Next: dispatch the Task 8 TDD implementer, then run specification and
  code-quality reviews.

## Slice Card

- Goal: expand the compact customer foundation into the complete
  permission-aware customer list, editor, and details workflow.
- Parent plan: `docs/superpowers/plans/2026-07-10-order-management-foundation.md`, Task 8.
- Files: customer page/editor/details components, route wiring, locale copy,
  and focused workflow tests.
- Boundary: customer master data only; commercial documents remain outside
  this foundation increment.
- Verification: focused Vitest, i18n, lint, and production build.
- Stop: focused tests and both review gates pass, or a plan conflict is found.

## ResumeStateHint

Resume on `codex/order-management`, confirm a clean or checkpoint-consistent
worktree, read Task 8 and the latest review evidence, then continue at the next
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
- Evidence: Task 6 passed specification review and code-quality re-review,
  154 focused frontend tests, all 11 locale parity checks, ESLint, diff-check,
  and the production build.
- Evidence: Task 7 passed specification review and code-quality re-review,
  131 focused frontend tests, all 11 locale parity checks, ESLint, diff-check,
  and the production build.
- Decision: continue.
