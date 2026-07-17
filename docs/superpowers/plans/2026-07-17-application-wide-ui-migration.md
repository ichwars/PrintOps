# Application-wide UI Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace direct browser form controls across the remaining PrintOps frontend with owned, accessible UI components while preserving every domain value and side effect.

**Architecture:** Extend the existing `components/ui` foundation with focused wrappers for individual radio, time, file, color, slider, and legacy date contracts. Use a TypeScript-AST migration audit and a temporary AST codemod for mechanical tag/import changes, then review and test specialized consumers by product area.

**Tech Stack:** React 19.2, TypeScript 5.9, Tailwind CSS 4.1, i18next, Vitest 4.1, Testing Library, Vite 8.

## Global Constraints

- Work directly on `codex/device-management-layout`; do not create another worktree.
- Do not add an external UI library.
- Do not change API payloads, validation rules, permissions, storage timing, or mutation triggers.
- Keep `YYYY-MM-DD` for date-only values and `HH:MM` for time-only values.
- Keep native semantics only inside `frontend/src/components/ui/`.
- Preserve current responsive layouts; desktop controls use 38 px and touch targets at least 44 px.
- Keep checkbox and radio glyphs vertically centered.
- Follow red-green TDD for foundation components and the migration audit.

---

### Task 1: Add the application-wide source audit

**Files:**
- Create: `frontend/src/__tests__/components/ui/ApplicationUiMigration.test.ts`

**Interfaces:**
- Produces `directBrowserControls(file, source): string[]`, an AST scan over application TSX files.

- [ ] Write a failing test that recursively scans `src/pages` and `src/components`, excluding `components/ui` and tests, and reports direct `select`, `textarea`, and visible `input` tags with file and line.
- [ ] Also reject specialized `TextField` types (`number`, `checkbox`, `radio`, `date`, `datetime-local`, `time`, `file`, `color`, `range`).
- [ ] Run `npx.cmd vitest run src/__tests__/components/ui/ApplicationUiMigration.test.ts`; expect current native-control locations in the failure.
- [ ] Commit the red audit together with Task 2 only after the new UI components make its focused component assertions green; keep the application-wide assertion failing until migrations complete.

### Task 2: Add missing owned control wrappers

**Files:**
- Modify: `frontend/src/components/ui/FormField.tsx`
- Modify: `frontend/src/components/ui/TextField.tsx`
- Modify: `frontend/src/components/ui/TextArea.tsx`
- Modify: `frontend/src/components/ui/Checkbox.tsx`
- Modify: `frontend/src/components/ui/LegacySelect.tsx`
- Create: `frontend/src/components/ui/Radio.tsx`
- Create: `frontend/src/components/ui/TimeField.tsx`
- Create: `frontend/src/components/ui/LegacyDatePicker.tsx`
- Create: `frontend/src/components/ui/FileInput.tsx`
- Create: `frontend/src/components/ui/ColorInput.tsx`
- Create: `frontend/src/components/ui/Slider.tsx`
- Modify: `frontend/src/components/ui/index.ts`
- Create: `frontend/src/__tests__/components/ui/SpecializedControls.test.tsx`

**Interfaces:**
- `Radio` consumes native radio props except `type`, renders a visually hidden native radio and centered owned indicator, and forwards the input ref.
- `TimeField` accepts controlled `value`, native-style `onChange` or `onValueChange`, and renders a text input with `inputMode="numeric"`, `HH:MM` placeholder and pattern.
- `LegacyDatePicker` accepts `value`, `min`, `max`, disabled/required state and native-style `onChange`, derives locale from i18next, and delegates to `DatePicker`.
- `FileInput`, `ColorInput`, and `Slider` forward native input refs/events while owning the visual classes and fixed input type.

- [ ] Add failing component tests for events, refs, focus, disabled states, centered radio glyph, locale-stable date values, `HH:MM`, slider styling, file selection and color changes.
- [ ] Run the focused tests and confirm missing exports fail.
- [ ] Implement the components and merge external/internal ARIA descriptions in TextField/TextArea.
- [ ] Make FormField return its control without an extra wrapper when no field metadata or wrapper class exists.
- [ ] Run focused UI tests and ESLint; expect zero failures.
- [ ] Commit as `feat(ui): add remaining form controls`.

### Task 3: Migrate selects and textareas

**Files:**
- Modify every application TSX file reported by the audit for direct `select` or `textarea`.
- Test: existing page/component tests plus `ApplicationUiMigration.test.ts`.

- [ ] Replace each `select` with `LegacySelect`, preserving options, disabled values, value coercion, `aria-label`, callback bodies and class names.
- [ ] Replace each textarea with `TextArea`, preserving value, rows, maxlength, callbacks and layout classes.
- [ ] Merge imports from the nearest `components/ui` barrel.
- [ ] Run TypeScript build to reveal incompatible native-only props; adapt the compatibility component only for generic behavior, otherwise update the consumer explicitly.
- [ ] Run affected tests and the audit; expect no direct selects or textareas.
- [ ] Commit by product families: orders/projects, inventory/archives, printing/profiles, remaining pages.

### Task 4: Migrate standard text inputs

**Files:**
- Modify every application TSX file reported for text, search, password, email, tel and URL inputs.

- [ ] Replace direct standard inputs with `TextField`; preserve refs, autocomplete, inputMode, patterns, placeholders, ARIA, events and classes.
- [ ] Do not convert dynamic numeric inputs to TextField; use NumberField.
- [ ] Run build and focused tests after each product family.
- [ ] Run the audit; expect no direct standard input tags.
- [ ] Commit by product families with `refactor(<area>): use shared text controls` messages.

### Task 5: Migrate selection, date and time controls

**Files:**
- Modify all reported checkbox/radio/date/datetime/time consumers, including `PrintModal/ScheduleOptions.tsx`.

- [ ] Replace checkboxes with `Checkbox`; convert the Library Trash imperative indeterminate ref to the `indeterminate` prop.
- [ ] Replace individual radios with `Radio`; retain group names and checked callbacks.
- [ ] Replace date inputs with `LegacyDatePicker` or typed `DatePicker`.
- [ ] Replace the hidden native datetime picker in ScheduleOptions with `DateTimePicker`, retaining the scheduled local value and validation.
- [ ] Replace native time fields with `TimeField`.
- [ ] Run focused tests, audit, build and lint.
- [ ] Commit as product-family migrations.

### Task 6: Encapsulate file, color and range inputs

**Files:**
- Modify every reported file, color and range consumer.

- [ ] Replace file inputs with `FileInput`, preserving refs, accepts, multiple selection and hidden/drop-zone behavior.
- [ ] Replace color inputs with `ColorInput`, preserving exact hex transformations.
- [ ] Replace range inputs with `Slider`, preserving numeric conversion, bounds, steps and media seek behavior.
- [ ] Run focused printing, spool, catalog, viewer and upload tests.
- [ ] Run the audit; expect no direct visible native inputs outside `components/ui`.
- [ ] Commit by product family.

### Task 7: Full verification and browser QA

**Files:**
- Generated: `static/index.html`, `static/assets/index-*.css`, `static/assets/index-*.js`.

- [ ] Run `npm.cmd run test:run`; require all tests and i18n parity to pass.
- [ ] Run `npm.cmd run lint`; require exit 0.
- [ ] Run `npm.cmd run build`; require TypeScript and Vite success.
- [ ] Run source searches to confirm only UI components contain native form tags.
- [ ] Browser-test Settings, printers, inventory, archives, projects, orders/calculation, profiles and SpoolBuddy at desktop and mobile widths in dark and light themes.
- [ ] Exercise select, checkbox, radio, date, time, file trigger, color and slider interactions without saving unrelated data; inspect console errors and horizontal overflow.
- [ ] Inspect `git diff --check`, generated asset references and working-tree status.
- [ ] Commit generated assets as `build(frontend): refresh application controls bundle`.

