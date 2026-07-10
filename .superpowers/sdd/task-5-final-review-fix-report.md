# Task 5 Final Review Fix Report

Status: verified, ready to merge

Files changed:
- `frontend/src/lib/settingsNavigation.ts`
- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/__tests__/lib/settingsNavigation.test.ts`
- `frontend/src/__tests__/pages/SettingsPage.test.tsx`

Root cause:
- Legacy `?tab=` aliases were only normalized to canonical top-level tabs. Initial page load never reused the existing card-scroll path, so aliases did not land on their documented default sections.
- The `users` legacy landing area relied on anchors that only existed when authentication was enabled, which made that alias unstable.
- `bed_cooled_threshold` was still rendered with notification provider settings even though the spec moved it into the production completion-rules area.

Fixes:
- Added canonical legacy helpers for default sub-tabs and default landing anchors in `settingsNavigation.ts`.
- Added initial-load legacy anchor scrolling in `SettingsPage.tsx`, guarded so it runs once after the relevant content is rendered.
- Moved the `users` landing anchor to a stable wrapper that exists whether authentication is enabled or disabled.
- Kept failure-detection scrolling pointed at the real rendered anchor (`card-fd-ml`).
- Moved `bed_cooled_threshold` into a new Printers & Production completion-rules card and removed it from Integrations / Notifications.
- Added regression coverage for alias-to-anchor mapping, legacy initial-load scroll landings, and the bed-cooled-threshold placement.

Verification:
- `npm.cmd run test -- SettingsPage.test.tsx settingsNavigation.test.ts --run` ✅
- `npm.cmd run check:i18n` ✅
- `npm.cmd run build` ✅
  - Build completed successfully.
  - Vite emitted the existing large-chunk warning for the main bundle.

Commit:
- Message: `fix: preserve settings legacy landing sections`
- Final short hash is recorded in current `HEAD` and the task handoff, since amending this report changes the commit hash itself.
