# Order Management Foundation Intent

## Requested Outcome

Implement the approved first order-management increment from
`docs/superpowers/plans/2026-07-10-order-management-foundation.md` on the
`codex/order-management` branch. All eventual network writes target only
`ichwars/PrintOps` through `origin`.

## Scope

- Relational business profiles, number sequences, and customer master data.
- Order-management permissions and safe default-role backfill.
- Profile and customer services and APIs.
- Frontend contracts, navigation, settings, and customer workspace.
- Focused, integration, browser, and authorization verification.

## Non-Goals

- Calculation, quote, order, delivery, invoice, payment, export, PDF-layout,
  and Lexware Office implementation; those remain later approved increments.
- Repairing unrelated existing test failures.
- Any write to `maziggy/bambuddy`.

## Baseline Read Set

- `docs/superpowers/specs/2026-07-10-order-management-design.md`
- `docs/superpowers/plans/2026-07-10-order-management-foundation.md`
- Existing SQLAlchemy model and registration patterns.
- Existing permission/default-group and API-key scope patterns.
- Existing API, React Query, navigation, settings, and i18n patterns.

## Impact And Risk

This increment adds persisted business identity and customer data, shared
permissions, and navigation surfaces. Primary risks are schema registration,
authorization leakage, number allocation races, optimistic-locking mistakes,
and inconsistent frontend/backend contracts.

## Execution Readiness

- Intent lock: implement only the approved foundation increment.
- Compatibility boundary: SQLite and PostgreSQL; existing APIs remain stable.
- Security boundary: new API-key capabilities fail closed; issuer tax and bank
  data require administrator-only order-settings permissions by default.
- Review gates: every task requires implementation, specification review,
  code-quality review, and focused verification before the next task.
- Completion evidence: all plan tasks checked, focused suites green, broader
  regressions classified, browser states inspected, fork-only remote verified.
