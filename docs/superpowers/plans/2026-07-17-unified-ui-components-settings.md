# Unified UI Components and Settings Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a typed PrintOps UI component foundation and migrate the complete settings experience to it without changing settings data, API contracts, permissions, translations, or save timing.

**Architecture:** Reusable controlled components live in `frontend/src/components/ui/` and expose value-oriented callbacks while keeping business logic in consumers. Native semantics remain inside simple controls; Select and Calendar use a shared portal-based FloatingLayer backed by the already-installed Floating UI. Existing `Button` and `Toggle` import paths become compatibility re-exports until later application areas migrate.

**Tech Stack:** React 19.2, TypeScript 5.9 strict mode, Tailwind CSS 4.1, `@floating-ui/dom` 1.7.5, Lucide React, Vitest 4.1, Testing Library, user-event, Vite 8.

## Global Constraints

- Do not add another UI component library.
- Keep the existing PrintOps color, theme, radius, and state language; ForgeDesk is behavior and architecture reference only.
- Desktop controls are 38 px high; touch-capable or small-screen controls expose at least 44 px targets.
- Checkbox SVGs are vertically centered inside the box, and the box is vertically centered against its label.
- Keep native browser semantics inside TextField, TextArea, Checkbox, Switch, and RadioGroup.
- Select and Calendar are custom rendered and fully keyboard accessible.
- Keep date-only values as `YYYY-MM-DD` without timezone conversion; keep time values as `HH:MM`.
- Preserve settings values, API payloads, permissions, translation keys, mutation triggers, and save timing.
- File, color, and range inputs are outside this phase and remain native.
- Do not implement JavaScript-driven artificial scrollbars.
- Migrate only SettingsPage and the settings components/dialogs reachable from it; other application areas are later phases.
- Follow TDD: failing focused test, minimal implementation, passing focused test, then commit.

---

## File Map

### New UI foundation

- `frontend/src/components/ui/FormField.tsx` — label, helper, error, required marker, and ARIA linkage.
- `frontend/src/components/ui/TextField.tsx` — controlled native input wrapper.
- `frontend/src/components/ui/TextArea.tsx` — controlled native textarea wrapper.
- `frontend/src/components/ui/Checkbox.tsx` — native checkbox semantics with centered custom SVG.
- `frontend/src/components/ui/Switch.tsx` — controlled semantic switch.
- `frontend/src/components/ui/RadioGroup.tsx` — controlled native radio group.
- `frontend/src/components/ui/Button.tsx` — canonical Button implementation.
- `frontend/src/components/ui/IconButton.tsx` — accessible icon action.
- `frontend/src/components/ui/ScrollArea.tsx` — native scrolling plus variant classes.
- `frontend/src/components/ui/FloatingLayer.tsx` — shared portal, positioning, dismissal, and focus return.
- `frontend/src/components/ui/Select.tsx` — typed custom combobox/listbox.
- `frontend/src/components/ui/dateMath.ts` — timezone-stable pure date-key helpers.
- `frontend/src/components/ui/Calendar.tsx` — keyboard-accessible custom month grid.
- `frontend/src/components/ui/DatePicker.tsx` — localized date field plus Calendar popover.
- `frontend/src/components/ui/DateTimePicker.tsx` — DatePicker plus `HH:MM` field.
- `frontend/src/components/ui/Modal.tsx` — dialog shell with focus management and ScrollArea body.
- `frontend/src/components/ui/Tabs.tsx` — controlled automatic-activation tabs.
- `frontend/src/components/ui/index.ts` — public exports only.

### Compatibility and shared styling

- `frontend/src/components/Button.tsx` — re-export canonical Button.
- `frontend/src/components/Toggle.tsx` — adapt legacy `onChange` to canonical Switch.
- `frontend/src/index.css` — shared control tokens and scrollbar variants.

### New component tests

- `frontend/src/__tests__/components/ui/FormControls.test.tsx`
- `frontend/src/__tests__/components/ui/SelectionControls.test.tsx`
- `frontend/src/__tests__/components/ui/ButtonScrollArea.test.tsx`
- `frontend/src/__tests__/components/ui/Select.test.tsx`
- `frontend/src/__tests__/components/ui/dateMath.test.ts`
- `frontend/src/__tests__/components/ui/Calendar.test.tsx`
- `frontend/src/__tests__/components/ui/DatePicker.test.tsx`
- `frontend/src/__tests__/components/ui/ModalTabs.test.tsx`
- `frontend/src/__tests__/components/AuthIntegrationUiMigration.test.tsx`
- `frontend/src/__tests__/components/CatalogSettingsUiMigration.test.tsx`

### Settings migration

- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/components/settings/DeviceManagement.tsx`
- `frontend/src/components/settings/BusinessProfileSettings.tsx`
- `frontend/src/components/settings/BusinessProfileEditorModal.tsx`
- `frontend/src/components/orders/calculation/CalculationSettings.tsx`
- `frontend/src/components/EmailSettings.tsx`
- `frontend/src/components/LDAPSettings.tsx`
- `frontend/src/components/OIDCProviderSettings.tsx`
- `frontend/src/components/TwoFactorSettings.tsx`
- `frontend/src/components/GitHubBackupSettings.tsx`
- `frontend/src/components/FailureDetectionSettings.tsx`
- `frontend/src/components/SmartPlugCard.tsx`
- `frontend/src/components/NotificationProviderCard.tsx`
- `frontend/src/components/NotificationTemplateEditor.tsx`
- `frontend/src/components/NotificationLogViewer.tsx`
- `frontend/src/components/SpoolmanSettings.tsx`
- `frontend/src/components/SpoolCatalogSettings.tsx`
- `frontend/src/components/ColorCatalogSettings.tsx`
- `frontend/src/components/ExternalLinksSettings.tsx`
- `frontend/src/components/SpoolBuddySettings.tsx`
- `frontend/src/components/VirtualPrinterList.tsx`
- `frontend/src/components/VirtualPrinterSettings.tsx`
- `frontend/src/components/VirtualPrinterCard.tsx`
- `frontend/src/components/VirtualPrinterAddDialog.tsx`
- `frontend/src/components/APIBrowser.tsx`
- `frontend/src/components/SlicerBundlesPanel.tsx`
- `frontend/src/components/SlicerPipelinesPanel.tsx`
- `frontend/src/components/PreheatFilamentTargetsEditor.tsx`
- `frontend/src/pages/CameraTokensPage.tsx`
- Settings-owned dialogs containing in-scope controls: `AddSmartPlugModal.tsx`, `AddNotificationModal.tsx`, `CreateUserAdvancedAuthModal.tsx`, `ConfirmModal.tsx`, `ApiKeyQRCodeModal.tsx`, and `LdapUserPicker.tsx`.

### Existing regression tests to update

- `frontend/src/__tests__/pages/SettingsPage.test.tsx`
- `frontend/src/__tests__/components/DeviceManagement.test.tsx`
- `frontend/src/__tests__/components/BusinessProfileSettings.test.tsx`
- `frontend/src/__tests__/components/OIDCProviderSettings.test.tsx`
- `frontend/src/__tests__/components/FailureDetectionSettings.test.tsx`
- `frontend/src/__tests__/components/SpoolmanSettings.test.tsx`
- `frontend/src/__tests__/components/SpoolCatalogSettings.test.tsx`
- `frontend/src/__tests__/components/ColorCatalogSettings.test.tsx`
- `frontend/src/__tests__/components/AddNotificationModal.test.tsx`
- `frontend/src/__tests__/components/GitHubBackupSettings.provider.test.tsx`
- `frontend/src/__tests__/components/GitHubBackupSettings.scheduled.test.tsx`
- `frontend/src/__tests__/components/Toggle.test.tsx`
- `frontend/src/__tests__/components/Button.test.tsx`

---

### Task 1: FormField, TextField, and TextArea

**Files:**
- Create: `frontend/src/components/ui/FormField.tsx`
- Create: `frontend/src/components/ui/TextField.tsx`
- Create: `frontend/src/components/ui/TextArea.tsx`
- Create: `frontend/src/components/ui/index.ts`
- Test: `frontend/src/__tests__/components/ui/FormControls.test.tsx`

**Interfaces:**
- Produces:
  - `FormFieldA11y = { controlId: string; describedBy?: string; invalid: boolean }`
  - `FormFieldProps = { id?: string; label?: ReactNode; helperText?: ReactNode; error?: ReactNode; required?: boolean; children(a11y): ReactNode }`
  - `TextFieldProps` extends native input props except `value`, `onChange`, and `size`; adds `value: string | number`, `onValueChange(value: string): void`, and FormField metadata.
  - `TextAreaProps` extends native textarea props except `value` and `onChange`; adds `value: string`, `onValueChange(value: string): void`, and FormField metadata.

- [ ] **Step 1: Write failing FormField and control tests**

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { TextArea, TextField } from '../../../components/ui';

describe('form controls', () => {
  it('links label, helper text, and error to the input', () => {
    render(<TextField label="Timeout" helperText="Seconds" error="Required" value="" onValueChange={() => {}} />);
    const input = screen.getByRole('textbox', { name: 'Timeout' });
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input.getAttribute('aria-describedby')).toContain('helper');
    expect(input.getAttribute('aria-describedby')).toContain('error');
  });

  it('reports value changes instead of DOM events', async () => {
    const onValueChange = vi.fn();
    render(<TextArea label="Notes" value="" onValueChange={onValueChange} />);
    await userEvent.setup().type(screen.getByRole('textbox', { name: 'Notes' }), 'abc');
    expect(onValueChange).toHaveBeenLastCalledWith('c');
  });
});
```

- [ ] **Step 2: Run the focused test and verify failure**

Run from `frontend`:

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/FormControls.test.tsx
```

Expected: FAIL because `components/ui` and its exports do not exist.

- [ ] **Step 3: Implement FormField and controlled native fields**

Use this exact render-prop contract in `FormField.tsx`:

```tsx
import { useId, type ReactNode } from 'react';

export type FormFieldA11y = { controlId: string; describedBy?: string; invalid: boolean };
export type FormFieldProps = {
  id?: string; label?: ReactNode; helperText?: ReactNode; error?: ReactNode;
  required?: boolean; className?: string;
  children: (a11y: FormFieldA11y) => ReactNode;
};

export function FormField({ id, label, helperText, error, required, className = '', children }: FormFieldProps) {
  const generatedId = useId();
  const controlId = id ?? `field-${generatedId.replace(/:/g, '')}`;
  const helperId = helperText ? `${controlId}-helper` : undefined;
  const errorId = error ? `${controlId}-error` : undefined;
  const describedBy = [helperId, errorId].filter(Boolean).join(' ') || undefined;
  return <div className={`space-y-1 ${className}`}>
    {label ? <label htmlFor={controlId} className="block text-sm text-bambu-gray-light">{label}{required ? <span aria-hidden="true" className="text-red-400"> *</span> : null}</label> : null}
    {children({ controlId, describedBy, invalid: Boolean(error) })}
    {helperText ? <p id={helperId} className="text-xs text-bambu-gray">{helperText}</p> : null}
    {error ? <p id={errorId} role="alert" className="text-xs text-red-400">{error}</p> : null}
  </div>;
}
```

Both controls must use the shared control class below and pass through native props:

```ts
export const controlClass = 'w-full h-[38px] px-3 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white placeholder:text-bambu-gray focus:border-bambu-green focus:outline-none focus:ring-2 focus:ring-bambu-green/30 disabled:opacity-50 disabled:cursor-not-allowed max-[768px]:min-h-11';
```

`TextField` calls `onValueChange(event.target.value)` and `TextArea` uses `min-h-24 h-auto py-2` while retaining the same state classes.

- [ ] **Step 4: Export and run focused tests**

Add explicit exports in `ui/index.ts`, then run:

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/FormControls.test.tsx
npx.cmd eslint src/components/ui/FormField.tsx src/components/ui/TextField.tsx src/components/ui/TextArea.tsx src/__tests__/components/ui/FormControls.test.tsx
```

Expected: tests PASS and ESLint exits 0.

- [ ] **Step 5: Commit the field foundation**

```powershell
git add frontend/src/components/ui frontend/src/__tests__/components/ui/FormControls.test.tsx
git commit -m "feat(ui): add form field controls"
```

---

### Task 2: Checkbox, Switch, and RadioGroup

**Files:**
- Create: `frontend/src/components/ui/Checkbox.tsx`
- Create: `frontend/src/components/ui/Switch.tsx`
- Create: `frontend/src/components/ui/RadioGroup.tsx`
- Modify: `frontend/src/components/ui/index.ts`
- Modify: `frontend/src/components/Toggle.tsx`
- Test: `frontend/src/__tests__/components/ui/SelectionControls.test.tsx`
- Test: `frontend/src/__tests__/components/Toggle.test.tsx`

**Interfaces:**
- Consumes: `FormField` from Task 1.
- Produces:
  - `CheckboxProps = { checked: boolean; indeterminate?: boolean; onCheckedChange(boolean): void; label: ReactNode; helperText?: ReactNode; error?: ReactNode }` plus native disabled/name/value props.
  - `SwitchProps = { checked: boolean; onCheckedChange(boolean): void; helperText?: ReactNode } & ({ label: ReactNode; ariaLabel?: never } | { label?: never; ariaLabel: string })`, plus native `disabled` and `name` props and the compatibility-only `stopPropagation` flag.
  - `RadioGroupProps<T extends string> = { value: T; onValueChange(T): void; options: { value: T; label: ReactNode; disabled?: boolean }[]; label?: ReactNode }`.

- [ ] **Step 1: Write failing semantics and alignment tests**

```tsx
it('centers the checkbox svg and exposes indeterminate state', () => {
  render(<Checkbox checked={false} indeterminate label="Partial" onCheckedChange={() => {}} />);
  const checkbox = screen.getByRole('checkbox', { name: 'Partial' });
  expect(checkbox).toHaveAttribute('aria-checked', 'mixed');
  const visual = screen.getByTestId('checkbox-visual');
  expect(visual).toHaveClass('items-center', 'justify-center', 'leading-none');
});

it('changes a radio group with arrow keys', async () => {
  const onValueChange = vi.fn();
  render(<RadioGroup label="Mode" value="a" onValueChange={onValueChange} options={[{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }]} />);
  screen.getByRole('radio', { name: 'A' }).focus();
  await userEvent.setup().keyboard('{ArrowRight}');
  expect(onValueChange).toHaveBeenCalledWith('b');
});
```

- [ ] **Step 2: Verify the focused test fails**

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/SelectionControls.test.tsx
```

Expected: FAIL because the exports are missing.

- [ ] **Step 3: Implement Checkbox with native semantics and centered SVG**

The input remains in the document and the visual box must use:

```tsx
<span data-testid="checkbox-visual" aria-hidden="true" className="flex h-[18px] w-[18px] shrink-0 items-center justify-center leading-none rounded border border-bambu-dark-tertiary bg-bambu-dark peer-focus-visible:ring-2 peer-focus-visible:ring-bambu-green max-[768px]:h-[22px] max-[768px]:w-[22px]">
  {indeterminate ? <Minus className="block h-3 w-3" strokeWidth={2.5} /> : checked ? <Check className="block h-3 w-3" strokeWidth={2.5} /> : null}
</span>
```

Use a native `<input type="checkbox" className="peer sr-only">`, assign `input.indeterminate = indeterminate` in `useEffect`, and set `aria-checked={indeterminate ? 'mixed' : checked}`.

- [ ] **Step 4: Implement Switch and RadioGroup**

`Switch` uses a native visually hidden checkbox, a track, and a thumb; `RadioGroup` uses `<fieldset>`, `<legend>`, and native radio inputs. On ArrowLeft/Up choose the previous enabled option, and on ArrowRight/Down choose the next enabled option with wrapping.

```ts
const nextIndex = (current: number, delta: -1 | 1, enabled: boolean[]) => {
  for (let step = 1; step <= enabled.length; step += 1) {
    const candidate = (current + delta * step + enabled.length) % enabled.length;
    if (enabled[candidate]) return candidate;
  }
  return current;
};
```

- [ ] **Step 5: Preserve the legacy Toggle API**

Replace the old implementation with an adapter:

```tsx
import { Switch } from './ui';
export function Toggle({ checked, onChange, disabled, ariaLabel }: ToggleProps) {
  return <Switch checked={checked} onCheckedChange={onChange} disabled={disabled} ariaLabel={ariaLabel ?? 'Toggle'} stopPropagation />;
}
```

The canonical `Switch` requires either a visible `label` or a non-empty `ariaLabel`; `stopPropagation` preserves existing Toggle behavior.

The legacy Toggle adapter is the only temporary exception to the new label requirement. Add optional `ariaLabel` to `ToggleProps`, pass it through when supplied, and forbid new settings imports of `Toggle`; migrated settings must use `Switch` with a visible label or translated `ariaLabel`.

- [ ] **Step 6: Run focused and legacy tests**

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/SelectionControls.test.tsx src/__tests__/components/Toggle.test.tsx
npx.cmd eslint src/components/ui/Checkbox.tsx src/components/ui/Switch.tsx src/components/ui/RadioGroup.tsx src/components/Toggle.tsx
```

Expected: all focused tests PASS.

- [ ] **Step 7: Commit selection controls**

```powershell
git add frontend/src/components/ui frontend/src/components/Toggle.tsx frontend/src/__tests__/components/ui/SelectionControls.test.tsx frontend/src/__tests__/components/Toggle.test.tsx
git commit -m "feat(ui): add selection controls"
```

---

### Task 3: Canonical Button, IconButton, and ScrollArea

**Files:**
- Create: `frontend/src/components/ui/Button.tsx`
- Create: `frontend/src/components/ui/IconButton.tsx`
- Create: `frontend/src/components/ui/ScrollArea.tsx`
- Modify: `frontend/src/components/ui/index.ts`
- Modify: `frontend/src/components/Button.tsx`
- Modify: `frontend/src/index.css`
- Test: `frontend/src/__tests__/components/ui/ButtonScrollArea.test.tsx`
- Test: `frontend/src/__tests__/components/Button.test.tsx`

**Interfaces:**
- Produces `Button` with existing variants and sizes plus `loading?: boolean`.
- Produces `IconButton` requiring `label: string`, `icon: LucideIcon`, and optional `pressed`.
- Produces `ScrollAreaProps = HTMLAttributes<HTMLDivElement> & { direction?: 'vertical' | 'horizontal' | 'both'; scrollbar?: 'normal' | 'thin' | 'hidden'; stableGutter?: boolean }`.

- [ ] **Step 1: Write failing Button and ScrollArea tests**

```tsx
it('requires an accessible icon label and exposes pressed state', () => {
  render(<IconButton label="Refresh" icon={RefreshCw} pressed onClick={() => {}} />);
  expect(screen.getByRole('button', { name: 'Refresh' })).toHaveAttribute('aria-pressed', 'true');
});

it('selects native scrolling classes by variant', () => {
  render(<ScrollArea data-testid="area" direction="both" scrollbar="thin" stableGutter />);
  expect(screen.getByTestId('area')).toHaveClass('overflow-auto', 'scrollbar-thin', 'scrollbar-gutter-stable');
});
```

- [ ] **Step 2: Verify tests fail**

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/ButtonScrollArea.test.tsx
```

- [ ] **Step 3: Move Button implementation and add compatibility export**

Move the existing Button implementation to `ui/Button.tsx`, retain all public props, add loading markup, and replace `components/Button.tsx` with:

```ts
export { Button } from './ui/Button';
export type { ButtonProps } from './ui/Button';
```

- [ ] **Step 4: Implement IconButton and ScrollArea**

Map direction exactly:

```ts
const directionClass = { vertical: 'overflow-x-hidden overflow-y-auto', horizontal: 'overflow-x-auto overflow-y-hidden', both: 'overflow-auto' }[direction];
const scrollbarClass = { normal: 'scrollbar-default', thin: 'scrollbar-thin', hidden: 'scrollbar-hidden' }[scrollbar];
```

Add CSS rules for Firefox `scrollbar-width`/`scrollbar-color` and WebKit pseudo-elements. `scrollbar-hidden` must retain scrolling and hide only the indicator. Use theme variables rather than hard-coded dark colors.

- [ ] **Step 5: Run focused and legacy tests**

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/ButtonScrollArea.test.tsx src/__tests__/components/Button.test.tsx
npx.cmd eslint src/components/ui/Button.tsx src/components/ui/IconButton.tsx src/components/ui/ScrollArea.tsx src/components/Button.tsx
```

Expected: PASS with no changes required in existing Button consumers.

- [ ] **Step 6: Commit action and scroll primitives**

```powershell
git add frontend/src/components/ui frontend/src/components/Button.tsx frontend/src/index.css frontend/src/__tests__/components/ui/ButtonScrollArea.test.tsx frontend/src/__tests__/components/Button.test.tsx
git commit -m "feat(ui): standardize buttons and scroll areas"
```

---

### Task 4: FloatingLayer

**Files:**
- Create: `frontend/src/components/ui/FloatingLayer.tsx`
- Modify: `frontend/src/components/ui/index.ts`
- Test: `frontend/src/__tests__/components/ui/Select.test.tsx`

**Interfaces:**
- Produces `FloatingLayerProps = { open: boolean; anchorRef: RefObject<HTMLElement | null>; children: ReactNode; onDismiss(): void; returnFocus?: boolean; className?: string; placement?: Placement; matchAnchorWidth?: boolean }`.

- [ ] **Step 1: Add failing portal and dismissal tests to Select.test.tsx**

```tsx
it('portals a floating layer and dismisses outside pointer events', async () => {
  const onDismiss = vi.fn();
  function Harness() {
    const ref = useRef<HTMLButtonElement>(null);
    return <><button ref={ref}>Anchor</button><FloatingLayer open anchorRef={ref} onDismiss={onDismiss}>Menu</FloatingLayer></>;
  }
  render(<Harness />);
  expect(screen.getByText('Menu').parentElement).toBe(document.body.lastElementChild);
  await userEvent.setup().click(document.body);
  expect(onDismiss).toHaveBeenCalledOnce();
});
```

- [ ] **Step 2: Verify the test fails**

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/Select.test.tsx
```

- [ ] **Step 3: Implement FloatingLayer with Floating UI**

Use `computePosition`, `autoUpdate`, `offset(6)`, `flip({ padding: 8 })`, `shift({ padding: 8 })`, and `size`. When `matchAnchorWidth` is true, apply the anchor width; always cap available height. Register outside pointer and Escape handlers only while open. Ignore events originating inside anchor or layer. Return focus only when dismissal came from Escape or explicit selection, not Tab.

```ts
const cleanup = autoUpdate(anchor, layer, () => {
  void computePosition(anchor, layer, { placement, middleware: [offset(6), flip({ padding: 8 }), shift({ padding: 8 }), size({ padding: 8, apply({ availableHeight, rects, elements }) { Object.assign(elements.floating.style, { maxHeight: `${Math.max(120, availableHeight)}px`, minWidth: matchAnchorWidth ? `${rects.reference.width}px` : '' }); } })] }).then(({ x, y }) => Object.assign(layer.style, { left: `${x}px`, top: `${y}px` }));
});
```

- [ ] **Step 4: Run focused test and lint**

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/Select.test.tsx
npx.cmd eslint src/components/ui/FloatingLayer.tsx
```

- [ ] **Step 5: Commit FloatingLayer**

```powershell
git add frontend/src/components/ui/FloatingLayer.tsx frontend/src/components/ui/index.ts frontend/src/__tests__/components/ui/Select.test.tsx
git commit -m "feat(ui): add floating layer primitive"
```

---

### Task 5: Custom Select

**Files:**
- Create: `frontend/src/components/ui/Select.tsx`
- Modify: `frontend/src/components/ui/index.ts`
- Test: `frontend/src/__tests__/components/ui/Select.test.tsx`

**Interfaces:**
- Consumes: `FormField`, `FloatingLayer`.
- Produces:

```ts
export type SelectValue = string | number;
export type SelectOption<T extends SelectValue> = { value: T; label: ReactNode; disabled?: boolean; group?: string };
export type SelectProps<T extends SelectValue> = {
  value: T; options: SelectOption<T>[]; onValueChange(value: T): void;
  label?: ReactNode; ariaLabel?: string; helperText?: ReactNode; error?: ReactNode;
  placeholder?: ReactNode; disabled?: boolean; required?: boolean;
  renderValue?: (option: SelectOption<T> | undefined, value: T) => ReactNode;
};
```

- [ ] **Step 1: Add failing behavior tests**

Cover open/close, ArrowUp/Down, Home/End, Enter, Escape focus return, Tab close, disabled options, prefix search, numeric values, groups, and unknown current values.

```tsx
it('selects with keyboard and returns focus', async () => {
  const onValueChange = vi.fn();
  render(<Select ariaLabel="Retries" value={3} onValueChange={onValueChange} options={[1, 3, 5].map(value => ({ value, label: `${value} times` }))} />);
  const trigger = screen.getByRole('combobox', { name: 'Retries' });
  trigger.focus();
  await userEvent.setup().keyboard('{Enter}{ArrowDown}{Enter}');
  expect(onValueChange).toHaveBeenCalledWith(5);
  expect(trigger).toHaveFocus();
});
```

- [ ] **Step 2: Run and verify failure**

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/Select.test.tsx
```

- [ ] **Step 3: Implement the typed combobox/listbox**

Use a button with `role="combobox"`, `aria-expanded`, `aria-controls`, and `aria-activedescendant`. Render options as buttons or focus-managed option elements inside `role="listbox"`; keep DOM focus on the trigger and move the active descendant. Generate stable IDs with `useId`.

Prefix search accumulates printable keys for 700 ms and selects the first enabled label beginning with the normalized query. Unknown values render through `renderValue(undefined, value)` or `String(value)` and must never call `onValueChange` on mount.

- [ ] **Step 4: Run focused tests and lint**

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/Select.test.tsx
npx.cmd eslint src/components/ui/Select.tsx src/__tests__/components/ui/Select.test.tsx
```

Expected: every keyboard and value-type test PASS.

- [ ] **Step 5: Commit Select**

```powershell
git add frontend/src/components/ui/Select.tsx frontend/src/components/ui/index.ts frontend/src/__tests__/components/ui/Select.test.tsx
git commit -m "feat(ui): add accessible custom select"
```

---

### Task 6: Timezone-Stable Date Math and Calendar

**Files:**
- Create: `frontend/src/components/ui/dateMath.ts`
- Create: `frontend/src/components/ui/Calendar.tsx`
- Modify: `frontend/src/components/ui/index.ts`
- Test: `frontend/src/__tests__/components/ui/dateMath.test.ts`
- Test: `frontend/src/__tests__/components/ui/Calendar.test.tsx`

**Interfaces:**
- Produces `DateKey = string` in `YYYY-MM-DD`.
- Produces `parseDateKey`, `formatDateKey`, `addDays`, `addMonthsClamped`, `buildMonthGrid`, `compareDateKeys`, and `weekStartsOn(locale)`.
- Produces `CalendarProps = { value?: DateKey; focusedValue?: DateKey; onSelect(DateKey): void; locale: string; min?: DateKey; max?: DateKey; isDateDisabled?(DateKey): boolean }`.

- [ ] **Step 1: Write failing pure date tests**

```ts
it('keeps date keys stable across leap days and month clamping', () => {
  expect(addDays('2028-02-28', 1)).toBe('2028-02-29');
  expect(addMonthsClamped('2026-01-31', 1)).toBe('2026-02-28');
  expect(formatDateKey(parseDateKey('2026-07-17'))).toBe('2026-07-17');
});
```

- [ ] **Step 2: Verify failure**

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/dateMath.test.ts
```

- [ ] **Step 3: Implement UTC-only date helpers**

Parse keys by numeric parts and use `Date.UTC`; never call `new Date('YYYY-MM-DD')` for display logic. Reject malformed keys with `undefined` rather than normalizing them silently.

```ts
export function parseDateKey(value: string): Date | undefined {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return undefined;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return formatDateKey(date) === value ? date : undefined;
}
```

- [ ] **Step 4: Write failing Calendar interaction tests**

Test Arrow keys, Home/End, PageUp/PageDown, Shift+PageUp/PageDown, min/max, disabled dates, today marker, localized month heading, selection, and Escape propagation.

```tsx
it('moves by month and year with Page keys', async () => {
  render(<Calendar locale="de-DE" value="2026-07-17" onSelect={() => {}} />);
  const grid = screen.getByRole('grid');
  grid.focus();
  await userEvent.setup().keyboard('{PageDown}');
  expect(screen.getByText('August 2026')).toBeInTheDocument();
  await userEvent.setup().keyboard('{Shift>}{PageDown}{/Shift}');
  expect(screen.getByText('August 2027')).toBeInTheDocument();
});
```

- [ ] **Step 5: Implement Calendar grid and keyboard model**

Use one roving focus date, `role="grid"`, weekday `columnheader`s, and day buttons with `aria-selected`, disabled state, and localized accessible labels. Build a fixed six-week grid so the popover height does not jump between months.

- [ ] **Step 6: Run date and Calendar tests**

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/dateMath.test.ts src/__tests__/components/ui/Calendar.test.tsx
npx.cmd eslint src/components/ui/dateMath.ts src/components/ui/Calendar.tsx
```

- [ ] **Step 7: Commit Calendar foundation**

```powershell
git add frontend/src/components/ui/dateMath.ts frontend/src/components/ui/Calendar.tsx frontend/src/components/ui/index.ts frontend/src/__tests__/components/ui/dateMath.test.ts frontend/src/__tests__/components/ui/Calendar.test.tsx
git commit -m "feat(ui): add accessible calendar"
```

---

### Task 7: DatePicker and DateTimePicker

**Files:**
- Create: `frontend/src/components/ui/DatePicker.tsx`
- Create: `frontend/src/components/ui/DateTimePicker.tsx`
- Modify: `frontend/src/components/ui/index.ts`
- Test: `frontend/src/__tests__/components/ui/DatePicker.test.tsx`

**Interfaces:**
- Consumes: `FormField`, `FloatingLayer`, `Calendar`, `DateKey`, `TextField`.
- Produces `DatePickerProps = { value: DateKey | ''; onValueChange(DateKey | ''): void; locale: string; label?: ReactNode; min?: DateKey; max?: DateKey; disabled?: boolean; error?: ReactNode }`.
- Produces `DateTimePickerProps = { dateValue: DateKey | ''; timeValue: string; onDateValueChange(DateKey | ''): void; onTimeValueChange(string): void; locale: string }` plus field metadata.

- [ ] **Step 1: Write failing picker tests**

```tsx
it('shows localized text but emits a stable date key', async () => {
  const onValueChange = vi.fn();
  render(<DatePicker label="Valid from" locale="de-DE" value="2026-07-17" onValueChange={onValueChange} />);
  expect(screen.getByRole('button', { name: /Valid from/ })).toHaveTextContent('17.07.2026');
  await userEvent.setup().click(screen.getByRole('button', { name: /Valid from/ }));
  await userEvent.setup().click(screen.getByRole('button', { name: /18. Juli 2026/ }));
  expect(onValueChange).toHaveBeenCalledWith('2026-07-18');
});
```

- [ ] **Step 2: Verify test failure**

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/DatePicker.test.tsx
```

- [ ] **Step 3: Implement DatePicker**

Render a FormField-wrapped trigger with a Calendar icon. Format valid values using `Intl.DateTimeFormat(locale, { year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'UTC' })`. Open Calendar through FloatingLayer, select and close, and return focus. Invalid external values display unchanged and set `aria-invalid`; do not emit on mount.

- [ ] **Step 4: Implement DateTimePicker**

Compose DatePicker and a text input constrained to `^([01]\d|2[0-3]):[0-5]\d$`. Keep date and time callbacks separate. Do not create a `Date`, timestamp, or timezone conversion.

- [ ] **Step 5: Run focused tests and lint**

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/DatePicker.test.tsx
npx.cmd eslint src/components/ui/DatePicker.tsx src/components/ui/DateTimePicker.tsx
```

- [ ] **Step 6: Commit date pickers**

```powershell
git add frontend/src/components/ui/DatePicker.tsx frontend/src/components/ui/DateTimePicker.tsx frontend/src/components/ui/index.ts frontend/src/__tests__/components/ui/DatePicker.test.tsx
git commit -m "feat(ui): add date picker controls"
```

---

### Task 8: Modal and Tabs

**Files:**
- Create: `frontend/src/components/ui/Modal.tsx`
- Create: `frontend/src/components/ui/Tabs.tsx`
- Modify: `frontend/src/components/ui/index.ts`
- Test: `frontend/src/__tests__/components/ui/ModalTabs.test.tsx`

**Interfaces:**
- Consumes: `IconButton`, `ScrollArea`.
- Produces `ModalProps = { open: boolean; onClose(): void; title: ReactNode; description?: ReactNode; children: ReactNode; closeOnBackdrop?: boolean; initialFocusRef?: RefObject<HTMLElement | null>; className?: string }`.
- Produces generic `TabsProps<T extends string> = { value: T; onValueChange(T): void; items: { value: T; label: ReactNode; content: ReactNode; disabled?: boolean }[]; ariaLabel: string }`.

- [ ] **Step 1: Write failing focus and keyboard tests**

```tsx
it('traps focus and restores the trigger after closing', async () => {
  function Harness() { const [open, setOpen] = useState(false); return <><button onClick={() => setOpen(true)}>Open</button><Modal open={open} onClose={() => setOpen(false)} title="Dialog"><button>Inside</button></Modal></>; }
  render(<Harness />);
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Open' }));
  expect(screen.getByRole('button', { name: 'Inside' })).toHaveFocus();
  await user.keyboard('{Escape}');
  expect(screen.getByRole('button', { name: 'Open' })).toHaveFocus();
});
```

- [ ] **Step 2: Verify failure**

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/ModalTabs.test.tsx
```

- [ ] **Step 3: Implement Modal focus management**

Capture `document.activeElement` when opening. Focus `initialFocusRef` or the first focusable control. On Tab/Shift+Tab wrap among enabled focusable descendants. Escape closes. Backdrop pointer closes only when `closeOnBackdrop` is true and `event.target === event.currentTarget`. Restore the captured element after close.

- [ ] **Step 4: Implement controlled automatic Tabs**

Use `role="tablist"`, `role="tab"`, and `role="tabpanel"` with generated IDs. Arrow keys skip disabled tabs and immediately call `onValueChange`; Home and End activate boundary tabs.

- [ ] **Step 5: Run tests and lint**

```powershell
npm.cmd run test:run -- src/__tests__/components/ui/ModalTabs.test.tsx
npx.cmd eslint src/components/ui/Modal.tsx src/components/ui/Tabs.tsx
```

- [ ] **Step 6: Commit overlays and navigation**

```powershell
git add frontend/src/components/ui/Modal.tsx frontend/src/components/ui/Tabs.tsx frontend/src/components/ui/index.ts frontend/src/__tests__/components/ui/ModalTabs.test.tsx
git commit -m "feat(ui): add modal and tabs"
```

---

### Task 9: Migrate Inline SettingsPage Controls

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/__tests__/pages/SettingsPage.test.tsx`

**Interfaces:**
- Consumes all public exports from `components/ui`.
- Must preserve every `updateSetting`, mutation, conditional render, permission check, option value, translation call, and helper text.

- [ ] **Step 1: Add failing source and behavior assertions**

Add regression coverage for FTP Select values, number fields, checkbox changes, localized DatePicker values where present, and unchanged mutation payloads. Replace assertions that cast comboboxes to `HTMLSelectElement` with user-visible role interaction.

```tsx
const retries = within(screen.getByTestId('ftp-retry-fields-grid')).getByRole('combobox', { name: 'Retry attempts' });
await user.click(retries);
await user.click(screen.getByRole('option', { name: '5 times' }));
expect(mockUpdateSettings).toHaveBeenCalledWith(expect.objectContaining({ ftp_retry_count: 5 }));
```

- [ ] **Step 2: Run SettingsPage tests and confirm the new expectation fails**

```powershell
npm.cmd run test:run -- src/__tests__/pages/SettingsPage.test.tsx
```

Expected: FAIL because current native selects do not expose the custom option interaction.

- [ ] **Step 3: Migrate native selects**

Replace all 21 `<select>` blocks in `SettingsPage.tsx` with typed `Select`. Convert option JSX to `options` arrays without changing values or labels. Numeric settings use numeric options and no `parseInt` in the consumer.

```tsx
<Select<number>
  label={t('settings.retryAttempts')}
  value={localSettings.ftp_retry_count ?? 3}
  options={[1,2,3,4,5,6,7,8,9,10].map(value => ({ value, label: t('settings.time', { count: value }) }))}
  onValueChange={value => updateSetting('ftp_retry_count', value)}
/>
```

- [ ] **Step 4: Migrate in-scope inputs and checkboxes**

Replace text/password/email/number/date inputs with `TextField` or `DatePicker`; replace visible checkboxes with `Checkbox` or `Switch` according to persistent binary-setting semantics. Keep hidden file, color, and range inputs unchanged.

For number fields preserve string editing where the current state is string; convert only at the same point the current handler converts.

Replace the settings tab and sub-tab button groups with controlled `Tabs` when they represent mutually exclusive panels. Keep URL/search-parameter updates in `SettingsPage`; `Tabs.onValueChange` calls the existing navigation handler.

- [ ] **Step 5: Replace inline scroll styling where a settings viewport exists**

Use `ScrollArea` only for existing explicit scroll containers; do not add new nested scrolling. Replace `.calendar-scroll` use only when the associated Calendar component owns the region.

- [ ] **Step 6: Run SettingsPage tests and lint**

```powershell
npm.cmd run test:run -- src/__tests__/pages/SettingsPage.test.tsx
npx.cmd eslint src/pages/SettingsPage.tsx src/__tests__/pages/SettingsPage.test.tsx
```

- [ ] **Step 7: Commit inline settings migration**

```powershell
git add frontend/src/pages/SettingsPage.tsx frontend/src/__tests__/pages/SettingsPage.test.tsx
git commit -m "refactor(settings): adopt shared form controls"
```

---

### Task 10: Migrate Device, Business Profile, and Calculation Settings

**Files:**
- Modify: `frontend/src/components/settings/DeviceManagement.tsx`
- Modify: `frontend/src/components/settings/BusinessProfileSettings.tsx`
- Modify: `frontend/src/components/settings/BusinessProfileEditorModal.tsx`
- Modify: `frontend/src/components/orders/calculation/CalculationSettings.tsx`
- Modify: related tests listed in File Map.

**Interfaces:**
- Consumes `TextField`, `Select`, `Checkbox`, `Switch`, `DatePicker`, `Modal`, `Button`, and `ScrollArea`.
- Leaves file upload input in BusinessProfileEditorModal native and hidden/visually specialized.

- [ ] **Step 1: Write failing device and business-profile interaction tests**

Add tests that choose dates through Calendar, select currency/tax mode through custom Select, toggle default/primary checkboxes, and assert the existing submit payload exactly.

```tsx
await user.click(screen.getByRole('button', { name: /Acquisition date/ }));
await user.click(screen.getByRole('button', { name: /17 July 2026/ }));
expect(screen.getByRole('button', { name: /Acquisition date/ })).toHaveTextContent('17/07/2026');
```

- [ ] **Step 2: Verify focused failures**

```powershell
npm.cmd run test:run -- src/__tests__/components/DeviceManagement.test.tsx src/__tests__/components/BusinessProfileSettings.test.tsx src/__tests__/components/CalculationEditors.test.tsx
```

- [ ] **Step 3: Migrate DeviceManagement**

Replace date and number inputs with DatePicker/TextField, existing buttons with Button/IconButton, and explicit scroll viewports with ScrollArea. Preserve cost calculation timing and payload values.

- [ ] **Step 4: Migrate Business Profile components**

Replace eleven selects, in-scope text/number/date controls, and checkboxes. Keep `type="file"` unchanged. Replace modal shell with canonical Modal while preserving submit, reset, and logo-upload behavior.

- [ ] **Step 5: Migrate CalculationSettings**

Replace currency, price-method, rounding, and energy-mode selects plus numeric fields. Preserve `SUPPORTED_CURRENCIES`, numeric coercion, and `onChange` keys.

- [ ] **Step 6: Run focused tests and lint**

```powershell
npm.cmd run test:run -- src/__tests__/components/DeviceManagement.test.tsx src/__tests__/components/BusinessProfileSettings.test.tsx src/__tests__/components/CalculationEditors.test.tsx
npx.cmd eslint src/components/settings/DeviceManagement.tsx src/components/settings/BusinessProfileSettings.tsx src/components/settings/BusinessProfileEditorModal.tsx src/components/orders/calculation/CalculationSettings.tsx
```

- [ ] **Step 7: Commit device and commercial settings migration**

```powershell
git add frontend/src/components/settings/DeviceManagement.tsx frontend/src/components/settings/BusinessProfileSettings.tsx frontend/src/components/settings/BusinessProfileEditorModal.tsx frontend/src/components/orders/calculation/CalculationSettings.tsx frontend/src/__tests__/components/DeviceManagement.test.tsx frontend/src/__tests__/components/BusinessProfileSettings.test.tsx frontend/src/__tests__/components/CalculationEditors.test.tsx
git commit -m "refactor(settings): migrate device and business controls"
```

---

### Task 11: Migrate Authentication, Integration, and Backup Settings

**Files:**
- Modify: `EmailSettings.tsx`, `LDAPSettings.tsx`, `OIDCProviderSettings.tsx`, `TwoFactorSettings.tsx`, `GitHubBackupSettings.tsx`, `FailureDetectionSettings.tsx`, `SmartPlugCard.tsx`, `NotificationProviderCard.tsx`, `NotificationTemplateEditor.tsx`, `NotificationLogViewer.tsx`.
- Modify settings-owned dialogs: `AddSmartPlugModal.tsx`, `AddNotificationModal.tsx`, `CreateUserAdvancedAuthModal.tsx`, `ConfirmModal.tsx`, `ApiKeyQRCodeModal.tsx`, `LdapUserPicker.tsx`.
- Create: `frontend/src/__tests__/components/AuthIntegrationUiMigration.test.tsx` for settings components that lack focused tests.
- Modify their existing tests.

**Interfaces:**
- Consumes all relevant UI primitives.
- Preserves provider IDs, auth secrets, test-connection actions, mutation keys, and modal close behavior.

- [ ] **Step 1: Update tests to interact through roles rather than native element values**

For every migrated Select, open the combobox and choose an option by `role="option"`. For every Switch/Checkbox, click the named control. Keep payload assertions unchanged.

```tsx
await user.click(within(failedRow).getByRole('combobox'));
await user.click(screen.getByRole('option', { name: '5' }));
expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ failed: 5 }));
```

- [ ] **Step 2: Run the focused group and confirm failures**

```powershell
npm.cmd run test:run -- src/__tests__/components/AddNotificationModal.test.tsx src/__tests__/components/OIDCProviderSettings.test.tsx src/__tests__/components/FailureDetectionSettings.test.tsx src/__tests__/components/GitHubBackupSettings.provider.test.tsx src/__tests__/components/GitHubBackupSettings.scheduled.test.tsx
```

- [ ] **Step 3: Migrate auth settings controls**

Use TextField for server, credential, search, and number values; Switch for persistent binary settings; Select for modes; Modal/ScrollArea for dialogs and result pickers. Preserve password autocomplete and input types.

- [ ] **Step 4: Migrate integration and backup controls**

Apply the same primitives to notification, smart-plug, failure-detection, GitHub backup, and scheduled backup controls. Keep file inputs and any range inputs native. Add focused coverage for Email, LDAP, TwoFactor, smart-plug, notification cards, and dialogs to `AuthIntegrationUiMigration.test.tsx` using their existing MSW handlers.

- [ ] **Step 5: Run group tests and lint**

```powershell
npm.cmd run test:run -- src/__tests__/components/AddNotificationModal.test.tsx src/__tests__/components/OIDCProviderSettings.test.tsx src/__tests__/components/FailureDetectionSettings.test.tsx src/__tests__/components/GitHubBackupSettings.provider.test.tsx src/__tests__/components/GitHubBackupSettings.scheduled.test.tsx src/__tests__/components/AuthIntegrationUiMigration.test.tsx
npx.cmd eslint src/components/EmailSettings.tsx src/components/LDAPSettings.tsx src/components/OIDCProviderSettings.tsx src/components/TwoFactorSettings.tsx src/components/GitHubBackupSettings.tsx src/components/FailureDetectionSettings.tsx src/components/AddSmartPlugModal.tsx src/components/AddNotificationModal.tsx src/components/CreateUserAdvancedAuthModal.tsx src/components/ConfirmModal.tsx src/components/ApiKeyQRCodeModal.tsx src/components/LdapUserPicker.tsx
```

- [ ] **Step 6: Commit auth and integration migration**

```powershell
git add frontend/src/components/EmailSettings.tsx frontend/src/components/LDAPSettings.tsx frontend/src/components/OIDCProviderSettings.tsx frontend/src/components/TwoFactorSettings.tsx frontend/src/components/GitHubBackupSettings.tsx frontend/src/components/FailureDetectionSettings.tsx frontend/src/components/SmartPlugCard.tsx frontend/src/components/NotificationProviderCard.tsx frontend/src/components/NotificationTemplateEditor.tsx frontend/src/components/NotificationLogViewer.tsx frontend/src/components/AddSmartPlugModal.tsx frontend/src/components/AddNotificationModal.tsx frontend/src/components/CreateUserAdvancedAuthModal.tsx frontend/src/components/ConfirmModal.tsx frontend/src/components/ApiKeyQRCodeModal.tsx frontend/src/components/LdapUserPicker.tsx frontend/src/__tests__/components/AddNotificationModal.test.tsx frontend/src/__tests__/components/OIDCProviderSettings.test.tsx frontend/src/__tests__/components/FailureDetectionSettings.test.tsx frontend/src/__tests__/components/GitHubBackupSettings.provider.test.tsx frontend/src/__tests__/components/GitHubBackupSettings.scheduled.test.tsx frontend/src/__tests__/components/AuthIntegrationUiMigration.test.tsx
git commit -m "refactor(settings): migrate auth and integration controls"
```

---

### Task 12: Migrate Catalog, Virtual Printer, Slicer, and Remaining Settings Controls

**Files:**
- Modify: `SpoolmanSettings.tsx`, `SpoolCatalogSettings.tsx`, `ColorCatalogSettings.tsx`, `ExternalLinksSettings.tsx`, `SpoolBuddySettings.tsx`, `VirtualPrinterList.tsx`, `VirtualPrinterSettings.tsx`, `VirtualPrinterCard.tsx`, `VirtualPrinterAddDialog.tsx`, `APIBrowser.tsx`, `SlicerBundlesPanel.tsx`, `SlicerPipelinesPanel.tsx`, `PreheatFilamentTargetsEditor.tsx`, `pages/CameraTokensPage.tsx`.
- Modify related existing tests from the File Map.
- Create: `frontend/src/__tests__/components/CatalogSettingsUiMigration.test.tsx` for remaining components without focused coverage.

**Interfaces:**
- Consumes UI primitives.
- Keeps file, color, and range inputs native.
- Keeps custom domain selectors whose behavior exceeds Select scope only when documented by an inline comment and covered by tests.

- [ ] **Step 1: Add failing interaction tests for each settings family**

Cover custom Select interactions, Checkbox/Switch state, numeric TextField changes, and unchanged payloads. Add one explicit assertion that native file/color/range inputs remain present where required.

Place new coverage for ExternalLinksSettings, SpoolBuddySettings, APIBrowser, Slicer panels, PreheatFilamentTargetsEditor, and VirtualPrinterList in `CatalogSettingsUiMigration.test.tsx`; reuse existing component tests for components that already have a dedicated file.

- [ ] **Step 2: Run the focused family tests and confirm failure**

```powershell
npm.cmd run test:run -- src/__tests__/components/SpoolmanSettings.test.tsx src/__tests__/components/SpoolCatalogSettings.test.tsx src/__tests__/components/ColorCatalogSettings.test.tsx src/__tests__/components/VirtualPrinterSettings.test.tsx src/__tests__/components/CatalogSettingsUiMigration.test.tsx src/__tests__/pages/CameraTokensPage.test.tsx
```

- [ ] **Step 3: Migrate in-scope catalog and SpoolBuddy controls**

Replace Select, TextField, Checkbox, Switch, Button/IconButton, Modal, and ScrollArea usages. Do not wrap hidden import file inputs or color inputs in TextField.

- [ ] **Step 4: Migrate virtual printer, API browser, and slicer controls**

Replace in-scope primitives and preserve endpoint values, virtual-printer mode values, slicer IDs, and save callbacks. Keep specialized searchable or hierarchical pickers only when canonical Select cannot represent them.

- [ ] **Step 5: Run focused tests and lint**

```powershell
npm.cmd run test:run -- src/__tests__/components/SpoolmanSettings.test.tsx src/__tests__/components/SpoolCatalogSettings.test.tsx src/__tests__/components/ColorCatalogSettings.test.tsx src/__tests__/components/VirtualPrinterSettings.test.tsx src/__tests__/components/CatalogSettingsUiMigration.test.tsx src/__tests__/pages/CameraTokensPage.test.tsx
npx.cmd eslint src/components/SpoolmanSettings.tsx src/components/SpoolCatalogSettings.tsx src/components/ColorCatalogSettings.tsx src/components/ExternalLinksSettings.tsx src/components/SpoolBuddySettings.tsx src/components/VirtualPrinterList.tsx src/components/VirtualPrinterSettings.tsx src/components/VirtualPrinterCard.tsx src/components/VirtualPrinterAddDialog.tsx src/components/APIBrowser.tsx src/components/SlicerBundlesPanel.tsx src/components/SlicerPipelinesPanel.tsx src/components/PreheatFilamentTargetsEditor.tsx src/pages/CameraTokensPage.tsx
```

- [ ] **Step 6: Commit remaining settings migration**

```powershell
git add frontend/src/components/SpoolmanSettings.tsx frontend/src/components/SpoolCatalogSettings.tsx frontend/src/components/ColorCatalogSettings.tsx frontend/src/components/ExternalLinksSettings.tsx frontend/src/components/SpoolBuddySettings.tsx frontend/src/components/VirtualPrinterList.tsx frontend/src/components/VirtualPrinterSettings.tsx frontend/src/components/VirtualPrinterCard.tsx frontend/src/components/VirtualPrinterAddDialog.tsx frontend/src/components/APIBrowser.tsx frontend/src/components/SlicerBundlesPanel.tsx frontend/src/components/SlicerPipelinesPanel.tsx frontend/src/components/PreheatFilamentTargetsEditor.tsx frontend/src/pages/CameraTokensPage.tsx frontend/src/__tests__/components/SpoolmanSettings.test.tsx frontend/src/__tests__/components/SpoolCatalogSettings.test.tsx frontend/src/__tests__/components/ColorCatalogSettings.test.tsx frontend/src/__tests__/components/VirtualPrinterSettings.test.tsx frontend/src/__tests__/components/CatalogSettingsUiMigration.test.tsx frontend/src/__tests__/pages/CameraTokensPage.test.tsx
git commit -m "refactor(settings): finish shared control migration"
```

---

### Task 13: Source Audit, Full Regression, Build, and Browser QA

**Files:**
- Modify only if verification finds a defect: files already listed above.
- Generated by build: `static/index.html`, `static/assets/index-*.css`, `static/assets/index-*.js`.

**Interfaces:**
- Acceptance gate for the entire plan.

- [ ] **Step 1: Audit remaining native in-scope controls**

Run scoped searches:

```powershell
$scope = @(
  'frontend/src/pages/SettingsPage.tsx', 'frontend/src/pages/CameraTokensPage.tsx',
  'frontend/src/components/settings', 'frontend/src/components/EmailSettings.tsx',
  'frontend/src/components/LDAPSettings.tsx', 'frontend/src/components/OIDCProviderSettings.tsx',
  'frontend/src/components/TwoFactorSettings.tsx', 'frontend/src/components/GitHubBackupSettings.tsx',
  'frontend/src/components/FailureDetectionSettings.tsx', 'frontend/src/components/SpoolmanSettings.tsx',
  'frontend/src/components/SmartPlugCard.tsx', 'frontend/src/components/NotificationProviderCard.tsx',
  'frontend/src/components/NotificationTemplateEditor.tsx', 'frontend/src/components/NotificationLogViewer.tsx',
  'frontend/src/components/SpoolCatalogSettings.tsx', 'frontend/src/components/ColorCatalogSettings.tsx',
  'frontend/src/components/ExternalLinksSettings.tsx', 'frontend/src/components/SpoolBuddySettings.tsx',
  'frontend/src/components/VirtualPrinterList.tsx', 'frontend/src/components/VirtualPrinterSettings.tsx',
  'frontend/src/components/VirtualPrinterCard.tsx', 'frontend/src/components/VirtualPrinterAddDialog.tsx',
  'frontend/src/components/APIBrowser.tsx', 'frontend/src/components/SlicerBundlesPanel.tsx',
  'frontend/src/components/SlicerPipelinesPanel.tsx', 'frontend/src/components/PreheatFilamentTargetsEditor.tsx',
  'frontend/src/components/orders/calculation/CalculationSettings.tsx',
  'frontend/src/components/AddSmartPlugModal.tsx', 'frontend/src/components/AddNotificationModal.tsx',
  'frontend/src/components/CreateUserAdvancedAuthModal.tsx', 'frontend/src/components/ConfirmModal.tsx',
  'frontend/src/components/ApiKeyQRCodeModal.tsx', 'frontend/src/components/LdapUserPicker.tsx'
)
rg -n '<select\b' $scope
rg -n 'type="(checkbox|date|datetime-local)"' $scope
rg -n '<textarea\b|<button\b|<input\b' $scope
```

Expected: no in-scope direct selects or visible standard checkboxes/date inputs remain. Each remaining match must be a file/color/range input, a native input inside `components/ui`, or a documented specialized control outside the phase.

- [ ] **Step 2: Run all focused UI and settings tests**

```powershell
npm.cmd run test:run -- src/__tests__/components/ui src/__tests__/pages/SettingsPage.test.tsx src/__tests__/components/DeviceManagement.test.tsx src/__tests__/components/BusinessProfileSettings.test.tsx src/__tests__/components/OIDCProviderSettings.test.tsx src/__tests__/components/FailureDetectionSettings.test.tsx src/__tests__/components/SpoolmanSettings.test.tsx src/__tests__/components/SpoolCatalogSettings.test.tsx src/__tests__/components/ColorCatalogSettings.test.tsx
```

Expected: all selected tests PASS.

- [ ] **Step 3: Run the complete frontend validation**

From `frontend`:

```powershell
npm.cmd run test:run
npm.cmd run lint
npm.cmd run build
```

Expected: full tests and i18n parity PASS, ESLint exits 0, TypeScript/Vite build succeeds. Record any pre-existing warning separately; do not suppress it as part of this work.

- [ ] **Step 4: Verify responsive browser behavior**

Run the built application against an isolated local data directory. Check at minimum:

- 1440×900 desktop, light and dark themes
- 390×844 mobile/touch layout
- all Settings tabs and sub-tabs
- Select open, keyboard selection, prefix search, disabled options, and viewport collision
- Calendar mouse selection, full keyboard navigation, min/max, leap day, and focus return
- Checkbox normal, checked, indeterminate, disabled, and vertically centered SVG
- Modal focus trap and Escape close
- ScrollArea normal, thin, and hidden variants
- Settings save toasts and unchanged network payloads
- Chromium and Firefox scrollbar rendering

Capture desktop and mobile screenshots plus console errors. Known unrelated warnings must be identified, not counted as component failures.

- [ ] **Step 5: Inspect the final diff and generated assets**

```powershell
git diff --check
git status --short
git diff --stat
Select-String -Path static/index.html -Pattern 'index-.*\.(css|js)'
```

Expected: no whitespace errors, only planned source/test/build files changed, and `static/index.html` references existing generated assets.

- [ ] **Step 6: Commit build assets and final verification fixes**

```powershell
git add static/index.html static/assets
git commit -m "build(frontend): refresh unified controls bundle"
```

If verification required source fixes after the preceding task commits, commit each fix with its affected tests before committing generated assets.

- [ ] **Step 7: Prepare handoff summary**

Report:

- component files created
- settings files migrated
- test totals and exact commands
- browser sizes, themes, and engines checked
- screenshot paths
- remaining native specialized controls by file and reason
- commits created
- working-tree status
