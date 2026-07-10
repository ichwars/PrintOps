# Order Management Foundation Checkpoint

## TodoCheckpointDraft

- Active: Task 4, business-profile schemas, service, and API.
- Pending: Tasks 5 through 9 from the implementation plan.
- Completed: Task 3, concurrency-safe number sequences.
- Completed: Task 2, order-management permissions and safe role backfill.
- Completed: Task 1, relational profile, sequence, and customer models.
- Completed: approved design and executable plan.
- Next: dispatch the Task 4 TDD implementer, then run specification and
  code-quality reviews.

## Slice Card

- Goal: expose secure, versioned business-profile configuration through
  schemas, service invariants, and API routes.
- Parent plan: `docs/superpowers/plans/2026-07-10-order-management-foundation.md`, Task 4.
- Files: business-profile schemas/service/routes, main router registration,
  and focused integration tests.
- Boundary: issuer profiles only; no customer API, calculation logic,
  accounting adapter, or frontend UI.
- Verification: focused profile API/permission tests plus Ruff.
- Stop: focused tests and both review gates pass, or a plan conflict is found.

## ResumeStateHint

Resume on `codex/order-management`, confirm a clean or checkpoint-consistent
worktree, read Task 4 and the latest review evidence, then continue at the next
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
- Decision: continue.
