# Final Review Fix Brief

## Goal

Resolve every confirmed finding from the final whole-branch review before the
order-management foundation is integrated into fork `main`.

## Backend Findings

1. Prevent SQLite races between customer creation and business-profile
   lifecycle changes from leaving orphaned customer accounts. A global
   foreign-key PRAGMA was evaluated and rejected because it changes legacy
   migration and fixture behavior outside this increment. The durable owner is
   instead the profile's customer-number sequence row: every involved SQLite
   write path must acquire that write lock before its first read. PostgreSQL
   continues to use row locks and database foreign keys.
2. Enforce per-profile uniqueness for manually supplied customer numbers by the
   normalized `number_key` on create and update, including case/Unicode variants
   and concurrent requests.
3. Revalidate normalized `kind` values after normalization so inputs that expand
   beyond the database column limit return validation errors instead of causing
   PostgreSQL persistence failures.
4. Make frontend/backend normalization parity valid for every supported Python
   version, including Python 3.11. Use one pinned/generated normalization owner
   rather than runtime-dependent Unicode behavior, and keep exhaustive parity
   verification meaningful.
5. Prevent deactivation of any business profile referenced by a customer
   account, matching the existing deletion invariant and avoiding uneditable
   historical customer accounts.

## Frontend Findings

1. Replace the profile editor's three-country, three-currency, two-locale, and
   two-timezone limitations with system-supported international input/options.
   Cover values outside the existing subset such as FR, JPY, fr-FR, and
   Asia/Tokyo.
2. Invalidate `business-profile-options` after every successful profile
   mutation as well as the full profile lists.
3. Expose every address and tax-identifier field supported by the profile API:
   address kind, label, additional line, street 2, region, and tax country plus
   validity dates. New rows must not hard-code one address kind.
4. Give the profile editor the same modal focus lifecycle as the customer
   editor: initial focus, focus trap, Escape handling, and focus restoration.
5. Localize client validation, known API conflicts/domain errors, and tax
   validation-status labels. German must not display raw English validation or
   conflict strings; all locale files must retain parity.

## Documentation Finding

Remove the blank line at EOF in `10-intent.md`, make
`git diff --check origin/main...HEAD` pass, and update checkpoint/evidence claims
to record the final-review correction wave and fresh verification rather than
claiming a clean pre-fix branch.

## Boundaries

- Preserve SQLite and PostgreSQL support.
- Preserve existing public API shapes unless a new stable error code is needed
  for localization; update all consumers and tests together if so.
- Keep order-management API-key capabilities fail-closed.
- Do not implement later increments such as quotes, invoices, exports, PDF
  rendering, or Lexware calls.
- Do not push, merge, or write to any remote.
- Do not revert unrelated user changes. Other agents may be active.

## Required Verification

- Focused backend tests for every invariant and race plus Ruff.
- Focused frontend component/page tests for profile and customer behavior.
- Generated-source check and exhaustive Unicode parity on a supported runtime,
  including Python 3.11 compatibility.
- Frontend locale parity, ESLint, TypeScript/build, and branch-wide diff-check.
- Report exact commands, counts, changed files, and any remaining concern.
