# FTP Retry Inline Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Arrange the three FTP retry select controls in one balanced responsive row while preserving the existing behavior and mobile usability.

**Architecture:** Keep the existing `ftpRetryCard` and setting handlers in `SettingsPage`. Replace only the vertical field container with a responsive Tailwind grid and make each select wrapper fill its grid cell; the timeout helper text remains inside the third cell.

**Tech Stack:** React 19, TypeScript, Tailwind CSS, Testing Library, Vitest, Vite, Playwright browser QA.

## Global Constraints

- Use three equal-width columns from the medium breakpoint upward.
- Keep one stacked column on narrow mobile viewports.
- Keep the weak-WLAN helper text directly below the connection-timeout select.
- Do not change setting keys, values, options, handlers, translations, persistence, or switch behavior.
- Preserve the existing dark surfaces, borders, radii, typography, focus color, and control height.
- Do not modify the printer, dryer, camera, default-printer, or virtual-printer layouts.
- Do not overwrite or stage `docs/session-handoff-2026-07-16.md`.

---

### Task 1: Add the Responsive FTP Retry Field Grid

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx:3263-3322`
- Modify: `frontend/src/__tests__/pages/SettingsPage.test.tsx`
- Test: `frontend/src/__tests__/pages/SettingsPage.test.tsx`

**Interfaces:**
- Consumes: Existing `localSettings.ftp_retry_count`, `localSettings.ftp_retry_delay`, `localSettings.ftp_timeout`, and `updateSetting`.
- Produces: `data-testid="ftp-retry-fields-grid"` containing exactly three full-width select wrappers.

- [ ] **Step 1: Add the failing layout assertion**

Extend the existing test named `composes device settings in two desktop columns before the full-width virtual printers area` after the FTP Retry assertion:

```tsx
const ftpRetryGrid = within(left).getByTestId('ftp-retry-fields-grid');
const ftpRetrySelects = within(ftpRetryGrid).getAllByRole('combobox');

expect(ftpRetryGrid).toHaveClass('grid-cols-1', 'md:grid-cols-3');
expect(ftpRetrySelects).toHaveLength(3);
for (const select of ftpRetrySelects) {
  expect(select.parentElement).toHaveClass('w-full');
}
expect(within(ftpRetryGrid).getByText('Increase for printers with weak WiFi')).toBeInTheDocument();
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
cd frontend
npx vitest run src/__tests__/pages/SettingsPage.test.tsx -t "composes device settings"
```

Expected: FAIL because `ftp-retry-fields-grid` does not exist.

- [ ] **Step 3: Replace the vertical FTP field stack with the responsive grid**

In `frontend/src/pages/SettingsPage.tsx`, replace:

```tsx
<div className="space-y-3 pt-2 border-t border-bambu-dark-tertiary">
```

with:

```tsx
<div
  data-testid="ftp-retry-fields-grid"
  className="grid grid-cols-1 gap-3 border-t border-bambu-dark-tertiary pt-3 md:grid-cols-3 md:items-start"
>
```

For each of the three select wrappers, replace:

```tsx
<div className="relative w-44">
```

with:

```tsx
<div className="relative w-full">
```

Keep the third field structured as:

```tsx
<div>
  <label className="mb-1 block text-sm text-bambu-gray">
    {t('settings.connectionTimeout')}
  </label>
  <div className="relative w-full">
    <select
      value={localSettings.ftp_timeout ?? 30}
      onChange={(e) => updateSetting('ftp_timeout', parseInt(e.target.value))}
      className="w-full appearance-none cursor-pointer rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 py-2 pr-10 text-white focus:border-bambu-green focus:outline-none"
    >
      {[10, 15, 20, 30, 45, 60, 90, 120, 180, 300].map(n => (
        <option key={n} value={n}>{t('settings.nSeconds', { count: n })}</option>
      ))}
    </select>
    <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-bambu-gray" />
  </div>
  <p className="mt-1 text-xs text-bambu-gray">
    {t('settings.increaseForWeakWifi')}
  </p>
</div>
```

Do not change any option arrays or `updateSetting` calls.

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```bash
cd frontend
npx vitest run src/__tests__/pages/SettingsPage.test.tsx -t "composes device settings"
```

Expected: PASS.

- [ ] **Step 5: Run targeted lint and SettingsPage tests**

Run:

```bash
cd frontend
npx eslint src/pages/SettingsPage.tsx src/__tests__/pages/SettingsPage.test.tsx
npx vitest run src/__tests__/pages/SettingsPage.test.tsx
```

Expected: ESLint exit 0 and all SettingsPage tests PASS.

- [ ] **Step 6: Commit the source and test change**

```bash
git add frontend/src/pages/SettingsPage.tsx frontend/src/__tests__/pages/SettingsPage.test.tsx
git commit -m "fix(settings): align FTP retry fields"
```

---

### Task 2: Build and Browser-Verify the Responsive Layout

**Files:**
- Modify through build: `static/index.html`
- Modify through build: `static/assets/index-*.css`
- Modify through build: `static/assets/index-*.js`
- Verify: `frontend/src/pages/SettingsPage.tsx`

**Interfaces:**
- Consumes: The responsive grid from Task 1.
- Produces: A current production bundle and visual evidence at desktop and mobile widths.

- [ ] **Step 1: Run the complete frontend verification**

Run:

```bash
cd frontend
npm run test:run
npm run build
```

Expected:

- All Vitest tests PASS.
- All locale leaf counts remain in parity.
- TypeScript and Vite build exit 0.
- Vite writes new hashed assets to `static/`.

- [ ] **Step 2: Inspect the generated output**

Run:

```bash
git status --short
git diff --check
git diff -- static/index.html
```

Expected: Only the existing untracked session handoff plus the new hashed frontend bundle changes are present.

- [ ] **Step 3: Verify the desktop layout in a real browser**

Open:

```text
http://127.0.0.1:8000/settings?tab=printers-production
```

At a viewport of at least `1280 × 800`, verify:

- The three labels and selects form one row.
- All three grid cells have equal widths.
- All select controls fill their cells.
- Select tops align.
- The weak-WLAN helper stays below the third select.
- No overlap, clipping, excessive empty gap, or horizontal overflow appears.

Exercise one select by opening it and confirming its options are unchanged.

- [ ] **Step 4: Verify the mobile fallback**

At `390 × 844`, verify:

- The three fields stack in their original logical order.
- Each select fills the card width.
- Labels and helper text remain readable.
- `document.documentElement.scrollWidth === window.innerWidth`.

- [ ] **Step 5: Compare against the approved reference**

Inspect:

- `C:/Users/droth/AppData/Local/Temp/codex-clipboard-306a61e9-f187-4f6e-a147-6d496192de84.png`
- Latest desktop implementation screenshot
- Latest mobile implementation screenshot

Confirm the marked vertical field group is now a clean horizontal row on desktop without changing the surrounding card hierarchy.

- [ ] **Step 6: Commit the generated bundle**

Stage only the build output:

```bash
git add static/index.html static/assets
git commit -m "build(frontend): refresh FTP retry layout bundle"
```
