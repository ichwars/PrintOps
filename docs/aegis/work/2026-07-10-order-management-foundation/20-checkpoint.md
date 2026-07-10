# Order Management Foundation Checkpoint

## TodoCheckpointDraft

- Active: Task 3, concurrency-safe number sequences.
- Pending: Tasks 4 through 9 from the implementation plan.
- Completed: Task 2, order-management permissions and safe role backfill.
- Completed: Task 1, relational profile, sequence, and customer models.
- Completed: approved design and executable plan.
- Next: dispatch the Task 3 TDD implementer, then run specification and
  code-quality reviews.

## Slice Card

- Goal: allocate formatted per-profile numbers without duplicates under
  concurrent writers.
- Parent plan: `docs/superpowers/plans/2026-07-10-order-management-foundation.md`, Task 3.
- Files: number-sequence service, domain exceptions, and focused unit tests.
- Boundary: allocation service only; no customer/profile API, document
  reservation semantics, or frontend code.
- Verification: focused sequence tests plus Ruff.
- Stop: focused tests and both review gates pass, or a plan conflict is found.

## ResumeStateHint

Resume on `codex/order-management`, confirm a clean or checkpoint-consistent
worktree, read Task 3 and the latest review evidence, then continue at the next
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
- Decision: continue.
