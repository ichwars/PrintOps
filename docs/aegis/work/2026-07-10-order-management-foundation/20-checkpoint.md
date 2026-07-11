# Order Management Foundation Checkpoint

## TodoCheckpointDraft

- Active: final whole-branch review and fork-only integration.
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
- Next: review the complete branch, verify fork remotes, push the feature branch
  to `origin`, and merge an internal fork pull request into fork `main` only.

## Slice Card

- Goal: integrate the reviewed order-management foundation into fork `main`.
- Parent plan: `docs/superpowers/plans/2026-07-10-order-management-foundation.md`, Task 9.
- Files: complete branch diff and GitHub integration metadata only.
- Boundary: the upstream repository remains fetch-only with a disabled push URL.
- Verification: whole-branch review, clean worktree, fork remotes, required fork
  checks, and post-merge fork `main` identity.
- Stop: fork `main` contains the reviewed commits and required checks pass, or a
  merge/check regression is found.

## ResumeStateHint

Resume on `codex/order-management`, confirm a clean or checkpoint-consistent
worktree, read the final Task 9 evidence, then continue at whole-branch review or
fork-only integration. `origin` is the only allowed push remote.

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
- Decision: continue.
