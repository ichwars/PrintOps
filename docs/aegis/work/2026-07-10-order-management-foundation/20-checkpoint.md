# Order Management Foundation Checkpoint

## TodoCheckpointDraft

- Active: Task 2, order-management permissions and safe role backfill.
- Pending: Tasks 3 through 9 from the implementation plan.
- Completed: Task 1, relational profile, sequence, and customer models.
- Completed: approved design and executable plan.
- Next: dispatch the Task 2 TDD implementer, then run specification and
  code-quality reviews.

## Slice Card

- Goal: add the complete order-management permission contract and safely
  upgrade default groups.
- Parent plan: `docs/superpowers/plans/2026-07-10-order-management-foundation.md`, Task 2.
- Files: permission declarations, default-group backfill, and focused tests.
- Boundary: authorization contract only; no API-key scopes, routes, services,
  model changes, or frontend code.
- Verification: focused permission and group-backfill tests plus Ruff.
- Stop: focused tests and both review gates pass, or a plan conflict is found.

## ResumeStateHint

Resume on `codex/order-management`, confirm a clean or checkpoint-consistent
worktree, read Task 2 and the latest review evidence, then continue at the next
open review or implementation step. `origin` is the only allowed push remote.

## DriftCheckDraft

- Scope: aligned with the approved foundation increment.
- Compatibility: existing model initialization remains green; Task 1 adds only
  the approved relational owners and wiring.
- New owners: only the model modules explicitly named by the plan.
- Evidence: Task 1 passed specification review, code-quality review, six
  focused behavior tests, Ruff, and PostgreSQL DDL compilation.
- Decision: continue.
