# Task 3 Report: Render Canonical Settings Rail And Preserve URL Aliases

## Outcome

Completed Task 3 on branch `codex/settings-information-architecture` without editing outside the owned file list.

## What changed

### `frontend/src/pages/SettingsPage.tsx`
- Switched Settings tab state from legacy ids to canonical `CanonicalSettingsTab` ids via `resolveSettingsTab(...)`.
- Preserved legacy deep links such as `?tab=queue`, `?tab=filament`, `?tab=backup`, and `?tab=email` by resolving them silently to canonical tabs and legacy default sub-tabs.
- Updated rail clicks to write canonical URL params using `canonicalTabToUrlParam(...)`.
- Replaced the hardcoded rail with `SETTINGS_NAV_ITEMS` and a local icon map.
- Kept search click-through working by preserving the temporary legacy anchor bridge, then resolving bridged targets back into canonical tabs.
- Kept pre-Task-4 compatibility by rendering the existing legacy content buckets under their new canonical parent tabs instead of moving cards.
- Preserved the SpoolBuddy device indicator by surfacing it on the `Warehouse & Material` canonical rail item.

### Locale files
- Added the seven new canonical `settings.tabs.*` labels to all owned locales.
- Backfilled additional missing `printops.nav.*` and `externalLinks.*` leaves across non-English locales so `npm.cmd run check:i18n` passes.
- Translated `printops.nav.dashboard` in German so parity no longer flags it as untranslated.

### `frontend/src/__tests__/pages/SettingsPage.test.tsx`
- Replaced the old rail rendering assertion with canonical rail coverage.
- Added legacy URL alias tests for `queue`, `filament`, `backup`, and `email`.
- Updated legacy rail-click tests to use the canonical rail labels.
- Pinned the intended Task 3 compatibility behavior: some cards still render under `Printers & Production` until Task 4 moves them.
- Updated the pipelines URL expectation to the canonical `tab=printers-production` param.

## Verification

Ran from `frontend`:

```powershell
npm.cmd run test -- SettingsPage.test.tsx settingsNavigation.test.ts --run
npm.cmd run check:i18n
```

Results:
- `vitest`: 3 files passed, 78 tests passed
- `check:i18n`: all locales in parity with `en`

## Notes

- I used the existing imported `Home` and `DollarSign` lucide icons for `Warehouse & Material` and `Orders & Calculation`, matching the task brief suggestion without adding dependencies.
- Per the Task 3 boundary, I did **not** move Settings content cards into their eventual canonical sections yet. The tests now explicitly document that temporary compatibility state so Task 4 can move them deliberately later.

---

## Task 3 Fix Follow-up: Canonical Compatibility Panes

### Outcome

Completed the Task 3 review follow-up on branch `codex/settings-information-architecture` with commit `e3904a9` (`fix: fill canonical settings compatibility panes`).

### What changed

#### `frontend/src/pages/SettingsPage.tsx`
- Re-pointed the reviewed search anchors so `card-filemanager`, `card-cost`, `card-ftpretry`, `card-prometheus`, `card-webhooks`, and `card-apibrowser` resolve to their canonical tabs.
- Extracted the reviewed compatibility cards into narrow local render helpers so they can mount under the canonical tab where search says they live.
- Filled the previously blank `Projects & Files` tab with the existing File Manager card.
- Filled the previously blank `Orders & Calculation` tab with the existing Cost Tracking card.
- Moved reviewed compatibility rendering to match canonical labels:
  - `FTP Retry` now renders under `Printers & Production`
  - `Prometheus Metrics` now renders under `Operations`
  - `Webhook Endpoints` and `API Browser` now render under `Integrations`
- Removed duplicate visible copies of those reviewed cards from their old compatibility panes instead of broadening the change into a larger Task 4 reorganization.

#### `frontend/src/__tests__/pages/SettingsPage.test.tsx`
- Added canonical tab coverage for `Projects & Files` -> File Manager and `Orders & Calculation` -> Cost Tracking.
- Added the requested search click-through coverage for `FTP Retry`, `Prometheus`, `Webhook`, and `API Browser`, asserting the active canonical tab and rendered reviewed pane.

### Verification

Ran from `frontend`:

```powershell
npm.cmd run test -- SettingsPage.test.tsx settingsNavigation.test.ts --run
npm.cmd run check:i18n
```

Results:
- `vitest`: 3 files passed, 84 tests passed
- `check:i18n`: all locales in parity with `en`

### Notes

- Only the owned Task 3 files were committed.
- This follow-up keeps the controller-approved canonical labels and updates staged compatibility rendering to match them without attempting the broader Task 4 card move.

---

## Task 3 Fix Follow-up: Canonical Pipeline URL Round-Trip

### Outcome

Completed the remaining Task 3 URL review finding on branch `codex/settings-information-architecture`.

### What changed

#### `frontend/src/pages/SettingsPage.tsx`
- Restored the `Pipelines` sub-tab from canonical `?tab=printers-production&sub=pipelines` URLs, while preserving the legacy `?tab=queue&sub=pipelines` alias behavior.
- Kept canonical writes for `Pipelines` on `?tab=printers-production&sub=pipelines`.
- Cleared stale `sub=pipelines` when settings search jumps from a canonical pipelines URL back to dispatch-side `Printers & Production` content.

#### `frontend/src/__tests__/pages/SettingsPage.test.tsx`
- Added coverage that `/settings?tab=printers-production&sub=pipelines` loads the `Pipelines` state.
- Added coverage that a search jump from a canonical pipelines URL to dispatch content clears `sub=pipelines`.
- Added low-cost regression coverage for search click-through to `File Manager` and `Cost Tracking` on their canonical tabs.

### Verification

Ran from `frontend`:

```powershell
npm.cmd run test -- SettingsPage.test.tsx settingsNavigation.test.ts --run
npm.cmd run check:i18n
```

Results:
- `vitest`: 3 files passed, 88 tests passed
- `check:i18n`: all locales in parity with `en`

---

## Task 3 Fix Follow-up: Search Alignment Review Finding

### Outcome

Completed the remaining Task 3 search alignment review finding on branch `codex/settings-information-architecture`.

### What changed

#### `frontend/src/pages/SettingsPage.tsx`
- Re-pointed the five reviewed legacy search anchors to their canonical tabs:
  - `card-archive` -> `printers-production`
  - `card-camera` -> `printers-production`
  - `card-updates` -> `operations`
  - `card-data` -> `operations`
  - `card-drying` -> `warehouse-material`
- Rendered those five cards on the canonical tabs advertised by search, using narrow local card helpers instead of broad reorganization.
- Removed the duplicate visible `Updates` compatibility copy from `General`.
- Restored the deployment-specific update CTA branches inside the extracted `Updates` card so the canonical `Operations` rendering preserves the existing Home Assistant, Docker, and Windows installer behaviors.

#### `frontend/src/__tests__/pages/SettingsPage.test.tsx`
- Added the five required search click-through regressions for `Archive Settings`, `Camera`, `Updates`, `Data Management`, and `Drying`, asserting both the active canonical tab and the expected card content.
- Updated affected settings tests to open the canonical tab before asserting moved card content.

### Verification

Ran from `frontend`:

```powershell
npm.cmd run test -- SettingsPage.test.tsx settingsNavigation.test.ts --run
npm.cmd run check:i18n
```

Results:
- `vitest`: 3 files passed, 93 tests passed
- `check:i18n`: all locales in parity with `en`
